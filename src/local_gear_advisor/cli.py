from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import PROJECT_ROOT, PROJECT_STAGING_RESULTS, analyze_export
from .profilesets import SimSettings

DEFAULT_RESULTS = PROJECT_STAGING_RESULTS
DEFAULT_RUN_ROOT = PROJECT_ROOT / "state" / "runs"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="local-gear-advisor")
    sub = parser.add_subparsers(dest="command")
    analyze = sub.add_parser("analyze", help="analyze a saved /simc export")
    analyze.add_argument("--input", type=Path, required=True)
    analyze.add_argument("--simc", type=Path, required=True)
    analyze.add_argument("--iterations", type=int, default=1000)
    analyze.add_argument(
        "--min-item-level",
        type=int,
        default=282,
        help="minimum candidate item level; 0 disables the filter (default: 282)",
    )
    analyze.add_argument(
        "--fight-style", choices=("Patchwerk", "DungeonSlice"), default="Patchwerk"
    )
    analyze.add_argument("--timeout", type=int, default=900)
    sub.add_parser("gui", help="open the local desktop interface")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command in (None, "gui"):
        from .gui import launch

        launch()
        return 0
    if args.command == "analyze":
        try:
            summary = analyze_export(
                export_text=args.input.read_text(encoding="utf-8"),
                executable=args.simc,
                settings=SimSettings(
                    iterations=args.iterations,
                    fight_style=args.fight_style,
                    min_item_level=args.min_item_level,
                ),
                results_path=DEFAULT_RESULTS,
                run_root=DEFAULT_RUN_ROOT,
                timeout_seconds=args.timeout,
            )
        except Exception as exc:
            print(f"Fehler: {exc}", file=sys.stderr)
            return 2
        print(
            f"OK: {summary.character_name} ({summary.spec}), "
            f"{summary.candidate_count} Items / {summary.variant_count} Varianten, "
            f"SimC {summary.simc_version}"
        )
        if summary.excluded_weapon_count:
            weapons = ", ".join(
                f"{weapon.name or 'item ' + str(weapon.item_id)} "
                f"(id={weapon.item_id}, {weapon.slot})"
                for weapon in summary.excluded_weapons
            )
            print(
                f"Ausgeschlossen: {summary.excluded_weapon_count} Waffen-Kandidat(en) "
                f"noch nicht unterstützt, nicht simuliert/veröffentlicht: {weapons}"
            )
        if summary.excluded_below_min_item_level_count:
            print(
                "Ausgeschlossen: "
                f"{summary.excluded_below_min_item_level_count} Kandidat(en) unter "
                f"Itemlevel {summary.min_item_level}."
            )
        if summary.excluded_unknown_item_level_count:
            print(
                "Ausgeschlossen: "
                f"{summary.excluded_unknown_item_level_count} Kandidat(en) mit "
                "unbekanntem oder ungültigem Itemlevel."
            )
        print(f"Ergebnis: {summary.results_path}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
