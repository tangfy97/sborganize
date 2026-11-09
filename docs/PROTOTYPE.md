# Alpha scope

The command-line product is usable for deterministic rules previews, local
preferences, exhaustive explicit policies, saved-plan inspection and fixture
rehearsal. Live USB writes remain experimental.

## Implemented

- Bundled, zero-hardware demo and offline guides.
- Readable compact previews, full detail, target-layout inspection, terminal color
  with plain/JSON modes, configuration initialization and backup browsing.
- Deterministic app categories, explicit bundle overrides, folder-role learning,
  service-region rules and ambiguous-app review.
- Whole-inventory advisory cloud review with opt-in metadata sharing, bounded
  batches, private successful caches, field diagnostics and local recheck.
- Exhaustive policies for emoji folder names, explicit folder order, adjacent
  groups and fully filled nonfinal internal pages.
- Self-owned pymobiledevice3 USB I/O, raw backup validation, exact freshness,
  confirmation before unchanged round-trip, then target write/readback.
- The newest generated plan is selected without overwriting other plan modes.

## Hardware checkpoint

A reviewed 248-app, 18-folder emoji policy completed on a development iPhone on
2026-11-09. The CLI exited successfully after source backup, unchanged round-trip,
write and strict readback. All apps were present, no loose apps remained, all
nonfinal folder pages held nine icons, and dock/widget nodes were preserved.
The user confirmed a satisfactory result and made subsequent manual refinements.
Those edits are user state, not a reason to rewrite or restore a stale plan.

Earlier failures are recorded in [research](research/springboard-icon-state.md):
source changes correctly blocked a round-trip; a newly empty trailing folder page
was removed by iOS, and the planner was corrected before broader use. Verification
was not relaxed for unknown payloads.

## Limits

- No broad iOS compatibility matrix. Hardware restore is still unvalidated.
- Unknown app purpose and unsupported widget shapes may prevent automation.
- Explicit policy mode reuses existing editable root folders/slots; it does not
  support arbitrary widget movement, nested folder redesign or deleting folders.
- Rules are incomplete and model advice can be wrong. High confidence and valid
  JSON do not establish an app's real purpose.
- Apple inference can be unavailable. No Ollama setup or automatic cloud fallback.
- No App Library-only inventory, App Store metadata runtime lookup, GUI, telemetry
  or uninstall features.

The [quick start](QUICKSTART.md), [CLI reference](CLI.md), [safety](SAFETY.md) and
[privacy](../PRIVACY.md) are the public usage path. Plans and research retain the
technical history; they are not a substitute for current command help.
