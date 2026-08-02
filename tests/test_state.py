from dataclasses import replace
from pathlib import Path

import pytest
from luaparser import ast

from local_gear_advisor.state import (
    AggregateState,
    ProfileItem,
    ProfileRecord,
    StateError,
    empty_state,
    load_state,
    merge_profile,
    normalize_identity,
    publish_profile_update,
    render_aggregate_lua,
    save_state,
)


def _record(
    *,
    region: str = "eu",
    realm: str = "TestRealm",
    name: str = "Testadin",
    spec_id: int = 66,
    character_class: str = "paladin",
    spec: str = "protection",
    generated_at: int = 1785573600,
) -> ProfileRecord:
    return ProfileRecord(
        identity=normalize_identity(region=region, realm=realm, name=name, spec_id=spec_id),
        character_class=character_class,
        spec=spec,
        level=90,
        race="maghar_orc",
        talents="CYQA...",
        trait_systems={"omnium_talents": "100:1/200:1"},
        baseline_gear={
            "head": ",id=100001",
            "neck": ",id=100002",
            "shoulder": None,
            "back": None,
            "chest": None,
            "wrist": None,
            "hands": None,
            "waist": None,
            "legs": None,
            "feet": None,
            "finger1": ",id=100101,enchant_id=7001,bonus_id=10/20",
            "finger2": None,
            "trinket1": None,
            "trinket2": None,
            "main_hand": ",id=100301",
            "off_hand": None,
        },
        fight_style="Patchwerk",
        baseline_dps=100000.0,
        simc_version="1205-01",
        simc_revision="5a982a3",
        game_version="12.0.7.68887",
        dbc_source="Live",
        profile_hash="a" * 64,
        generated_at=generated_at,
        items=(
            ProfileItem(
                options=",id=200101,gem_id=3001/0/3002,bonus_id=50/51",
                item_id=200101,
                item_name="Candidate Ring (253)",
                fingerprint="b" * 64,
                best_slot="finger2",
                candidate_dps=102000.0,
                delta_percent=2.0,
                iterations=2500,
            ),
        ),
    )


def test_normalize_identity_matches_wow_runtime_tokens() -> None:
    identity = normalize_identity(
        region="EU", realm="La Croisade écarlate", name="Testadin", spec_id=66
    )

    assert identity.region == "eu"
    assert identity.realm == "la_croisade_écarlate"
    assert identity.name == "Testadin"
    assert identity.spec_id == 66


def test_normalize_identity_rejects_empty_fields() -> None:
    with pytest.raises(StateError):
        normalize_identity(region="", realm="testrealm", name="Testadin", spec_id=66)
    with pytest.raises(StateError):
        normalize_identity(region="eu", realm="testrealm", name="Testadin", spec_id=0)
    with pytest.raises(StateError, match="empty after WoW tokenization"):
        normalize_identity(region="eu", realm="!!!", name="Testadin", spec_id=66)
    with pytest.raises(StateError, match="unsupported region"):
        normalize_identity(region="moon", realm="testrealm", name="Testadin", spec_id=66)


def test_empty_state_has_no_profiles_and_is_valid_v2() -> None:
    state = empty_state()

    assert state.profiles == ()
    lua = render_aggregate_lua(state)
    assert "schemaVersion = 2" in lua
    assert "profiles = {" in lua
    ast.parse(lua)


def test_merge_profile_keeps_distinct_identities_coexisting() -> None:
    state = empty_state()
    state = merge_profile(state, _record(name="Alice", spec_id=66))
    state = merge_profile(state, _record(name="Bob", spec_id=66))

    assert {r.identity.name for r in state.profiles} == {"Alice", "Bob"}


