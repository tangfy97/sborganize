# sborganize — Implementation Plan

**Date:** 2026-11-08\
**Design:** [2026-11-08-sborganize-design.md](./2026-11-08-sborganize-design.md)

Ship in vertical slices. Each slice leaves the CLI runnable and documented.

**Prototype checkpoint (2026-11-08):** Phases 0–3 are implemented, with semantic
CLI regression tests rather than full renderer snapshots. Phase 4 has an optional
read adapter tested against fake services, awaiting hardware validation. Phase 5
has fixture rehearsals and opt-in experimental writes, awaiting hardware validation.
Phase 6 has a compiled Apple on-device bridge and a separately opted-in OpenRouter
path; Apple currently reports model_not_ready on the development Mac. See
[prototype scope](../PROTOTYPE.md). Modules use a flat package at this size.

**2026-11-09 extension:** `review` now produces whole-inventory advisory reports,
including grouped apps. Explicit `review --cloud` selects OpenRouter directly,
with validated batches, resumable private caches and coverage checks. Offline
review of a saved personal snapshot includes all 244 apps. The first real-key
unresolved-only request completed but all four suggestions were rejected; no
accepted live model suggestions or phone writes are claimed. Full cloud review
quality remains to be assessed. See [review design](2026-11-09-whole-inventory-review.md).

**Later 2026-11-09 checkpoint:** The full cloud run covered 244/244 apps, exposing
semantic errors despite schema validity. Local recheck, known-identity and region/
folder-domain checks now filter those errors. `plan --from-review` converts saved
advice plus explicit local rules into a separate preview. The current phone has
246 apps; a strictly additive refresh retained current payloads, with two new apps
handled locally rather than claimed as cloud-reviewed. Verified backup and XML
preparation succeeded. Hardware writes awaited review/confirmation at that checkpoint.

**Authorized execution checkpoint:** The first unchanged round-trip detected
new app icons and lost opaque widget fields, so it stopped before the target.
After explicit user-requested retry from the inspected current source, the
unchanged round-trip passed and the target was written: 248 apps, three pages,
two new icons kept loose. A newly empty trailing folder page explained the
initial strict readback error; the planner fix makes the expected fingerprint
match the saved immediate readback. Later changes were observed and their origin
is awaiting clarification. No further writes occurred. Hardware restore and
broad compatibility remain unvalidated. Synthetic regressions cover these cases.

---

## Phase 0 — Skeleton (docs + package)

**Outcome:** Installable empty CLI that prints help.

- [x] Repo layout, README, PRIVACY, design docs
- [x] `pyproject.toml` (package `sborganize`, entry point `sborganize`)
- [x] Typer commands: `demo`, `doctor`, `scan`, `score`, `plan`, `apply`, `restore`, `backup`
- [x] `src/sborganize/__init__.py` version
- [x] Ruff + pytest wired; `pip` install editable
- [x] LICENSE (GPL-3.0-or-later, matching optional pymobiledevice3)

**Exit:** `pip install -e .` → `sborganize --help`

---

## Phase 1 — Model + fixtures (no USB)

**Outcome:** Parse/normalize sample IconState; score and print layout offline.

- [x] `model.py` — Layout, Page, Folder, Icon, Slot
- [x] `model.py` / `storage.py` — raw list ↔ Layout / plist; preserve unknown nodes
- [x] `fixtures/demo_layout.json` — synthetic multi-page sample, also packaged
- [x] `sborganize demo` — load fixture, print scan-like view + score + plan
- [x] Unit tests for round-trip serialize (raw → model → raw)

**Exit:** `sborganize demo` and `sborganize score --fixture …` work offline

---

## Phase 2 — Score + calm CLI rendering

**Outcome:** Nordic-minimal terminal output people can scan in seconds.

- [x] `score.py` — page tax, loose ratio, sparsity, folder bloat, pin health
- [x] `render.py` — quiet layout dump, score card, diff verbs
- [x] `--json` for scan/score/plan
- [ ] Snapshot tests for renderer (ANSI optional / stripped)

**Exit:** Fixture scores are stable and explained in bullets

---

## Phase 3 — Rules planner

**Outcome:** Useful plans without any LLM or network.

