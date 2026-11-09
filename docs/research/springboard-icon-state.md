# Research: SpringBoard IconState

**Date:** 2026-11-08\
**Status:** Working notes for implementers

## Prototype checkpoint

The optional adapter is pinned to `pymobiledevice3==11.50.2`. Its installed source
was inspected: `create_using_usbmux`, `list_devices`, `get_icon_state` and service
context management are asynchronous. The adapter filters USB devices, requires
explicit selection when more than one is present, uses `autopair=False`, and calls
only `get_icon_state`. Pairing can be initiated explicitly with
`python -m pymobiledevice3 lockdown pair` after connecting and unlocking.

API reference: [11.50.2 SpringBoard service](https://github.com/doronz88/pymobiledevice3/blob/v11.50.2/pymobiledevice3/services/springboard.py)
and [lockdown connection](https://github.com/doronz88/pymobiledevice3/blob/v11.50.2/pymobiledevice3/lockdown.py).
The dependency is GPL-3.0-or-later; this project uses the same license.

A user has reported a successful direct USB read, including a correctly identified
dock. The iOS / host versions and full raw shape have not been recorded or
independently validated at that initial checkpoint. Later write testing is recorded
below. The synthetic fixture defines the
first list as the dock. Unknown real-device shapes must be captured and validated
before broad write support is claimed. Connections are read-only by default;
`--experimental-write` enables the verified safety protocol explicitly.

The pinned library's `set_icon_state` uses XML plist framing. `None` is not XML
plist-compatible. Device-ready planning removes only loose vacancies after the
last fixed anchor; unresolved anchored gaps refuse before writes. Real preflight
also serializes the exact source and target. Post-write signatures ignore only
known app `iconModDate` / `bundleVersion` bookkeeping; unknown payloads stay strict.

## Authorized hardware checkpoint (2026-11-09)

The first unchanged round-trip was correctly rejected: two recognized app icons
appeared and two opaque widget nodes lost `userSelectedElementIdentifier` in the
returned state. The target was not written. The origin of newly appearing apps
was not established. We did not add an unknown-field exclusion to verification.

After the user explicitly requested retry, the inspected stable post-round-trip
state became the new source. The same approved placements were retained and the
two additional icons stayed loose. Unknown nodes in the new target matched the
new source exactly. The unchanged round-trip passed, and the target was written:
248 apps, three pages, two loose icons. Inventory, dock and opaque nodes were preserved.

The initial strict target readback differed only because an edited folder had
expected inner page lengths `[2, 0]` while iOS returned `[2]`. Removing only that
newly empty trailing page from the expected target made the entire structural
fingerprint match the saved immediate device readback. The planner now performs
that cleanup before writing, limited to edited folders; verification was not loosened.

A later read showed additional folder ordering and membership changes after the
matching immediate readback. Their origin is awaiting clarification. No further
writes or automatic restoration were performed. Exact backups and private local
readbacks are retained; personal dumps are not committed. Hardware restore is
still unvalidated and this does not establish broad iOS compatibility.

## Source of truth

[pymobiledevice3](https://github.com/doronz88/pymobiledevice3) exposes SpringBoard services:

- `SpringBoardServicesService.get_icon_state(format_version="2")` → nested list (pages → slots)
- `SpringBoardServicesService.set_icon_state(newstate)` → write layout
- CLI: `pymobiledevice3 springboard state get`

Docs / references:

- [SpringBoard CLI](https://doronz88.github.io/pymobiledevice3/latest/cli/springboard/)
- Historical `set_icon_state` plist issues fixed upstream ([#993](https://github.com/doronz88/pymobiledevice3/issues/993), [#995](https://github.com/doronz88/pymobiledevice3/pull/995)) — pin a known-good pymobiledevice3 version after first successful write tests.

## Shape (observed)

`get_icon_state` returns a **list of pages**. Each page is a **list of entries**. Entries look like dicts with fields such as:

- `bundleIdentifier` / `displayIdentifier`
- `displayName`
- `bundleVersion`
- `iconModDate`

Folders and widgets appear as richer structures (exact keys vary by iOS). **sborganize must treat unknown entry types as opaque** and pass them through on write.

Dock is typically represented as a dedicated page/list in the overall structure — confirm against live dumps and fixtures; do not assume Unjiggle’s internal model.

## Connection caveats

- Device must be unlocked / trusted over USB.
- Some developer services on newer iOS versions need tunnel / RSD workflows. Do not
  assume this for SpringBoard without a reproduced failure. The prototype only
  implements the direct trusted USB path and does not start tunnels.
- `doctor` should surface the same failure modes with copy-pasteable fixes.

## Safety implications for us

1. Always backup the **exact** raw state we read, not only the normalized model.
2. Round-trip: write the backup payload unchanged, read again, compare fingerprint.
3. After applying a plan, read back; iOS may add or move icons even when the write “succeeded”.
4. Never claim bit-identical permanence across reboot.

## What we will capture in fixtures

- Multi-page home screen with loose apps
- Nested folders with multiple inner pages
- Dock pins
- At least one opaque/widget-like node (when we have a dump)
- Empty / sparse pages for compaction tests

Store fixtures as JSON-serialized icon state (datetime fields as ISO strings) under `fixtures/`.

## Out of scope for this note

- Reversing private SpringBoard XPC beyond pymobiledevice3
- Non-USB transports as primary path
