# Whole-inventory organization review

Date: 2026-11-09. Extends the accepted CLI design in response to the user's request
to reassess apps already inside folders and to stop spending time on local models.

## Behavior

Keep `plan --existing-only` conservative and preserve its unresolved-only cloud
scope. Add a separate `review` command for every recognized Home Screen app,
including grouped apps, dock and pins. Default review uses offline rules;
`review --cloud` explicitly selects OpenRouter without probing Apple or Ollama.
Reuse existing folder names and domain categories. Mainland-China and Hong Kong
local services have separate groups; all other markets use domain folders.
Existing regional membership is context rather than an authoritative region rule.

The alternatives were expanding `plan --cloud` implicitly, or immediately adding
bulk rearrangement out of existing folders. A separate advisory command makes
the broader metadata scope explicit and allows recommendations to be examined
before solving folder-emptying, compaction and write semantics.

## Data and validation

Build stable opaque app/folder IDs from the inventory. Send names/IDs, current
folder labels, domain/region hints and folder counts/categories. Omit raw IconState,
device identity, coordinates, opaque nodes and credentials. Structured batch
responses must cover each requested app ID exactly once with bounded fields and
existing target IDs. Missing/duplicate/invalid results leave the batch unreviewed.
The requested schema uses a required object property for each app ID, rather than
an array with repeated ID enums. Well-formed legacy arrays still validate. Domain
and reason fields must be nonempty; unknowns have an explicit sentinel. Duplicate
JSON object keys are rejected. Failures save bounded known-field candidate data
and field/type/length diagnostics privately under `reviews/rejected/`, separately
from successful caches. No malformed response is accepted to improve coverage.
Uncertainty, regional conflicts and explicit config conflicts need human review.
Protected source apps still receive advice, but their status remains protected.

Requests contain at most 16 apps and 4096 output tokens, with a maximum inventory
of 512 icons and 96 folders. There are no automatic retries or provider fallbacks.
Successful valid batches are privately cached by model and exact request content;
rerunning resumes from cache. Provider/key acquisition is lazy, so an entirely
cached run needs neither a key nor a prompt. `--refresh` deliberately bypasses
cache. Failed runs save partial coverage and exit with status 1.

## Output and safety

Save `reviews/latest.json`: kind `organization_review`, per-app keep/move/review/
protected/unreviewed status, reasons, folder incoming/outgoing counts, source
fingerprint, model and coverage. It contains no raw source or writable target.
It never overwrites `plans/latest.json`; plan loading rejects an advisory report.
`--from-plan` reviews the original saved snapshot without reading USB and clearly
labels that limitation. Subsequent `review --recheck` validates saved original
candidates without inference. `plan --from-review` creates a separate preview at
`plans/reorganization.json`, honoring strong rules before model suggestions.
Regional claims require independent evidence, known app identities override
conflicting domains and destination folders need established matching roles.
Explicit local mappings may create a new folder; the model cannot. Existing
folders cannot be emptied or removed. Edited editable folders may shift remaining
apps while removing gaps, and every such move is shown. The apply gate is unchanged.

`--refresh-device` accepts only newly appended recognized icons and allowed
bookkeeping changes on existing apps from the same device. Existing structure,
opaque nodes and folder metadata must remain unchanged. New icons use explicit
local rules or remain loose; coverage metadata distinguishes them from the old
model-reviewed inventory. Other changes require a new review.

## Verification

Synthetic tests cover grouped apps, dock/pins, nested/opaque folders, independent
region assessment, explicit overrides, incomplete and malformed batches, cache
resume/refresh, request bounds, metadata minimization and CLI snapshot isolation.
An offline pass over the saved personal snapshot verifies all 244 recognized
apps are included. No personal dump is added to fixtures and no phone is written.
Live cloud quality requires the user to run with their ephemeral local key.

The first live full review failed batch validation at 0/244. The original response
was not retained, so its exact cause is unknown. The revised contract and private
diagnostics address reproducibility and are verified with synthetic HTTP tests.
OpenRouter notes that schema enforcement varies by provider; local validation
remains required. Reference: [structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs).

The next real-key run covered 244/244 apps. It still misidentified CZ, contradicted
its own GoPay destination and confused weather, cloud storage and generic Home
semantics. Local rules and validation now address these cases. The user assigned
their four self-authored prototypes to Test. A fresh USB read found two appended
icons; the 246-app preview reuses prior advice, handles those additions locally and
makes no new inference request. Physical write validation remains pending.
