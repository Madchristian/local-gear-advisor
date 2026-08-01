from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .simc_export import MAX_VALID_ITEM_LEVEL, ItemSpec, SimcExport

_DUAL_SLOTS = {
    "finger1": ("finger1", "finger2"),
    "finger2": ("finger1", "finger2"),
    "trinket1": ("trinket1", "trinket2"),
    "trinket2": ("trinket1", "trinket2"),
}
_ALLOWED_FIGHT_STYLES = frozenset({"Patchwerk", "DungeonSlice"})


@dataclass(frozen=True)
class SimSettings:
    iterations: int = 1000
    fight_style: str = "Patchwerk"
    profileset_work_threads: int = 1
    min_item_level: int = 0

    def __post_init__(self) -> None:
        if not 100 <= self.iterations <= 1_000_000:
            raise ValueError("iterations must be between 100 and 1,000,000")
        if self.fight_style not in _ALLOWED_FIGHT_STYLES:
            raise ValueError(f"unsupported fight style: {self.fight_style}")
        if self.profileset_work_threads < 1:
            raise ValueError("profileset_work_threads must be positive")
        if not 0 <= self.min_item_level <= MAX_VALID_ITEM_LEVEL:
            raise ValueError(
                f"min_item_level must be between 0 (disabled) and {MAX_VALID_ITEM_LEVEL}"
            )


@dataclass(frozen=True)
class ProfileVariant:
    profileset_name: str
    item_id: int
    item_fingerprint: str
    item_name: str | None
    source_slot: str
    target_slot: str
    options: str


@dataclass(frozen=True)
class BuiltProfileSets:
    input_text: str
    profile_hash: str
    variants: tuple[ProfileVariant, ...]
    settings: SimSettings


def _target_slots(item: ItemSpec) -> tuple[str, ...]:
    return _DUAL_SLOTS.get(item.slot, (item.slot,))


def build_profileset_input(profile: SimcExport, settings: SimSettings) -> BuiltProfileSets:
    variants: list[ProfileVariant] = []
    profile_lines: list[str] = []
    seen_fingerprints: set[str] = set()
    for candidate in profile.candidates:
        if candidate.fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(candidate.fingerprint)
        for target_slot in _target_slots(candidate):
            identity = f"{candidate.fingerprint}:{target_slot}"
            suffix = hashlib.sha256(identity.encode("ascii")).hexdigest()[:12]
            name = f"item_{candidate.item_id}_{target_slot}_{suffix}"
            variant = ProfileVariant(
                profileset_name=name,
                item_id=candidate.item_id,
                item_fingerprint=candidate.fingerprint,
                item_name=candidate.name,
                source_slot=candidate.slot,
                target_slot=target_slot,
                options=candidate.options,
            )
            variants.append(variant)
            profile_lines.append(f'profileset."{name}"={target_slot}={candidate.options}')

    input_text = "\n".join(
        [
            profile.base_profile.rstrip(),
            "",
            f"iterations={settings.iterations}",
            f"fight_style={settings.fight_style}",
            "profileset_metric=dps",
            f"profileset_work_threads={settings.profileset_work_threads}",
            "",
            *profile_lines,
            "",
        ]
    )
    profile_hash = hashlib.sha256(input_text.encode("utf-8")).hexdigest()
    return BuiltProfileSets(
        input_text=input_text,
        profile_hash=profile_hash,
        variants=tuple(variants),
        settings=settings,
    )
