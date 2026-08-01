# Local Gear Advisor

Local-only Windows companion plus WoW Retail addon. Python 3.11+ backend; WoW addon uses Lua 5.1.

## Non-negotiable boundaries
- Never write to the live WoW tree while Wow.exe is running or process state is unknown.
- Never modify WoW SavedVariables externally.
- Project work stays under this repository until an explicit reviewed install approval.
- subprocess calls use argv lists, shell=False, explicit timeout, and captured output.
- Unknown/unsupported SimC items and procs are never scored as zero; report unknown.
- Results are bound to exact item strings, profile hash, scenario, and SimC version.
- GUI startup is read-only and triggers no scan, simulation, install, network, or task registration.
- No telemetry or network dependency.
- Use strict RED-GREEN-REFACTOR. Run the focused failing test before implementation, then the full suite.
- Do not commit, install, package, publish, or touch D:\\World of Warcraft without explicit approval.

## MVP
- Paste a normal `/simc` export containing equipped gear and bag items.
- Parse character/spec/talents, equipped item lines, and bag item candidates.
- Compare each candidate only against the currently equipped baseline.
- Generate valid SimulationCraft profilesets, including both ring/trinket slots where applicable.
- Execute a user-selected local simc.exe safely and parse machine-readable/JSON results.
- Generate an inert `addon/LocalGearAdvisor/Results.lua` inside the project.
- Tooltip addon displays exact cached results, age, scenario, and stale/unknown states.
- Initial UI may be a small Tkinter shell; backend behavior must be independently testable.

## Commands
- Tests: `python -m pytest -q`
- Syntax: `python -m compileall -q src tests`
