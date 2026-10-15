"""Widget queries and explicit argv actions. Private data stays in memory."""

import asyncio
import base64
import calendar as cal
import hashlib
import ipaddress
import json
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from layout import fit_text, text_width
from runtime import ROOT, image_size, number, private_file, query, run, stop, text


def row(left, label, action=None, keep=False, color=None, **style):
    out = {"left": left, "label": label, "action": action, "keep": keep}
    out.update(style)
    if color:
        out["color"] = color
    return out


async def front_app(bar):
    front = await query(ROOT / "helper/axmenu", "front")
    if isinstance(front, dict):
        await bar.set(
            "front_app", label=fit_text(front.get("name"), 160, bar.cfg["font_size"])
        )


async def workspaces(bar):
    snapshot = await bar.wm.read(inventory=bar.open_popup == "workspaces")
    label = text(snapshot.current or snapshot.status or "wm off", 16)
    if snapshot.backend == "omniwm":
        label = text(snapshot.current_name or label, 12)
    if snapshot.maximized:
        label += " [max]"
    elif snapshot.current:
        label += " [ · ]"
    label = text(label, 20)
    match = re.match(r"^([0-9]+)(.*)$", label)
    number = match.group(1) if match else ""
    suffix = match.group(2) if match else label
    weight = "Bold" if bar.cfg["wm_number_bold"] else "Regular"
    await bar.set(
        "workspaces",
        icon=number,
        label=suffix + " ▾",
        **{
            "icon.drawing": "on" if number else "off",
            "icon.font": f"{bar.cfg['font']}:{weight}:{bar.cfg['font_size']}",
            "icon.padding_left": 8 if number else 0,
            "label.padding_left": 0 if number else 8,
            "label.width": round(text_width(suffix + " ▾", bar.cfg["font_size"])),
        },
    )
    await bar.refit_media()
    if bar.wm.backend and (bar.wm_task is None or bar.wm_task.done()):
        bar.wm_task = bar.task(bar.wm.watch(bar.notify))
    if bar.open_popup == "workspaces":
        rows = [
            row(
                "●" if w.key == snapshot.current else w.name,
                w.name + " · " + ", ".join(w.apps) + f" ({w.count})",
                bar.action("workspace", w.key),
            )
            for w in snapshot.workspaces
        ]
        if not rows:
            rows = [
                row(
                    "",
                    "No occupied workspaces"
                    if snapshot.backend
                    else snapshot.detail or "Start AeroSpace or OmniWM",
                )
            ]
        await bar.popup("workspaces", (snapshot.backend or "WORKSPACES").upper(), rows)


async def clock(bar):
    now = datetime.now()
    await bar.set("clock", icon=now.strftime("%m.%d"), label=now.strftime("%H:%M"))


async def calendar_popup(bar):
    now = datetime.now()
    index = now.year * 12 + now.month - 1 + bar.calendar_offset
    year, month = divmod(index, 12)
    month += 1
    prev = 12 if month == 1 else month - 1
    following = 1 if month == 12 else month + 1
    rows = [
        row(
            "",
            f"{year:04}.{month:02}",
            bar.action("month", 0),
            True,
            kind="center",
            right="●",
        ),
        row(
            "", f"‹ {prev:02}", bar.action("month", -1), True, color=bar.palette["dim"]
        ),
        row(
            "",
            f"{following:02} ›",
            bar.action("month", 1),
            True,
            color=bar.palette["dim"],
            align="right",
        ),
    ]
    events = []
    if bar.flags["calendar"]:
        events = await query(
            ROOT / "helper/Events.app/Contents/MacOS/Events",
            f"{year:04}-{month:02}-01",
            json.dumps(bar.cfg["calendar_names"]),
            timeout=35,
        )
    holidays = set()
    for event in events if isinstance(events, list) else []:
        if (
            bar.cfg["holiday_calendar"]
            and event.get("calendar") == bar.cfg["holiday_calendar"]
        ):
            for m, d in re.findall(r"(\d{2})[.-](\d{2})", event.get("date", "")):
                if int(m) == month:
                    holidays.add(int(d))
    error = bar.palette["error"]
    info = bar.palette.get("info", "0xff7fb8d9")
    rows.append(
        row(
            "",
            "",
            kind="calendar",
            cells=[
                {
                    "label": label,
                    "color": error
                    if i == 0
                    else info
                    if i == 6
                    else bar.palette["dim"],
                }
                for i, label in enumerate(("SU", "MO", "TU", "WE", "TH", "FR", "SA"))
            ],
        )
    )
    today = now.day if (year, month) == (now.year, now.month) else 0
    for week in cal.Calendar(firstweekday=6).monthdayscalendar(year, month):
        rows.append(
            row(
                "",
                "",
                kind="calendar",
                cells=[
                    {
                        "label": f"[{d:2}]"
                        if d and d == today
                        else str(d)
                        if d
                        else "",
                        "color": error
                        if i == 0 or d in holidays
                        else info
                        if i == 6
                        else bar.palette["text"],
                    }
                    for i, d in enumerate(week)
                ],
            )
        )
    if isinstance(events, dict) and events.get("error") == "calendar_permission":
        rows.append(
            row("", "Allow Calendars for SketchyBar Events", color=bar.palette["muted"])
        )
    for event in events[:16] if isinstance(events, list) else []:
        rows.append(
            row(
                event.get("date", ""),
                event.get("title", ""),
                bar.action("open_app", "Calendar"),
                key_width=86,
                color=error
                if bar.cfg["holiday_calendar"]
                and event.get("calendar") == bar.cfg["holiday_calendar"]
                else None,
            )
        )
    rows.append(
        row(
            "",
            "Calendar ↗",
            bar.action("open_app", "Calendar"),
            color=bar.palette["muted"],
        )
    )
    await bar.popup("clock", "CALENDAR", rows)


