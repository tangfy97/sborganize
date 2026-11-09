# Emoji folders and an all-app policy

[Home](../README.md) · [CLI reference](CLI.md) · [Classification](CLASSIFICATION.md)

Use this mode when you deliberately want to reconsider apps already inside
folders, rename the groups and fill their internal pages. It makes no model call.
An exhaustive policy requires careful review; it is not a promise of perfect
automatic app recognition.

## Export, edit, preview

```sh
sborganize policy export
```

This reads the current USB layout and saves:

- `~/.sborganize/policies/draft.json`: every recognized app and current membership.
- `~/.sborganize/policies/draft.source.json`: the exact source snapshot.

It does not change the phone or overwrite earlier drafts. Use `--output FILE.json`
for another draft, `--fixture FILE` for a synthetic layout, or `--from-plan FILE`
for a saved plan's original snapshot.

Edit the draft:

1. Give every folder a unique emoji-only name. Multiple emoji are supported.
2. Keep folder IDs stable. Map each source slot to a unique existing target slot.
3. Assign every app to a folder ID. Resolve all `REVIEW` destinations.
4. Check each app's reason; publisher origin does not establish purpose or region.
5. Keep dock entries assigned to `dock`.

Then preview:

```sh
cd ~/.sborganize/policies
sborganize plan --policy draft.json --source-snapshot draft.source.json --device-ready
sborganize show --after
sborganize show --details
```

The resulting plan is selected for apply, without replacing your other plan files.
The per-app audit is saved to `reviews/domain-policy-audit.json`.

## Format

The following is a **schema illustration**, not an executable complete policy:

```json
{
  "schema_version": 1,
  "kind": "organization_policy",
  "source_fingerprint": "copied by policy export",
  "folder_page_size": 9,
  "folders": [
    {"id": "banks", "name": "🏦💰", "source": [1, 2], "target": [1, 2]},
    {"id": "bills", "name": "🧾💸", "source": [1, 3], "target": [1, 3]}
  ],
  "adjacent_groups": [["banks", "bills"]],
  "apps": {
    "com.example.bank": {
      "name": "Example Bank", "folder": "banks", "rank": 0,
      "reason": "Banking account and transfers."
    }
  }
}
```

Paths are zero-based `[page, slot]` pairs. Page 0 is the dock and cannot be a
folder source or target. Preserve exported source coordinates; the public API
does not use visible grid-cell coordinates around widgets.

Optional `rank` controls order inside a folder; ties preserve source inventory
order. Pages are packed to `folder_page_size` before a new page starts. A pair
in `adjacent_groups` must occupy consecutive slots on one page.

Every existing root folder and slot must be reused once. No folder can end empty.
Only `displayName` may change in its other metadata. App payloads, pins, dock and
opaque nodes stay protected. Folders containing pins, nested folders or unknown
children refuse this mode.

## Apply and maintain

```sh
sborganize apply --experimental-write
```

All [safety checks](SAFETY.md) still run. Changed device state invalidates the
snapshot; export and review again instead of editing the fingerprint blindly.
Keep persistent preferences in TOML as well, so later rules previews retain your
known app categories. The policy remains local and should not be posted publicly.
