"""Geometry regressions that security-only tests cannot catch."""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))
from bar import Bar
from layout import build, fit_text, media_geometry, popup_geometry, text_width
from pixels import generate
from runtime import config, image_size

PALETTE = {
    "text": "0xffe6ebe6",
    "muted": "0xff8b968e",
    "dim": "0xff6b776f",
    "bg": "0xff08090a",
    "surface": "0xff0b0e0d",
    "line": "0xff1e2422",
    "accent": "0xff3ed49c",
    "fill": "0xff194a39",
    "error": "0xffe0685f",
    "warn": "0xffe0b64a",
}


class GeometryTests(unittest.TestCase):
    def test_long_and_wide_text_fits_the_actual_column(self):
        for value in ("x" * 200, "会議" * 50, "cafe\u0301 " * 40, "short"):
            for width in (0, 30, 72, 240):
                with self.subTest(value=value[:10], width=width):
                    self.assertLessEqual(text_width(fit_text(value, width)), width)

    def test_popup_alignment_keeps_both_edges_on_each_display(self):
        for screen_x in (0, -1920, 1512):
            for x in (5, 100, 700, 1400):
                align, shift = popup_geometry(screen_x + x, 85, 391, screen_x, 1512)
                anchor = screen_x + x
                if align == "right":
                    anchor += 85 - 391
                elif align == "center":
                    anchor += (85 - 391) / 2
                self.assertEqual(shift, 0)
                self.assertGreaterEqual(anchor, screen_x + 5)
                self.assertLessEqual(anchor + 391, screen_x + 1512 - 5)

    def test_media_preserves_five_point_gaps(self):
        title, available = media_geometry(280, 656, 230)
        self.assertEqual(280 + 5 + title + 230 + 5, 656)
        self.assertEqual(available, 366)
        self.assertEqual(media_geometry(600, 656, 230)[0], 0)

    def test_pixel_cat_contains_four_distinct_frames_and_private_files(self):
        with tempfile.TemporaryDirectory() as path:
            folder = generate(Path(path), PALETTE)
            frames = [(folder / f"cat_{n}.png").read_bytes() for n in range(1, 5)]
            self.assertEqual({image_size(f) for f in frames}, {(66, 66)})
            self.assertEqual(len(set(frames)), 3)  # Original walk repeats frame 2.
            self.assertEqual((folder.stat().st_mode & 0o777), 0o700)
            self.assertEqual(((folder / "cat_1.png").stat().st_mode & 0o777), 0o600)

    def test_feature_combinations_have_no_missing_bracket_members(self):
        # Optional media, volume, and all right-side integrations can be disabled.
        for media in (False, True):
            for volume in (False, True):
                for extras in (False, True):
                    cfg = config(ROOT)
                    cfg["features"]["media"] = media
                    cfg["features"]["volume"] = volume
                    for name in (
                        "usage",
                        "system",
                        "battery",
                        "wifi",
                        "ports",
                        "tailscale",
                    ):
                        cfg["features"][name] = extras
                    bar = Bar(cfg, Path("/tmp/test-layout"))
                    bar.palette = PALETTE
                    args = build(bar)
                    created = set()
                    i = 0
                    while i < len(args):
                        if args[i : i + 2] == ["--add", "item"]:
                            created.add(args[i + 2])
                        elif args[i : i + 2] == ["--add", "bracket"]:
                            j = i + 3
                            while j < len(args) and not args[j].startswith("--"):
                                self.assertIn(args[j], created)
                                j += 1
                        i += 1


class PopupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bar = Bar(config(ROOT), Path(self.tmp.name))
        self.bar.palette = PALETTE
        self.bar.sb = AsyncMock(return_value="{}")
        self.bar.open_popup = "clock"

    async def asyncTearDown(self):
        for task in self.bar.tasks:
            task.cancel()
        await asyncio.gather(*self.bar.tasks, return_exceptions=True)
        self.tmp.cleanup()

    async def test_popup_columns_and_alignment_stay_within_the_frame(self):
        parent = {
            "bounding_rects": {"display-1": {"origin": [1412, 5], "size": [85, 33]}}
        }
        with patch("bar.query", new_callable=AsyncMock, return_value=parent):
            await self.bar.popup(
                "clock", "CALENDAR", [{"left": "long key" * 10, "label": "会議" * 100}]
            )
        self.assertEqual(self.bar.props["clock", "popup.align"], "right")
        calls = self.bar.sb.call_args_list
        args = next(c.args for c in calls if "clock.row.1" in c.args)
        # Read the row's --set segment, independently of command ordering.
        sections = []
        for i, arg in enumerate(args):
            if arg == "--set" and args[i + 1] == "clock.row.1":
                end = next(
                    (j for j in range(i + 2, len(args)) if args[j].startswith("--")),
                    len(args),
                )
                sections.append(dict(a.split("=", 1) for a in args[i + 2 : end]))
        props = sections[0]
        self.assertLessEqual(text_width(props["label"]), int(props["label.width"]))
        self.assertLessEqual(
            int(props["icon.width"]) + int(props["label.width"]) + 24,
            int(props["width"]),
        )
        self.assertEqual(props["padding_left"], "0")
        self.assertEqual(props["padding_right"], "0")

    async def test_many_calendar_events_fit_short_screens(self):
        self.bar.display_frame["h"] = 600
        with patch("bar.query", new_callable=AsyncMock, return_value=None):
            await self.bar.popup(
                "clock", "EVENTS", [{"label": f"Event {n}"} for n in range(60)]
            )
        self.assertLessEqual(self.bar.popup_items["clock"] * 24 + 18, 600 - 70)

    async def test_artwork_has_its_own_tall_row(self):
        self.bar.open_popup = "media"
        with patch("bar.query", new_callable=AsyncMock, return_value=None):
            await self.bar.popup(
                "media",
                "MEDIA",
                [
                    {
                        "label": "",
                        "height": 144,
                        "image": "/tmp/safe-art",
                        "image_scale": 0.5,
                    },
                    {"left": "title", "label": "Still visible"},
                ],
            )
        args = self.bar.sb.call_args_list[0].args
        self.assertIn("background.height=144", args)
        self.assertIn("background.image=/tmp/safe-art", args)
        self.assertIn("label=Still visible", args)

    async def test_slider_and_text_share_one_width_budget(self):
        self.bar.open_popup = "volume"
        with patch("bar.query", new_callable=AsyncMock, return_value=None):
            await self.bar.popup(
                "volume",
                "VOLUME",
                [{"left": "vol", "label": "50%", "slider": True, "slider_value": 50}],
            )
        args = self.bar.sb.call_args_list[0].args
        i = next(
            i
            for i, a in enumerate(args)
            if a == "--set" and args[i + 1] == "volume.row.1"
        )
        end = next(
            (j for j in range(i + 2, len(args)) if args[j].startswith("--")), len(args)
        )
        props = dict(a.split("=", 1) for a in args[i + 2 : end])
        self.assertLessEqual(
            int(props["icon.width"])
            + int(props["label.width"])
            + int(props["slider.width"])
            + 24,
            int(props["width"]),
        )

    async def test_padding_stays_after_rows_when_inventory_grows(self):
        with patch("bar.query", new_callable=AsyncMock, return_value=None):
            await self.bar.popup("clock", "EVENTS", [{"label": "one"}])
            initial = next(
                c.args for c in self.bar.sb.call_args_list if "clock.pad.top" in c.args
            )
            self.assertLess(
                initial.index("clock.row.0"), initial.index("clock.pad.gap")
            )
            self.assertLess(
                initial.index("clock.pad.gap"), initial.index("clock.row.1")
            )
            self.assertLess(
                initial.index("clock.row.1"), initial.index("clock.pad.bottom")
            )
            self.bar.sb.reset_mock()
            await self.bar.popup(
                "clock", "EVENTS", [{"label": "one"}, {"label": "two"}]
            )
            grown = self.bar.sb.call_args_list[0].args
            self.assertEqual(grown[:2], ("--remove", "clock.pad.bottom"))
            self.assertGreater(
                grown.index("clock.pad.bottom", 2), grown.index("clock.row.2")
            )

    async def test_progress_plates_never_exceed_the_island(self):
        self.bar.media_layout = (7, 400)
        for elapsed in (-10, 0, 50, 99, 500):
            self.bar.media_state = {"duration": 100, "elapsedTime": elapsed}
            await self.bar.progress()
            for name in ("media.fill", "media.mask", "media.round"):
                width = int(self.bar.props[name, "label.width"])
                self.assertGreaterEqual(width, 0)
                self.assertLessEqual(width, 400)
