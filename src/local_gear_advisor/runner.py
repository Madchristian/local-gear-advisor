from __future__ import annotations

import json
import math
import re
import subprocess
import uuid
from collections.abc import Callable, Mapping, Set
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SimcRunError(RuntimeError):
    """Closed failure: no result data is safe to publish."""


@dataclass(frozen=True)
class ParsedSimcReport:
    simc_version: str
    git_revision: str
    fight_style: str
    game_version: str
    dbc_source: str
    baseline_dps: float
    variant_dps: dict[str, float]
    iterations: dict[str, int]


def _positive_number(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise SimcRunError(f"{label} is not numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise SimcRunError(f"{label} is not a positive finite number")
    return number


def parse_json2_report(report: Mapping[str, Any], *, expected_names: Set[str]) -> ParsedSimcReport:
    if not str(report.get("report_version", "")).startswith("2."):
        raise SimcRunError("unsupported SimulationCraft JSON report version")
    simc_version = report.get("version")
    git_revision = report.get("git_revision")
    if not isinstance(simc_version, str) or not simc_version.strip():
        raise SimcRunError("report has no SimulationCraft version")
    if not isinstance(git_revision, str) or not git_revision.strip():
        raise SimcRunError("report has no SimulationCraft git revision")
    logs = report.get("logs", [])
    if not isinstance(logs, list):
        raise SimcRunError("report logs are malformed")
    for entry in logs:
        if not isinstance(entry, Mapping):
            raise SimcRunError("report log entry is malformed")
        level = entry.get("level")
        message = entry.get("message")
        if not isinstance(level, str) or not isinstance(message, str):
            raise SimcRunError("report log entry has invalid level or message")
        if level.casefold() in {"warning", "error", "fatal", "critical"}:
            raise SimcRunError(f"SimulationCraft {level}: {message}")
    sim = report.get("sim")
    if not isinstance(sim, Mapping):
        raise SimcRunError("report has no sim object")
    options = sim.get("options")
    if not isinstance(options, Mapping):
        raise SimcRunError("report has no simulation options")
    fight_style = options.get("fight_style")
    dbc = options.get("dbc")
    if not isinstance(fight_style, str) or not fight_style:
        raise SimcRunError("report has no fight style")
    if not isinstance(dbc, Mapping):
        raise SimcRunError("report has no DBC provenance")
    dbc_source = dbc.get("version_used")
    if not isinstance(dbc_source, str) or not dbc_source:
        raise SimcRunError("report has no DBC source")
    dbc_details = dbc.get(dbc_source)
    if not isinstance(dbc_details, Mapping):
        raise SimcRunError("report has no details for the selected DBC source")
    game_version = dbc_details.get("wow_version")
    if not isinstance(game_version, str) or not game_version:
        raise SimcRunError("report has no simulated WoW version")
    players = sim.get("players")
    if not isinstance(players, list) or len(players) != 1 or not isinstance(players[0], Mapping):
        raise SimcRunError("report must contain exactly one baseline player")
    try:
        baseline_raw = players[0]["collected_data"]["dps"]["mean"]
    except (KeyError, TypeError) as exc:
        raise SimcRunError("report has no baseline DPS mean") from exc
    baseline_dps = _positive_number(baseline_raw, "baseline DPS")

    profilesets = sim.get("profilesets")
    if not isinstance(profilesets, Mapping):
        raise SimcRunError("report has no profilesets object")
    if profilesets.get("metric") != "Damage per Second":
        raise SimcRunError("profileset report does not use the DPS metric")
    raw_results = profilesets.get("results")
    if not isinstance(raw_results, list):
        raise SimcRunError("profileset results are malformed")

    variant_dps: dict[str, float] = {}
    iterations: dict[str, int] = {}
    for entry in raw_results:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("name"), str):
            raise SimcRunError("profileset result entry is malformed")
        name = entry["name"]
        if name in variant_dps:
            raise SimcRunError(f"duplicate profileset result: {name}")
        variant_dps[name] = _positive_number(entry.get("mean"), f"profileset {name} mean")
        count = entry.get("iterations")
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise SimcRunError(f"profileset {name} has invalid iterations")
        iterations[name] = count

    actual_names = set(variant_dps)
    missing = expected_names - actual_names
    unexpected = actual_names - expected_names
    if missing:
        raise SimcRunError(f"missing profileset results: {', '.join(sorted(missing))}")
    if unexpected:
        raise SimcRunError(f"unexpected profileset results: {', '.join(sorted(unexpected))}")

    return ParsedSimcReport(
        simc_version=simc_version,
        git_revision=git_revision,
        fight_style=fight_style,
        game_version=game_version,
        dbc_source=dbc_source,
        baseline_dps=baseline_dps,
        variant_dps=variant_dps,
        iterations=iterations,
    )


def run_simc(
    *,
    executable: Path,
    input_text: str,
    expected_names: Set[str],
    run_root: Path,
    timeout_seconds: int = 600,
    process_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> ParsedSimcReport:
    executable = executable.resolve()
    if executable.name.casefold() != "simc.exe":
        raise SimcRunError(
            f"executable must be named simc.exe, got {executable.name!r}; "
            "SimulationCraft.exe and other basenames are rejected"
        )
    if not executable.is_file():
        raise SimcRunError(f"simc executable does not exist: {executable}")
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be positive")

    run_dir = run_root.resolve() / f"run-{uuid.uuid4().hex}"
    run_dir.mkdir(parents=True, exist_ok=False)
    profile_path = run_dir / "input.simc"
    report_path = run_dir / "report.json"
    profile_path.write_text(input_text, encoding="utf-8", newline="\n")

    argv = [str(executable), str(profile_path), f"json2={report_path}"]
    try:
        completed = process_runner(
            argv,
            cwd=executable.parent,
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SimcRunError(f"SimulationCraft timed out after {timeout_seconds} seconds") from exc
    except OSError as exc:
        raise SimcRunError(f"SimulationCraft could not be started: {exc}") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "no diagnostic output").strip()
        raise SimcRunError(
            f"SimulationCraft failed with exit code {completed.returncode}: {detail}"
        )
    diagnostics = "\n".join((completed.stdout or "", completed.stderr or ""))
    warning = re.search(r"^\s*(?:warning|error)\s*:.*$", diagnostics, re.IGNORECASE | re.MULTILINE)
    if warning:
        raise SimcRunError(f"SimulationCraft emitted a warning/error: {warning.group(0).strip()}")
    if not report_path.is_file():
        raise SimcRunError("SimulationCraft succeeded but did not create a JSON2 report")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SimcRunError("SimulationCraft JSON2 report is unreadable") from exc
    if not isinstance(report, Mapping):
        raise SimcRunError("SimulationCraft JSON2 report root is not an object")
    return parse_json2_report(report, expected_names=expected_names)