def test_merge_profile_replaces_only_matching_identity() -> None:
    state = empty_state()
    state = merge_profile(state, _record(name="Alice", spec_id=66, generated_at=1000))
    state = merge_profile(state, _record(name="Bob", spec_id=66, generated_at=1000))
    state = merge_profile(state, _record(name="Alice", spec_id=66, generated_at=2000))

    assert len(state.profiles) == 2
    alice = next(r for r in state.profiles if r.identity.name == "Alice")
    bob = next(r for r in state.profiles if r.identity.name == "Bob")
    assert alice.generated_at == 2000
    assert bob.generated_at == 1000


def test_merge_profile_retains_two_specs_of_same_character() -> None:
    state = empty_state()
    state = merge_profile(state, _record(name="Alice", spec_id=66, spec="protection"))
    state = merge_profile(state, _record(name="Alice", spec_id=70, spec="retribution"))

    assert len(state.profiles) == 2
    assert {r.spec for r in state.profiles} == {"protection", "retribution"}


def test_merge_profile_identity_is_case_insensitive_on_region_and_realm() -> None:
    state = empty_state()
    state = merge_profile(state, _record(region="eu", realm="testrealm"))
    state = merge_profile(state, _record(region="EU", realm="TESTREALM"))

    assert len(state.profiles) == 1


def test_save_and_load_state_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "state" / "profiles.json"
    state = empty_state()
    state = merge_profile(state, _record(name="Alice", spec_id=66))
    state = merge_profile(state, _record(name="Bob", spec_id=70, spec="retribution"))

    save_state(path, state)
    loaded = load_state(path)

    assert {r.identity.name for r in loaded.profiles} == {"Alice", "Bob"}
    bob = next(r for r in loaded.profiles if r.identity.name == "Bob")
    assert bob.spec == "retribution"
    assert bob.items[0].item_id == 200101


def test_load_state_missing_file_returns_empty_state(tmp_path: Path) -> None:
    state = load_state(tmp_path / "state" / "profiles.json")

    assert state.profiles == ()


def test_load_state_rejects_duplicate_identity(tmp_path: Path) -> None:
    path = tmp_path / "profiles.json"
    payload = (
        '{"schemaVersion": 2, "profiles": ['
        '{"identity": {"region": "eu", "realm": "r", "name": "A", "specId": 66}, "duplicate": 1},'
        '{"identity": {"region": "eu", "realm": "r", "name": "A", "specId": 66}, "duplicate": 2}'
        "]}"
    )
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(StateError, match="duplicate"):
        load_state(path)


def test_load_state_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "profiles.json"
    path.write_text('{"schemaVersion": 2, "schemaVersion": 2, "profiles": []}', encoding="utf-8")

    with pytest.raises(StateError, match="duplicate"):
        load_state(path)


def test_load_state_rejects_wrong_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "profiles.json"
    path.write_text('{"schemaVersion": 1, "profiles": []}', encoding="utf-8")

    with pytest.raises(StateError, match="schemaVersion"):
        load_state(path)


def test_load_state_rejects_nonfinite_dps(tmp_path: Path) -> None:
    path = tmp_path / "profiles.json"
    state = merge_profile(empty_state(), _record())
    save_state(path, state)
    text = path.read_text(encoding="utf-8").replace("100000.0", "NaN")
    path.write_text(text, encoding="utf-8")

    with pytest.raises(StateError):
        load_state(path)


def test_load_state_rejects_invalid_hashes_and_extra_trait_systems(tmp_path: Path) -> None:
    path = tmp_path / "profiles.json"
    state = merge_profile(empty_state(), _record())
    save_state(path, state)
    original = path.read_text(encoding="utf-8")

    path.write_text(
        original.replace('"profileHash": "' + "a" * 64 + '"', '"profileHash": "no"'),
        encoding="utf-8",
    )
    with pytest.raises(StateError, match="profileHash"):
        load_state(path)

    path.write_text(
        original.replace(
            '"omnium_talents": "100:1/200:1"',
            '"extra": "unsafe", "omnium_talents": "100:1/200:1"',
        ),
        encoding="utf-8",
    )
    with pytest.raises(StateError, match="traitSystems"):
        load_state(path)


