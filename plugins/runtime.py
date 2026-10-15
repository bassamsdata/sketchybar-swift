"""Private IPC, bounded child processes and typed configuration. No shell eval."""

import asyncio
import contextlib
import hashlib
import json
import math
import os
import re
import shlex
import socket
import stat
import struct
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURES = {
    "workspaces",
    "front_app",
    "folder",
    "next_event",
    "media",
    "volume",
    "calendar",
    "wifi",
    "wifi_scan",
    "battery",
    "usage",
    "system",
    "ports",
    "tailscale",
    "notifications",
}
LIMIT = 2 * 1024 * 1024


def image_size(data):
    """Read dimensions without decoding pixels; reject unsupported image formats."""
    if (
        data.startswith(b"\x89PNG\r\n\x1a\n")
        and len(data) >= 24
        and data[12:16] == b"IHDR"
    ):
        width, height = struct.unpack(">II", data[16:24])
        return (width, height) if min(width, height) > 0 else None
    if data.startswith(b"\xff\xd8\xff"):
        pos = 2
        while pos + 4 <= len(data):
            if data[pos] != 255:
                return None
            marker = data[pos + 1]
            pos += 2
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                continue
            size = int.from_bytes(data[pos : pos + 2], "big")
            if size < 2 or pos + size > len(data):
                return None
            if marker in (0xC0, 0xC1, 0xC2) and size >= 7:
                height, width = struct.unpack(">HH", data[pos + 3 : pos + 7])
                return (width, height) if min(width, height) > 0 else None
            pos += size
    return None


def text(value, limit=80):
    """Control characters stay display data, never rows, options or commands."""
    value = "".join(
        " " if unicodedata.category(c).startswith("C") else c for c in str(value or "")
    )
    return value if len(value) <= limit else value[: limit - 1] + "…"


def number(value, fallback=0, low=0, high=100):
    try:
        v = float(value)
        return max(low, min(high, v)) if math.isfinite(v) else fallback
    except (TypeError, ValueError, OverflowError):
        return fallback


def config(root=ROOT):
    cfg = json.loads((root / "config.json").read_text())
    allowed = {
        "animations",
        "theme",
        "display",
        "wordmark",
        "height",
        "opacity",
        "popup_blur",
        "window_manager",
        "work_dir",
        "calendar_names",
        "holiday_calendar",
        "notification_apps",
        "features",
    }
    if isinstance(cfg, dict):
        cfg.setdefault("animations", True)
        defaults = {
            "wordmark_animation": False,
            "wm_number_bold": True,
            "cat_grass_color": "auto",
            "containers": {},
            "width": 0,
            "margin": 5,
            "corner_radius": 13,
            "circle_radius": 16,
            "popup_corner_radius": 0,
            "popup_width": 0,
            "font": "JetBrains Mono",
            "font_size": 12,
        }
        for key, value in defaults.items():
            cfg.setdefault(key, value)
        allowed.update(defaults)
    if not isinstance(cfg, dict) or set(cfg) != allowed:
        raise ValueError("config.json has missing or unknown settings")
    for key in ("animations", "wordmark_animation", "wm_number_bold"):
        if type(cfg[key]) is not bool:
            raise ValueError(key + " must be a boolean")
    grass = cfg["cat_grass_color"]
    if not isinstance(grass, str) or (
        grass != "auto" and not re.fullmatch(r"#[0-9a-fA-F]{6}", grass)
    ):
        raise ValueError("cat_grass_color must be auto or #RRGGBB")
    overrides = cfg["containers"]
    names = ("left", "right", "media", "apps", "cat", "settings")
    if not isinstance(overrides, dict) or set(overrides) - set(names):
        raise ValueError("invalid containers")
    containers = {}
    for name in names:
        values = {
            "padding": 0 if name in ("cat", "settings") else 12,
            "item_gap": 14 if name == "right" else 12,
            "gap": 0 if name == "right" else 8,
            "height": 0,
            "corner_radius": -1,
            "border_width": 1,
        }
        if name in ("cat", "settings"):
            values.pop("padding")
            values.pop("item_gap")
        custom = overrides.get(name, {})
        if not isinstance(custom, dict) or set(custom) - set(values):
            raise ValueError("invalid container " + name)
        values.update(custom)
        for key, lo, hi in (
            ("padding", 0, 40),
            ("item_gap", 0, 60),
            ("gap", 0, 60),
            ("height", 0, cfg["height"] if type(cfg["height"]) is int else 60),
            ("corner_radius", -1, 60),
            ("border_width", 0, 4),
        ):
            if key not in values:
                continue
            if type(values[key]) is not int or not lo <= values[key] <= hi:
                raise ValueError("invalid containers." + name + "." + key)
        if 0 < values["height"] < 16:
            raise ValueError("container height must be 0 or >=16")
        containers[name] = values
    cfg["containers"] = containers
    for key, lo, hi in (
        ("width", 0, 16384),
        ("margin", 0, 500),
        ("corner_radius", 0, 60),
        ("circle_radius", 0, 60),
        ("popup_corner_radius", 0, 60),
        ("popup_width", 0, 1200),
        ("font_size", 9, 20),
    ):
        if type(cfg[key]) is not int or not lo <= cfg[key] <= hi:
            raise ValueError("invalid " + key)
    if 0 < cfg["width"] < 600 or 0 < cfg["popup_width"] < 180:
        raise ValueError("width must be 0 or >=600; popup_width must be 0 or >=180")
    if (
        not isinstance(cfg["font"], str)
        or not 1 <= len(cfg["font"]) <= 80
        or any(c in cfg["font"] for c in ":\n\r\x00")
    ):
        raise ValueError("invalid font family")
    if cfg["theme"] not in ("dark", "light", "auto"):
        raise ValueError("theme must be dark, light or auto")
    if cfg["window_manager"] not in ("auto", "aerospace", "omniwm", "off"):
        raise ValueError("invalid window_manager")
    if cfg["display"] != "main" and (
        type(cfg["display"]) is not int or cfg["display"] < 1
    ):
        raise ValueError("display must be main or a positive display number")
    for key, lo, hi in (("height", 24, 60), ("opacity", 0, 100), ("popup_blur", 0, 40)):
        if type(cfg[key]) is not int or not lo <= cfg[key] <= hi:
            raise ValueError("invalid " + key)
    for key in ("wordmark", "work_dir", "holiday_calendar"):
        if not isinstance(cfg[key], str) or len(cfg[key]) > 1024:
            raise ValueError("invalid " + key)
    for key in ("calendar_names", "notification_apps"):
        if (
            not isinstance(cfg[key], list)
            or len(cfg[key]) > 32
            or any(not isinstance(s, str) or len(s) > 256 for s in cfg[key])
        ):
            raise ValueError("invalid " + key)
    flags = cfg["features"]
    if (
        not isinstance(flags, dict)
        or set(flags) != FEATURES
        or any(type(v) is not bool for v in flags.values())
    ):
        raise ValueError("features must contain the documented boolean flags")
    return cfg


