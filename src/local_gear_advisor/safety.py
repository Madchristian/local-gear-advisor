from __future__ import annotations

import csv
import io
import subprocess
from collections.abc import Callable
from enum import Enum
from pathlib import Path


class WowState(Enum):
    RUNNING = "running"
    NOT_RUNNING = "not_running"
    UNKNOWN = "unknown"


class UnsafePublishError(RuntimeError):
    pass


def query_wow_state(
    process_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> WowState:
    try:
        completed = process_runner(
            ["tasklist.exe", "/FO", "CSV", "/NH"],
            shell=False,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return WowState.UNKNOWN
    if completed.returncode != 0:
        return WowState.UNKNOWN
    output = completed.stdout or ""
    saw_process = False
    try:
        rows = csv.reader(io.StringIO(output))
        for row in rows:
            if not row:
                continue
            image_name = row[0].strip().casefold()
            if image_name in {"wow.exe", "wowt.exe", "wowb.exe"}:
                return WowState.RUNNING
            if image_name.endswith(".exe"):
                saw_process = True
    except (csv.Error, TypeError):
        return WowState.UNKNOWN
    if saw_process or output.strip().upper().startswith("INFO:"):
        return WowState.NOT_RUNNING
    return WowState.UNKNOWN


def is_live_addon_path(path: Path) -> bool:
    normalized = str(path.resolve()).replace("\\", "/").casefold()
    return "/interface/addons/" in normalized


def ensure_staging_target(target: Path, staging_target: Path) -> None:
    target_absolute = target.absolute()
    staging_absolute = staging_target.absolute()
    if target_absolute != staging_absolute:
        raise UnsafePublishError(
            f"MVP publication is restricted to the staging Results.lua: {staging_absolute}"
        )
    if target_absolute.resolve() != target_absolute:
        raise UnsafePublishError("staging path must not traverse a symlink or directory junction")


def ensure_publish_safe(
    target: Path,
    *,
    state_query: Callable[[], WowState] = query_wow_state,
) -> None:
    if not is_live_addon_path(target):
        return
    state = state_query()
    if state is WowState.RUNNING:
        raise UnsafePublishError("World of Warcraft is running; live addon writes are blocked")
    if state is WowState.UNKNOWN:
        raise UnsafePublishError(
            "World of Warcraft process state is unknown; live addon writes are blocked"
        )