async def next_event(bar):
    events = await query(
        ROOT / "helper/Events.app/Contents/MacOS/Events",
        "today",
        json.dumps(bar.cfg["calendar_names"]),
        timeout=6,
    )
    now = datetime.now().timestamp()
    events = (
        [e for e in events if number(e.get("start"), high=1e12) <= now + 3600]
        if isinstance(events, list)
        else []
    )
    if events:
        event = events[0]
        await bar.set(
            "next_event",
            drawing="on",
            label=text(event.get("date", "") + " " + event.get("title", ""), 24),
        )
    else:
        await bar.set("next_event", drawing="off")
    await bar.refit_media()


async def next_popup(bar):
    events = await query(
        ROOT / "helper/Events.app/Contents/MacOS/Events",
        "today",
        json.dumps(bar.cfg["calendar_names"]),
        timeout=6,
    )
    await bar.popup(
        "next_event",
        "TODAY",
        [
            row(
                e.get("date", ""),
                e.get("title", ""),
                bar.action("open_app", "Calendar"),
            )
            for e in events[:20]
        ]
        if isinstance(events, list) and events
        else [row("", "No events")],
    )


async def media(bar):
    if (
        bar.media_source_data is not None
        and time.monotonic() - bar.media_stream_seen < 35
    ):
        data = bar.media_source_data
    else:
        data = (
            await query("media-control", "get")
            if shutil.which("media-control")
            else None
        )
        bar.media_source_data = data if isinstance(data, dict) else None
    # Apple Music is deliberately excluded; no AppleScript fallback remains.
    if not isinstance(data, dict) or data.get("bundleIdentifier") == "com.apple.Music":
        data = {}
    old = bar.media_state
    bar.media_state = data
    if (
        any(
            old.get(k) != data.get(k)
            for k in ("title", "appName", "applicationName", "bundleIdentifier")
        )
        or bar.media_layout is None
    ):
        await bar.refit_media()
    await bar.set(
        "media", **{"label.color": bar.palette["text"] if data else bar.palette["dim"]}
    )
    await bar.set("media.play", label="❚❚" if data.get("playing") is True else "▶")
    if bar.open_popup == "media":
        await media_popup(bar)


