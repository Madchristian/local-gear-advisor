# Local Gear Advisor MVP

## Goal
Show an item-tooltip recommendation based on local SimulationCraft comparisons rather than static Pawn weights, including modeled trinket/proc effects, with a bounded copy/paste transport that can activate a profile in the running WoW client.

## Inputs
1. A pasted SimulationCraft addon export (`/simc`, bags included).
2. A user-selected `simc.exe`.
3. Scenario settings (initially Patchwerk/Single Target; DungeonSlice is explicit and separate).

## Outputs
- Structured run report and canonical profile state under `%LOCALAPPDATA%\LocalGearAdvisor` (with the documented absolute per-user fallback when `LOCALAPPDATA` is unusable).
- Generated staging addon and `Results.lua` projection under that external runtime root; the checked-in `addon/LocalGearAdvisor/Results.lua` remains an immutable empty placeholder.
- A bounded, canonical `LGA2` text transport for explicit copy/paste, validation and transactional application by the in-game addon. The confirmed import becomes active immediately and is persisted account-wide by WoW SavedVariables.
- Optional result-only installation into an explicitly selected compatible live addon after a fresh fail-closed check proves that WoW is closed. This never replaces `Core.lua`, the TOC, or SavedVariables.

## Correctness contract
- Candidate identity uses the exact SimC item specification, not item ID alone.
- Ring and trinket candidates are tested in both legal slots.
- Unsupported/unparseable candidates are `unknown`, never zero-valued.
- A result is current only when profile hash, scenario, settings, and SimC version match.
- Failed, timed-out, malformed, or warning-invalidated simulations do not publish new results.
- Aggregate state and staging Lua under the external runtime root use a hash-bound crash-recovery journal under an OS lock.
- Explicit live publication is limited to `Results.lua` and uses a target-bound publisher lock, stable directory and code-file handles, fresh WoW checks before each live mutation, a same-filesystem backup, create-if-absent publication, and verified readback.

## Out of scope for MVP
- Full combinatorial Top Gear, including coupled weapon-loadout evaluation.
- External or unattended writes to SavedVariables; persistence occurs only after explicit validation and confirmation inside WoW.
- Live addon-file replacement while WoW is running. Local analysis and `LGA2` copy/paste remain supported after the reviewed addon code has been installed once with WoW closed.
- Raidbots/network simulation integration.
- Claims of accurate tank survivability until a separately validated metric is selected.
- Automatic installation without explicit opt-in, a scheduler, or a frozen EXE.

## Tank presentation
DPS deltas may be shown as simulated. Defensive suitability remains a separate clearly labeled estimate/unknown until the chosen SimC survivability metric is validated. No invented combined score.
