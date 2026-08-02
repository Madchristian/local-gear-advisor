from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from .profilesets import BuiltProfileSets, ProfileVariant
from .runner import ParsedSimcReport, SimcRunError
from .simc_export import SimcExport
from .spec_registry import load_spec_registry


@dataclass(frozen=True)
class EvaluatedItem:
    item_id: int
    item_name: str | None
    options: str
    fingerprint: str
    best_slot: str
    baseline_dps: float
    candidate_dps: float
    delta_percent: float
    iterations: int


@dataclass(frozen=True)
class Evaluation:
    generated_at: int
    simc_version: str
    git_revision: str
    fight_style: str
    game_version: str
    dbc_source: str
    baseline_dps: float
    items: tuple[EvaluatedItem, ...]


def evaluate_results(
    profile: SimcExport,
    built: BuiltProfileSets,
    report: ParsedSimcReport,
    *,
    generated_at: int,
) -> Evaluation:
    if generated_at < 0:
        raise ValueError("generated_at must not be negative")
    grouped: dict[str, list[tuple[ProfileVariant, float]]] = {}
    for variant in built.variants:
        try:
            value = report.variant_dps[variant.profileset_name]
        except KeyError as exc:
            raise SimcRunError(f"missing result for {variant.profileset_name}") from exc
        grouped.setdefault(variant.item_fingerprint, []).append((variant, value))

    by_fingerprint = {candidate.fingerprint: candidate for candidate in profile.candidates}
    items: list[EvaluatedItem] = []
    seen: set[str] = set()
    for candidate in profile.candidates:
        if candidate.fingerprint in seen:
            continue
        seen.add(candidate.fingerprint)
        choices = grouped.get(candidate.fingerprint)
        if not choices:
            raise SimcRunError(f"candidate {candidate.item_id} has no simulated variants")
        best_variant, best_dps = max(choices, key=lambda choice: choice[1])
        iterations = report.iterations[best_variant.profileset_name]
        delta_percent = ((best_dps / report.baseline_dps) - 1.0) * 100.0
        source = by_fingerprint[candidate.fingerprint]
        items.append(
            EvaluatedItem(
                item_id=source.item_id,
                item_name=source.name,
                options=source.options,
                fingerprint=source.fingerprint,
                best_slot=best_variant.target_slot,
                baseline_dps=report.baseline_dps,
                candidate_dps=best_dps,
                delta_percent=delta_percent,
                iterations=iterations,
            )
        )
    return Evaluation(
        generated_at=generated_at,
        simc_version=report.simc_version,
        git_revision=report.git_revision,
        fight_style=report.fight_style,
        game_version=report.game_version,
        dbc_source=report.dbc_source,
        baseline_dps=report.baseline_dps,
        items=tuple(items),
    )


def ensure_supported_profile(profile: SimcExport) -> int:
    registry = load_spec_registry()
    try:
        return registry.specs[(profile.character_class, profile.spec)]
    except KeyError as exc:
        raise ValueError(
            f"unsupported class/spec pair: {profile.character_class}/{profile.spec}"
        ) from exc


def write_atomic_verified(target: Path, content: str) -> None:
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = target.with_name(f"{target.name}.lock")
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise OSError(f"publication is already in progress: {lock}") from exc
    try:
        os.write(lock_fd, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(lock_fd)
        data = content.encode("utf-8")
        expected = hashlib.sha256(data).digest()
        old_data = target.read_bytes() if target.exists() else None
        temp = target.with_name(f"{target.name}.tmp-{uuid.uuid4().hex}")
        try:
            with temp.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if hashlib.sha256(temp.read_bytes()).digest() != expected:
                raise OSError("temporary result verification failed")
            os.replace(temp, target)
            if hashlib.sha256(target.read_bytes()).digest() != expected:
                raise OSError("published result verification failed")
        except Exception:
            if temp.exists():
                temp.unlink()
            current_data = target.read_bytes() if target.exists() else None
            if old_data is not None and current_data != old_data:
                rollback = target.with_name(f"{target.name}.rollback-{uuid.uuid4().hex}")
                rollback.write_bytes(old_data)
                os.replace(rollback, target)
            elif old_data is None and target.exists():
                target.unlink()
            raise
    finally:
        os.close(lock_fd)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