async def media_popup(bar):
    d = bar.media_state
    elapsed = int(number(d.get("elapsedTime"), high=864000))
    duration = int(number(d.get("duration"), high=864000))
    stamp = d.get("timestamp")
    if d.get("playing") and isinstance(stamp, str):
        try:
            elapsed += max(
                0,
                int(
                    time.time()
                    - datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
                ),
            )
        except ValueError:
            pass

    def duration_text(n):
        return f"{n // 60}:{n % 60:02}"

    rows = [
        row("title", d.get("title") or "Nothing playing"),
        row("artist", d.get("artist") or "—"),
        row(
            "time",
            duration_text(min(elapsed, duration)) + " / " + duration_text(duration)
            if duration
            else "live / unknown duration",
        ),
    ]
    if d:
        rows += [
            row("«", "Previous", bar.action("media.prev"), True),
            row("▶", "Play / pause", bar.action("media.play"), True),
            row("»", "Next", bar.action("media.next"), True),
        ]
    # Embedded artwork gets its own row so the song title remains visible.
    art = d.get("artworkData")
    if isinstance(art, str) and len(art) < 1400000:
        try:
            data = base64.b64decode(art, validate=True)
            dimensions = image_size(data)
            if dimensions and max(dimensions) <= 2048 and len(data) <= 1024 * 1024:
                path = bar.cache / ("art-" + hashlib.sha256(data).hexdigest()[:16])
                fd = private_file(path, truncate=True)
                with os.fdopen(fd, "wb") as file:
                    file.write(data)
                rows.insert(
                    0,
                    {
                        "label": "",
                        "image": str(path),
                        "height": 144,
                        "image_scale": min(1, 120 / max(dimensions)),
                    },
                )
                for old in bar.cache.glob("art-*"):
                    if old != path:
                        old.unlink(missing_ok=True)
        except (ValueError, OSError):
            pass
    await bar.popup("media", "MEDIA", rows)


async def volume(bar):
    out = await run(
        "osascript",
        "-e",
        "set s to get volume settings",
        "-e",
        'return (output volume of s as text) & "," & (output muted of s as text)',
    )
    parts = out.strip().split(",")
    value = int(number(parts[0] if parts else 0))
    muted = len(parts) > 1 and parts[1].strip() == "true"
    bar.volume_muted = muted
    await bar.set("volume", **{"icon": "\U000f0581" if muted else "\U000f057e"})
    for i in range(1, 6):
        await bar.set(
            f"volume.{i}",
            **{
                "background.color": bar.palette["text"]
                if not muted and value >= i * 20 - 10
                else bar.palette["bg"]
            },
        )
    if bar.open_popup == "volume" and getattr(bar, "volume_rows", None):
        bar.volume_rows[0].update(label=f"{value}%", slider_value=value)
        bar.volume_rows[1]["label"] = "Unmute" if muted else "Mute"
        await bar.popup("volume", "VOLUME", bar.volume_rows)


async def volume_popup(bar):
    devices = await query(ROOT / "helper/audio")
    bluetooth = await query(ROOT / "helper/audio", "bt", timeout=6)
    value = int(
        number(await run("osascript", "-e", "output volume of (get volume settings)"))
    )
    slider = row("vol", str(value) + "%")
    slider.update(slider=True, slider_value=value)
    rows = [
        slider,
        row(
            "",
            "Unmute" if getattr(bar, "volume_muted", False) else "Mute",
            bar.action("mute"),
            True,
            icon=str(bar.pixels / "mute.png"),
        ),
        row("", "OUTPUT", kind="section"),
    ]
    for d in devices[:8] if isinstance(devices, list) else []:
        if type(d.get("id")) is int and d["id"] > 0:
            rows.append(
                row(
                    "▱" if d.get("kind") == "builtin" else "♫",
                    d.get("name", "—"),
                    bar.action("audio", "set", str(d["id"])),
                    True,
                    icon=str(
                        bar.pixels
                        / (
                            "laptop.png"
                            if d.get("kind") == "builtin"
                            else "headphones.png"
                        )
                    ),
                    right="✓" if d.get("current") else "",
                    color=bar.palette["text"]
                    if d.get("current")
                    else bar.palette["muted"],
                )
            )
    for d in bluetooth[:4] if isinstance(bluetooth, list) else []:
        addr = d.get("address", "")
        if re.fullmatch(r"[0-9A-Fa-f]{2}(?:[-:][0-9A-Fa-f]{2}){5}", addr):
            rows.append(
                row(
                    "bt", d.get("name", "—"), bar.action("audio", "connect", addr), True
                )
            )
    rows.append(row("open", "Sound Settings ↗", bar.action("settings", "sound")))
    bar.volume_rows = rows
    await bar.popup("volume", "VOLUME", rows)


async def wifi_details():
    hardware = await run("networksetup", "-listallhardwareports")
    match = re.search(
        r"Hardware Port: (?:Wi-Fi|AirPort)\s+Device: ([A-Za-z0-9]+)", hardware
    )
    interface = match[1] if match else "en0"
    ip, summary = await asyncio.gather(
        run("ipconfig", "getifaddr", interface),
        run("ipconfig", "getsummary", interface),
    )
    ssid = re.search(r"SSID\s*:\s*([^\n]+)", summary)
    ssid = ssid[1].strip() if ssid else ""
    if ssid == "<redacted>":
        ssid = ""
    return interface, ip.strip(), ssid


