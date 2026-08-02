from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from .deploy_results import expected_addon_assets
from .import_codec import encode_profile_transport
from .profilesets import SimSettings, build_profileset_input
from .results import ensure_supported_profile, evaluate_results, write_atomic_verified
from .runner import ParsedSimcReport, SimcRunError, run_simc
from .safety import ensure_staging_target
from .simc_export import MAX_VALID_ITEM_LEVEL, MIN_VALID_ITEM_LEVEL, parse_simc_export
from .spec_registry import load_spec_registry
from .state import (
    ProfileItem,
    ProfileRecord,
    normalize_identity,
    publish_profile_update,
    render_aggregate_lua,
)

_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ADDON = _SOURCE_ROOT / "addon" / "LocalGearAdvisor"
_FALLBACK_LOCAL_APP_DATA = Path.home() / "AppData" / "Local"
_CONFIGURED_LOCAL_APP_DATA = os.environ.get("LOCALAPPDATA", "").strip()
_RUNTIME_ROOT = (
    Path(_CONFIGURED_LOCAL_APP_DATA) if _CONFIGURED_LOCAL_APP_DATA else _FALLBACK_LOCAL_APP_DATA
)
if not _RUNTIME_ROOT.is_absolute():
    _RUNTIME_ROOT = _FALLBACK_LOCAL_APP_DATA
PROJECT_ROOT = _RUNTIME_ROOT / "LocalGearAdvisor"
PROJECT_STAGING_RESULTS = PROJECT_ROOT / "addon" / "LocalGearAdvisor" / "Results.lua"
PROJECT_STATE_PATH = PROJECT_ROOT / "state" / "profiles.json"
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
_BASELINE_SLOTS = (
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
    "off_hand",
)


def _stage_packaged_addon_assets(results_path: Path) -> None:
    if results_path.resolve() != PROJECT_STAGING_RESULTS.resolve():
        return
    if results_path.parent.resolve() == _SOURCE_ADDON.resolve():
        return
    for name, content in expected_addon_assets().items():
        write_atomic_verified(results_path.parent / name, content.decode("utf-8"))


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
    state_path: Path
    excluded_weapon_count: int
    excluded_weapons: tuple[ExcludedCandidate, ...]
    excluded_below_min_item_level_count: int
    excluded_below_min_item_level: tuple[ExcludedCandidate, ...]
    excluded_unknown_item_level_count: int
    excluded_unknown_item_level: tuple[ExcludedCandidate, ...]
    min_item_level: int
    region: str
    realm: str
    spec_id: int
    retained_profile_count: int
    results_sha256: str
    transport_text: str


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
    state_path: Path = PROJECT_STATE_PATH,
) -> AnalysisSummary:
    if results_path.resolve() == (_SOURCE_ADDON / "Results.lua").resolve():
        raise ValueError("source addon Results.lua cannot be used as analysis staging")
    ensure_staging_target(results_path, staging_target)
    profile = parse_simc_export(export_text)
    spec_id = ensure_supported_profile(profile)
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

    identity = normalize_identity(
        region=profile.region, realm=profile.server, name=profile.character_name, spec_id=spec_id
    )
    record = ProfileRecord(
        identity=identity,
        character_class=profile.character_class,
        spec=profile.spec,
        level=profile.level,
        race=profile.race,
        talents=profile.talents,
        trait_systems=dict(profile.trait_systems),
        baseline_gear={
            slot: (profile.equipped[slot].options if slot in profile.equipped else None)
            for slot in _BASELINE_SLOTS
        },
        fight_style=evaluation.fight_style,
        baseline_dps=evaluation.baseline_dps,
        simc_version=evaluation.simc_version,
        simc_revision=evaluation.git_revision,
        game_version=evaluation.game_version,
        dbc_source=evaluation.dbc_source,
        profile_hash=built.profile_hash,
        generated_at=evaluation.generated_at,
        items=tuple(
            ProfileItem(
                options=item.options,
                item_id=item.item_id,
                item_name=item.item_name,
                fingerprint=item.fingerprint,
                best_slot=item.best_slot,
                candidate_dps=item.candidate_dps,
                delta_percent=item.delta_percent,
                iterations=item.iterations,
            )
            for item in evaluation.items
        ),
    )

    # The destination was allowlisted before simulation; these are the only staging writes.
    _stage_packaged_addon_assets(results_path)
    new_state = publish_profile_update(
        state_path=state_path, results_path=results_path, record=record
    )
    return AnalysisSummary(
        character_name=profile.character_name,
        spec=profile.spec,
        candidate_count=len({item.fingerprint for item in profile.candidates}),
        variant_count=len(built.variants),
        simc_version=report.simc_version,
        results_path=results_path.resolve(),
        state_path=state_path.resolve(),
        excluded_weapon_count=len(excluded_weapons),
        excluded_weapons=excluded_weapons,
        excluded_below_min_item_level_count=len(excluded_below_min_item_level),
        excluded_below_min_item_level=excluded_below_min_item_level,
        excluded_unknown_item_level_count=len(excluded_unknown_item_level),
        excluded_unknown_item_level=excluded_unknown_item_level,
        min_item_level=settings.min_item_level,
        region=identity.region,
        realm=identity.realm,
        spec_id=identity.spec_id,
        retained_profile_count=len(new_state.profiles),
        results_sha256=hashlib.sha256(render_aggregate_lua(new_state).encode("utf-8")).hexdigest(),
        transport_text=encode_profile_transport(record),
    )
