"""User-facing appearance, local assets, and reference popup regressions."""

import asyncio
import json
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))
import widgets
from bar import Bar
from layout import build
from pixels import generate
from rendering import popup_width
from runtime import config
from test_layout import PALETTE
from wm import Snapshot


class AppearanceTests(unittest.TestCase):
    def test_appearance_defaults_and_media_disabled(self):
        cfg = config(ROOT)
        self.assertFalse(cfg["features"]["media"])
        self.assertEqual(cfg["font"], "CommitMonoGhostty")
        self.assertFalse(cfg["features"]["wifi"])
        self.assertEqual(cfg["height"], 30)
        self.assertEqual(cfg["corner_radius"], 13)
        self.assertEqual(popup_width(cfg, "clock", 1512), 255)
        cfg["font_size"] = 18
        self.assertEqual(popup_width(cfg, "clock", 1512), 382)
        cfg["popup_width"] = 320
        self.assertEqual(popup_width(cfg, "clock", 1512), 320)

    def test_volume_is_next_to_clock_and_circles_follow_height(self):
        bar = Bar(config(ROOT), Path("/tmp/appearance"))
        bar.palette = PALETTE
        args = build(bar)
        positions = [
            (args[i + 2], args[i + 3])
            for i in range(len(args) - 3)
            if args[i : i + 2] == ["--add", "item"]
        ]
        self.assertEqual(dict(positions)["volume"], "right")
        right = [
            name
            for name, position in positions
            if position == "right"
            and not name.startswith("main.")
            and name != "right.gap"
        ]
        self.assertEqual(
            right[:7],
            [
                "clock",
                "volume.5",
                "volume.4",
                "volume.3",
                "volume.2",
                "volume.1",
                "volume",
            ],
        )
        self.assertNotIn("notch.gap", dict(positions))
        for name in ("system", "settings"):
            i = next(
                i
                for i, arg in enumerate(args)
                if arg == "--set" and args[i + 1] == name
            )
            end = next(
                (j for j in range(i + 2, len(args)) if args[j].startswith("--")),
                len(args),
            )
            props = dict(a.split("=", 1) for a in args[i + 2 : end])
            self.assertEqual(props["background.height"], "30")
            self.assertEqual(props["icon.width"], "30")

    def test_container_edges_do_not_extend_past_their_gap(self):
        cfg = config(ROOT)
        cfg["containers"]["apps"].update(gap=19, padding=9, height=24, corner_radius=3)
        bar = Bar(cfg, Path("/tmp/appearance"))
        bar.palette = PALETTE
        args = build(bar)

        def props(name):
            i = next(
                i for i, a in enumerate(args) if a == "--set" and args[i + 1] == name
            )
            end = next(
                (j for j in range(i + 2, len(args)) if args[j].startswith("--")),
                len(args),
            )
            return dict(a.split("=", 1) for a in args[i + 2 : end])

        self.assertEqual(props("usage")["width"], "0")
        self.assertNotIn("padding_left", props("usage"))
        self.assertEqual(props("apps.gap")["width"], "19")
        self.assertEqual(props("apps.pad.right")["width"], "9")
        self.assertEqual(props("apps.cap")["background.height"], "24")
        self.assertEqual(props("apps.cap")["background.corner_radius"], "3")
        self.assertEqual(
            props("main.gap.volume")["width"], props("main.gap.battery")["width"]
        )
        self.assertEqual(
            props("main.gap.battery")["width"], props("main.gap.usage")["width"]
        )
        for name in ("ports", "tailscale", "clock", "battery", "volume"):
            self.assertNotIn("padding_left", props(name))
            self.assertNotIn("padding_right", props(name))

    def test_invalid_container_settings_are_rejected(self):
        for values in (
            {"apps": {"gap": -1}},
            {"right": {"height": 50}},
            {"unknown": {}},
            {"cat": {"border_width": 10}},
        ):
            with tempfile.TemporaryDirectory() as directory:
                cfg = config(ROOT)
                cfg["containers"] = values
                (Path(directory) / "config.json").write_text(json.dumps(cfg))
                with self.assertRaises(ValueError):
                    config(Path(directory))

    def test_grass_color_changes_only_grass_pixels(self):
        def decode(path):
            data = path.read_bytes()
            chunks, offset = [], 8
            while offset < len(data):
                size = int.from_bytes(data[offset : offset + 4], "big")
                if data[offset + 4 : offset + 8] == b"IDAT":
                    chunks.append(data[offset + 8 : offset + 8 + size])
                offset += size + 12
            raw = zlib.decompress(b"".join(chunks))
            return [
                raw[y * 265 + 1 + x * 4 : y * 265 + 5 + x * 4]
                for y in range(66)
                for x in range(66)
            ]

        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            original = decode(generate(cache / "original", PALETTE) / "cat_1.png")
            custom = decode(
                generate(cache / "custom", PALETTE, "#6b5e30") / "cat_1.png"
            )
            automatic = decode(generate(cache / "auto", PALETTE, "auto") / "cat_1.png")
            grass = bytes((0x26, 0x79, 0x5A, 255))
            self.assertIn(grass, original)
            for before, after, themed in zip(original, custom, automatic):
                if before == grass:
                    self.assertEqual(after, bytes((0x6B, 0x5E, 0x30, 255)))
                    self.assertEqual(themed, bytes((0x19, 0x4A, 0x39, 255)))
                else:
                    self.assertEqual(before, after)
                    self.assertEqual(before, themed)

    def test_invalid_appearance_values_are_rejected(self):
        for key, value in (
            ("wm_number_bold", "yes"),
            ("cat_grass_color", "https://example.com/icon"),
            ("cat_grass_color", "#12345"),
            ("font_size", 30),
            ("width", 200),
            ("corner_radius", -1),
            ("font", "bad:Regular:40"),
            ("popup_width", 40),
        ):
            with tempfile.TemporaryDirectory() as directory:
                cfg = config(ROOT)
                cfg[key] = value
                (Path(directory) / "config.json").write_text(json.dumps(cfg))
                with self.assertRaises(ValueError):
                    config(Path(directory))

    def test_local_icons_are_enabled_and_no_agent_word_is_emitted(self):
        bar = Bar(config(ROOT), Path("/tmp/appearance"))
        bar.palette = PALETTE
        args = build(bar)
        self.assertNotIn("icon=agent", args)
        self.assertNotIn("icon=\uecb1", args)
        self.assertNotIn("icon=\uecb2", args)
        for item in ("ports", "tailscale", "usage.claude", "usage.codex"):
            i = next(
                i
                for i, arg in enumerate(args)
                if arg == "--set" and args[i + 1] == item
            )
            end = next(
                (j for j in range(i + 2, len(args)) if args[j].startswith("--")),
                len(args),
            )
            props = dict(a.split("=", 1) for a in args[i + 2 : end])
            self.assertEqual(props["icon.background.drawing"], "on")
            self.assertEqual(props["icon.background.image.drawing"], "on")
            self.assertFalse(props["icon.background.image"].startswith("http"))
        for name in ("openai.svg", "claude.svg"):
            asset = (ROOT / "assets" / name).read_text()
            self.assertNotIn("href=", asset)
            self.assertNotIn("<script", asset)


class PopupReferenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bar = Bar(config(ROOT), Path(self.tmp.name))
        self.bar.palette = PALETTE
        self.bar.sb = AsyncMock(return_value="{}")
        self.bar.popup = AsyncMock()

    async def asyncTearDown(self):
        for task in self.bar.tasks:
            task.cancel()
        await asyncio.gather(*self.bar.tasks, return_exceptions=True)
        self.tmp.cleanup()

    async def test_only_the_numeric_workspace_prefix_is_bold(self):
        for label, expected_icon, expected_label in (
            ("12", "12", " [max] ▾"),
            ("12 Code", "12", " Code [max] ▾"),
            ("Code", "", "Code [max] ▾"),
        ):
            self.bar.wm.read = AsyncMock(
                return_value=Snapshot(current=label, maximized=True)
            )
            self.bar.cfg["wm_number_bold"] = True
            await widgets.workspaces(self.bar)
            self.assertEqual(self.bar.props["workspaces", "icon"], expected_icon)
            self.assertEqual(self.bar.props["workspaces", "label"], expected_label)
            self.assertIn(":Bold:", self.bar.props["workspaces", "icon.font"])
            self.bar.cfg["wm_number_bold"] = False
            await widgets.workspaces(self.bar)
            self.assertIn(":Regular:", self.bar.props["workspaces", "icon.font"])

    async def test_static_wordmark_does_not_stop_cat_animation(self):
        self.bar.animations = True
        self.bar.cfg["wordmark_animation"] = False
        self.bar.set_many = AsyncMock()
        ticks = iter(range(8))

        async def advance(_):
            if self.bar.set_many.await_count >= 6:
                self.bar.closed.set()

        with (
            patch("bar.time.monotonic", side_effect=lambda: next(ticks)),
            patch("bar.asyncio.sleep", side_effect=advance),
        ):
            await self.bar.visuals()
        updates = [call.args[0] for call in self.bar.set_many.call_args_list]
        self.assertFalse(any("wordmark.cursor" in update for update in updates))
        self.assertGreater(
            len({u["system"]["background.image"] for u in updates if "system" in u}), 1
        )

    async def test_claude_stays_visible_without_fresh_cache(self):
        with (
            patch("widgets.local_usage", return_value={}),
            patch("widgets.Path.is_dir", return_value=True),
        ):
            await widgets.usage(self.bar)
        self.assertEqual(self.bar.props["usage.claude", "drawing"], "on")
        self.assertEqual(self.bar.props["usage.claude", "label"], "—")

    async def test_usage_popup_has_both_providers_and_reference_gauges(self):
        self.bar.usage_data = {
            "Claude": [("five_hour", 21, "")],
            "Codex": [("primary", 10, "")],
        }
        await widgets.usage_popup(self.bar)
        rows = self.bar.popup.call_args.args[2]
        self.assertEqual(
            [r["label"] for r in rows if r.get("icon")], ["claude", "codex"]
        )
        self.assertEqual(len([r for r in rows if r.get("kind") == "gauge"]), 4)

    async def test_calendar_uses_colored_seven_column_rows(self):
        self.bar.flags["calendar"] = False
        await widgets.calendar_popup(self.bar)
        args = self.bar.popup.call_args.args
        self.assertEqual(args[1], "CALENDAR")
        grids = [r for r in args[2] if r.get("kind") == "calendar"]
        self.assertTrue(grids)
        self.assertTrue(all(len(r["cells"]) == 7 for r in grids))
        self.assertNotEqual(
            grids[0]["cells"][0]["color"], grids[0]["cells"][1]["color"]
        )
