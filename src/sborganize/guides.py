"""Short, offline manuals available from every installed copy."""

GUIDES = {
    "start": """# sborganize · a calmer Home Screen

Rules first. Preview first. No account or model required.

## 1. Try it without a phone
```sh
sborganize demo
```
The bundled example is synthetic. This command contacts nothing and saves nothing.

## 2. Connect and inspect
Connect your iPhone by USB, unlock it, and choose Trust This Computer.
```sh
sborganize doctor
sborganize scan
sborganize plan --existing-only --device-ready
sborganize show --after
```
The plan groups loose apps into existing folders and preserves already grouped apps.
It never changes your phone. `show --details` lists every proposed position change.

## 3. Apply only after reviewing
```sh
sborganize apply --experimental-write
```
The default answer is No. The command backs up and verifies the source, asks for
confirmation, checks an unchanged round-trip, then writes and verifies the target.

## Other routes
`sborganize guide offline` — rehearse apply/restore with no phone.
`sborganize guide config` — remember pins and category choices.
`sborganize guide policy` — emoji names, all-app grouping and full folder pages.
`sborganize guide cloud` — optional, explicit OpenRouter review.
`sborganize guide safety` — limits, backups and recovery.
""",
    "offline": """# Rehearse without a phone

Use a separate data directory so the demo does not replace your selected phone plan.
```sh
sborganize --data-dir /tmp/sborganize-demo demo --save
cd /tmp/sborganize-demo
sborganize --data-dir . show --after
sborganize --data-dir . apply --fixture examples/demo.json
sborganize --data-dir . restore --fixture simulations/latest.json
```
Both write commands ask for confirmation. They simulate the same backup and
round-trip protocol and save separate output files. They never open USB or change
the original fixture. The demo creates no network requests or model calls.

`--json` works on demo, scan, score, plan, show, review, doctor and backups.
Redirected output contains no terminal colors. Use `--no-color` before a command
to disable colors explicitly, or set the standard NO_COLOR environment variable.
""",
    "config": """# Keep your preferences

```sh
sborganize config init
sborganize config path
sborganize config show
```
Edit the printed TOML path. Existing files are never overwritten by init.

```toml
[pins]
bundle_ids = ["com.example.favourite"]

[categories]
"com.example.bank" = "Finance"
"com.example.bill" = "Expenses"

[folders.map]
Finance = "🏦💰"
Expenses = "🧾💸"

[regions]
"com.example.bank" = "GLOBAL"
"com.example.bill" = "GLOBAL"
```
These are placeholder bundle IDs. Use the actual ID from `scan --json`.
Folder maps target names already on the phone; they do not rename folders.
GLOBAL means outside the CN/HK local-service buckets, including other local markets.

For separate local-service groups, use `[folders.regions]` with distinct CN/HK names.
Pins, the dock and opaque widget nodes are always protected. Put global options
such as `--data-dir PATH` and `--config FILE` before the command.
""",
    "policy": """# Deliberate all-app redesign

A policy is an editable local JSON file. It lists every recognized app, destination
and reason, plus explicit emoji folder names and source/target positions.

```sh
sborganize policy export
```
This reads the layout and saves a draft plus its source snapshot. It makes no
model call and changes nothing on the phone. Review the generated draft: replace
text folder names with emoji, resolve loose apps marked REVIEW, and check every
destination and reason. Existing folder slots must be reused exactly once.

```sh
cd ~/.sborganize/policies
sborganize plan --policy draft.json --source-snapshot draft.source.json --device-ready
sborganize show --after
sborganize show --details
sborganize apply --experimental-write
```
Each nonfinal folder page is filled before the next page. Rename/reorder permission
is explicit and limited to folder display names and declared positions. Other
metadata, app payloads, dock, pins and unknown nodes remain protected. A folder
containing a pin, nested folder or unsupported child cannot be redesigned this way.

Policies bind to the captured source. If the phone changes, export and review again.
Your previous plans and cloud reports are preserved; apply selects the newest plan.
""",
    "cloud": """# Optional cloud advice

Cloud inference is never required. Rules work without credits, accounts or models.

```sh
sborganize plan --existing-only --cloud --device-ready
```
This sends unresolved app names/IDs and folder summaries to OpenRouter and its
routed provider. A hidden terminal prompt asks for your key if the local
OPENROUTER_API_KEY variable is absent. Prompted keys are not stored or exported.

```sh
sborganize review --cloud
```
This broader opt-in reviews ALL Home Screen apps, including grouped apps. It sends
names/IDs and current folder membership in bounded batches. Successful batches
are cached privately; rerun the same command to resume. `--refresh` charges new
requests by deliberately bypassing cache. An incomplete run exits unsuccessfully.

Advice is not an apply plan. Schema completeness does not prove the classification
is right. Review region, domain and purpose. Raw IconState, device identity,
credentials, screenshots and app contents are never in model prompts.

`--no-network` blocks cloud. Setting a key alone enables nothing. `--smart` is a
separate Apple-only path that falls back to rules and never invokes cloud or Ollama.
""",
    "safety": """# Before writing to a phone

Live writes are experimental. Read access and a successful demo do not establish
compatibility with your iOS version. iOS may normalize or reflow layouts.

Every apply and restore runs:
1. Exact identity, inventory, pins, unknown-node and freshness checks.
2. A raw local backup, reloaded and checked for integrity.
3. Confirmation before any write, including the unchanged round-trip.
4. Unchanged write and strict structural readback.
5. Target write and strict structural readback.

Only known app bookkeeping may differ. Unknown nodes are not silently ignored.
Declining makes zero writes. `--yes` skips only confirmation; all checks remain.
There are no automatic write retries or rollbacks.

## Recover
```sh
sborganize backups
sborganize restore --experimental-write --backup /path/printed/by/apply.json
```
Use the exact undo backup reported by apply; restore creates its own undo backup.
If a check fails, stop, inspect the phone and retain the backup. A backup is not a
promise that iOS will accept the old state. Hardware restore is not yet validated.

Only trusted USB Home Screen state is read. No app contents, messages or photos
are accessed. Your data root contains sensitive app metadata: do not upload it.
""",
}