async def wifi(bar):
    _, ip, ssid = await wifi_details()
    await bar.set("wifi", label=text(ssid or ("on" if ip else "off"), 16))


async def wifi_popup(bar):
    interface, ip, ssid = await wifi_details()
    router = (await run("ipconfig", "getoption", interface, "router")).strip()
    rows = [
        row("ssid", ssid or "hidden by macOS"),
        row("ip", ip or "—"),
        row("router", router or "—"),
    ]
    rows.append(row("", "NETWORKS", kind="section"))
    if bar.flags["wifi_scan"]:
        await bar.popup("wifi", "WI-FI", rows + [row("", "Scanning saved networks…")])
        scan = await query(
            ROOT / "helper/WifiScan.app/Contents/MacOS/WifiScan", timeout=35
        )
        saved = (
            await run("networksetup", "-listpreferredwirelessnetworks", interface)
        ).splitlines()[1:]
        saved = {s.strip() for s in saved}
        networks = scan.get("networks", []) if isinstance(scan, dict) else []
        if isinstance(scan, dict) and scan.get("status") == "denied":
            rows.append(
                row("", "Location access required", bar.action("settings", "location"))
            )
        else:
            for n in networks:
                name = n.get("ssid")
                if isinstance(name, str) and name in saved:
                    rows.append(
                        row(
                            "●" if name == ssid else "◒",
                            name,
                            bar.action("wifi", interface, name),
                            icon=str(
                                bar.pixels
                                / ("wifi.png" if name == ssid else "wifi-outline.png")
                            ),
                            right="✓" if name == ssid else "",
                            color=bar.palette["text"]
                            if name == ssid
                            else bar.palette["muted"],
                        )
                    )
                if len(rows) >= 7:
                    break
    else:
        rows.append(row("", "Scanning disabled", color=bar.palette["muted"]))
    rows.append(row("open", "Wi-Fi Settings ↗", bar.action("settings", "wifi")))
    await bar.popup("wifi", "WI-FI", rows)


async def battery_data():
    out = await run("pmset", "-g", "batt")
    match = re.search(r"(\d+)%", out)
    return out, int(match[1]) if match else None


async def battery(bar):
    out, value = await battery_data()
    color = (
        bar.palette["error"]
        if value is not None and value <= 20 and "AC Power" not in out
        else bar.palette["accent"]
    )
    await bar.set("battery", **{"icon.color": bar.palette["muted"]})
    for i in range(1, 6):
        await bar.set(
            f"battery.{i}",
            **{
                "background.color": color
                if value is not None and value >= i * 20 - 10
                else bar.palette["line"]
            },
        )


async def battery_popup(bar):
    out, value = await battery_data()
    remaining = re.search(r"\d+:\d+ remaining", out)
    awake = bar.caffeinate is not None and bar.caffeinate.returncode is None
    await bar.popup(
        "battery",
        "BATTERY",
        [
            row("charge", f"{value}%" if value is not None else "—"),
            row("power", "AC power" if "AC Power" in out else "battery"),
            row("left", remaining[0] if remaining else "calculating / full"),
            row(
                "awake",
                "Stop keeping awake" if awake else "Keep awake while running",
                bar.action("awake"),
                True,
            ),
            row("open", "Battery Settings ↗", bar.action("settings", "battery")),
        ],
    )


async def system(bar):
    # Sampling stays at 15 seconds; the owned visual task animates cached values.
    cpu, cores, pressure = await asyncio.gather(
        run("ps", "-A", "-o", "%cpu="),
        run("sysctl", "-n", "hw.ncpu"),
        run("memory_pressure"),
    )
    use = sum(number(v, high=100000) for v in cpu.split()) / max(
        1, number(cores, high=1024)
    )
    free = re.search(r"free percentage:\s*(\d+)", pressure)
    bar.system_data = (int(use), 100 - int(free[1]) if free else None)
    if bar.open_popup == "system":
        await system_popup(bar)


