from __future__ import annotations

import json
import multiprocessing
import re
import sys
import tkinter as tk
from collections.abc import Callable, Sequence
from importlib import resources
from pathlib import Path
from typing import TextIO

from .deploy_results import CODE_FILE_NAMES
from .import_codec import TRANSPORT_MAGIC
from .spec_registry import load_spec_registry

APPLICATION_NAME = "Local Gear Advisor"
HELPER_VERSION = "0.2.1"
ADDON_SCHEMA_VERSION = 2
_ADDON_FILES = tuple(sorted((*CODE_FILE_NAMES, "Results.lua")))


def _portable_icon_path() -> Path:
    packaged = resources.files("local_gear_advisor").joinpath(
        "portable_assets", "LocalGearAdvisor.ico"
    )
    if packaged.is_file():
        return Path(str(packaged))
    source = Path(__file__).resolve().parents[2] / "portable" / "LocalGearAdvisor.ico"
    if source.is_file():
        return source
    raise OSError("portable window icon is unavailable")


def apply_window_icon(root) -> bool:
    try:
        root.iconbitmap(default=str(_portable_icon_path()))
    except (OSError, tk.TclError):
        return False
    return True


def _addon_root():
    packaged = resources.files("local_gear_advisor").joinpath("addon_template")
    if packaged.is_dir():
        return packaged
    source = Path(__file__).resolve().parents[2] / "addon" / "LocalGearAdvisor"
    if source.is_dir():
        return source
    raise RuntimeError("packaged addon assets are unavailable")


def portable_contract() -> dict[str, object]:
    if TRANSPORT_MAGIC != "LGA2":
        raise RuntimeError("portable helper transport must remain LGA2")
    if ADDON_SCHEMA_VERSION != 2:
        raise RuntimeError("portable helper schema must remain version 2")

    root = _addon_root()
    observed = tuple(sorted(entry.name for entry in root.iterdir() if entry.is_file()))
    if observed != _ADDON_FILES:
        raise RuntimeError("packaged addon inventory does not match the v0.2 contract")

    toc = root.joinpath("LocalGearAdvisor.toc").read_text(encoding="utf-8")
    match = re.search(r"^## Version:\s*(\S+)\s*$", toc, re.MULTILINE)
    if match is None:
        raise RuntimeError("packaged addon has no version marker")
    if match.group(1) != "0.2.0":
        raise RuntimeError("packaged addon must remain version 0.2.0")

    results = root.joinpath("Results.lua").read_text(encoding="utf-8")
    if not re.search(r"schemaVersion\s*=\s*2\s*,", results):
        raise RuntimeError("packaged Results.lua is not the empty schema-2 placeholder")
    if not re.search(r"profiles\s*=\s*\{\s*\}\s*,", results):
        raise RuntimeError("packaged Results.lua is not empty")

    registry = load_spec_registry()
    return {
        "application": APPLICATION_NAME,
        "helperVersion": HELPER_VERSION,
        "transportMagic": TRANSPORT_MAGIC,
        "addonSchemaVersion": ADDON_SCHEMA_VERSION,
        "specCount": len(registry.specs),
        "addonVersion": match.group(1),
        "addonFiles": list(observed),
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    launcher: Callable[[], None] | None = None,
    output: TextIO | None = None,
) -> int:
    multiprocessing.freeze_support()
    arguments = list(sys.argv[1:] if argv is None else argv)
    stream = sys.stdout if output is None else output

    if arguments == ["--portable-smoke-test"]:
        print(json.dumps(portable_contract(), sort_keys=True), file=stream)
        return 0
    if arguments:
        print(f"unknown portable argument: {arguments[0]}", file=stream)
        return 2

    portable_contract()
    if launcher is None:
        from .gui import launch

        launcher = launch
    launcher()
    return 0
