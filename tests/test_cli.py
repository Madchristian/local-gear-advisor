import pytest

from local_gear_advisor.cli import _parser


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
