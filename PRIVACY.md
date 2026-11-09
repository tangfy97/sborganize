# Privacy

`sborganize` keeps planning local by default. This policy was updated on 2026-11-09
for optional OpenRouter, whole-inventory review and local CLI workflows.

## Modes

- **Default:** deterministic offline rules. No model and no network request.
- **`--smart`:** Apple Foundation Models `SystemLanguageModel` on this Mac, then
  rules if unavailable. It never calls Ollama, OpenRouter or Private Cloud Compute.
- **`--cloud`:** explicit opt-in to OpenRouter and its routed inference provider.
  It is separate from `--smart` and is never an automatic fallback.
- **`--no-network`:** prevents `--cloud`; the combination is rejected before any
  device read or request. App Store metadata lookup is not implemented.

Setting `OPENROUTER_API_KEY` alone enables no network behavior. No accounts or
telemetry are required for local modes. Cloud mode requires the user's own
OpenRouter account and key.

## What we read

From a trusted USB phone, we read only Home Screen IconState: app names and bundle
IDs, folder names/contents, dock/page positions and raw fields needed to preserve
widgets and unknown nodes. We do not inspect app containers, photos, messages,
contacts, health records, mail bodies or browsing history. No apps are uninstalled.

## What a model sees

`plan` refinement considers only apps unresolved by the rules, with bounded requests.
The separate `review` command considers every recognized Home Screen app, including
apps inside folders, dock and pins. Default review is offline rules; it does not
probe local models. It saves advice and cannot be passed to `apply`.

Apple sees the unresolved app name/ID, existing domain/region hints, eligible
folder names, local category summaries and up to three peer names per folder.
The Swift bridge explicitly uses `SystemLanguageModel.default`, not a hosted or
Private Cloud Compute model. Availability is checked before any inference.

`plan --cloud` sends **unresolved app names/IDs, domain/region hints, folder
names, category summaries and counts** to `https://openrouter.ai/api/v1/chat/completions`.
Known peer app names are omitted from plan-refinement prompts.

`review --cloud` explicitly shares a broader inventory: **all recognized Home
Screen app names/IDs, current folder ID/name (or Dock/Loose label), domain/region
hints, protected status, and folder labels/category summaries/counts**. Each
request contains at most 16 apps plus the folder summaries. Over the complete run,
every app is included. `GLOBAL` in this review means outside the mainland-China
and Hong Kong local-service groups; other local markets use domain folders.
`--from-plan` uses a saved plan's original snapshot instead of reading the phone.
Existing regional-folder membership does not establish an app's service region
during full review.

Reports preserve original model candidates so `review --recheck` can validate them
locally without a key or network. `plan --from-review` likewise reuses saved advice
and local rules, then writes a separate regrouping preview. It cannot make a cloud
request. Explicit local mappings may create a requested folder; the model cannot.
`--refresh-device` reads USB again, accepting only appended recognized icons and
known bookkeeping changes. Newly added icons are handled by explicit local rules
or retained; they are not represented as having been reviewed by the cloud model.

`plan --policy` is entirely offline. Its exhaustive local policy includes app
names/IDs, chosen destinations/reasons and explicit folder source/target positions.
The separate local audit includes group counts and home positions. Neither file
is sent to a model or another service. All device-write protections still apply;
explicit folder-edit declarations permit only the reviewed positions and names,
never arbitrary changes to other metadata or unknown nodes.

Raw IconState, device IDs, page/slot coordinates, widgets, backups, screenshots
and credentials are never included in either mode.
A list of app names can still reveal personal interests; choose cloud mode only
when comfortable sharing that metadata with OpenRouter and its routed provider.

The client requests providers with `data_collection=deny`; retention and logging
still depend on the service's current policies and account settings. This flag
is not a promise that a third party retains nothing. No redirects, automatic
provider/model fallbacks or request retries are used. Model refusal or uncertainty
keeps the app for review. Model suggestions cannot write to the phone directly.

Service region is independent of nationality, location, publisher origin or
language. We do not infer the user's personal traits from installed apps.

## Credentials and cost

