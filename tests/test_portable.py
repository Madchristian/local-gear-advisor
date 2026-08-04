from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from local_gear_advisor import portable


class _FakeRoot:
    def __init__(self) -> None:
        self.icon: str | None = None

    def iconbitmap(self, *, default: str) -> None:
        self.icon = default


def test_portable_smoke_contract_is_read_only_and_lga2() -> None:
    output = io.StringIO()

    result = portable.main(["--portable-smoke-test"], output=output)

    assert result == 0
    contract = json.loads(output.getvalue())
    assert contract["application"] == "Local Gear Advisor"
    assert contract["helperVersion"] == "0.2.1"
    assert contract["transportMagic"] == "LGA2"
    assert contract["addonSchemaVersion"] == 2
    assert contract["addonVersion"] == "0.2.0"
    assert contract["specCount"] == 40
    assert contract["addonFiles"] == [
        "Core.lua",
        "Import.lua",
        "LocalGearAdvisor.toc",
        "Localization.lua",
        "Minimap.lua",
        "Results.lua",
        "Sha256.lua",
        "UI.lua",
    ]


def test_portable_normal_start_launches_gui_once() -> None:
    calls: list[str] = []

    result = portable.main([], launcher=lambda: calls.append("launched"))

    assert result == 0
    assert calls == ["launched"]


def test_portable_normal_start_validates_frozen_assets_before_gui(monkeypatch) -> None:
    calls: list[str] = []

    def reject_assets() -> dict[str, object]:
        raise RuntimeError("invalid frozen assets")

    monkeypatch.setattr(portable, "portable_contract", reject_assets)

    with pytest.raises(RuntimeError, match="invalid frozen assets"):
        portable.main([], launcher=lambda: calls.append("launched"))
    assert calls == []


def test_portable_contract_rejects_transport_drift(monkeypatch) -> None:
    monkeypatch.setattr(portable, "TRANSPORT_MAGIC", "LGA3")

    with pytest.raises(RuntimeError, match="LGA2"):
        portable.portable_contract()


def test_portable_rejects_unknown_arguments_without_opening_gui() -> None:
    calls: list[str] = []
    output = io.StringIO()

    result = portable.main(
        ["--unexpected"], launcher=lambda: calls.append("launched"), output=output
    )

    assert result == 2
    assert calls == []
    assert "unknown portable argument" in output.getvalue()


def test_portable_window_icon_uses_the_checked_in_ico() -> None:
    root = _FakeRoot()

    assert portable.apply_window_icon(root) is True
    assert root.icon is not None
    assert Path(root.icon).name == "LocalGearAdvisor.ico"
    assert Path(root.icon).is_file()


def test_portable_entry_smoke_mode_runs_as_a_real_process() -> None:
    root = Path(__file__).parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")

    completed = subprocess.run(  # noqa: S603 - fixed local interpreter and repository entry
        [sys.executable, str(root / "portable_entry.py"), "--portable-smoke-test"],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        shell=False,
    )

    assert completed.returncode == 0, completed.stderr
    contract = json.loads(completed.stdout)
    assert contract["transportMagic"] == "LGA2"
    assert contract["specCount"] == 40


def test_portable_entry_reports_top_level_failures_without_a_traceback() -> None:
    import portable_entry

    errors: list[str] = []

    def fail() -> int:
        raise RuntimeError("frozen startup failed")

    assert portable_entry.run(entry=fail, show_error=errors.append) == 1
    assert errors == ["Local Gear Advisor konnte nicht gestartet werden:\n\nfrozen startup failed"]
