from pathlib import Path

import pytest

from local_gear_advisor.simc_export import parse_simc_export

FIXTURE = Path(__file__).parent / "fixtures" / "sample.simc"


def test_parse_export_separates_equipped_gear_and_bag_candidates() -> None:
    profile = parse_simc_export(FIXTURE.read_text(encoding="utf-8"))

    assert profile.character_class == "paladin"
    assert profile.character_name == "Testadin"
    assert profile.spec == "protection"
    assert profile.region == "eu"
    assert profile.server == "testrealm"
    assert profile.talents == "CYQA..."
    assert profile.trait_systems == {"omnium_talents": "100:1/200:1"}
    assert profile.equipped["finger1"].item_id == 100101
    assert profile.equipped["trinket2"].item_id == 100202

    assert [candidate.item_id for candidate in profile.candidates] == [200101, 200201, 200001]
    assert profile.candidates[0].name == "Candidate Ring (253)"
    assert profile.candidates[0].slot == "finger1"
    assert profile.candidates[0].options == ",id=200101,gem_id=3001/0/3002,bonus_id=50/51"


def test_parse_export_excludes_commented_bag_lines_from_baseline() -> None:
    profile = parse_simc_export(FIXTURE.read_text(encoding="utf-8"))

    assert "### Gear from Bags" not in profile.base_profile
    assert "id=200101" not in profile.base_profile
    assert "id=300101" not in profile.base_profile
    assert 'paladin="Testadin"' in profile.base_profile
    assert "trinket1=,id=100201" in profile.base_profile


def test_parse_export_warns_instead_of_silently_scoring_malformed_candidate() -> None:
    profile = parse_simc_export(FIXTURE.read_text(encoding="utf-8"))

    assert len(profile.warnings) == 1
    assert profile.warnings[0].line_number > 0
    assert "item id" in profile.warnings[0].message.lower()


def test_parse_warns_on_unsupported_candidate_slot() -> None:
    text = FIXTURE.read_text(encoding="utf-8").replace(
        "# head=this_has_no_item_id", "# relic=,id=999001"
    )
    profile = parse_simc_export(text)

    assert any("unsupported equipment slot" in warning.message for warning in profile.warnings)


def test_parse_warns_when_candidate_name_has_no_item_line() -> None:
    text = FIXTURE.read_text(encoding="utf-8").replace(
        "### Weekly Reward Choices",
        "#\n# Missing Candidate Line\n#\n### Weekly Reward Choices",
    )
    profile = parse_simc_export(text)

    assert any("description has no item line" in warning.message for warning in profile.warnings)


def test_duplicate_profile_directives_are_rejected() -> None:
    text = FIXTURE.read_text(encoding="utf-8").replace(
        "spec=protection", "spec=protection\nspec=retribution"
    )

    with pytest.raises(ValueError, match="duplicate SimC directive.*spec"):
        parse_simc_export(text)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('paladin="Testadin"', 'paladin="bad;name"'),
        ("region=eu", "region=evil"),
        ("server=testrealm", "server=x;html=C:/unsafe"),
        ("level=90", "level=999"),
        ("talents=CYQA...", "talents=bad;html=C:/unsafe"),
        ("omnium_talents=100:1/200:1", "omnium_talents=bogus"),
    ],
)
def test_invalid_or_unsafe_bound_profile_values_are_rejected(old: str, new: str) -> None:
    text = FIXTURE.read_text(encoding="utf-8").replace(old, new)

    with pytest.raises(ValueError):
        parse_simc_export(text)


def test_exact_candidate_identity_changes_with_bonus_ids() -> None:
    text = FIXTURE.read_text(encoding="utf-8")
    first = parse_simc_export(text).candidates[0]
    second = parse_simc_export(text.replace("bonus_id=50/51", "bonus_id=50/52")).candidates[0]

    assert first.fingerprint != second.fingerprint


def test_unknown_active_simc_directive_is_rejected() -> None:
    text = FIXTURE.read_text(encoding="utf-8").replace(
        'paladin="Testadin"',
        'paladin="Testadin"\nhtml=C:/Users/TestUser/Desktop/report.html',
    )
    try:
        parse_simc_export(text)
    except ValueError as error:
        assert "unsafe or unsupported" in str(error)
    else:
        raise AssertionError("unsafe SimC directive was accepted")


def test_source_import_or_network_value_is_rejected() -> None:
    text = FIXTURE.read_text(encoding="utf-8").replace(
        'paladin="Testadin"',
        'paladin="Testadin"\nsource=https://example.invalid/profile.simc',
    )
    try:
        parse_simc_export(text)
    except ValueError as error:
        assert "source=default" in str(error)
    else:
        raise AssertionError("network source was accepted")