The optional key comes from `OPENROUTER_API_KEY`, or a hidden terminal prompt when
`--cloud` is explicitly selected and no environment key exists. Prompted keys are
held only in the current process: they are not exported or saved. If hidden input
is unavailable, the CLI refuses to fall back to echoed input. Noninteractive
commands do not prompt and need the environment variable.

Never paste a key into chat, commit it to git or place it in a plan. Prompts sent
to models, backups, plan metadata and errors never contain the credential. Local
`.env` files are ignored by git but are not loaded by the CLI.

The default optional cloud model is `qwen/qwen3.5-flash-02-23`. Cloud plan refinement
is bounded to eight unresolved apps and 256 output tokens per request. Whole
review supports at most 512 app icons and 96 existing folders, in batches of 16,
with 4096 output tokens per request and no automatic retries. Complete valid
batches are cached locally by model and request content. Reruns reuse those
batches without contacting the provider; `--refresh` explicitly bypasses cache
and incurs new requests. Cache-only review needs no key or terminal prompt.
Prices can change; use an account/key spending limit when desired. No inference
request is made merely to run `doctor` or check whether a key exists.

## Local storage

The default root is `~/.sborganize/`; global `--data-dir PATH` selects another root.
Plans live in `plans/`, advisory whole-inventory reports in `reviews/`, exact raw
backups in `backups/`, fixture results in `simulations/`, and the compiled Apple
CLI bridge in `cache/`. `plans/selected.json` stores only the selected plan's local
filename. `config init` creates commented preferences without overwriting an
existing file. `policy export` saves an app-by-app draft and exact source snapshot
under `policies/`; these can reveal your inventory. Plain `demo` saves nothing;
`demo --save` additionally stores the bundled synthetic layout under `examples/`
and selects its fixture plan. Use a separate data root for demonstrations.

Help, built-in guides, config inspection, saved-plan inspection and backup listing
do not contact a phone or model. Cloud review responses are cached under `cache/reviews/`;
these and the reports contain sensitive app metadata and reasons, but no raw state
or device ID. Delete the corresponding files to clear stored review data.
Rejected batches write bounded known-field candidate projections and field/type/
length diagnostics to `reviews/rejected/`, with the same private file permissions.
They do not save arbitrary response fields, raw HTTP bodies or credentials and are
never reused as successful cached results.
Incomplete runs save their coverage and error, exit unsuccessfully and do not
claim that unreviewed apps were assessed. New data files use
mode `0600`; new storage directories use `0700`. Raw states are encoded as a
base64 binary plist inside JSON to preserve bytes, dates and unknown fields.
Base64 is not encryption. Model suggestions/review reasons are stored locally
with the plan. The Apple bridge receives prompts through stdin, not command-line
arguments or temporary prompt files.

## Writes and restore

Phone writes are off by default. Experimental live `apply` / `restore` require
`--experimental-write`; apply additionally requires a reviewed `--device-ready`
USB plan. A fixture plan cannot be applied to a USB source. The gate:

1. Validates identity, app inventory, unknown nodes, pins and plan freshness.
2. Saves and reload-verifies the exact current state backup.
3. Asks for confirmation (unless `--yes` was explicitly selected).
4. Re-reads to reject changes during confirmation, then writes the current state
   unchanged and checks the round-trip.
5. Writes the target only after that check, then verifies read-back.

No writes occur after declined confirmation. Post-write comparisons ignore only
`iconModDate` and `bundleVersion` on recognized app nodes, which iOS can refresh;
unknown-node payloads, dock/folder structure and positions remain strict. Reads
may settle for up to five seconds; writes are never automatically retried.
Any mismatch retains the backup and reports failure. Restore uses the same gate
and saves an undo backup. A backup cannot guarantee that iOS will preserve layout.

`--device-ready` removes newly empty loose slots only after the last fixed anchor
on a page; remaining loose apps may shift, and all such moves appear in preview.
If a gap would require moving a widget, existing folder or pin, USB preparation
refuses instead of inventing a protocol empty marker.

## Sharing with assistants

Prefer redacted summaries. Raw backups and JSON scans can reveal your entire app
inventory. No personal device dump is committed to fixtures. Public model/API
reference research during development does not send phone inventory.
