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
