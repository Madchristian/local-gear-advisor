# Local Gear Advisor MVP

## Goal
Show an item-tooltip recommendation based on local SimulationCraft comparisons rather than static Pawn weights, including modeled trinket/proc effects.

## Inputs
1. A pasted SimulationCraft addon export (`/simc`, bags included).
2. A user-selected `simc.exe`.
3. Scenario settings (initially Patchwerk/Single Target; DungeonSlice is explicit and separate).

## Outputs
- Structured run report under project-local state.
- Generated project-local `addon/LocalGearAdvisor/Results.lua`.
- No live WoW installation in the implementation phase.

## Correctness contract
- Candidate identity uses the exact SimC item specification, not item ID alone.
- Ring and trinket candidates are tested in both legal slots.
- Unsupported/unparseable candidates are `unknown`, never zero-valued.
- A result is current only when profile hash, scenario, settings, and SimC version match.
- Failed, timed-out, malformed, or warning-invalidated simulations do not publish new results.
- Publication is same-parent temporary file plus verified atomic replacement within project-local output only.

## Out of scope for MVP
- Full combinatorial Top Gear.
- Automatic writes to SavedVariables.
- Automatic simulation while WoW is running.
- Raidbots/network integration.
- Claims of accurate tank survivability until a separately validated metric is selected.
- Live WoW installation, release ZIP, scheduler, or frozen EXE.

## Tank presentation
DPS deltas may be shown as simulated. Defensive suitability remains a separate clearly labeled estimate/unknown until the chosen SimC survivability metric is validated. No invented combined score.