def test_load_state_rejects_duplicate_item_fingerprint(tmp_path: Path) -> None:
    path = tmp_path / "profiles.json"
    record = _record()
    duplicate = ProfileItem(
        options=",id=200102",
        item_id=200102,
        item_name="Other",
        fingerprint=record.items[0].fingerprint,
        best_slot="finger1",
        candidate_dps=101000.0,
        delta_percent=1.0,
        iterations=2500,
    )
    invalid = AggregateState(profiles=(replace(record, items=record.items + (duplicate,)),))

    with pytest.raises(StateError, match="duplicate item fingerprint"):
        save_state(path, invalid)


def test_save_state_rejects_item_option_id_mismatch(tmp_path: Path) -> None:
    record = _record()
    mismatched = replace(record.items[0], options=",id=999999")
    invalid = AggregateState(profiles=(replace(record, items=(mismatched,)),))

    with pytest.raises(StateError, match="does not match"):
        save_state(tmp_path / "profiles.json", invalid)


def test_save_state_rejects_duplicate_item_option_keys(tmp_path: Path) -> None:
    record = _record()
    duplicated = replace(record.items[0], options=",id=200101,bonus_id=1,bonus_id=2")
    invalid = AggregateState(profiles=(replace(record, items=(duplicated,)),))

    with pytest.raises(StateError, match="duplicate option keys"):
        save_state(tmp_path / "profiles.json", invalid)


def test_render_orders_items_deterministically_by_options() -> None:
    record = _record()
    earlier = ProfileItem(
        options=",id=100000",
        item_id=100000,
        item_name="Earlier",
        fingerprint="c" * 64,
        best_slot="head",
        candidate_dps=99000.0,
        delta_percent=-1.0,
        iterations=2500,
    )
    lua = render_aggregate_lua(
        AggregateState(profiles=(replace(record, items=record.items + (earlier,)),))
    )

    assert lua.index('[",id=100000"]') < lua.index('[",id=200101')


def test_load_state_rejects_tampered_extra_key(tmp_path: Path) -> None:
    path = tmp_path / "profiles.json"
    path.write_text('{"schemaVersion": 2, "profiles": [], "extra": true}', encoding="utf-8")

    with pytest.raises(StateError):
        load_state(path)


def test_render_aggregate_lua_is_deterministic_and_isolates_records() -> None:
    state = empty_state()
    state = merge_profile(state, _record(name="Alice", spec_id=66))
    state = merge_profile(state, _record(name="Bob", spec_id=70, spec="retribution"))

    first = render_aggregate_lua(state)
    second = render_aggregate_lua(state)

    assert first == second
    assert first.count('characterName = "Alice"') == 1
    assert first.count('characterName = "Bob"') == 1
    ast.parse(first)


def test_render_aggregate_lua_keys_items_by_exact_options_per_profile() -> None:
    state = merge_profile(empty_state(), _record())
    lua = render_aggregate_lua(state)

    assert '[",id=200101,gem_id=3001/0/3002,bonus_id=50/51"]' in lua
    assert 'bestSlot = "finger2"' in lua
    assert "off_hand = false" in lua
    assert 'finger1 = ",id=100101,enchant_id=7001,bonus_id=10/20"' in lua


def test_aggregate_state_is_immutable_and_ordered_deterministically() -> None:
    state = AggregateState(profiles=())
    assert state.profiles == ()


def test_publish_profile_update_writes_state_and_lua_together(tmp_path: Path) -> None:
    state_path = tmp_path / "state" / "profiles.json"
    results_path = tmp_path / "addon" / "Results.lua"

    published = publish_profile_update(
        state_path=state_path, results_path=results_path, record=_record(name="Alice")
    )

    assert published.profiles[0].identity.name == "Alice"
    assert load_state(state_path).profiles[0].identity.name == "Alice"
    assert 'characterName = "Alice"' in results_path.read_text(encoding="utf-8")


