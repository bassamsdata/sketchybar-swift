import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))
import widgets


class PortTests(unittest.IsolatedAsyncioTestCase):
    async def test_nested_repository_listeners_are_listed_once_and_outsiders_excluded(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "repos"
            nested = root / "goalio360" / "design"
            nested.mkdir(parents=True)
            outside = base / "repos-other"
            outside.mkdir()
            bar = SimpleNamespace(
                cfg={"work_dir": str(root)}, popup=AsyncMock(), action=Mock()
            )
            listeners = (
                "p11\ncPython\nn*:4321\nn[::1]:4321\n"
                "p12\ncPython\nn*:4323\n"
                "p13\ncnode\nn*:3000\n"
                "p14\ncdocker-proxy\nn*:9999\n"
            )
            cwd = f"p11\nn{nested}\np12\nn{nested}\np13\nn{outside}\np14\nn{nested}\n"
            with patch(
                "widgets.run", new_callable=AsyncMock, side_effect=[listeners, cwd]
            ):
                await widgets.ports_popup(bar)
            rows = bar.popup.call_args.args[2]
            self.assertEqual([r["left"] for r in rows], [":4321", ":4323"])
            self.assertEqual(rows[0]["label"], "goalio360/design · Python")
            self.assertEqual(
                [c.args for c in bar.action.call_args_list],
                [("port", 4321), ("port", 4323)],
            )

    async def test_directory_identity_handles_macos_case_variants(self):
        def same_directory(ancestor, root):
            return str(ancestor).casefold() == str(root).casefold()

        with patch.object(Path, "samefile", same_directory):
            self.assertEqual(
                widgets.project_relative_path(
                    Path("/Users/test/repos/goalio360/design"),
                    Path("/Users/test/Repos"),
                ),
                Path("goalio360/design"),
            )
            self.assertIsNone(
                widgets.project_relative_path(
                    Path("/Users/test/repos-other"), Path("/Users/test/Repos")
                )
            )

    async def test_symlinked_work_root_matches_real_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repos"
            nested = root / "project" / "web"
            nested.mkdir(parents=True)
            alias = Path(directory) / "projects"
            alias.symlink_to(root, target_is_directory=True)
            self.assertEqual(
                widgets.project_relative_path(nested, alias), Path("project/web")
            )
