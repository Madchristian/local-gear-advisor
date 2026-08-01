from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from importlib import resources
from pathlib import Path

from .profilesets import SimSettings, build_profileset_input
from .results import (
    ensure_supported_profile,
    evaluate_results,
    render_results_lua,
    write_atomic_verified,
)
from .runner import ParsedSimcReport, SimcRunError, run_simc
from .safety import ensure_staging_target
from .simc_export import MAX_VALID_ITEM_LEVEL, MIN_VALID_ITEM_LEVEL, parse_simc_export
from .spec_registry import load_spec_registry

_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ADDON = _SOURCE_ROOT / "addon" / "LocalGearAdvisor"
if _SOURCE_ADDON.is_dir():
    PROJECT_ROOT = _SOURCE_ROOT
else:
    PROJECT_ROOT = (
        Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "LocalGearAdvisor"
    )
PROJECT_STAGING_RESULTS = PROJECT_ROOT / "addon" / "LocalGearAdvisor" / "Results.lua"
_UNSUPPORTED_TITAN_DISC_BELT_IDS = frozenset({242664, 245964, 245965, 245966})
_REQUIRED_BASELINE_SLOTS = frozenset(
    {
        "head",
        "neck",
        "shoulder",
        "back",
        "chest",
        "wrist",
        "hands",
        "waist",
        "legs",
        "feet",
        "finger1",
        "finger2",
        "trinket1",
        "trinket2",
        "main_hand",
    }
)


def _stage_packaged_addon_assets(results_path: Path) -> None:
    if results_path.resolve() != PROJECT_STAGING_RESULTS.resolve():
        return
    if results_path.parent.resolve() == _SOURCE_ADDON.resolve():
        return
    package_root = resources.files("local_gear_advisor").joinpath("addon_template")
    for name in ("LocalGearAdvisor.toc", "Core.lua"):
        content = package_root.joinpath(name).read_text(encoding="utf-8")
        write_atomic_verified(results_path.parent / name, content)


@dataclass(frozen=True)
class ExcludedCandidate:
    item_id: int
    name: str | None
    slot: str
    item_level: int | None = None


@dataclass(frozen=True)
class AnalysisSummary:
    character_name: str
    spec: str
    candidate_count: int
    variant_count: int
    simc_version: str
    results_path: Path
    excluded_weapon_count: int
    excluded_weapons: tuple[ExcludedCandidate, ...]
    excluded_below_min_item_level_count: int
    excluded_below_min_item_level: tuple[ExcludedCandidate, ...]
    excluded_unknown_item_level_count: int
    excluded_unknown_item_level: tuple[ExcludedCandidate, ...]
    min_item_level: int


