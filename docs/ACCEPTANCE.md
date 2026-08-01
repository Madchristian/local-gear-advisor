# MVP Acceptance Matrix

Stand: 2026-08-01

This document separates automated/source verification from the still-required personal and in-game acceptance steps.

| Requirement | Status | Evidence / remaining step |
|---|---|---|
| Parse a complete official `/simc` export including bags | Verified with fixtures and a real bundled SimC profile | Parser tests; real local integration run |
| Never execute raw imported directives | Verified | Strict directive allowlist, duplicate rejection, value validation, and hostile-directive tests |
| Simulate each supported bag candidate against equipped baseline | Verified | Profileset tests and real trinket integration run |
| Try rings/trinkets in both legal slots | Verified | Profileset unit tests |
| Exclude coupled weapon changes without blocking supported items | Verified | Pipeline tests for weapons below and at/above the configured threshold; weapons are never simulated or published |
| Configurable minimum candidate item level | Verified | Parser, settings, pipeline and CLI/GUI plumbing tests; default 282, 0 disables filtering |
| Report all-excluded runs transparently without publishing | Verified | Below-threshold-only, unknown-level-only and weapon-only regression tests preserve the prior result |
| Validate complete baseline and unknown candidates | Verified | Parser/pipeline tests |
| Run `simc.exe` locally without a shell | Verified | Runner tests plus real Windows SimC nightly run |
| Validate JSON2 results and provenance | Verified | Runner/pipeline tests; real `1205-01`, revision `5a982a3`, WoW `12.0.7.68887`, DBC `Live` report |
| Add current specializations without runtime AI or per-Spec code branches | Verified | Deterministic generator produces 40 canonical entries from pinned SimC revision `5a982a3`; runtime and generator reject drift, malformed data, missing classes and revision mismatch fail-closed |
| Support Guardian Druid through registry data | Verified in parser/pipeline harness | Generic export path renders `druid/guardian` as WoW spec ID `104` without a pipeline special case; a personal Berker export remains an optional real-world acceptance run |
| Bind results to character, talents, traits, gear, scenario, build, and SimC provenance | Verified in source/runtime harness | Python/Lua tests and Fengari API-mock harness |
| Publish only to controlled staging, atomically and under lock | Verified | Safety/results/pipeline tests |
| Package the addon assets in the wheel | Verified | Clean wheel build and isolated wheel-install end-to-end run |
| Windows GitHub CI | Verified | CI runs Ruff, pytest, compileall, and build checks on `windows-latest` |
| Personal Protection Paladin `/simc` export | Verified locally | Sensimar: 69 unique candidates; at threshold 282, 65 filtered, 2 weapons excluded, 2 supported items / 4 slot variants simulated with 10,000 iterations |
| Live personal `Results.lua` installation | Verified | Installed after a fresh fail-closed check proved `Wow.exe` was stopped; live addon and personal result were byte-verified |
| WoW Retail 12.0.7 personal-result tooltip smoke test | Pending | Install reviewed personal result, start WoW, verify both item tooltips and inspect BugGrabber/BugSack |

A GitHub repository or green automated suite is not a substitute for the final in-game smoke test.
