"""Build the libs folder for Dynamo in Revit 2026 (Python 3.9, Windows x64).

Run on any machine that has pip:

    python build_libs.py

It installs ``infrared-sdk[geodata]==1.0.0`` and its dependencies into
``build/libs`` as wheels for Python 3.9 on win_amd64, copies ``ir_dynamo``,
``revit`` and ``dynamo`` (the ``.dyn`` files) beside them, and writes
``build/infrared-dynamo-libs.zip``. The zip has no top folder: the user unzips it
into one folder (the libs folder) and gives that folder to the Dynamo script.
``build/`` is not committed.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import List

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
LIBS = BUILD / "libs"
ZIP = BUILD / "infrared-dynamo-libs.zip"
REQUIREMENT = "infrared-sdk[geodata]==1.0.0"
OWN_FOLDERS = ["ir_dynamo", "ir_revit", "dynamo"]


def pip_install() -> None:
    """Download the wheels of Python 3.9 for Windows x64, binary only."""
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--target",
        str(LIBS),
        "--python-version",
        "3.9",
        "--platform",
        "win_amd64",
        "--only-binary=:all:",
        "--implementation",
        "cp",
        "--no-compile",
        REQUIREMENT,
    ]
    subprocess.run(command, check=True)


def wheel_tags() -> List[str]:
    """The tags of every installed wheel, from the ``WHEEL`` files."""
    tags = set()
    for wheel_file in LIBS.glob("*.dist-info/WHEEL"):
        for line in wheel_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("Tag:"):
                tags.add("%s  %s" % (wheel_file.parent.name, line[4:].strip()))
    return sorted(tags)


def copy_own_code() -> None:
    for name in OWN_FOLDERS:
        source = HERE / name
        if source.is_dir():
            shutil.copytree(
                source,
                LIBS / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )


def make_zip() -> None:
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(LIBS.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(LIBS))


def main() -> None:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    LIBS.mkdir(parents=True)
    pip_install()
    copy_own_code()
    make_zip()
    print("Wheel tags:")
    print("\n".join(wheel_tags()))
    print("Zip: %s (%.1f MB)" % (ZIP, ZIP.stat().st_size / 1e6))


if __name__ == "__main__":
    main()
