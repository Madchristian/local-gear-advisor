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
- Optional result-only installation into an explicitly selected compatible live addon after a fresh fail-closed check proves that WoW is closed. This never replaces `Core.lua`, the TOC, or SavedVariables.

## Correctness contract
- Candidate identity uses the exact SimC item specification, not item ID alone.
- Ring and trinket candidates are tested in both legal slots.
- Unsupported/unparseable candidates are `unknown`, never zero-valued.
- A result is current only when profile hash, scenario, settings, and SimC version match.
- Failed, timed-out, malformed, or warning-invalidated simulations do not publish new results.
- Project-local aggregate state and staging Lua use a hash-bound crash-recovery journal under an OS lock.
- Explicit live publication is limited to `Results.lua` and uses a target-bound publisher lock, stable directory and code-file handles, fresh WoW checks before each live mutation, a same-filesystem backup, create-if-absent publication, and verified readback.

## Out of scope for MVP
- Full combinatorial Top Gear.
- Automatic writes to SavedVariables.
- Automatic simulation while WoW is running.
- Raidbots/network integration.
- Claims of accurate tank survivability until a separately validated metric is selected.
- Automatic installation without explicit opt-in, writes to addon code/TOC/SavedVariables, release ZIP, scheduler, or frozen EXE.

## Tank presentation
DPS deltas may be shown as simulated. Defensive suitability remains a separate clearly labeled estimate/unknown until the chosen SimC survivability metric is validated. No invented combined score.
