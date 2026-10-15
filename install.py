#!/usr/bin/env python3
"""Validate and compile before replacing anything. Never start services."""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "plugins"))
from runtime import config  # noqa: E402


def replace(stage, dest):
    """Rollback if publishing the prepared directory fails."""
    backup = None
    if dest.exists() or dest.is_symlink():
        info = dest.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError("destination must be a real directory owned by you")
        backup = dest.with_name(
            dest.name + ".bak." + datetime.now().strftime("%Y%m%d%H%M%S%f")
        )
        os.replace(dest, backup)
    try:
        os.replace(stage, dest)
    except BaseException:
        if backup:
            os.replace(backup, dest)
        raise
    return backup


def install(dest):
    config()
    if sys.version_info < (3, 9):
        raise ValueError("Python 3.9 or newer is required")
    tools = ("sketchybar", "swiftc", "codesign")
    missing = [tool for tool in tools if not shutil.which(tool)]
    if missing:
        raise ValueError(
            "Missing prerequisites: " + ", ".join(missing) + ". See README.md."
        )
    dest = Path(os.path.abspath(dest))
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        raise ValueError("refusing a symlink destination")
    if dest == ROOT or ROOT in dest.parents or dest in ROOT.parents:
        raise ValueError("destination must be outside the source checkout")
    stage = Path(tempfile.mkdtemp(prefix=".sketchybar-stage-", dir=dest.parent))
    try:
        for name in ("plugins", "helper"):
            (stage / name).mkdir()
            for source in (ROOT / name).iterdir():
                if source.is_file() and source.suffix in (".py", ".sh", ".swift"):
                    if source.is_symlink():
                        raise ValueError("refusing a symlink source file")
                    shutil.copy2(source, stage / name / source.name)
        for name in ("sketchybarrc", "config.json", "LICENSE", "README.md"):
            shutil.copy2(ROOT / name, stage / name)
        shutil.copytree(ROOT / "docs", stage / "docs")
        for asset in (ROOT / "assets").iterdir():
            if asset.is_symlink() or not asset.is_file():
                raise ValueError("assets must be regular local files")
        shutil.copytree(ROOT / "assets", stage / "assets")
        subprocess.run(
            [sys.executable, str(stage / "plugins/bar.py"), "check"], check=True
        )
        spec = importlib.util.spec_from_file_location(
            "build_helpers", ROOT / "helper/build.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.build(stage / "helper")
        (stage / "sketchybarrc").chmod(0o700)
        # Record actual installed dependency identities; never auto-upgrade them.
        versions = {}
        for tool in ("sketchybar", "swiftc", "media-control", "aerospace", "omniwmctl"):
            path = shutil.which(tool)
            if path:
                versions[tool] = {
                    "path": path,
                    "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                }
        (stage / "installed-dependencies.json").write_text(
            json.dumps(versions, indent=2) + "\n"
        )
        backup = replace(stage, dest)
        print("Installed: " + str(dest))
        if backup:
            print("Previous configuration: " + str(backup))
        print(
            "No service started. Review config.json, then start SketchyBar when ready."
        )
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=Path.home() / ".config/sketchybar")
    args = parser.parse_args()
    install(args.dest)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print("Installation failed: " + str(error), file=sys.stderr)
        sys.exit(1)
