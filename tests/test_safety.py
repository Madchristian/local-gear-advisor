import subprocess
from pathlib import Path

import pytest

from local_gear_advisor.safety import (
    UnsafePublishError,
    WowState,
    ensure_publish_safe,
    ensure_staging_target,
    query_wow_state,
)


def _completed(stdout: str, returncode: int = 0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


def test_tasklist_failure_is_unknown_not_not_running() -> None:
    state = query_wow_state(lambda *_args, **_kwargs: _completed("access denied", 1))
    assert state is WowState.UNKNOWN


def test_empty_success_output_is_unknown() -> None:
    state = query_wow_state(lambda *_args, **_kwargs: _completed(""))
    assert state is WowState.UNKNOWN


def test_tasklist_detects_running_wow_exactly() -> None:
    state = query_wow_state(
        lambda *_args, **_kwargs: _completed(
            '"explorer.exe","100","Console","1","10,000 K"\r\n'
            '"Wow.exe","1234","Console","1","1,000 K"\r\n'
        )
    )
    assert state is WowState.RUNNING


def test_tasklist_detects_running_ptr_client() -> None:
    state = query_wow_state(
        lambda *_args, **_kwargs: _completed(
            '"explorer.exe","100","Console","1","10,000 K"\r\n'
            '"WowT.exe","1234","Console","1","1,000 K"\r\n'
        )
    )
    assert state is WowState.RUNNING


def test_normal_process_list_without_wow_is_not_running() -> None:
    state = query_wow_state(
        lambda *_args, **_kwargs: _completed('"explorer.exe","100","Console","1","10,000 K"\r\n')
    )
    assert state is WowState.NOT_RUNNING


def test_live_addon_write_is_blocked_when_wow_runs() -> None:
    target = Path(
        r"C:\Game\World of Warcraft\_retail_\Interface\AddOns\LocalGearAdvisor\Results.lua"
    )
    with pytest.raises(UnsafePublishError, match="running"):
        ensure_publish_safe(target, state_query=lambda: WowState.RUNNING)


def test_project_staging_write_does_not_query_wow(tmp_path: Path) -> None:
    called = False

    def query():
        nonlocal called
        called = True
        return WowState.UNKNOWN

    ensure_publish_safe(tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua", state_query=query)
    assert called is False


def test_staging_target_rejects_directory_link(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this Windows configuration")
    target = linked / "Results.lua"

    with pytest.raises(UnsafePublishError, match="symlink or directory junction"):
        ensure_staging_target(target, target)
