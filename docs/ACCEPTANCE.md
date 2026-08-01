# MVP Acceptance Matrix

Stand: 2026-08-01

This document separates automated/source verification from the still-required personal and in-game acceptance steps.

| Requirement | Status | Evidence / remaining step |
|---|---|---|
| Parse a complete official `/simc` export including bags | Verified with fixtures and a real bundled SimC profile | Parser tests; real local integration run |
| Never execute raw imported directives | Verified | Strict directive allowlist, duplicate rejection, value validation, and hostile-directive tests |
| Simulate each supported bag candidate against equipped baseline | Verified | Profileset tests and real trinket integration run |
| Try rings/trinkets in both legal slots | Verified | Profileset unit tests |
| Reject coupled weapon changes | Verified | Pipeline fail-closed tests |
| Validate complete baseline and unknown candidates | Verified | Parser/pipeline tests |
| Run `simc.exe` locally without a shell | Verified | Runner tests plus real Windows SimC nightly run |
| Validate JSON2 results and provenance | Verified | Runner/pipeline tests; real `1205-01`, revision `5a982a3`, WoW `12.0.7.68887`, DBC `Live` report |
| Bind results to character, talents, traits, gear, scenario, build, and SimC provenance | Verified in source/runtime harness | Python/Lua tests and Fengari API-mock harness |
| Publish only to controlled staging, atomically and under lock | Verified | Safety/results/pipeline tests |
| Package the addon assets in the wheel | Verified | Clean wheel build and isolated wheel-install end-to-end run |
| Windows GitHub CI | Verified | CI runs Ruff, pytest, compileall, and build checks on `windows-latest` |
| Personal Elemental Shaman `/simc` export | Pending | User must provide a fresh full `/simc` export with bags |
| Live addon installation | Blocked while WoW runs | Perform separately only after `Wow.exe` is definitely stopped |
| WoW Retail 12.0.7 in-game tooltip smoke test | Pending | Install staging addon, start WoW, verify matching/stale/unsupported tooltips and inspect BugGrabber/BugSack |

A GitHub repository or green automated suite is not a substitute for the final in-game smoke test.
