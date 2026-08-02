from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .deploy_results import (
    expected_addon_assets,
    extract_addon_template,
    publish_results_live,
    utc_timestamp,
)
from .pipeline import PROJECT_ROOT, PROJECT_STAGING_RESULTS, analyze_export
from .profilesets import SimSettings

DEFAULT_RESULTS = PROJECT_STAGING_RESULTS
DEFAULT_RUN_ROOT = PROJECT_ROOT / "state" / "runs"
DEFAULT_DEPLOY_RECEIPT = PROJECT_ROOT / "state" / "live-results-receipt.json"


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
    analyze.add_argument(
        "--install-live",
        action="store_true",
        help="install the verified aggregate Results.lua after analysis (requires --addon-dir)",
    )
    analyze.add_argument("--addon-dir", type=Path)
    stage_addon = sub.add_parser(
        "stage-addon", help="extract a byte-verified addon folder for manual installation"
    )
    stage_addon.add_argument("--output", type=Path, required=True)
    sub.add_parser("gui", help="open the local desktop interface")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command in (None, "gui"):
        from .gui import launch

        launch()
        return 0
    if args.command == "stage-addon":
        try:
            output = extract_addon_template(args.output)
        except Exception as exc:
            print(f"Fehler: {exc}", file=sys.stderr)
            return 2
        print(f"Addon-Staging bytegenau erstellt: {output}")
        return 0
    if args.command == "analyze":
        if args.install_live and args.addon_dir is None:
            print("Fehler: --install-live erfordert --addon-dir.", file=sys.stderr)
            return 2
        if args.addon_dir is not None and not args.install_live:
            print(
                "Fehler: --addon-dir darf nur mit --install-live verwendet werden.", file=sys.stderr
            )
            return 2
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
        print(
            f"Profil: {summary.region}/{summary.realm}/{summary.character_name}/"
            f"Spec {summary.spec_id}; {summary.retained_profile_count} gespeicherte Profile."
        )
        print("Hinweis: Nur offensiver DPS-Vergleich; keine defensive Tank- oder Heilermetrik.")
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
        if args.install_live:
            try:
                receipt = publish_results_live(
                    staged_results=summary.results_path,
                    canonical_state_path=summary.state_path,
                    expected_staged_sha256=summary.results_sha256,
                    addon_dir=args.addon_dir,
                    expected_code_files=expected_addon_assets(),
                    receipt_path=DEFAULT_DEPLOY_RECEIPT,
                    timestamp=utc_timestamp(),
                )
            except Exception as exc:
                print(
                    f"Installation blockiert/fehlgeschlagen; Staging bleibt erhalten: {exc}",
                    file=sys.stderr,
                )
                return 2
            print(f"Installiert: {receipt.addon_dir} (Backup: {receipt.backup})")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
