from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from luaparser import ast
from luaparser import astnodes as nodes

from local_gear_advisor.pipeline import PROJECT_STAGING_RESULTS, PROJECT_STATE_PATH
from local_gear_advisor.state import (
    ProfileItem,
    ProfileRecord,
    normalize_identity,
    publish_profile_update,
)

_ROOT_KEYS = {
    "schemaVersion",
    "generatedAt",
    "profileHash",
    "simcVersion",
    "simcRevision",
    "gameVersion",
    "dbcSource",
    "characterName",
    "region",
    "server",
    "class",
    "spec",
    "specID",
    "level",
    "race",
    "talents",
    "traitSystems",
    "baselineGear",
    "fightStyle",
    "baselineDps",
    "items",
}
_ITEM_KEYS = {
    "itemID",
    "name",
    "fingerprint",
    "bestSlot",
    "candidateDps",
    "deltaPercent",
    "iterations",
    "status",
}
_BASELINE_SLOTS = {
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
}


class MigrationError(RuntimeError):
    pass


def _key(node: nodes.Node) -> str:
    if isinstance(node, nodes.Name):
        return node.id
    if isinstance(node, nodes.String):
        return node.s.decode("utf-8")
    raise MigrationError(f"unsupported Lua table key node: {type(node).__name__}")


def _literal(node: nodes.Node) -> Any:
    if isinstance(node, nodes.String):
        return node.s.decode("utf-8")
    if isinstance(node, nodes.Number):
        return node.n
    if isinstance(node, nodes.UMinusOp) and isinstance(node.operand, nodes.Number):
        return -node.operand.n
    if isinstance(node, nodes.FalseExpr):
        return False
    if isinstance(node, nodes.TrueExpr):
        return True
    if isinstance(node, nodes.Nil):
        return None
    if isinstance(node, nodes.Table):
        result: dict[str, Any] = {}
        for field in node.fields:
            if not isinstance(field, nodes.Field) or field.key is None:
                raise MigrationError("schema-v1 tables must contain only explicit keyed fields")
            key = _key(field.key)
            if key in result:
                raise MigrationError(f"duplicate Lua table key: {key!r}")
            result[key] = _literal(field.value)
        return result
    raise MigrationError(f"non-literal Lua node is forbidden: {type(node).__name__}")


def _exact_dict(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        found = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise MigrationError(f"{label} keys mismatch: {found}")
    return value


def parse_generated_v1(text: str) -> ProfileRecord:
    if len(text.encode("utf-8")) > 2 * 1024 * 1024:
        raise MigrationError("schema-v1 Results.lua exceeds 2 MiB")
    try:
        tree = ast.parse(text)
    except Exception as exc:
        raise MigrationError(f"schema-v1 Results.lua is not valid Lua: {exc}") from exc
    statements = tree.body.body
    if len(statements) != 1 or not isinstance(statements[0], nodes.Assign):
        raise MigrationError("schema-v1 Results.lua must contain exactly one assignment")
    assignment = statements[0]
    if len(assignment.targets) != 1 or len(assignment.values) != 1:
        raise MigrationError("schema-v1 assignment shape is invalid")
    target = assignment.targets[0]
    if not isinstance(target, nodes.Name) or target.id != "LocalGearAdvisorResults":
        raise MigrationError("schema-v1 assignment target is invalid")
    root = _exact_dict(_literal(assignment.values[0]), _ROOT_KEYS, "root")
    if type(root["schemaVersion"]) is not int or root["schemaVersion"] != 1:
        raise MigrationError("only generated schemaVersion 1 results can be migrated")
    traits = _exact_dict(root["traitSystems"], {"omnium_talents"}, "traitSystems")
    baseline = _exact_dict(root["baselineGear"], _BASELINE_SLOTS, "baselineGear")
    items_raw = root["items"]
    if not isinstance(items_raw, dict):
        raise MigrationError("items must be a keyed table")
    items: list[ProfileItem] = []
    for options, raw in items_raw.items():
        item = _exact_dict(raw, _ITEM_KEYS, f"item {options!r}")
        if item["status"] != "simulated":
            raise MigrationError(f"item {options!r} has an unsupported status")
        items.append(
            ProfileItem(
                options=options,
                item_id=item["itemID"],
                item_name=item["name"] or None,
                fingerprint=item["fingerprint"],
                best_slot=item["bestSlot"],
                candidate_dps=item["candidateDps"],
                delta_percent=item["deltaPercent"],
                iterations=item["iterations"],
            )
        )
    return ProfileRecord(
        identity=normalize_identity(
            region=root["region"],
            realm=root["server"],
            name=root["characterName"],
            spec_id=root["specID"],
        ),
        character_class=root["class"],
        spec=root["spec"],
        level=root["level"],
        race=root["race"],
        talents=root["talents"],
        trait_systems=traits,
        baseline_gear={key: (None if value is False else value) for key, value in baseline.items()},
        fight_style=root["fightStyle"],
        baseline_dps=root["baselineDps"],
        simc_version=root["simcVersion"],
        simc_revision=root["simcRevision"],
        game_version=root["gameVersion"],
        dbc_source=root["dbcSource"],
        profile_hash=root["profileHash"],
        generated_at=root["generatedAt"],
        items=tuple(sorted(items, key=lambda value: value.options)),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate generated schema-v1 Results.lua archives")
    parser.add_argument("inputs", nargs="+", type=Path)
    args = parser.parse_args(argv)
    records = [parse_generated_v1(path.read_text(encoding="utf-8")) for path in args.inputs]
    state = None
    for record in records:
        state = publish_profile_update(
            state_path=PROJECT_STATE_PATH,
            results_path=PROJECT_STAGING_RESULTS,
            record=record,
        )
    print(
        f"Migrated {len(records)} profile(s); aggregate now contains "
        f"{len(state.profiles)} profile(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
