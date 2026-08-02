from types import SimpleNamespace

import pytest

from local_gear_advisor.cli import _parser, main


def test_cli_min_item_level_defaults_to_282_and_is_configurable() -> None:
    parser = _parser()
    base = ["analyze", "--input", "character.simc", "--simc", "simc.exe"]

    assert parser.parse_args(base).min_item_level == 282
    assert parser.parse_args([*base, "--min-item-level", "290"]).min_item_level == 290


def test_cli_passes_and_reports_applied_min_item_level(tmp_path, monkeypatch, capsys) -> None:
    export = tmp_path / "character.simc"
    export.write_text("safe export", encoding="utf-8")
    observed = {}

    def fake_analyze_export(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(
            character_name="Testadin",
            spec="protection",
            candidate_count=1,
            variant_count=1,
            simc_version="1205-01",
            excluded_weapon_count=0,
            excluded_weapons=(),
            excluded_below_min_item_level_count=2,
            excluded_unknown_item_level_count=0,
            min_item_level=290,
            results_path=tmp_path / "Results.lua",
            retained_profile_count=2,
            region="eu",
            realm="testrealm",
            spec_id=66,
            results_sha256="a" * 64,
        )

    monkeypatch.setattr("local_gear_advisor.cli.analyze_export", fake_analyze_export)

    result = main(
        [
            "analyze",
            "--input",
            str(export),
            "--simc",
            "simc.exe",
            "--min-item-level",
            "290",
        ]
    )

    assert result == 0
    assert observed["settings"].min_item_level == 290
    output = capsys.readouterr().out
    assert "2 Kandidat(en) unter Itemlevel 290" in output
    assert "Nur offensiver DPS-Vergleich" in output
    assert "2 gespeicherte Profile" in output


def test_cli_does_not_accept_arbitrary_output_path() -> None:
    with pytest.raises(SystemExit):
        _parser().parse_args(
            [
                "analyze",
                "--input",
                "character.simc",
                "--simc",
                "simc.exe",
                "--output",
                "C:/unsafe/Results.lua",
            ]
        )


def test_cli_stage_addon_creates_a_complete_byte_verified_manual_install_source(
    tmp_path, monkeypatch, capsys
) -> None:
    output = tmp_path / "LocalGearAdvisor"
    observed = {}

    def fake_extract(destination):
        observed["destination"] = destination
        destination.mkdir()
        return destination

    monkeypatch.setattr("local_gear_advisor.cli.extract_addon_template", fake_extract)

    assert main(["stage-addon", "--output", str(output)]) == 0
    assert observed["destination"] == output
    assert str(output) in capsys.readouterr().out


def _summary(tmp_path):
    return SimpleNamespace(
        character_name="Testadin",
        spec="protection",
        candidate_count=1,
        variant_count=1,
        simc_version="1205-01",
        excluded_weapon_count=0,
        excluded_weapons=(),
        excluded_below_min_item_level_count=0,
        excluded_unknown_item_level_count=0,
        min_item_level=282,
        results_path=tmp_path / "Results.lua",
        state_path=tmp_path / "profiles.json",
        retained_profile_count=1,
        region="eu",
        realm="testrealm",
        spec_id=66,
        results_sha256="b" * 64,
    )


def test_cli_live_install_requires_explicit_addon_directory(tmp_path, monkeypatch, capsys) -> None:
    export = tmp_path / "character.simc"
    export.write_text("safe export", encoding="utf-8")
    monkeypatch.setattr(
        "local_gear_advisor.cli.analyze_export", lambda **kwargs: _summary(tmp_path)
    )

    result = main(
        [
            "analyze",
            "--input",
            str(export),
            "--simc",
            "simc.exe",
            "--install-live",
        ]
    )

    assert result == 2
    assert "--addon-dir" in capsys.readouterr().err


def test_cli_explicit_live_install_uses_pinned_staged_hash(tmp_path, monkeypatch) -> None:
    export = tmp_path / "character.simc"
    export.write_text("safe export", encoding="utf-8")
    staged = tmp_path / "Results.lua"
    staged.write_text("result", encoding="utf-8")
    addon = tmp_path / "Interface" / "AddOns" / "LocalGearAdvisor"
    observed = {}
    summary = _summary(tmp_path)
    monkeypatch.setattr("local_gear_advisor.cli.analyze_export", lambda **kwargs: summary)
    monkeypatch.setattr(
        "local_gear_advisor.cli.expected_addon_assets", lambda: {"Core.lua": b"core"}
    )
    monkeypatch.setattr("local_gear_advisor.cli.utc_timestamp", lambda: "20260801T200000Z")

    def fake_publish(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(addon_dir=addon, backup=tmp_path / "backup.lua")

    monkeypatch.setattr("local_gear_advisor.cli.publish_results_live", fake_publish)

    assert (
        main(
            [
                "analyze",
                "--input",
                str(export),
                "--simc",
                "simc.exe",
                "--install-live",
                "--addon-dir",
                str(addon),
            ]
        )
        == 0
    )
    assert observed["expected_staged_sha256"] == "b" * 64
    assert observed["staged_results"] == staged
    assert observed["canonical_state_path"] == summary.state_path
    assert observed["addon_dir"] == addon