async def system_popup(bar):
    cpu, mem = getattr(bar, "system_data", (0, None))
    disk = await run("diskutil", "info", "/")
    total = re.search(r"Container Total Space:.*?\((\d+) Bytes\)", disk)
    free = re.search(r"Container Free Space:.*?\((\d+) Bytes\)", disk)
    storage = (
        f"{(int(total[1]) - int(free[1])) / 1e9:.0f} / {int(total[1]) / 1e9:.0f} GB"
        if total and free
        else "—"
    )
    await bar.popup(
        "system",
        "SYSTEM",
        [
            row("cpu", f"{cpu}%"),
            row("memory", f"{mem}%" if mem is not None else "—"),
            row("ssd", storage),
            row(
                "open", "Activity Monitor ↗", bar.action("open_app", "Activity Monitor")
            ),
        ],
    )


def project_relative_path(path, root):
    """Match real directory identities, including case-insensitive macOS paths."""
    parts = []
    for ancestor in (path, *path.parents):
        try:
            if ancestor.samefile(root):
                return Path(*reversed(parts))
        except OSError:
            pass
        parts.append(ancestor.name)
    return None


async def ports_popup(bar):
    out = await run(
        "lsof",
        "-nP",
        "-iTCP",
        "-sTCP:LISTEN",
        "-Fpcn",
        timeout=5,
        allow_failure=True,
    )
    entries, pid, proc = [], "", ""
    for line in out.splitlines():
        if line.startswith("p"):
            pid = line[1:]
        elif line.startswith("c"):
            proc = line[1:]
        elif line.startswith("n"):
            port = line.rsplit(":", 1)[-1]
            if pid.isdecimal() and port.isdecimal() and 0 < int(port) <= 65535:
                entries.append((pid, proc, int(port)))
    pids = sorted({p for p, _, _ in entries})
    cwd = (
        await run(
            "lsof",
            "-a",
            "-d",
            "cwd",
            "-p",
            ",".join(pids),
            "-Fpn",
            allow_failure=True,
        )
        if pids
        else ""
    )
    dirs, pid = {}, ""
    for line in cwd.splitlines():
        if line.startswith("p"):
            pid = line[1:]
        elif line.startswith("n"):
            dirs[pid] = Path(line[1:]).resolve()
    root = Path(bar.cfg["work_dir"]).expanduser().resolve()
    rows, seen = [], set()
    for pid, proc, port in sorted(entries, key=lambda e: e[2]):
        path = dirs.get(pid)
        relative = project_relative_path(path, root) if path is not None else None
        if (
            relative is None
            or port in seen
            or proc.lower().startswith(("docker", "orbstack", "ollama"))
        ):
            continue
        seen.add(port)
        rows.append(
            row(":" + str(port), str(relative) + " · " + proc, bar.action("port", port))
        )
    await bar.popup(
        "ports", "PORTS", rows or [row("", "No listeners under " + str(root))]
    )


