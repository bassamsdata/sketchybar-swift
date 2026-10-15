import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))
import wm


class WorkspacesTests(unittest.TestCase):
    def test_aerospace_only_occupied_workspaces_and_maximized(self):
        snapshot = wm.aero_snapshot(
            [{"workspace": "10"}],
            [
                {"workspace": "10", "app-name": "Browser"},
                {"workspace": "2", "app-name": "Terminal"},
                {"workspace": "2", "app-name": "Terminal"},
                {"workspace": "work'; $(touch x)", "app-name": "Editor"},
            ],
            [{"workspace": "10", "window-is-fullscreen": True}],
        )
        self.assertTrue(snapshot.maximized)
        self.assertEqual(snapshot.current, "10")
        self.assertEqual(
            [w.key for w in snapshot.workspaces], ["2", "10", "work'; $(touch x)"]
        )
        self.assertEqual(snapshot.workspaces[0].apps, ["Terminal"])
        self.assertEqual(snapshot.workspaces[0].count, 2)

    def test_empty_current_workspace_remains_visible_but_not_in_popup(self):
        snapshot = wm.aero_snapshot([{"workspace": "empty"}], [], [])
        self.assertEqual(snapshot.current, "empty")
        self.assertFalse(snapshot.maximized)
        self.assertEqual(snapshot.workspaces, [])

    def test_omni_current_workspace_names_occupancy_and_fullscreen(self):
        spaces = [
            {"id": "1", "rawName": "1", "displayName": "Code", "isCurrent": True},
            {"id": "2", "rawName": "2", "isCurrent": False},
            {"id": "3", "rawName": "3", "isCurrent": False},
        ]
        windows = [
            {"workspace": {"id": "1"}, "app": {"name": "Editor"}, "isFullscreen": True},
            {"workspace": {"id": "3"}, "app": {"name": "Terminal"}},
            {"workspace": {"id": "2"}, "isScratchpad": True},
        ]
        snapshot = wm.omni_snapshot(spaces, windows)
        self.assertEqual(snapshot.current_name, "Code")
        self.assertEqual([w.key for w in snapshot.workspaces], ["1", "3"])
        self.assertTrue(snapshot.maximized)

    def test_omni_envelope_matches_official_payload_schema(self):
        reply = {
            "ok": True,
            "result": {"kind": "workspaces", "payload": {"workspaces": [{"id": "1"}]}},
        }
        self.assertEqual(wm.payload(reply, "workspaces"), [{"id": "1"}])
        self.assertIsNone(wm.payload({"ok": False}, "workspaces"))


class ManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_auto_detection_falls_back_to_running_omni(self):
        manager = wm.Manager("auto")
        manager.aero, manager.omni = "aero-test", "omni-test"

        async def reply(*args, **kwargs):
            if args[0] == "aero-test":
                return None
            key = args[2]
            value = (
                [{"id": "1", "rawName": "1", "isCurrent": True}]
                if key == "workspaces"
                else []
            )
            return {"ok": True, "result": {"payload": {key: value}}}

        with patch("wm.query", side_effect=reply):
            snapshot = await manager.read()
        self.assertEqual(snapshot.backend, "omniwm")

    async def test_collapsed_aerospace_never_queries_window_inventory(self):
        manager = wm.Manager("aerospace")
        manager.aero = "aero-test"
        with patch(
            "wm.query",
            new_callable=AsyncMock,
            side_effect=[
                [{"workspace": "1"}],
                [{"workspace": "1", "window-is-fullscreen": False}],
            ],
        ) as query:
            await manager.read(inventory=False)
        self.assertFalse(any("--all" in c.args for c in query.call_args_list))

    async def test_focus_passes_workspace_as_literal_argument(self):
        manager = wm.Manager("aerospace")
        manager.backend, manager.aero = "aerospace", "aero-test"
        with patch("wm.run", new_callable=AsyncMock) as execute:
            await manager.focus("work'; $(touch marker)")
            self.assertEqual(
                execute.call_args.args,
                ("aero-test", "workspace", "--", "work'; $(touch marker)"),
            )

    async def test_no_manager_hides_status_without_native_spaces_fallback(self):
        manager = wm.Manager("auto")
        manager.aero = manager.omni = None
        snapshot = await manager.read(inventory=True)
        self.assertEqual(snapshot.backend, "")
        self.assertEqual(snapshot.workspaces, [])

    async def test_omni_connection_error_reports_ipc_not_wm_off(self):
        manager = wm.Manager("omniwm")
        manager.omni = "omni-test"
        with patch(
            "wm.query",
            new_callable=AsyncMock,
            return_value={"ok": False, "code": "transport_failure"},
        ) as execute:
            snapshot = await manager.read()
        self.assertEqual(snapshot.status, "omni IPC")
        self.assertIn("enable IPC", snapshot.detail)
        self.assertTrue(execute.call_args.kwargs["allow_failure"])
        self.assertIn("--format", execute.call_args.args)

    async def test_omni_version_mismatch_has_a_distinct_status(self):
        manager = wm.Manager("omniwm")
        manager.omni = "omni-test"
        with patch(
            "wm.query",
            new_callable=AsyncMock,
            return_value={"ok": False, "code": "protocol_mismatch"},
        ):
            snapshot = await manager.read()
        self.assertEqual(snapshot.status, "omni version")
