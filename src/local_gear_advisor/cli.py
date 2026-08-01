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
        print(f"Ergebnis: {summary.results_path}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
