import asyncio
import io
import json
import os
import shlex
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))
sys.path.insert(0, str(ROOT))
import runtime
import widgets
from bar import Bar, main

import install


class ConfigurationTests(unittest.TestCase):
    def test_reload_preserves_existing_runtime_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            log = cache / "runtime.log"
            log.write_text("previous runtime stopped\n")

            def spawn(*args, **kwargs):
                # Simulate the new child's diagnostic output on the inherited fd.
                os.write(kwargs["stderr"], b"new runtime started\n")

            with (
                patch.object(sys, "argv", ["bar.py", "setup"]),
                patch("bar.config"),
                patch("bar.read_palette"),
                patch("bar.send"),
                patch("bar.cache_path", return_value=cache),
                patch("bar.subprocess.Popen", side_effect=spawn),
            ):
                main()
            self.assertEqual(
                log.read_text(), "previous runtime stopped\nnew runtime started\n"
            )

    def test_config_is_typed_data(self):
        cfg = runtime.config(ROOT)
        self.assertEqual(cfg["window_manager"], "auto")
        self.assertFalse(cfg["features"]["wifi_scan"])
        with tempfile.TemporaryDirectory() as path:
            path = Path(path)
            cfg["opacity"] = "$(touch should-not-exist)"
            (path / "config.json").write_text(json.dumps(cfg))
            with self.assertRaises(ValueError):
                runtime.config(path)
            self.assertFalse((path / "should-not-exist").exists())

    def test_unknown_features_rejected(self):
        cfg = runtime.config(ROOT)
        cfg["features"]["pilo"] = True
        with tempfile.TemporaryDirectory() as path:
            (Path(path) / "config.json").write_text(json.dumps(cfg))
            with self.assertRaises(ValueError):
                runtime.config(Path(path))

    def test_private_directory_and_symlink(self):
        with tempfile.TemporaryDirectory() as path:
            base = Path(path)
            owned = runtime.private_dir(base / "owned")
            self.assertEqual(stat.S_IMODE(owned.stat().st_mode), 0o700)
            (base / "link").symlink_to(owned)
            with self.assertRaises(ValueError):
                runtime.private_dir(base / "link")

    def test_private_file_refuses_symlinks_and_fifos(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            target = root / "target"
            target.write_text("preserve")
            (root / "link").symlink_to(target)
            with self.assertRaises(OSError):
                runtime.private_file(root / "link", truncate=True)
            self.assertEqual(target.read_text(), "preserve")
            os.mkfifo(root / "fifo")
            with self.assertRaises((OSError, ValueError)):
                runtime.private_file(root / "fifo", truncate=True)
            fd = runtime.private_file(root / "file")
            os.close(fd)
            self.assertEqual(stat.S_IMODE((root / "file").stat().st_mode), 0o600)

    def test_callback_quotes_paths_and_never_uses_labels(self):
        path = Path("/tmp/a path with ' quotes; $(touch marker)")
        argv = shlex.split(runtime.command("popup.clock", path))
        self.assertEqual(argv[1], str(path / "plugins/bar.py"))
        self.assertEqual(argv[2:], ["send", "popup.clock"])

    def test_artwork_dimensions_are_read_without_decoding(self):
        header = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
        self.assertEqual(
            runtime.image_size(header + struct.pack(">II", 120, 120)), (120, 120)
        )
        self.assertEqual(
            runtime.image_size(header + struct.pack(">II", 50000, 50000)),
            (50000, 50000),
        )
        self.assertIsNone(runtime.image_size(b"not an image"))


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bar = Bar(runtime.config(ROOT), Path(self.tmp.name))
        self.bar.palette = {
            "text": "0xffffffff",
            "muted": "0xff888888",
            "line": "0xff222222",
            "dim": "0xff666666",
            "error": "0xffff4444",
            "warn": "0xffffff00",
        }
        self.bar.sb = AsyncMock(return_value="{}")
        self.query_patch = patch("bar.query", new_callable=AsyncMock, return_value=None)
        self.query_patch.start()

    async def asyncTearDown(self):
        for task in list(self.bar.tasks):
            task.cancel()
        await asyncio.gather(*list(self.bar.tasks), return_exceptions=True)
        self.query_patch.stop()
        self.tmp.cleanup()

    async def test_malicious_titles_never_become_click_code(self):
        poison = "meeting\t0xffffffff\tprintf INJECTION #\n$(touch marker); '"
        clicked = AsyncMock()
        self.bar.open_popup = "clock"
        await self.bar.popup("clock", poison, [widgets.row(poison, poison, clicked)])
        args = self.bar.sb.call_args_list[0].args
        callbacks = [
            a.removeprefix("click_script=")
            for a in args
            if a.startswith("click_script=")
        ]
        self.assertEqual(len(callbacks), 2)
        self.assertEqual(callbacks[0], "")
        argv = shlex.split(callbacks[1])
        self.assertRegex(argv[-1], r"^action\.[0-9a-f]{32}$")
        self.assertNotIn("INJECTION", callbacks[1])
        self.assertNotIn("\n", "".join(a for a in args if a.startswith("label=")))
        await self.bar.event({"event": argv[-1]})
        clicked.assert_awaited_once()

    async def test_forged_or_stale_actions_are_ignored(self):
        clicked = AsyncMock()
        self.bar.open_popup = "wifi"
        await self.bar.popup("wifi", "WI-FI", [widgets.row("", "x", clicked)])
        token = next(iter(self.bar.actions))
        await self.bar.event({"event": "action.printf INJECTION"})
        await self.bar.close_popup()
        await self.bar.event({"event": token})
        clicked.assert_not_awaited()

    async def test_empty_sketchybar_geometry_reply_is_retried(self):
        with patch(
            "runtime.run",
            new_callable=AsyncMock,
            side_effect=["", '{"bounding_rects": {}}'],
        ) as execute:
            result = await runtime.query("sketchybar", "--query", "clock")
        self.assertEqual(result, {"bounding_rects": {}})
        self.assertEqual(execute.await_count, 2)

    async def test_label_updates_are_deduplicated(self):
        await self.bar.set("clock", label="12:00")
        await self.bar.set("clock", label="12:00")
        self.assertEqual(self.bar.sb.await_count, 1)

    async def test_failed_probes_keep_runtime_alive_and_refresh_on_recovery(self):
        self.bar.sb = AsyncMock(side_effect=["", "", "", "{}", "{}"])
        self.bar.refresh_display = AsyncMock()
        with patch("sys.stderr", new_callable=io.StringIO) as log:
            for _ in range(3):
                await self.bar.probe()
                self.assertFalse(self.bar.closed.is_set())
                self.assertTrue(self.bar.sb_unavailable)
            self.bar.refresh_display.assert_not_awaited()
            await self.bar.probe()
            await self.bar.probe()
        self.assertFalse(self.bar.sb_unavailable)
        self.assertFalse(self.bar.closed.is_set())
        self.bar.refresh_display.assert_awaited_once()
        self.assertEqual(log.getvalue().count("unavailable"), 1)
        self.assertEqual(log.getvalue().count("recovered"), 1)

    async def test_wake_clears_cached_values_closes_popup_and_updates_widgets(self):
        self.bar.props[("clock", "label")] = "12:00"
        self.bar.open_popup = "clock"
        self.bar.props[("clock", "popup.drawing")] = "off"
        self.bar.actions["action.stale"] = ("clock", AsyncMock(), False)
        self.bar.measure_display = AsyncMock()
        self.bar.refit_media = AsyncMock()
        self.bar.notify = Mock()
        await self.bar.event({"event": "system_woke"})
        self.assertNotIn(("clock", "label"), self.bar.props)
        self.assertEqual(self.bar.open_popup, "")
        self.assertFalse(self.bar.actions)
        self.bar.measure_display.assert_awaited_once()
        self.bar.refit_media.assert_awaited_once()
        self.assertEqual(
            {call.args[0] for call in self.bar.notify.call_args_list},
            self.bar.enabled_items(),
        )
        self.assertIn(
            ("--set", "clock", "popup.drawing=off"),
            [call.args for call in self.bar.sb.call_args_list],
        )
        # Identical labels must be resent after wake, despite earlier caching.
        await self.bar.set("clock", label="12:00")
        self.bar.sb.assert_awaited_with("--set", "clock", "label=12:00")

    async def test_failed_periodic_probe_still_accepts_wake_and_shutdown_over_ipc(self):
        self.bar.flags = {key: False for key in self.bar.flags}
        self.bar.sb = AsyncMock(return_value="")
        self.bar.setup = AsyncMock()
        self.bar.measure_display = AsyncMock()
        self.bar.refit_media = AsyncMock()
        self.bar.notify = Mock()
        loop = asyncio.get_running_loop()
        path = self.bar.cache / "events.sock"
        with (
            patch.object(loop, "add_signal_handler"),
            patch("sys.stderr", new_callable=io.StringIO) as log,
        ):
            server = asyncio.create_task(self.bar.start())
            try:
                for _ in range(100):
                    if self.bar.sb_unavailable:
                        break
                    await asyncio.sleep(0.01)
                self.assertTrue(self.bar.sb_unavailable)
                self.assertFalse(server.done())
                self.assertTrue(path.exists())
                with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
                    sock.sendto(b'{"event":"system_woke"}', str(path))
                    for _ in range(100):
                        if self.bar.measure_display.await_count:
                            break
                        await asyncio.sleep(0.01)
                    self.bar.measure_display.assert_awaited_once()
                    sock.sendto(b'{"event":"shutdown"}', str(path))
                await asyncio.wait_for(server, 2)
                self.assertIn("runtime stopping: shutdown requested", log.getvalue())
            finally:
                server.cancel()
                await asyncio.gather(server, return_exceptions=True)
        self.assertFalse(path.exists())
        self.assertFalse(self.bar.tasks)

    async def test_workspace_event_bursts_are_coalesced(self):
        update = AsyncMock()
        with patch.dict(widgets.UPDATES, {"workspaces": update}):
            for _ in range(100):
                self.bar.notify("workspaces")
            await asyncio.sleep(0.25)
        update.assert_awaited_once_with(self.bar)

    async def test_events_during_update_get_one_followup(self):
        started = asyncio.Event()
        release = asyncio.Event()

        async def update(bar):
            started.set()
            await release.wait()

        mock = AsyncMock(side_effect=update)
        with patch.dict(widgets.UPDATES, {"workspaces": mock}):
            self.bar.notify("workspaces")
            await started.wait()
            for _ in range(20):
                self.bar.notify("workspaces")
            release.set()
            await asyncio.sleep(0.25)
        self.assertEqual(mock.await_count, 2)

    async def test_disabled_widgets_do_no_work(self):
        self.bar.flags["workspaces"] = False
        self.bar.notify("workspaces")
        self.assertFalse(self.bar.tasks)

    async def test_unsafe_volume_input_is_rejected(self):
        with patch("bar.run", new_callable=AsyncMock) as execute:
            await self.bar.event(
                {"event": "slider.volume", "percentage": "50; touch marker"}
            )
            execute.assert_not_awaited()

    async def test_wifi_name_is_one_literal_argv_argument(self):
        ssid = "cafe'; $(touch marker)\t#"
        with patch("widgets.run", new_callable=AsyncMock) as execute:
            await widgets.dispatch(self.bar, "wifi", "en0", ssid)
            self.assertEqual(
                execute.call_args.args,
                ("networksetup", "-setairportnetwork", "en0", ssid),
            )

    async def test_apple_music_is_ignored_and_never_controlled(self):
        with (
            patch(
                "widgets.query",
                new_callable=AsyncMock,
                return_value={"bundleIdentifier": "com.apple.Music"},
            ),
            patch("widgets.shutil.which", return_value="media-control"),
            patch("widgets.run", new_callable=AsyncMock) as execute,
        ):
            await widgets.media(self.bar)
            self.assertEqual(self.bar.media_state, {})
            await widgets.dispatch(self.bar, "media.play")
            execute.assert_not_awaited()

    async def test_cli_error_envelope_can_be_read_without_suppressing_exit_status_by_default(
        self,
    ):
        args = (
            sys.executable,
            "-c",
            'import sys; print(\'{"ok": false, "code": "transport_failure"}\'); sys.exit(2)',
        )
        self.assertEqual(await runtime.run(*args), "")
        result = await runtime.query(*args, allow_failure=True)
        self.assertEqual(result["code"], "transport_failure")

    async def test_child_timeout_and_output_limit(self):
        start = time.monotonic()
        result = await runtime.run(
            sys.executable, "-c", "import time; time.sleep(10)", timeout=0.1
        )
        self.assertEqual(result, "")
        self.assertLess(time.monotonic() - start, 3)
        result = await runtime.run(sys.executable, "-c", "print('x' * 10000)", limit=64)
        self.assertEqual(result, "")

    async def test_media_progress_diffs_do_not_schedule_extra_queries(self):
        lines = [
            json.dumps(
                {"diff": False, "payload": {"title": "Track", "playing": True}}
            ).encode(),
            json.dumps({"diff": True, "payload": {"elapsedTime": 1}}).encode(),
            json.dumps({"diff": True, "payload": {"elapsedTime": 2}}).encode(),
            b"",
        ]
        proc = SimpleNamespace(
            stdout=SimpleNamespace(readline=AsyncMock(side_effect=lines)), returncode=0
        )
        self.bar.notify = Mock()
        with patch(
            "bar.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=proc,
        ):
            await self.bar.stream(["media-test"], "media")
        self.bar.notify.assert_called_once_with("media")
        self.assertEqual(self.bar.media_source_data["elapsedTime"], 2)

    async def test_artwork_is_removed_on_close(self):
        (self.bar.cache / "art-deadbeef").write_bytes(b"test")
        await self.bar.close_popup()
        self.assertFalse(list(self.bar.cache.glob("art-*")))

    async def test_private_ipc_shutdown_reaps_runtime_tasks(self):
        self.bar.flags = {key: False for key in self.bar.flags}
        with (
            patch("bar.query", new_callable=AsyncMock, return_value=None),
            patch(
                "bar.asyncio.get_running_loop", wraps=asyncio.get_running_loop
            ) as get_loop,
        ):
            loop = asyncio.get_running_loop()
            get_loop.return_value = loop
            with patch.object(loop, "add_signal_handler"):
                server = asyncio.create_task(self.bar.start())
                path = self.bar.cache / "events.sock"
                for _ in range(100):
                    if path.exists():
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
                    sock.sendto(b'{"event":"shutdown"}', str(path))
                await asyncio.wait_for(server, 2)
        self.assertFalse(path.exists())
        self.assertFalse(self.bar.tasks)


class InstallerTests(unittest.TestCase):
    def test_failed_publish_restores_previous_configuration(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            dest, stage = root / "config", root / "stage"
            dest.mkdir()
            stage.mkdir()
            (dest / "valuable").write_text("old config")
            real_replace = os.replace

            def fail(source, target):
                if source == stage:
                    raise OSError("simulated publish failure")
                real_replace(source, target)

            with patch("install.os.replace", side_effect=fail):
                with self.assertRaises(OSError):
                    install.replace(stage, dest)
            self.assertEqual((dest / "valuable").read_text(), "old config")

    def test_failed_validation_keeps_existing_config_and_cleans_stage(self):
        with tempfile.TemporaryDirectory() as path:
            dest = Path(path) / "config"
            dest.mkdir()
            (dest / "valuable").write_text("old config")
            with (
                patch("install.shutil.which", return_value="/usr/bin/true"),
                patch(
                    "install.subprocess.run",
                    side_effect=subprocess.CalledProcessError(1, "check"),
                ),
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    install.install(dest)
            self.assertEqual((dest / "valuable").read_text(), "old config")
            self.assertEqual(list(Path(path).glob(".sketchybar-stage-*")), [])

    def test_symlink_destination_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            (root / "real").mkdir()
            (root / "dest").symlink_to(root / "real")
            (root / "stage").mkdir()
            with self.assertRaises(ValueError):
                install.replace(root / "stage", root / "dest")
            self.assertTrue((root / "dest").is_symlink())
