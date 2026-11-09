# Compatibility and verification

This is an alpha, with deliberately explicit live-write opt-in.

## Host support

- Python 3.11+ is required.
- macOS is the starting point for trusted USB iPhone access.
- Linux supports rules, demo, fixtures, local reports and package tests. Linux USB
  access has not been validated on hardware.
- Apple Foundation Models additionally needs a compatible Apple silicon Mac,
  macOS 26+, model assets and a Swift toolchain. It is optional and can be unavailable.

CI exercises Linux on Python 3.11–3.14 and macOS on Python 3.14. No CI job needs a
phone, account, API key or model asset. The wheel is installed and exercised
outside the checkout before release artifacts are produced.

## Hardware observations

On 2026-11-09, one self-owned development iPhone completed:

- Trusted USB reads and exact raw backups.
- An unchanged round-trip through the safety gate.
- A reviewed all-app emoji policy write with 248 recognized apps and 18 folders.
- Strict target readback with all apps present, zero loose apps, full nonfinal
  folder pages, and protected dock/widget nodes retained.

The user confirmed the result and made subsequent manual refinements. Those
refinements must be treated as current user state, never overwritten by a stale plan.

The exact iOS release was not recorded in that test session, so no numerical iOS
support range is claimed. Hardware restore is not yet validated. Widget shapes,
opaque-node fields and iOS reflow behavior still require more device coverage.
The adapter is pinned to pymobiledevice3 11.50.2.

## Why strict checks can stop a run

An earlier unchanged write exposed new icons and changed opaque widget fields;
the target was correctly blocked. Another expected trailing empty folder page
was removed by iOS; the planner was fixed to remove newly empty trailing pages
in edited folders before writing. Verification was not weakened to ignore unknown
payloads. Synthetic regression tests cover both cases.

Please report redacted platform details and reproducible synthetic states.
Do not publish private device dumps. See [security reporting](../SECURITY.md).
