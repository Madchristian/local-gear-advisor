# MVP Acceptance Matrix

Stand: 2026-08-02

This document separates automated/source verification from the still-required in-game acceptance step. It deliberately excludes personal exports, character results, local paths, and earlier installation history.

| Requirement | Status | Evidence / remaining step |
|---|---|---|
| Parse a complete official `/simc` export including bags | Verified with synthetic fixtures derived from the official format | Parser tests cover equipped gear, bag candidates, metadata, limits and malformed input |
| Never execute raw imported directives | Verified | Strict directive allowlist, duplicate rejection, value validation, and hostile-directive tests |
| Simulate each supported bag candidate against equipped baseline | Verified | Profileset and pipeline tests cover supported candidates and legal slot variants |
| Try rings/trinkets in both legal slots | Verified | Profileset unit tests |
| Exclude coupled weapon changes without blocking supported items | Verified | Pipeline tests for weapons below and at/above the configured threshold; weapons are never simulated or published |
| Configurable minimum candidate item level | Verified | Parser, settings, pipeline and CLI/GUI plumbing tests; default 282, 0 disables filtering |
| Report all-excluded runs transparently without publishing | Verified | Below-threshold-only, unknown-level-only and weapon-only regression tests preserve the prior result |
| Validate complete baseline and unknown candidates | Verified | Parser/pipeline tests |
| Run `simc.exe` locally without a shell | Verified | Runner tests enforce argv execution with `shell=False`, executable identity, version/revision checks, timeout and output limits |
| Validate JSON2 results and provenance | Verified | Runner/pipeline tests bind the pinned revision, client build, DBC, profile, scenario, traits and settings |
| Add current specializations without runtime AI or per-Spec code branches | Verified | Deterministic generator produces 40 canonical entries from pinned SimC revision `5a982a3`; runtime and generator reject drift, malformed data, missing classes and revision mismatch fail-closed |
| Support Guardian Druid through registry data | Verified in parser/pipeline harness | Generic export path renders `druid/guardian` as WoW spec ID `104` without a pipeline special case |
| Bind results to character, talents, traits, gear, scenario, build, and SimC provenance | Verified in source/runtime harness | Python/Lua tests and a pinned Lupa Lua-5.1 WoW-API mock harness |
| Publish aggregate state and staging Lua under one OS lock with crash recovery | Verified | Durable path-bound pre-write journal binds old and new hashes, restores controlled failures and interrupted known generations, refuses foreign generations, and treats lock contention fail-closed |
| Retain multiple character/spec profiles without cross-character fallback | Verified in Python and Lua runtime harnesses | Schema 2 identity/update tests, malformed/dense-array/duplicate rejection, bounded DPS/delta/timestamp fields, exact current-character/spec selection |
| Migrate generated schema-1 archives without executing Lua | Verified with synthetic fixtures | Literal-only AST conversion rejects calls, extras, duplicate keys and Boolean schema versions, and merges validated records by exact identity |
| Install only `Results.lua` when WoW is freshly closed | Verified with isolated filesystem/process mocks | Canonical JSON-to-Lua binding; target-bound cross-receipt OS lock; exact target/Core/TOC checks; stable directory plus write-/replace-denying Core/TOC handles; fresh checks before backup-directory writes, recovery preparation/link/cleanup, prepared/probe writes, rename, create-if-absent publication and cleanup; crash journal/recovery; readback; SavedVariables aggregate digests; receipt state outside the complete Retail tree; and foreign-generation preservation. Post-publication failures retain the validated generation rather than risking a destructive rollback; no test touches live WoW files. |
| GUI auto-install and retry without rerunning SimC | Verified in source/unit harness | Auto-install defaults off; completed-analysis hash/state binding is retained; blocked deployment keeps staging and enables a separate retry; a new analysis clears stale retry state |
| CLI remains staging-only unless explicitly requested | Verified | `--install-live` requires `--addon-dir`; deployment errors preserve staging |
| Package the addon assets in the wheel and sdist | Verified | Non-destructive build, byte-identical schema-2 addon assets, and isolated wheel/sdist installation/import checks |
| Windows GitHub CI | Verified | CI uses immutable action SHAs and a pinned uv version, then runs Ruff lint/format, registry drift, pytest, compileall, build, exact Git-to-sdist and wheel addon-asset checks, and isolated wheel/sdist installs on `windows-latest` |
| WoW Retail in-game tooltip smoke test | Pending | After a separately authorized result-only installation, start WoW, verify matching and non-matching character/spec behavior, inspect item tooltips, and check Lua error logs |

A GitHub repository or green automated suite is not a substitute for the final in-game smoke test.