def analyze_export(
    *,
    export_text: str,
    executable: Path,
    settings: SimSettings,
    results_path: Path,
    run_root: Path,
    generated_at: int | None = None,
    timeout_seconds: int = 900,
    simc_runner: Callable[..., ParsedSimcReport] = run_simc,
    staging_target: Path = PROJECT_STAGING_RESULTS,
) -> AnalysisSummary:
    ensure_staging_target(results_path, staging_target)
    profile = parse_simc_export(export_text)
    ensure_supported_profile(profile)
    if profile.warnings:
        details = "; ".join(
            f"line {warning.line_number}: {warning.message}" for warning in profile.warnings
        )
        raise ValueError(f"unparseable bag candidates block publication: {details}")
    missing_slots = sorted(_REQUIRED_BASELINE_SLOTS - profile.equipped.keys())
    if missing_slots:
        raise ValueError(f"incomplete equipped baseline; missing slots: {', '.join(missing_slots)}")
    titan_disc_belts = [
        item for item in profile.candidates if item.item_id in _UNSUPPORTED_TITAN_DISC_BELT_IDS
    ]
    if titan_disc_belts:
        raise ValueError(
            "Titan Disc belt candidates are not supported because their tooltip-only "
            "titan_disc_id cannot be reconstructed safely"
        )

    remaining_candidates = list(profile.candidates)
    excluded_below_min_by_fingerprint: dict[str, ExcludedCandidate] = {}
    excluded_unknown_level_by_fingerprint: dict[str, ExcludedCandidate] = {}
    if settings.min_item_level:
        kept: list = []
        for item in remaining_candidates:
            level = item.item_level
            if level is None or not (MIN_VALID_ITEM_LEVEL <= level <= MAX_VALID_ITEM_LEVEL):
                excluded_unknown_level_by_fingerprint.setdefault(
                    item.fingerprint,
                    ExcludedCandidate(
                        item_id=item.item_id, name=item.name, slot=item.slot, item_level=level
                    ),
                )
            elif level < settings.min_item_level:
                excluded_below_min_by_fingerprint.setdefault(
                    item.fingerprint,
                    ExcludedCandidate(
                        item_id=item.item_id, name=item.name, slot=item.slot, item_level=level
                    ),
                )
            else:
                kept.append(item)
        remaining_candidates = kept

    excluded_weapons_by_fingerprint: dict[str, ExcludedCandidate] = {}
    non_weapon_candidates = []
    for item in remaining_candidates:
        if item.slot in {"main_hand", "off_hand"}:
            excluded_weapons_by_fingerprint.setdefault(
                item.fingerprint,
                ExcludedCandidate(
                    item_id=item.item_id,
                    name=item.name,
                    slot=item.slot,
                    item_level=item.item_level,
                ),
            )
        else:
            non_weapon_candidates.append(item)
    profile = replace(profile, candidates=tuple(non_weapon_candidates))
    excluded_weapons = tuple(excluded_weapons_by_fingerprint.values())
    excluded_below_min_item_level = tuple(excluded_below_min_by_fingerprint.values())
    excluded_unknown_item_level = tuple(excluded_unknown_level_by_fingerprint.values())
    if not profile.candidates:
        reasons = []
        if excluded_below_min_item_level:
            reasons.append(
                f"{len(excluded_below_min_item_level)} below minimum item level "
                f"{settings.min_item_level}"
            )
        if excluded_unknown_item_level:
            reasons.append(f"{len(excluded_unknown_item_level)} unknown or invalid item level")
        if excluded_weapons:
            reasons.append(f"{len(excluded_weapons)} unsupported weapon")
        if reasons:
            raise ValueError("no candidates remain after exclusions: " + "; ".join(reasons))
        raise ValueError("SimC export contains no valid bag candidates")
    built = build_profileset_input(profile, settings)
    if not built.variants:
        raise ValueError("no valid profileset variants were generated")

    report = simc_runner(
        executable=executable,
        input_text=built.input_text,
        expected_names={variant.profileset_name for variant in built.variants},
        run_root=run_root,
        timeout_seconds=timeout_seconds,
    )
    if report.fight_style != settings.fight_style:
        raise SimcRunError(
            f"SimulationCraft reported fight style {report.fight_style!r}, "
            f"expected {settings.fight_style!r}"
        )
    if report.dbc_source != "Live" or report.game_version != "12.0.7.68887":
        raise SimcRunError(
            f"unsupported SimulationCraft game data: {report.dbc_source} {report.game_version}"
        )
    registry_revision = load_spec_registry().source_revision
    if report.git_revision != registry_revision:
        raise SimcRunError(
            f"SimulationCraft git revision {report.git_revision!r} does not match the pinned "
            f"specialization registry revision {registry_revision!r}"
        )
    wrong_iterations = sorted(
        name for name, count in report.iterations.items() if count != settings.iterations
    )
    if wrong_iterations:
        raise SimcRunError(
            "profileset iteration count does not match the requested settings: "
            + ", ".join(wrong_iterations)
        )
    timestamp = int(time.time()) if generated_at is None else generated_at
    evaluation = evaluate_results(profile, built, report, generated_at=timestamp)
    lua = render_results_lua(profile, built, evaluation)

    # The destination was allowlisted before simulation; these are the only staging writes.
    _stage_packaged_addon_assets(results_path)
    write_atomic_verified(results_path, lua)
    return AnalysisSummary(
        character_name=profile.character_name,
        spec=profile.spec,
        candidate_count=len({item.fingerprint for item in profile.candidates}),
        variant_count=len(built.variants),
        simc_version=report.simc_version,
        results_path=results_path.resolve(),
        excluded_weapon_count=len(excluded_weapons),
        excluded_weapons=excluded_weapons,
        excluded_below_min_item_level_count=len(excluded_below_min_item_level),
        excluded_below_min_item_level=excluded_below_min_item_level,
        excluded_unknown_item_level_count=len(excluded_unknown_item_level),
        excluded_unknown_item_level=excluded_unknown_item_level,
        min_item_level=settings.min_item_level,
    )