def tailscale_path():
    return shutil.which("tailscale") or next(
        (
            str(p)
            for p in [Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale")]
            if p.is_file()
        ),
        None,
    )


async def tailscale(bar):
    cli = tailscale_path()
    d = await query(cli, "status", "--json", timeout=5) if cli else None
    bar.tailscale_data = d if isinstance(d, dict) else {}
    await bar.set(
        "tailscale",
        drawing="on" if cli else "off",
        **{
            "icon.background.image": str(
                bar.pixels
                / (
                    "ts_on.png"
                    if bar.tailscale_data.get("BackendState") == "Running"
                    else "ts_off.png"
                )
            )
        },
    )


async def tailscale_popup(bar):
    await tailscale(bar)
    d = bar.tailscale_data
    peers = [d.get("Self") or {}] + list((d.get("Peer") or {}).values())
    tailnet = d.get("CurrentTailnet") or {}
    rows = [
        row(
            "status",
            "connected" if d.get("BackendState") == "Running" else "offline",
            right=tailnet.get("Name", ""),
            right_color=bar.palette["dim"],
        )
    ]
    for peer in peers[:16]:
        name = peer.get("HostName") or peer.get("DNSName") or "device"
        ips = peer.get("TailscaleIPs") or []
        try:
            ip = str(ipaddress.ip_address(ips[0]))
        except (ValueError, IndexError):
            continue
        action = bar.action("copy_ip", ip)
        dns = peer.get("DNSName", "").rstrip(".")
        if peer.get("OS") == "macOS" and re.fullmatch(r"[a-zA-Z0-9.-]{1,253}", dns):
            action = bar.action("vnc", dns)
            name += " ↗"
        online = peer.get("Online")
        rows.append(
            row(
                "●" if online else "○",
                name,
                action,
                right=ip if online else "offline",
                bold=peer == d.get("Self"),
                left_color=bar.palette["accent"] if online else bar.palette["dim"],
                color=bar.palette["text"] if online else bar.palette["muted"],
            )
        )
    rows.append(
        row(
            "open", "admin ↗", bar.action("tailscale_admin"), color=bar.palette["muted"]
        )
    )
    await bar.popup("tailscale", "TAILSCALE", rows)


def local_usage():
    """Read usage fields only; never auth.json, credentials or keychains."""
    home = Path.home()
    out = {}

    def load(path):
        if path.stat().st_size > 2 * 1024 * 1024:
            return {}
        return json.loads(path.read_text())

    def live(stamp):
        try:
            return (
                datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
                > time.time()
            )
        except (ValueError, TypeError, AttributeError):
            return False

    try:
        data = (
            load(home / ".claude.json")
            .get("cachedUsageUtilization", {})
            .get("utilization", {})
        )
        out["Claude"] = [
            (
                key,
                int(number(data[key].get("utilization"))),
                data[key].get("resets_at", ""),
            )
            for key in ("five_hour", "seven_day")
            if isinstance(data.get(key), dict) and live(data[key].get("resets_at"))
        ]
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    try:
        files = [
            p
            for sub in ("sessions", "archived_sessions")
            for p in (home / ".codex" / sub).glob("**/rollout-*.jsonl")
        ]
        candidates = set(
            sorted(files, key=lambda p: p.name, reverse=True)[:10]
            + sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:10]
        )
        best, limits = "", {}
        for path in candidates:
            with path.open("rb") as file:
                file.seek(max(0, path.stat().st_size - 200000))
                for line in file.read(200000).splitlines():
                    if b'"rate_limits"' not in line:
                        continue
                    try:
                        data = json.loads(line)
                        value = (data.get("payload") or {}).get("rate_limits")
                        stamp = data.get("timestamp", "")
                        if isinstance(value, dict) and stamp > best:
                            best, limits = stamp, value
                    except (ValueError, AttributeError, TypeError):
                        pass
        rows = []
        for key in ("primary", "secondary"):
            d = limits.get(key) or {}
            reset = number(d.get("resets_at"), high=1e12)
            if reset > time.time() and isinstance(d.get("used_percent"), (float, int)):
                rows.append(
                    (
                        key,
                        int(number(d["used_percent"])),
                        datetime.fromtimestamp(reset).isoformat(),
                    )
                )
        if rows:
            out["Codex"] = rows
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        pass
    return out


async def usage(bar):
    bar.usage_data = await asyncio.to_thread(local_usage)
    visible = 0
    for name in ("Claude", "Codex"):
        values = bar.usage_data.get(name) or []
        home = Path.home()
        available = (
            bool(values)
            or (home / (".claude" if name == "Claude" else ".codex")).is_dir()
        )
        visible += int(available)
        percent = values[0][1] if values else None
        color = (
            bar.palette["error"]
            if percent is not None and percent >= 95
            else bar.palette["warn"]
            if percent is not None and percent >= 80
            else bar.palette["text"]
        )
        await bar.set(
            "usage." + name.lower(),
            drawing="on" if available else "off",
            label=f"{percent}%" if percent is not None else "—",
            **{"label.color": color},
        )
    await bar.set("usage", drawing="on" if visible else "off")
    await bar.set("main.gap.usage", drawing="on" if visible else "off")
    await bar.set("usage.gap", drawing="on" if visible == 2 else "off")
    if bar.open_popup == "usage":
        await usage_popup(bar)