def test_publish_profile_update_merges_sequential_updates_without_losing_either(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "state" / "profiles.json"
    results_path = tmp_path / "addon" / "Results.lua"

    publish_profile_update(
        state_path=state_path, results_path=results_path, record=_record(name="Alice")
    )
    second = publish_profile_update(
        state_path=state_path, results_path=results_path, record=_record(name="Bob", spec_id=70)
    )

    assert {r.identity.name for r in second.profiles} == {"Alice", "Bob"}
    reloaded = load_state(state_path)
    assert {r.identity.name for r in reloaded.profiles} == {"Alice", "Bob"}
    published_lua = results_path.read_text(encoding="utf-8")
    assert 'characterName = "Alice"' in published_lua
    assert 'characterName = "Bob"' in published_lua


def test_publish_profile_update_rejects_concurrent_lock_contention_and_touches_nothing(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "state" / "profiles.json"
    results_path = tmp_path / "addon" / "Results.lua"
    publish_profile_update(
        state_path=state_path, results_path=results_path, record=_record(name="Alice")
    )
    state_before = state_path.read_bytes()
    lua_before = results_path.read_bytes()

    lock_path = state_path.with_name(state_path.name + ".publish.lock")
    import local_gear_advisor.state as state_module

    with state_module._exclusive_state_lock(lock_path):
        with pytest.raises(StateError, match="already in progress"):
            publish_profile_update(
                state_path=state_path, results_path=results_path, record=_record(name="Bob")
            )

    assert state_path.read_bytes() == state_before
    assert results_path.read_bytes() == lua_before


def test_publish_profile_update_restores_both_files_when_lua_write_fails(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "state" / "profiles.json"
    results_path = tmp_path / "addon" / "Results.lua"
    publish_profile_update(
        state_path=state_path, results_path=results_path, record=_record(name="Alice")
    )
    state_before = state_path.read_bytes()
    lua_before = results_path.read_bytes()

    def failing_writer(path: Path, content: str) -> None:
        import local_gear_advisor.state as state_module

        state_module._atomic_text_writer(path, content)
        raise OSError("simulated disk failure while publishing Results.lua")

    with pytest.raises(OSError, match="simulated disk failure"):
        publish_profile_update(
            state_path=state_path,
            results_path=results_path,
            record=_record(name="Bob", spec_id=70),
            lua_writer=failing_writer,
        )

    assert state_path.read_bytes() == state_before
    assert results_path.read_bytes() == lua_before
    assert {r.identity.name for r in load_state(state_path).profiles} == {"Alice"}


def test_publish_profile_update_recovers_both_files_after_process_interruption(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "state" / "profiles.json"
    results_path = tmp_path / "addon" / "Results.lua"
    publish_profile_update(
        state_path=state_path, results_path=results_path, record=_record(name="Alice")
    )

    lua_before = results_path.read_bytes()

    def interrupted_writer(_path: Path, _content: str) -> None:
        raise KeyboardInterrupt("simulated process interruption")

    with pytest.raises(KeyboardInterrupt, match="process interruption"):
        publish_profile_update(
            state_path=state_path,
            results_path=results_path,
            record=_record(name="Bob", spec_id=70),
            lua_writer=interrupted_writer,
        )

    journal = state_path.with_name(state_path.name + ".publish.pending.json")
    assert journal.is_file()
    assert results_path.read_bytes() == lua_before

    recovered = publish_profile_update(
        state_path=state_path,
        results_path=results_path,
        record=_record(name="Carol", spec_id=70),
    )

    assert {record.identity.name for record in recovered.profiles} == {"Alice", "Carol"}
    assert {record.identity.name for record in load_state(state_path).profiles} == {
        "Alice",
        "Carol",
    }
    published = results_path.read_text(encoding="utf-8")
    assert 'characterName = "Alice"' in published
    assert 'characterName = "Carol"' in published
    assert 'characterName = "Bob"' not in published
    assert not journal.exists()


def test_pending_recovery_refuses_to_overwrite_a_foreign_generation(tmp_path: Path) -> None:
    state_path = tmp_path / "state" / "profiles.json"
    results_path = tmp_path / "addon" / "Results.lua"
    publish_profile_update(
        state_path=state_path, results_path=results_path, record=_record(name="Alice")
    )

    def interrupted_writer(_path: Path, _content: str) -> None:
        raise KeyboardInterrupt("simulated process interruption")

    with pytest.raises(KeyboardInterrupt):
        publish_profile_update(
            state_path=state_path,
            results_path=results_path,
            record=_record(name="Bob", spec_id=70),
            lua_writer=interrupted_writer,
        )

    foreign = b"foreign concurrent Results.lua generation"
    results_path.write_bytes(foreign)
    with pytest.raises(StateError, match="refused a foreign generation"):
        publish_profile_update(
            state_path=state_path,
            results_path=results_path,
            record=_record(name="Carol", spec_id=70),
        )
    assert results_path.read_bytes() == foreign
    assert state_path.with_name(state_path.name + ".publish.pending.json").is_file()


def test_ordinary_writer_failure_does_not_overwrite_a_foreign_generation(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "state" / "profiles.json"
    results_path = tmp_path / "addon" / "Results.lua"
    publish_profile_update(
        state_path=state_path, results_path=results_path, record=_record(name="Alice")
    )
    foreign = "foreign concurrent Results.lua generation"

    def foreign_writer(path: Path, _content: str) -> None:
        path.write_text(foreign, encoding="utf-8")
        raise OSError("foreign writer won before local error handling")

    with pytest.raises(StateError, match="refused a foreign generation"):
        publish_profile_update(
            state_path=state_path,
            results_path=results_path,
            record=_record(name="Bob", spec_id=70),
            lua_writer=foreign_writer,
        )
    assert results_path.read_text(encoding="utf-8") == foreign


@pytest.mark.parametrize(
    ("record", "message"),
    [
        (replace(_record(), baseline_dps=1_000_000_000_001.0), "baselineDps"),
        (
            replace(
                _record(),
                items=(replace(_record().items[0], candidate_dps=1_000_000_000_001.0),),
            ),
            "candidateDps",
        ),
        (
            replace(
                _record(),
                items=(replace(_record().items[0], delta_percent=1_000_001.0),),
            ),
            "deltaPercent",
        ),
    ],
)
def test_render_rejects_implausible_dps_and_delta_ranges(
    record: ProfileRecord, message: str
) -> None:
    with pytest.raises(StateError, match=message):
        render_aggregate_lua(AggregateState(profiles=(record,)))


def test_render_rejects_generated_timestamp_outside_lua_exact_integer_range() -> None:
    record = replace(_record(), generated_at=9_007_199_254_740_992)
    with pytest.raises(StateError, match="generatedAt is out of range"):
        render_aggregate_lua(AggregateState(profiles=(record,)))


def test_control_characters_are_rejected_before_lua_rendering() -> None:
    record = _record()
    invalid_item = replace(record.items[0], item_name="bad\rname")
    with pytest.raises(StateError, match="control character"):
        render_aggregate_lua(AggregateState(profiles=(replace(record, items=(invalid_item,)),)))


def test_publish_profile_update_first_write_failure_leaves_no_half_state(tmp_path: Path) -> None:
    state_path = tmp_path / "state" / "profiles.json"
    results_path = tmp_path / "addon" / "Results.lua"

    def failing_writer(_path: Path, _content: str) -> None:
        raise OSError("simulated disk failure while publishing Results.lua")

    with pytest.raises(OSError, match="simulated disk failure"):
        publish_profile_update(
            state_path=state_path,
            results_path=results_path,
            record=_record(name="Alice"),
            lua_writer=failing_writer,
        )

    assert not state_path.exists()
    assert not results_path.exists()
