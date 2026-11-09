# Safety and recovery

[Home](../README.md) · [Troubleshooting](TROUBLESHOOTING.md) · [Privacy](../PRIVACY.md)

Live apply/restore are experimental. The app rearranges Home Screen entries; it
does not uninstall apps or read their contents. iOS may normalize or reflow a
layout. A valid backup cannot guarantee that iOS will accept a restoration.

## The write gate

Every apply and restore:

1. Verifies device identity, app inventory, protected nodes and exact freshness.
2. Saves the raw current state and reload-verifies its integrity.
3. Asks for confirmation **before any write**.
4. Writes the current state unchanged and checks structural readback.
5. Writes the approved target only after the round-trip passes.
6. Checks the target by reading it back.

The default answer is No. Declining performs zero writes. `--yes` skips only the
prompt; it does not bypass any other gate. After confirmation, the source is read
again to catch concurrent edits. Keep the phone unlocked and do not manually
rearrange it during the operation.

Only known bookkeeping on recognized app nodes (`iconModDate`, `bundleVersion`)
is ignored after writes. Unknown node payloads remain strict. Explicit policy
mode permits only its declared folder names and positions; other metadata must
remain intact. Default planning does not permit folder renames or moves.

## If a check fails

Stop and inspect the phone. Do not assume either that nothing was written or
that every requested position was accepted. The terminal stage and error tell
you whether the target was reached. A failed unchanged round-trip means the target
was not written; a target readback failure means the target may have reflowed.

Backups remain on any transport or validation failure. No write is automatically
retried, and there is no automatic rollback. Re-read and review the current
layout before making another plan. Never hide an unknown-node mismatch just to
make a verification pass.

## Find and restore an undo backup

```sh
sborganize backups
sborganize restore --experimental-write --backup /exact/path/reported/by/apply.json
```

Use the exact backup associated with the operation you want to undo. Without
`--backup`, restore chooses the newest backup for the connected device/source;
an explicit path is clearer after several backups. Restore creates a fresh undo
backup and runs the same confirmation, round-trip and readback protocol.

Hardware restore is not yet validated. It is covered by fake-device and fixture
tests. [Offline rehearsal](QUICKSTART.md#rehearse-the-write-protocol-without-usb)
is available without connecting a phone.

## Keep local data private

Plans, scans, policies, reviews and backups may reveal app inventory and device
identity. Their local files use private permissions. Do not attach raw data to a
public issue. Prefer OS versions, command names, redacted errors and synthetic
reproductions. See [SECURITY.md](../SECURITY.md).
