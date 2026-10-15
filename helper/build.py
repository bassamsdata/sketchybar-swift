#!/usr/bin/env python3
"""Compile reviewed local sources; no downloads or package installation."""

import argparse
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

SOURCE = Path(__file__).resolve().parent


def build(output):
    compiler = shutil.which("swiftc")
    if not compiler:
        raise RuntimeError("Install Xcode Command Line Tools first")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    cache = output / ".module-cache"

    def compile_source(name, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                compiler,
                "-O",
                "-module-cache-path",
                str(cache),
                str(SOURCE / (name + ".swift")),
                "-o",
                str(target),
            ],
            check=True,
        )

    for name in ("audio", "axmenu", "notch", "clickaway", "render"):
        compile_source(name, output / name)
    for source, name, permission in (
        (
            "events",
            "Events",
            {
                "NSCalendarsFullAccessUsageDescription": "Show your events only in the SketchyBar calendar."
            },
        ),
        (
            "wifiscan",
            "WifiScan",
            {
                "NSLocationWhenInUseUsageDescription": "List nearby saved Wi-Fi networks on request.",
                "NSLocationUsageDescription": "List nearby saved Wi-Fi networks on request.",
            },
        ),
    ):
        app = output / (name + ".app")
        compile_source(source, app / "Contents/MacOS" / name)
        info = {
            "CFBundleIdentifier": "local.sketchybar.island." + source,
            "CFBundleName": "SketchyBar " + name,
            "CFBundleExecutable": name,
            "CFBundlePackageType": "APPL",
            "CFBundleVersion": "1",
            "LSMinimumSystemVersion": "14.0",
            "LSUIElement": True,
            **permission,
        }
        with (app / "Contents/Info.plist").open("wb") as file:
            plistlib.dump(info, file)
        subprocess.run(["codesign", "--force", "--sign", "-", str(app)], check=True)
    shutil.rmtree(cache, ignore_errors=True)


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=SOURCE)
    build(parser.parse_args().output)