- [x] `config.py` — load `~/.sborganize/config.toml` with defaults
- [x] `planner.py` — pin respect, folder match, create threshold, compact
- [x] `planner.py` — Plan + human/json diff
- [x] `sborganize plan --fixture …` writes `plans/latest.json`
- [x] Tests: loose apps fold into existing folders; pins immobile; trailing empty pages drop

**Exit:** Demo fixture plan looks sensible; pure deterministic

---

## Phase 4 — Device read path

**Outcome:** Real iPhone scan over USB.

- [x] `device.py` — lockdown / usbmux; clear trust errors (fake-service verified)
- [x] `device.py` — `get_icon_state`; normalize via model
- [x] `sborganize scan` / `score` without `--fixture` (hardware validation pending)
- [x] `sborganize doctor` — device read access and actionable pairing hints
- [x] Document iOS / pairing caveats (link research note)
- [ ] Validate on a physical iPhone and record OS / raw shape

**Exit:** Developer can `scan` a trusted phone; failures are actionable

---

## Phase 5 — Backup + round-trip + write

**Outcome:** Safe apply/restore.

- [x] `safety.py` — timestamped JSON backups per UDID and source
- [x] `model.py` / `safety.py` — strict fingerprint; round-trip unchanged write on fixtures
- [x] `device.py` — guarded `set_icon_state` through pinned pymobiledevice3
- [x] `sborganize backup`; fixture and gated experimental USB `apply` / `restore`
- [x] Apply gate: backup → confirm → round-trip → write → read-back
- [x] Integration test with mocked device service (no hardware)

Confirmation moved before the unchanged round-trip so declining makes zero writes.
Live writes now require explicit experimental opt-in, a device-ready plan and
the same gate. Full phone apply/restore validation is still pending.

**Exit:** Apply is impossible without the gate; restore covered by tests

---

## Phase 6 — Optional metadata + model refinement

**Outcome:** Apple-only local refinement by default; user-requested OpenRouter is explicit opt-in.

- [ ] `meta/itunes_lookup.py` — opt-in network; cache under `~/.sborganize/cache/`
- [ ] `--no-network` honored everywhere
- [x] `apple.py` + bundled Swift source — compiled on-device probe / guided generation
- [x] `smart.py` — validate suggestions against pins, regions, targets and inventory
- [x] `sborganize plan --smart` + `doctor --smart` Apple availability checks
- [x] `openrouter.py` — optional minimized-metadata requests, separate `--cloud` opt-in
- [x] `review.py` — all-app advice, region/config validation, batching/cache and partial reports
- [ ] Accepted real model suggestions / full cloud review validation (Apple assets not ready)

Ollama was removed from scope at the user's request.

**Exit:** `--smart` never calls hosted LLM APIs; degrades cleanly to rules.
Only explicit `--cloud` may use OpenRouter; no default or hidden cloud fallback.

---

## Phase 7 — Hardening + OSS polish

**Outcome:** Others can clone and contribute.

- [x] CONTRIBUTING.md, SECURITY.md
- [ ] CI: lint + unit tests on macOS (and Linux model-only jobs)
- [ ] Support matrix note (macOS host, iOS versions tested)
- [x] Example `config.toml`
- [x] Changelog

**Exit:** External contributor can run demo + tests without a phone

---

## Suggested build order (this week)

1. Phase 0 + 1 (skeleton + demo) — same day\
2. Phase 2 + 3 (score + rules plan) — next\
3. Phase 4 (real scan) when a phone is available\
4. Phase 5 before any real rearrange\
5. Phase 6 only after rules feel good\

## Explicit non-work until later

- GUI / Swift shell\
- Implicit cloud providers or raw layout uploads
- Uninstall / archive automation\
- App Store distribution\

## Definition of done for “v1 usable”

A stranger on a Mac can:

1. `pip install -e .`\
2. `sborganize demo` and understand the score\
3. Plug in iPhone, Trust, `sborganize scan && sborganize plan`\
4. Read the diff, then `sborganize apply` with eyes open\
5. `sborganize restore` if they dislike the result\

…and know from PRIVACY.md which local mode ran and what metadata an explicit
cloud run would share.