async def usage_popup(bar):
    rows = []
    usage_data = getattr(bar, "usage_data", {})
    for name, icon, tint in (
        ("Claude", "claude.png", "0xffd97757"),
        ("Codex", "openai.png", bar.palette["text"]),
    ):
        values = usage_data.get(name) or []
        if (
            not values
            and not (
                Path.home() / (".claude" if name == "Claude" else ".codex")
            ).is_dir()
        ):
            continue
        rows.append(row("", name.lower(), icon=str(bar.pixels / icon)))
        windows = {
            "5h" if k in ("five_hour", "primary") else "week": (pct, reset)
            for k, pct, reset in values
        }
        for key in ("5h", "week"):
            pct, reset = windows.get(key, (None, ""))
            try:
                stamp = datetime.fromisoformat(
                    reset.replace("Z", "+00:00")
                ).astimezone()
                reset_text = stamp.strftime(
                    "%H:%M reset" if key == "5h" else "%m.%d reset"
                )
            except (ValueError, AttributeError):
                reset_text = "—"
            rows.append(
                row(key, f"{pct}%" if pct is not None else "—", right=reset_text)
            )
            rows.append(
                row("", "", kind="gauge", percent=pct or 0, height=16, color=tint)
            )
    if not any(usage_data.values()):
        rows.append(row("", "No current cached usage", color=bar.palette["muted"]))
    await bar.popup("usage", "USAGE", rows)


async def notifications(bar):
    total = 0
    for app in bar.cfg["notification_apps"]:
        out = await run("lsappinfo", "info", "-only", "StatusLabel", app)
        value = re.search(r'"label"="(\d+)"', out)
        total += int(value[1]) if value else 0
    await bar.set("notifications", label=str(total), drawing="on" if total else "off")
    await bar.set("main.gap.notifications", drawing="on" if total else "off")


async def appmenu_popup(bar):
    front = await query(ROOT / "helper/axmenu", "front")
    if not isinstance(front, dict) or type(front.get("pid")) is not int:
        await bar.popup("front_app", "APP", [row("", "Accessibility access required")])
        return
    pid = front["pid"]
    menus = await query(ROOT / "helper/axmenu", "menus", pid, timeout=5)
    rows = [row("", "Settings…", bar.action("app_settings", pid))]
    for menu in menus if isinstance(menus, list) else []:
        if type(menu.get("menu")) is int and menu["menu"] >= 0:
            rows.append(
                row(
                    "›",
                    menu.get("title", ""),
                    bar.action("app_menu", pid, menu["menu"]),
                    True,
                )
            )
    if len(rows) == 1:
        rows.append(row("", "Allow Accessibility to read app menus"))
    await bar.popup("front_app", front.get("name", "APP"), rows)


async def submenu(bar, pid, index):
    menus = await query(ROOT / "helper/axmenu", "menus", pid, timeout=5)
    menu = (
        next((m for m in menus if m.get("menu") == index), {})
        if isinstance(menus, list)
        else {}
    )
    rows = [row("‹", "Back", bar.action("app_back"), True)]
    for item in menu.get("items", []):
        if type(item.get("index")) is int and item["index"] >= 0:
            rows.append(
                row(
                    item.get("shortcut", ""),
                    item.get("title", ""),
                    bar.action("app_press", pid, index, item["index"])
                    if item.get("enabled")
                    else None,
                )
            )
    await bar.popup("front_app", menu.get("title", "MENU"), rows)


async def settings_popup(bar):
    await bar.popup(
        "settings",
        "SETTINGS",
        [
            row("edit", "Open config.json", bar.action("edit")),
            row("reload", "Validate configuration and reload", bar.action("reload")),
            row(
                "open", "Activity Monitor ↗", bar.action("open_app", "Activity Monitor")
            ),
        ],
    )


async def notifications_popup(bar):
    await bar.popup(
        "notifications",
        "DOCK BADGES",
        [row("", ", ".join(bar.cfg["notification_apps"]))],
    )


async def folder_popup(bar):
    await bar.popup(
        "folder", "FOLDER", [row("", "Updated by the optional shell_cwd hook")]
    )


