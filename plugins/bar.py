#!/usr/bin/env python3
"""One event-driven SketchyBar runtime. Labels never supply executable code."""

import asyncio
import fcntl
import functools
import json
import os
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path

from layout import build, fit_text, media_geometry, popup_geometry, text_width
from palette import read_palette
from pixels import generate
from rendering import popup_width
from rendering import rows as render_rows
from runtime import (
    ROOT,
    cache_path,
    command,
    config,
    private_file,
    query,
    run,
    send,
    stop,
    text,
)
from wm import Manager


class Bar:
    def __init__(self, cfg, cache):
        self.cfg, self.cache = cfg, cache
        self.flags = cfg["features"]
        self.wm = Manager(cfg["window_manager"])
        self.tasks = set()
        self.work = {}
        self.pending = set()
        self.props = {}
        self.actions = {}
        self.popup_items = {}
        self.popup_hosts = {}
        self.popup_images = {}
        self.open_popup = ""
        self.popup_anchor = ""
        self.clickaway = None
        self.wm_task = None
        self.ui_task = None
        self.closed = asyncio.Event()
        self.media_state = {}
        self.media_source_data = None
        self.media_stream_seen = 0
        self.caffeinate = None
        self.calendar_offset = 0
        self.last_probe = 0
        self.sb_unavailable = False
        self.last_restart = 0
        self.palette = {}
        self.display_frame = {"x": 0, "w": 1512, "h": 982}
        self.notch_left = 656
        self.pixels = cache / "pixels"
        self.media_layout = None
        self.layout_lock = asyncio.Lock()
        self.created = set()
        self.animations = cfg.get("animations", True)
        self.underlines = set()
        self.system_data = (0, None)

    def task(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def sb(self, *args):
        return await run("sketchybar", *args, timeout=4)

    def shutdown(self, reason):
        if not self.closed.is_set():
            print("runtime stopping: " + reason, file=sys.stderr, flush=True)
            self.closed.set()

    async def refresh_display(self):
        # Commands can fail during sleep/wake even if their values were cached.
        self.props.clear()
        await self.close_popup()
        await self.measure_display()
        await self.refit_media()
        for name in self.enabled_items():
            self.notify(name)

    async def probe(self):
        if not (await self.sb("--query", "bar")).strip():
            if not self.sb_unavailable:
                print(
                    "SketchyBar query unavailable; retrying",
                    file=sys.stderr,
                    flush=True,
                )
            self.sb_unavailable = True
        elif self.sb_unavailable:
            self.sb_unavailable = False
            print("SketchyBar query recovered; refreshing", file=sys.stderr, flush=True)
            await self.refresh_display()

    async def set(self, item, **props):
        await self.set_many({item: props})

    async def set_many(self, updates):
        args, changed = [], {}
        for item, props in updates.items():
            values = {
                k: str(v)
                for k, v in props.items()
                if self.props.get((item, k)) != str(v)
            }
            if values:
                args += ["--set", item, *(k + "=" + v for k, v in values.items())]
                changed.update({(item, k): v for k, v in values.items()})
        if args:
            await self.sb(*args)
            self.props.update(changed)

    def action(self, name, *args):
        return functools.partial(self.dispatch, name, *args)

    async def popup(self, parent, title, rows):
        """Store typed actions in memory; callbacks contain only random handles."""
        if self.open_popup != parent:
            return
        anchor = self.popup_anchor or parent
        self.actions = {k: v for k, v in self.actions.items() if v[0] != parent}
        scale = self.cfg["font_size"] / 12
        max_rows = min(
            32, max(4, int((self.display_frame["h"] - 110) / (24 * scale)) - 1)
        )
        if len(rows) > max_rows:
            rows = rows[: max_rows - 1] + [
                {"label": f"+{len(rows) - max_rows + 1} more"}
            ]
        width = popup_width(self.cfg, parent, self.display_frame["w"])
        parent_data = await query("sketchybar", "--query", anchor)
        bounds = (parent_data or {}).get("bounding_rects", {})
        rect = next(iter(bounds.values()), None)
        if rect and rect["origin"][0] >= self.display_frame["x"]:
            # Choose a width for which a real left/right anchor fits. Moving the
            # popup background alone would leave its child windows behind.
            room = max(
                self.display_frame["x"]
                + self.display_frame["w"]
                - 5
                - rect["origin"][0],
                rect["origin"][0] + rect["size"][0] - self.display_frame["x"] - 5,
            )
            width = min(width, int(room) - 1)
            align, _ = popup_geometry(
                rect["origin"][0],
                rect["size"][0],
                width + 1,
                self.display_frame["x"],
                self.display_frame["w"],
                prefer_right=parent in ("clock", "wifi", "volume"),
                prefer_center=parent == "usage",
            )
            await self.set(anchor, **{"popup.align": align})
        images = await render_rows(self, parent, title, rows, width)
        n = len(rows) + 1
        old = self.popup_items.get(parent, 0)
        args = []
        if old and self.popup_hosts.get(parent, parent) != anchor:
            # Popup windows belong to their host. Recreate them when switching
            # between Claude and Codex so the popup follows the clicked cell.
            for suffix in ["pad.top", "pad.gap", "pad.bottom"] + [
                f"row.{i}" for i in range(old)
            ]:
                args += ["--remove", f"{parent}.{suffix}"]
            old = 0

        def pad(suffix):
            args.extend(
                [
                    "--add",
                    "item",
                    f"{parent}.pad.{suffix}",
                    "popup." + anchor,
                    "--set",
                    f"{parent}.pad.{suffix}",
                    "icon.drawing=off",
                    "label.drawing=off",
                    "padding_left=0",
                    "padding_right=0",
                    "background.drawing=on",
                    "background.color=0x00000000",
                    "background.height=" + str(round(6 * scale)),
                    "y_offset=0",
                ]
            )

        if not old:
            pad("top")
        elif n > old:
            args += ["--remove", f"{parent}.pad.bottom"]
        for i in range(n, old):
            args += ["--remove", f"{parent}.row.{i}"]
        for i in range(old, n):
            args += [
                "--add",
                "slider" if i > 0 and rows[i - 1].get("slider") else "item",
                f"{parent}.row.{i}",
                "popup." + anchor,
            ]
            if i > 0 and rows[i - 1].get("slider"):
                args += ["150"]
            if i == 0:
                pad("gap")
        if not old or n > old:
            pad("bottom")
        title_row = {"left": "", "label": title, "color": self.palette["muted"]}
        for i, row in enumerate([title_row] + rows):
            handle = ""
            if callable(row.get("action")):
                handle = "action." + secrets.token_hex(16)
                self.actions[handle] = (parent, row["action"], row.get("keep", False))
            has_key = bool(row.get("left"))
            key_width = 68 if has_key else 0
            slider_width = (
                min(150, max(0, width - key_width - 60)) if row.get("slider") else 0
            )
            label_width = max(0, width - key_width - 24 - slider_width)
            args += [
                "--set",
                f"{parent}.row.{i}",
                f"width={width}",
                "padding_left=0",
                "padding_right=0",
                "y_offset=0",
                "icon=" + fit_text(row.get("left", ""), key_width - 8),
                "icon.drawing=" + ("on" if has_key else "off"),
                "icon.width=" + str(key_width),
                "icon.padding_left=12",
                "icon.padding_right=0",
                "icon.align=left",
                "label=" + fit_text(row.get("label", ""), label_width),
                "label.width=" + str(label_width),
                "label.max_chars=0",
                "label.align=left",
                "label.drawing=on",
                "label.padding_left=" + ("0" if has_key else "12"),
                "label.padding_right=12",
                "label.color=" + row.get("color", self.palette["text"]),
                "label.font="
                + self.cfg["font"]
                + (":Bold:" if i == 0 else ":Regular:")
                + str(self.cfg["font_size"] - (1 if i == 0 else 0)),
                "icon.color=" + self.palette["muted"],
                "background.drawing=on",
                "background.color=0x00000000",
                "background.height="
                + str(round(row.get("height", 24) * self.cfg["font_size"] / 12)),
                "background.image.drawing=" + ("on" if row.get("image") else "off"),
                "click_script=" + (command(handle) if handle else ""),
            ]
            if row.get("image"):
                args += [
                    "background.image=" + row["image"],
                    "background.image.scale=" + str(row["image_scale"]),
                    "label.drawing=off",
                    "icon.drawing=off",
                ]
            if images:
                args += [
                    "background.image=" + images[i],
                    "background.image.drawing=on",
                    "background.image.scale=0.5",
                    "label.drawing=off",
                    "icon.drawing=off",
                ]
            if row.get("slider"):
                slider_width = min(
                    round(132 * self.cfg["font_size"] / 12), max(0, width - 120)
                )
                args += [
                    "icon=",
                    "icon.drawing=on",
                    "icon.width=" + str(round(64 * self.cfg["font_size"] / 12)),
                    "icon.padding_left=0",
                    "label.width=0",
                    "label.drawing=off",
                ]
                args += [
                    "slider.width=" + str(slider_width),
                    "slider.percentage=" + str(row["slider_value"]),
                    "slider.highlight_color=" + self.palette["text"],
                    "slider.background.color=" + self.palette["line"],
                    "slider.background.height=10",
                    "slider.background.y_offset=-1",
                    "slider.knob.drawing=off",
                    "updates=on",
                    "script=" + command("slider.volume"),
                    "--subscribe",
                    f"{parent}.row.{i}",
                    "mouse.clicked",
                ]
        if parent not in self.underlines:
            members = (
                [parent, "usage.claude", "usage.codex"]
                if parent == "usage"
                else [parent]
            )
            args += [
                "--add",
                "bracket",
                parent + ".underline",
                *members,
                "--set",
                parent + ".underline",
                "background.drawing=off",
                "background.color=" + self.palette["text"],
                "background.height=2",
                "background.y_offset=" + str(1 - self.cfg["height"] // 2),
                "y_offset=0",
                "padding_left=0",
                "padding_right=0",
            ]
            self.underlines.add(parent)
        if self.open_popup != parent or (self.popup_anchor or parent) != anchor:
            self.actions = {k: v for k, v in self.actions.items() if v[0] != parent}
            for path in images:
                Path(path).unlink(missing_ok=True)
            return
        await self.sb(*args)
        self.popup_items[parent] = n
        self.popup_hosts[parent] = anchor
        for path in self.popup_images.get(parent, []):
            Path(path).unlink(missing_ok=True)
        self.popup_images[parent] = images
        await self.set(parent + ".underline", **{"background.drawing": "on"})
        await self.set(anchor, **{"popup.drawing": "on"})

    async def close_popup(self):
        if self.open_popup:
            await self.set(
                self.popup_anchor or self.open_popup, **{"popup.drawing": "off"}
            )
            await self.set(
                self.open_popup + ".underline", **{"background.drawing": "off"}
            )
        self.open_popup = ""
        self.popup_anchor = ""
        self.actions.clear()
        for path in self.cache.glob("art-*"):
            path.unlink(missing_ok=True)
        if self.clickaway:
            if self.clickaway is not asyncio.current_task():
                self.clickaway.cancel()
            self.clickaway = None

    async def watch_clickaway(self):
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                str(ROOT / "helper/clickaway"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            if await proc.stdout.readline():
                await self.close_popup()
        except OSError:
            pass
        finally:
            if proc is not None:
                await stop(proc)

    async def toggle_popup(self, name, anchor=None):
        anchor = anchor or name
        if self.open_popup == name and (self.popup_anchor or name) == anchor:
            await self.close_popup()
            return
        await self.close_popup()
        self.open_popup = name
        self.popup_anchor = anchor
        self.calendar_offset = 0
        from widgets import POPUPS

        fn = POPUPS.get(name)
        if fn:
            await fn(self)
            self.clickaway = self.task(self.watch_clickaway())

    async def dispatch(self, name, *args):
        from widgets import dispatch

        await dispatch(self, name, *args)

    def notify(self, name):
        """Trailing coalescing: at most one concurrent update per widget."""
        if name not in self.enabled_items():
            return
        self.pending.add(name)
        if name not in self.work:

            async def update():
                try:
                    while name in self.pending:
                        self.pending.discard(name)
                        await asyncio.sleep(0.15)
                        self.pending.discard(name)
                        from widgets import UPDATES

                        fn = UPDATES.get(name)
                        if fn:
                            try:
                                await fn(self)
                            except (
                                ValueError,
                                TypeError,
                                KeyError,
                                OSError,
                                IndexError,
                            ):
                                # Never log private labels/CLI output.
                                print("widget update failed: " + name, file=sys.stderr)
                finally:
                    self.work.pop(name, None)

            self.work[name] = self.task(update())

    async def event(self, message):
        event = message.get("event")
        if event == "shutdown":
            self.shutdown("shutdown requested")
        elif isinstance(event, str) and event.startswith("action."):
            action = self.actions.get(event)
            if action and action[0] == self.open_popup:
                try:
                    await action[1]()
                finally:
                    if not action[2]:
                        await self.close_popup()
        elif isinstance(event, str) and event.startswith("popup."):
            name = event[6:]
            if name in ("usage.claude", "usage.codex") and self.flags["usage"]:
                await self.toggle_popup("usage", anchor=name)
            elif name in self.enabled_items():
                await self.toggle_popup(name)
        elif event in ("media.prev", "media.play", "media.next"):
            await self.dispatch(event)
        elif event == "front_app_switched":
            if message.get("info") in (
                "SketchyBar Events",
                "SketchyBar WifiScan",
                "WifiScan",
            ):
                return
            await self.close_popup()
            if self.flags["front_app"]:
                await self.set(
                    "front_app",
                    label=fit_text(message.get("info"), 160, self.cfg["font_size"]),
                )
                await self.refit_media()
            self.notify("workspaces")
        elif event == "slider.volume" and self.flags["volume"]:
            value = message.get("percentage")
            if isinstance(value, str) and value.isdecimal() and 0 <= int(value) <= 100:
                await run(
                    "osascript", "-e", "set volume output volume " + str(int(value))
                )
                self.notify("volume")
        elif event == "shell_cwd" and self.flags["folder"]:
            path = message.get("cwd")
            if isinstance(path, str) and len(path) < 4096 and Path(path).is_dir():
                branch = await run("git", "-C", path, "branch", "--show-current")
                await self.set(
                    "folder",
                    label=text(Path(path).name + " " + branch.strip(), 24),
                    drawing="on",
                )
                await self.refit_media()
        elif event in ("system_woke", "display_change"):
            await self.refresh_display()
        elif event == "volume_change":
            self.notify("volume")
        elif event == "wifi_change":
            self.notify("wifi")
        elif event == "power_source_change":
            self.notify("battery")
        elif event == "theme_change" and self.cfg["theme"] == "auto":
            await self.sb("--reload")

    def enabled_items(self):
        items = {k for k, v in self.flags.items() if v}
        items -= {"calendar", "wifi_scan"}
        return items | {"clock", "settings"}

    async def measure_display(self):
        displays = await query("sketchybar", "--query", "displays")
        if not isinstance(displays, list) or not displays:
            return
        wanted = self.cfg["display"]
        display = next(
            (
                d
                for d in displays
                if (
                    wanted == "main"
                    and d.get("frame", {}).get("x") == 0
                    and d.get("frame", {}).get("y") == 0
                )
                or d.get("arrangement-id") == wanted
            ),
            displays[0],
        )
        self.display_frame = display["frame"]
        width = self.cfg["width"]
        margin = (
            max(self.cfg["margin"], round((self.display_frame["w"] - width) / 2))
            if width
            else self.cfg["margin"]
        )
        await self.sb("--bar", "margin=" + str(margin))
        self.notch_left = self.display_frame["w"] / 2
        bounds = (
            await run(ROOT / "helper/notch", str(display.get("DirectDisplayID", "")))
        ).split()
        if len(bounds) == 2 and all(v.isdecimal() for v in bounds):
            self.notch_left = int(bounds[0])
            width = max(0, int(bounds[1]) - int(bounds[0]))
            await self.sb("--bar", "notch_width=" + str(width or 200))

    async def setup(self):
        theme = self.cfg["theme"]
        if theme == "auto":
            theme = (
                "dark"
                if "Dark" in await run("defaults", "read", "-g", "AppleInterfaceStyle")
                else "light"
            )
        self.palette = (
            {
                "bg": "08090a",
                "surface": "0b0e0d",
                "text": "e6ebe6",
                "muted": "8b968e",
                "dim": "6b776f",
                "line": "1e2422",
                "warn": "e0b64a",
                "error": "e0685f",
                "accent": "3ed49c",
                "fill": "194a39",
            }
            if theme == "dark"
            else {
                "bg": "f4f6f4",
                "surface": "ffffff",
                "text": "101413",
                "muted": "59635c",
                "dim": "6e7a72",
                "line": "d3dad4",
                "warn": "8a6410",
                "error": "b03a30",
                "accent": "3ed49c",
                "fill": "b3dfca",
            }
        )
        self.palette.update(read_palette())
        self.palette = {k: "0xff" + v for k, v in self.palette.items()}
        if self.animations:
            self.animations = (
                await run(
                    "defaults", "read", "com.apple.universalaccess", "reduceMotion"
                )
            ).strip() != "1"
        self.pixels = generate(self.cache, self.palette, self.cfg["cat_grass_color"])
        await run(
            ROOT / "helper/render",
            "icons",
            ROOT / "assets",
            self.pixels,
            self.palette["text"],
            self.palette["dim"],
            timeout=5,
        )
        await self.sb(*build(self))
        await self.measure_display()
        from widgets import front_app

        if self.flags["front_app"]:
            await front_app(self)
        await self.refit_media()
        for name in self.enabled_items():
            self.notify(name)

    async def refit_media(self):
        if not self.flags["media"]:
            return
        async with self.layout_lock:
            left = await query("sketchybar", "--query", "island.left")
            bounds = (left or {}).get("bounding_rects", {})
            rect = next(iter(bounds.values()), None)
            if not rect:
                return
            left_end = rect["origin"][0] + rect["size"][0] - self.display_frame["x"]
            app = fit_text(
                self.media_state.get("appName")
                or self.media_state.get("applicationName")
                or "media",
                80,
            )
            app_width = round(text_width(app)) + 8
            # EQ is 18pt plus padding; transport includes two configured gaps.
            gap = self.cfg["containers"]["media"]["gap"]
            padding = self.cfg["containers"]["media"]["padding"]
            left_gap = self.cfg["containers"]["left"]["gap"]
            available = self.notch_left - left_end - gap - left_gap
            transport = 74 + 2 * self.cfg["containers"]["media"]["item_gap"]
            controls = transport
            left_padding = 18 + padding
            show_transport = (
                available >= left_padding + app_width + controls + padding + 40
            )
            if not show_transport:
                controls = 0
            title_width, _ = media_geometry(
                left_end,
                self.notch_left,
                left_padding + app_width + controls + padding,
                gap,
            )
            args = []
            for name in (
                "media.prev",
                "media.play",
                "media.next",
                "media.prev.gap",
                "media.play.gap",
            ):
                args += [
                    "--set",
                    name,
                    "drawing=" + ("on" if show_transport else "off"),
                ]
            args += [
                "--set",
                "media",
                "icon=" + app,
                "icon.width=" + str(app_width),
                "label=" + fit_text(self.media_state.get("title") or "—", title_width),
                "label.width=" + str(title_width),
            ]
            await self.sb(*args)
            media = await query("sketchybar", "--query", "island.media")
            rect = next(iter((media or {}).get("bounding_rects", {}).values()), None)
            if rect:
                self.media_layout = (
                    rect["origin"][0] - self.display_frame["x"] + 2 - left_end,
                    max(0, rect["size"][0] - 4),
                )
            await self.progress()

    async def progress(self):
        if not self.media_layout:
            return
        d = self.media_state
        duration = d.get("duration") or 0
        try:
            elapsed = float(d.get("elapsedTime") or 0)
            if d.get("playing") and isinstance(d.get("timestamp"), str):
                from datetime import datetime

                elapsed += max(
                    0,
                    time.time()
                    - datetime.fromisoformat(
                        d["timestamp"].replace("Z", "+00:00")
                    ).timestamp(),
                )
            ratio = max(0, min(1, elapsed / float(duration))) if duration else 0
        except (ValueError, TypeError, OverflowError):
            ratio = 0
        offset, width = self.media_layout
        filled = round(width * ratio)
        visible = "on" if d and filled else "off"
        near_end = filled > width - 22
        values = {
            "media.fill": {
                "label.width": filled if near_end else width,
                "padding_left": round(offset),
                "padding_right": -(filled if near_end else width),
            },
            "media.mask": {
                "label.width": 0 if near_end else max(0, width - 11 - filled),
                "padding_left": filled,
                "padding_right": -(
                    filled + (0 if near_end else max(0, width - 11 - filled))
                ),
            },
            "media.round": {
                "label.width": 0 if near_end else width - filled,
                "padding_left": filled,
                "padding_right": -(filled + (0 if near_end else width - filled)),
            },
        }
        await self.set_many(
            {name: {"drawing": visible, **props} for name, props in values.items()}
        )

    async def visuals(self):
        # One owned task, at most four image frames/s; no shell animation processes.
        frame, next_cat, next_eq, next_progress, next_cursor = 0, 0, 0, 0, 0
        cursor = True
        while not self.closed.is_set():
            now = time.monotonic()
            updates = {}
            if self.flags["system"] and now >= next_cat:
                cpu, mem = self.system_data
                frame = frame % 4 + 1 if self.animations else 1
                suffix = "_warn" if mem is not None and mem >= 80 else ""
                updates["system"] = {
                    "background.image": str(self.pixels / f"cat_{frame}{suffix}.png")
                }
                next_cat = now + (
                    max(0.25, 0.6 - min(100, cpu) * 0.004) if self.animations else 15
                )
            if (
                self.animations
                and self.cfg["wordmark_animation"]
                and now >= next_cursor
            ):
                cursor = not cursor
                updates["wordmark.cursor"] = {
                    "background.color": self.palette["accent"]
                    if cursor
                    else "0x00000000"
                }
                next_cursor = now + 1
            if self.flags["media"] and now >= next_eq:
                playing = self.media_state.get("playing") is True
                for n in range(1, 4):
                    height = (
                        (3, 7, 11, 5)[(int(now * 2) + n) % 4]
                        if playing and self.animations
                        else 4
                        if playing
                        else 2
                    )
                    updates[f"media.eq.{n}"] = {
                        "background.height": height,
                        "background.y_offset": (height - 10) // 2,
                        "background.color": self.palette["muted"]
                        if playing
                        else self.palette["dim"],
                    }
                next_eq = now + 0.5
            await self.set_many(updates)
            if self.flags["media"] and now >= next_progress:
                await self.progress()
                next_progress = now + 2
            await asyncio.sleep(0.25)

    async def stream(self, args, widget):
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                limit=2 * 1024 * 1024,
            )
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                if widget == "media":
                    # Progress-only diffs update memory without extra CLI queries.
                    try:
                        event = json.loads(line)
                        data = event.get("payload")
                        if not isinstance(data, dict):
                            continue
                        before = self.media_source_data or {}
                        after = dict(before) if event.get("diff") is True else {}
                        after.update(data)
                        self.media_source_data = after
                        self.media_stream_seen = time.monotonic()
                        keys = (
                            "title",
                            "artist",
                            "bundleIdentifier",
                            "playing",
                            "artworkData",
                        )
                        if not any(before.get(k) != after.get(k) for k in keys):
                            continue
                    except (ValueError, AttributeError):
                        continue
                self.notify(widget)
        except (OSError, ValueError):
            pass
        finally:
            if proc is not None:
                await stop(proc)

    async def periodic(self):
        intervals = {
            "clock": 30,
            "wifi": 60,
            "battery": 60,
            "usage": 60,
            "system": 15,
            "notifications": 60,
            "tailscale": 60,
            "next_event": 60,
            "volume": 60,
            "media": 30,
        }
        due = {name: time.monotonic() + seconds for name, seconds in intervals.items()}
        media_task = None
        audio_task = None
        while not self.closed.is_set():
            now = time.monotonic()
            for name, seconds in intervals.items():
                if name in self.enabled_items() and now >= due[name]:
                    self.notify(name)
                    due[name] = now + seconds
            if now - self.last_probe >= (5 if self.sb_unavailable else 30):
                self.last_probe = now
                if self.flags["workspaces"]:
                    self.notify("workspaces")
                # Owned stream children are restarted only if the handle finished.
                if (
                    self.flags["media"]
                    and shutil.which("media-control")
                    and (media_task is None or media_task.done())
                ):
                    media_task = self.task(
                        self.stream([shutil.which("media-control"), "stream"], "media")
                    )
                if self.flags["volume"] and (audio_task is None or audio_task.done()):
                    audio_task = self.task(
                        self.stream([str(ROOT / "helper/audio"), "watch"], "volume")
                    )
                # A missing reply is normal during sleep/wake. Keep the IPC
                # server alive so clicks and system_woke can recover the bar.
                await self.probe()
            # Refresh moving time only while the media popup is open.
            if self.open_popup == "media" and now >= due.get("media_popup", 0):
                self.notify("media")
                due["media_popup"] = now + 5
            await asyncio.sleep(1)

    async def serve(self, sock):
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue(maxsize=64)

        def receive():
            try:
                data = sock.recv(8193)
                if len(data) <= 8192:
                    message = json.loads(data)
                    if isinstance(message, dict):
                        if message.get("event") == "shutdown":
                            self.shutdown("shutdown requested")
                        else:
                            queue.put_nowait(message)
            except (OSError, ValueError, asyncio.QueueFull):
                pass

        loop.add_reader(sock.fileno(), receive)
        try:
            while not self.closed.is_set():
                message = await queue.get()
                try:
                    event = message.get("event", "")
                    if isinstance(event, str) and event.startswith(
                        ("popup.", "action.", "media.", "slider.")
                    ):
                        if self.ui_task and not self.ui_task.done():
                            if event.startswith("popup."):
                                self.ui_task.cancel()
                                await asyncio.gather(
                                    self.ui_task, return_exceptions=True
                                )
                            else:
                                continue

                        async def handle(value):
                            try:
                                await self.event(value)
                            except (
                                OSError,
                                ValueError,
                                TypeError,
                                KeyError,
                                IndexError,
                            ):
                                print("action failed", file=sys.stderr)

                        self.ui_task = self.task(handle(message))
                    else:
                        await self.event(message)
                except (OSError, ValueError, TypeError, KeyError, IndexError):
                    print("event rejected", file=sys.stderr)
        finally:
            loop.remove_reader(sock.fileno())

    async def start(self):
        sock_path = self.cache / "events.sock"
        # Lock ownership is held by main before removing a previous stale socket.
        if sock_path.exists() or sock_path.is_symlink():
            s = sock_path.lstat()
            if not stat.S_ISSOCK(s.st_mode) or s.st_uid != os.getuid():
                raise ValueError("refusing unsafe socket path")
            sock_path.unlink()
        for path in self.cache.glob("art-*"):
            path.unlink(missing_ok=True)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.bind(str(sock_path))
        sock_path.chmod(0o600)
        sock.setblocking(False)
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self.shutdown, sig.name)
        try:
            await self.setup()
            print("runtime started", file=sys.stderr, flush=True)
            self.task(self.serve(sock))
            self.task(self.periodic())
            self.task(self.visuals())
            await self.closed.wait()
        finally:
            for task in list(self.tasks):
                task.cancel()
            await asyncio.gather(*list(self.tasks), return_exceptions=True)
            if self.caffeinate is not None:
                await stop(self.caffeinate)
            for path in self.cache.glob("art-*"):
                path.unlink(missing_ok=True)
            sock.close()
            sock_path.unlink(missing_ok=True)
            print("runtime stopped", file=sys.stderr, flush=True)


async def daemon():
    cfg = config()
    cache = cache_path()
    # O_NOFOLLOW stops symlink-based lock redirection. No PID file or pkill.
    fd = private_file(cache / "runtime.lock")
    try:
        if os.fstat(fd).st_uid != os.getuid() or not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("invalid lock file")
        os.fchmod(fd, 0o600)
        for _ in range(60):
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                await asyncio.sleep(0.1)
        else:
            raise ValueError("previous runtime did not release its lock")
        await Bar(cfg, cache).start()
    finally:
        os.close(fd)


def main():
    os.umask(0o077)
    os.environ["PATH"] = (
        "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    )
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    if mode == "check":
        config()
        read_palette()
        print("configuration valid")
    elif mode == "send" and len(sys.argv) == 3:
        name = sys.argv[2]
        message = {"event": name}
        if name == "event":
            message = {
                "event": os.environ.get("SENDER"),
                "info": os.environ.get("INFO", "")[:4096],
                "cwd": os.environ.get("CWD", "")[:4096],
            }
        elif name == "slider.volume" and os.environ.get("SENDER") == "mouse.clicked":
            message["percentage"] = os.environ.get("PERCENTAGE", "")[:8]
        send(message)
    elif mode == "setup":
        config()  # A broken edit leaves the old runtime running.
        read_palette()
        send({"event": "shutdown"})
        log = cache_path() / "runtime.log"
        # The outgoing runtime may still be logging while releasing its lock.
        # Append atomically so reloads preserve ordered shutdown diagnostics.
        fd = private_file(log)
        try:
            if (
                not stat.S_ISREG(os.fstat(fd).st_mode)
                or os.fstat(fd).st_uid != os.getuid()
            ):
                raise ValueError("invalid diagnostics file")
            os.fchmod(fd, 0o600)
            fcntl.fcntl(fd, fcntl.F_SETFL, fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_APPEND)
            subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "daemon"],
                stdout=subprocess.DEVNULL,
                stderr=fd,
                start_new_session=True,
            )
        finally:
            os.close(fd)
    elif mode == "daemon":
        asyncio.run(daemon())
    else:
        raise ValueError("usage: bar.py check|setup|daemon|send EVENT")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