def private_dir(path):
    """Refuse symlinks and foreign ownership before changing any permissions."""
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    s = path.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid():
        raise ValueError("runtime directory must be an owned real directory")
    path.chmod(0o700)
    return path


def cache_path(root=ROOT):
    # Distinct instances/config copies never terminate or signal one another.
    suffix = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:10]
    return private_dir(Path.home() / ".cache" / ("sb-island-" + suffix))


def command(event, root=ROOT):
    # Only internal event names or random action handles can enter shell scripts.
    return shlex.join([sys.executable, str(root / "plugins/bar.py"), "send", event])


def private_file(path, truncate=False):
    flags = os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode):
            raise ValueError("runtime file must be an owned regular file")
        os.fchmod(fd, 0o600)
        if truncate:
            os.ftruncate(fd, 0)
        return fd
    except BaseException:
        os.close(fd)
        raise


def send(message, root=ROOT):
    path = cache_path(root) / "events.sock"
    data = json.dumps(message).encode()
    if len(data) > 8192:
        return False
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        try:
            sock.sendto(data, str(path))
            return True
        except OSError:
            return False


async def stop(proc):
    """Terminate only a live child represented by our process handle."""
    if proc.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), 1)
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()


async def run(
    *args, timeout=3, limit=LIMIT, env=None, input_data=None, allow_failure=False
):
    """Run an argv vector with time and output limits, always reaping children."""
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *(str(a) for a in args),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
            stdin=asyncio.subprocess.PIPE if input_data is not None else None,
        )

        if input_data is not None:
            if len(input_data) > LIMIT:
                raise ValueError("child input limit exceeded")
            proc.stdin.write(input_data)
            await asyncio.wait_for(proc.stdin.drain(), timeout)
            proc.stdin.close()

        async def read():
            chunks, size = [], 0
            while True:
                chunk = await proc.stdout.read(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise ValueError("child output limit exceeded")
                chunks.append(chunk)
            await proc.wait()
            if proc.returncode and not allow_failure:
                return ""
            return b"".join(chunks).decode("utf-8", "replace")

        return await asyncio.wait_for(read(), timeout)
    except (OSError, asyncio.TimeoutError, ValueError):
        return ""
    finally:
        if proc is not None:
            await stop(proc)


async def query(*args, **kwargs):
    # SketchyBar can briefly return an empty reply while processing a batch.
    # Retry geometry reads before falling back to an unmeasured layout.
    attempts = 3 if args and args[0] == "sketchybar" else 1
    for attempt in range(attempts):
        try:
            return json.loads(await run(*args, **kwargs))
        except (ValueError, TypeError):
            if attempt + 1 < attempts:
                await asyncio.sleep(0.05)
    return None
