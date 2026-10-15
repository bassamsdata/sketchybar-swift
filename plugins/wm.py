"""Read-only WM discovery/queries, event streams, and explicit focus actions."""

import asyncio
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from runtime import query, run, stop


@dataclass
class Workspace:
    key: str
    name: str
    apps: list = field(default_factory=list)
    count: int = 0


@dataclass
class Snapshot:
    backend: str = ""
    current: str = ""
    maximized: bool = False
    workspaces: list = field(default_factory=list)
    current_name: str = ""
    status: str = ""
    detail: str = ""


def payload(reply, key):
    if not isinstance(reply, dict) or reply.get("ok") is not True:
        return None
    data = reply.get("result", {}).get("payload", {})
    return data.get(key) if isinstance(data, dict) else None


def aero_snapshot(current, windows, focused):
    if not isinstance(current, list) or not current:
        return None
    key = current[0].get("workspace")
    if not isinstance(key, str):
        return None
    groups = {}
    for w in windows if isinstance(windows, list) else []:
        name, app = w.get("workspace"), w.get("app-name")
        if not isinstance(name, str):
            continue
        group = groups.setdefault(name, Workspace(name, name))
        group.count += 1
        if isinstance(app, str) and app not in group.apps:
            group.apps.append(app)
    full = (
        any(
            w.get("workspace") == key and w.get("window-is-fullscreen") is True
            for w in focused
            if isinstance(w, dict)
        )
        if isinstance(focused, list)
        else False
    )
    return Snapshot(
        "aerospace",
        key,
        full,
        sorted(
            groups.values(),
            key=lambda w: (
                not w.name.isdecimal(),
                int(w.name) if w.name.isdecimal() else w.name,
            ),
        ),
    )


def omni_snapshot(workspaces, windows):
    if not isinstance(workspaces, list) or not isinstance(windows, list):
        return None
    current = next((w for w in workspaces if w.get("isCurrent")), None)
    if current is None:
        current = next((w for w in workspaces if w.get("isFocused")), None)
    if current is None or not isinstance(current.get("id"), str):
        return None
    groups, full = {}, False
    for w in windows:
        ref = w.get("workspace") or {}
        key = ref.get("id")
        if not isinstance(key, str) or w.get("isScratchpad"):
            continue
        group = groups.setdefault(
            key, Workspace(key, ref.get("displayName") or ref.get("rawName") or key)
        )
        group.count += 1
        app = (w.get("app") or {}).get("name")
        if isinstance(app, str) and app not in group.apps:
            group.apps.append(app)
        if key == current["id"] and w.get("isFullscreen") is True:
            full = True
    # The configured workspace list supplies stable display names and order.
    occupied = []
    for w in workspaces:
        if w.get("id") in groups:
            group = groups[w["id"]]
            group.name = w.get("displayName") or w.get("rawName") or group.key
            occupied.append(group)
    return Snapshot(
        "omniwm",
        current["id"],
        full,
        occupied,
        current.get("displayName") or current.get("rawName") or current["id"],
    )


class Manager:
    def __init__(self, preference="auto"):
        self.preference = preference
        self.backend = ""
        self.aero = shutil.which("aerospace")
        p = Path("/Applications/OmniWM.app/Contents/MacOS/omniwmctl")
        self.omni = str(p) if p.is_file() else shutil.which("omniwmctl")
        self.snapshot = Snapshot()
        self.watcher = None

    async def read(self, inventory=False):
        if self.preference == "off":
            return Snapshot()
        unavailable = Snapshot()
        order = ([self.backend] if self.backend else []) + (
            ["aerospace", "omniwm"] if self.preference == "auto" else [self.preference]
        )
        for backend in dict.fromkeys(order):
            if backend == "aerospace" and self.aero:
                current = await query(
                    self.aero, "list-workspaces", "--focused", "--json"
                )
                if not current:
                    continue
                # Occupancy is queried only on expand, never every focus event.
                windows = (
                    (
                        await query(
                            self.aero,
                            "list-windows",
                            "--all",
                            "--format",
                            "%{workspace} %{app-name}",
                            "--json",
                        )
                    )
                    if inventory
                    else []
                )
                focused = await query(
                    self.aero,
                    "list-windows",
                    "--focused",
                    "--format",
                    "%{workspace} %{window-is-fullscreen}",
                    "--json",
                )
                snapshot = aero_snapshot(current, windows, focused)
            elif backend == "omniwm" and self.omni:
                fields = "id,raw-name,display-name,is-current,is-focused"
                reply = await query(
                    self.omni,
                    "query",
                    "workspaces",
                    "--fields",
                    fields,
                    "--format",
                    "json",
                    allow_failure=True,
                )
                workspaces = payload(reply, "workspaces")
                if workspaces is None:
                    code = (
                        reply.get("code") if isinstance(reply, dict) else "unavailable"
                    )
                    if code == "protocol_mismatch":
                        unavailable = Snapshot(
                            status="omni version",
                            detail="OmniWM and its CLI must use matching protocol versions.",
                        )
                    elif code == "unauthorized":
                        unavailable = Snapshot(
                            status="omni auth",
                            detail="OmniWM rejected local CLI authorization.",
                        )
                    else:
                        unavailable = Snapshot(
                            status="omni IPC",
                            detail="Start OmniWM and enable IPC in its status menu.",
                        )
                    continue
                windows = payload(
                    await query(
                        self.omni,
                        "query",
                        "windows",
                        *([] if inventory else ["--focused"]),
                        "--fields",
                        "workspace,app,is-fullscreen,is-scratchpad",
                        "--format",
                        "json",
                        allow_failure=True,
                    ),
                    "windows",
                )
                snapshot = omni_snapshot(workspaces, windows)
            else:
                continue
            if snapshot is not None:
                self.backend, self.snapshot = backend, snapshot
                return snapshot
        self.backend, self.snapshot = "", unavailable
        return self.snapshot

    def stream_args(self):
        if self.backend == "aerospace":
            return [
                self.aero,
                "subscribe",
                "focus-changed",
                "focused-workspace-changed",
                "focused-monitor-changed",
                "window-detected",
                "binding-triggered",
            ]
        if self.backend == "omniwm":
            return [
                self.omni,
                "subscribe",
                "active-workspace,focus,windows-changed,layout-changed",
                "--reconnect",
                "--format",
                "ndjson",
            ]
        return []

    async def watch(self, notify):
        args = self.stream_args()
        if not args:
            return
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                limit=2 * 1024 * 1024,
            )
            while await proc.stdout.readline():
                notify("workspaces")
        except (OSError, ValueError):
            pass
        finally:
            if proc is not None:
                await stop(proc)
            self.backend = ""

    async def focus(self, key):
        if not isinstance(key, str) or not key or len(key) > 256:
            return
        if self.backend == "aerospace":
            await run(self.aero, "workspace", "--", key)
        elif self.backend == "omniwm" and not key.startswith("--"):
            await run(self.omni, "workspace", "focus-name", key)