async def dispatch(bar, name, *args):
    """Closed set of actions; arguments originate from validated query objects."""
    if name == "workspace":
        await bar.wm.focus(args[0])
        bar.notify("workspaces")
    elif name in ("media.prev", "media.play", "media.next"):
        if not bar.media_state:
            return
        subcommand = {
            "media.prev": "previous-track",
            "media.play": "toggle-play-pause",
            "media.next": "next-track",
        }[name]
        # Recheck the active source before any control; never control Apple Music.
        data = await query("media-control", "get")
        if isinstance(data, dict) and data.get("bundleIdentifier") != "com.apple.Music":
            await run("media-control", subcommand)
            bar.notify("media")
    elif name == "month":
        bar.calendar_offset = (
            0 if args[0] == 0 else max(-120, min(120, bar.calendar_offset + args[0]))
        )
        await calendar_popup(bar)
    elif name == "open_app" and args[0] in ("Calendar", "Activity Monitor"):
        await run("open", "-a", args[0])
    elif name == "settings":
        urls = {
            "wifi": "com.apple.wifi-settings-extension",
            "sound": "com.apple.Sound-Settings.extension",
            "battery": "com.apple.Battery-Settings.extension",
            "location": "com.apple.preference.security?Privacy_LocationServices",
        }
        if args[0] in urls:
            await run("open", "x-apple.systempreferences:" + urls[args[0]])
    elif name == "mute":
        await run(
            "osascript",
            "-e",
            "set volume output muted (not output muted of (get volume settings))",
        )
        bar.notify("volume")
    elif name == "volume" and args[0] in (-10, 10):
        value = int(
            number(
                await run("osascript", "-e", "output volume of (get volume settings)")
            )
        )
        await run(
            "osascript",
            "-e",
            "set volume output volume " + str(max(0, min(100, value + args[0]))),
        )
        bar.notify("volume")
    elif name == "audio" and args[0] in ("set", "connect"):
        valid = (args[0] == "set" and re.fullmatch(r"[1-9][0-9]{0,9}", args[1])) or (
            args[0] == "connect"
            and re.fullmatch(r"[0-9A-Fa-f]{2}(?:[-:][0-9A-Fa-f]{2}){5}", args[1])
        )
        if valid:
            await run(ROOT / "helper/audio", args[0], args[1], timeout=12)
            bar.notify("volume")
            if bar.open_popup == "volume":
                await volume_popup(bar)
    elif name == "wifi" and re.fullmatch(r"[A-Za-z0-9]+", args[0]):
        await run("networksetup", "-setairportnetwork", args[0], args[1], timeout=20)
        bar.notify("wifi")
    elif name == "awake":
        if bar.caffeinate is not None and bar.caffeinate.returncode is None:
            await stop(bar.caffeinate)
            bar.caffeinate = None
        else:
            bar.caffeinate = await asyncio.create_subprocess_exec(
                "caffeinate", "-di", "-w", str(os.getpid())
            )
        await battery_popup(bar)
    elif name == "port" and type(args[0]) is int and 0 < args[0] <= 65535:
        await run("open", "http://localhost:" + str(args[0]))
    elif name == "copy_ip":
        ip = str(ipaddress.ip_address(args[0]))
        proc = await asyncio.create_subprocess_exec(
            "pbcopy", stdin=asyncio.subprocess.PIPE
        )
        try:
            await asyncio.wait_for(proc.communicate(ip.encode()), 2)
        finally:
            await stop(proc)
    elif name == "vnc" and re.fullmatch(r"[A-Za-z0-9.-]{1,253}", args[0]):
        await run("open", "vnc://" + args[0])
    elif name == "tailscale_admin":
        await run("open", "https://login.tailscale.com/admin")
    elif name == "app_menu":
        await submenu(bar, *args)
    elif name == "app_back":
        await appmenu_popup(bar)
    elif name in ("app_settings", "app_press"):
        front = await query(ROOT / "helper/axmenu", "front")
        if (
            isinstance(front, dict)
            and front.get("pid") == args[0]
            and all(type(a) is int and a >= 0 for a in args)
        ):
            await run(
                ROOT / "helper/axmenu",
                "settings" if name == "app_settings" else "press",
                *args,
            )
    elif name == "edit":
        await run("open", "-t", ROOT / "config.json")
    elif name == "reload":
        from runtime import config

        try:
            config()
        except ValueError:
            await bar.popup(
                "settings",
                "CONFIG ERROR",
                [row("", "Fix config.json before reloading")],
            )
            return
        await bar.sb("--reload")


UPDATES = {
    "workspaces": workspaces,
    "clock": clock,
    "media": media,
    "volume": volume,
    "wifi": wifi,
    "battery": battery,
    "system": system,
    "tailscale": tailscale,
    "usage": usage,
    "notifications": notifications,
    "next_event": next_event,
}
POPUPS = {
    "workspaces": workspaces,
    "clock": calendar_popup,
    "media": media_popup,
    "volume": volume_popup,
    "wifi": wifi_popup,
    "battery": battery_popup,
    "system": system_popup,
    "ports": ports_popup,
    "tailscale": tailscale_popup,
    "usage": usage_popup,
    "front_app": appmenu_popup,
    "settings": settings_popup,
    "next_event": next_popup,
    "notifications": notifications_popup,
    "folder": folder_popup,
}
