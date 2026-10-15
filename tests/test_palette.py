"""Palette data must be local, bounded, complete, and unmodified."""

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))
from palette import KEYS, read_palette


class PaletteTests(unittest.TestCase):
    def payload(self):
        colors = {key: "#abcdef" for key in KEYS}
        body = "\n".join(key + "=" + colors[key] for key in sorted(KEYS))
        return {
            "managed_by": "avra.nvim",
            "colors": colors,
            "checksum": hashlib.sha256(body.encode()).hexdigest(),
        }

    def test_missing_palette_uses_configured_theme(self):
        with tempfile.TemporaryDirectory() as path:
            self.assertEqual(read_palette(Path(path)), {})

    def test_valid_palette_is_converted_to_argb_ready_values(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            (root / "appearance.json").write_text(json.dumps(self.payload()))
            self.assertEqual(read_palette(root), {key: "abcdef" for key in KEYS})

    def test_invalid_or_edited_palette_is_rejected(self):
        for bad in ("color", "checksum", "size", "missing"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as path:
                data = self.payload()
                if bad == "color":
                    data["colors"]["bg"] = "$(touch /tmp/no)"
                elif bad == "checksum":
                    data["checksum"] = "0" * 64
                elif bad == "missing":
                    del data["colors"]["bg"]
                content = " " * 5000 if bad == "size" else json.dumps(data)
                (Path(path) / "appearance.json").write_text(content)
                with self.assertRaises(ValueError):
                    read_palette(Path(path))

    def test_symlink_and_fifo_are_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            palette = root / "appearance.json"
            (root / "target").write_text(json.dumps(self.payload()))
            palette.symlink_to(root / "target")
            with self.assertRaises(OSError):
                read_palette(root)
            palette.unlink()
            os.mkfifo(palette)
            with self.assertRaises(ValueError):
                read_palette(root)
