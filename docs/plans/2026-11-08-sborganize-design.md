# sborganize — Design

**Date:** 2026-11-08\
**Status:** Accepted (brainstorm validated)\
**Scope:** Open-source CLI only. No branded app, no App Store product.

**Prototype checkpoint:** See [PROTOTYPE.md](../PROTOTYPE.md) for implemented scope.
The accepted architecture remains the target. The prototype is offline-first,
supports USB reads, fixture rehearsals and guarded experimental phone writes.

**User amendment (2026-11-08):** Apple on-device → rules is now the local smart
chain; Ollama is excluded. The user explicitly added optional OpenRouter support,
available only with `--cloud` and a local key. Never send raw IconState to a model.
Experimental phone writes require `--device-ready` plus `--experimental-write`
and the complete safety gate. See PRIVACY.md for the current data contract.

## Problem

iPhone home screens accumulate loose apps, sparse pages, and inconsistent folders. Existing options are either:

- **Manual drag** — slow, error-prone at scale
- **Unjiggle + script kits** (e.g. lunkerchen/iphone-home-screen-organizer) — capable, but fragmented commands, cloud LLM by default, and another product’s write path

We want something **simpler, smarter where it matters, privacy-first**, with a calm Nordic CLI — and **our own SpringBoard read/write**, not a wrapper around Unjiggle.

## Goals

1. **Intuitive** — few commands; default path is safe and obvious
2. **Privacy first** — local by default; external metadata sharing requires explicit `--cloud`
3. **Local intelligence** — rules first; `--smart` uses Apple on-device → rules; no Ollama
4. **Self-owned I/O** — read/write `IconState` via `pymobiledevice3`, not Unjiggle
5. **Safe writes** — preview by default; explicit `apply`; backup + round-trip before mutation
6. **CLI only (v1)** — ship a tool people can clone and run; GUI is out of scope

## Non-goals (v1)

- Branded consumer app / menu bar / App Store
- Jailbreak, uninstall, or Screen Time scraping as a dependency
- Sending raw layouts or implicit/default requests to hosted AI APIs
- Pixel-perfect guarantee that iOS will keep every icon where we wrote it forever
- Replacing Unjiggle’s commercial GUI product

## Decisions (from brainstorm)

| Topic | Choice |
|-------|--------|
| Device I/O | Self-implemented on `pymobiledevice3` |
| Language | Python 3.11+ |
| Intelligence | Rules primary; `--smart` → Apple on-device → rules; optional explicit `--cloud` |
| Writes | Available, but **preview by default**; explicit `apply` |
| Safety | Mandatory backup + round-trip before apply |
| Product shape | Open-source GitHub CLI; technical name `sborganize` |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  CLI (Typer)                                            │
│  scan · score · plan · apply · restore · demo · doctor  │
└───────────────┬─────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────┐
│  Safety                                                 │
│  backup · verify · round-trip · confirm · restore       │
└───────────────┬─────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────┐
│  Planner                                                │
│  rules → (optional) smart refine → Plan + Diff          │
└───────────────┬─────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────┐
│  Model                                                  │
│  Layout · Page · Folder · Icon · Diff · Score           │
└───────────────┬─────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────┐
│  Device                                                 │
│  lockdownd / USB · get_icon_state · set_icon_state      │
│  (demo/fixture path when no phone)                      │
└─────────────────────────────────────────────────────────┘
```

### Layers

1. **Device** — Connect over USB (trusted). Read/write SpringBoard icon state. Never touch photos, messages, contacts, health, mail bodies, or browsing history.
2. **Model** — Immutable-friendly layout graph and an explicit `Plan` / `Diff` (what would change).
3. **Planner** — Deterministic rules by default. Optional local model only to resolve ambiguity.
4. **Safety** — Gate every mutation.
5. **CLI** — Thin, calm presentation of the above.

### On-disk data (`~/.sborganize/`)

```
~/.sborganize/
  config.toml          # prefs: dock pins, folder map, feature flags
  cache/
    itunes_lookup.json # optional App Store metadata (opt-in network)
  backups/
    <timestamp>-<udid>.json
  plans/
    latest.json        # last plan for apply
```

No analytics. No accounts. No telemetry.

## Data model (conceptual)

```text
Layout
  udid, ios_version?, captured_at
  dock: [Slot]
  pages: [Page]
  library_only?: [Icon]   # if/when inventory beyond home screen is available

Page
  index
  slots: [Slot]           # grid; empty slots represented explicitly or as holes

Slot
  empty | Icon | Folder | WidgetRef?

Icon
  bundle_id
  display_name
  display_identifier?
  category?               # from rules / cache / smart

Folder
  name
  pages: [[Icon]]         # folder-internal pages (3×3 typical)
```

Raw SpringBoard plist/list-of-lists from `get_icon_state` is normalized into this model on read, and serialized back on write. Unknown node types are preserved as opaque payloads so we do not drop widgets or future shapes.

## CLI surface

| Command | Mutates phone? | Purpose |
|---------|----------------|---------|
| `sborganize demo` | No | Sample fixture layout; no USB |
| `sborganize doctor` | No | Device, trust, Python, optional Apple availability probe |
| `sborganize scan` | No | Print current layout (pages, folders, loose apps) |
| `sborganize score` | No | Organization score + short diagnosis |
| `sborganize plan` | No | Build plan; write `plans/latest.json`; print calm diff |
| `sborganize apply` | **Yes** | Apply last (or given) plan after backup + round-trip + confirm |
| `sborganize restore` | **Yes** | Restore a backup |
| `sborganize backup` | No* | Save current layout only (*does not rearrange) |

### Typical flow

```bash
sborganize doctor
sborganize scan
sborganize score
sborganize plan                 # rules only
sborganize plan --smart         # optional local refine
sborganize apply                # confirm → backup → round-trip → write
# if wrong:
sborganize restore
```

### Flags (stable intent)

- `--udid` — multi-device
- `--fixture PATH` — offline layout JSON
- `--existing-only` — on `plan`, reuse existing folders and keep previously grouped
  apps at their current positions; create no folders and skip folder repacking
- `--smart` — enable local model refine on `plan`
- `--cloud` — separately opt in to OpenRouter with minimized metadata; no automatic fallback
- `--device-ready` — prepare an XML-compatible target and show loose-position compaction
- `--experimental-write` — explicitly enable live apply/restore through the safety gate
- `--no-network` — disable iTunes/App Store lookup
- `--json` — machine-readable output
- `--yes` — skip interactive confirm on `apply`/`restore` (still runs backup + round-trip)

## Planner

### Default (rules)

1. **Respect pins** — dock apps and user-pinned bundle IDs never move unless config says so
2. **Reuse folders** — map loose apps into existing folders by:
   - bundle ID overrides (`config.toml`)
   - display-name / bundle heuristics
   - roles supported by multiple known apps already inside emoji or mixed folders;
     leave multiple plausible destinations for explicit review
   - optional App Store primary genre (network opt-in)
   - Service-region routing takes priority: recognized mainland-China and Hong Kong
     local services use separate regional folders. Global products use domain groups;
     language and publisher origin do not decide region. Unknown placements need review.
3. **Create sparingly** — only create a new folder when ≥ N loose apps share a clear category (default N=3)
4. **Compact** — pack folder pages (e.g. 9 per page); drop empty home-screen pages after moves
5. **Never delete/uninstall** — plans only rearrange; archive/delete are out of scope

### `--smart` refine

Input to the model: **names, categories, folder titles, counts** — not photos or messages. Runs locally:

1. Try **Apple on-device** path if available on this Mac/OS (best-effort; may be absent)
2. Else **no-op** — keep rules plan; report the real availability reason once

`--cloud` is a separate optional mode, never an automatic fallback. It requires
`OPENROUTER_API_KEY` and sends only unresolved app names/IDs plus folder labels,
categories and counts to OpenRouter and its routed provider. Known peer names,
raw layouts and device identity are omitted. `--no-network` rejects this mode.

### Whole-inventory review (2026-11-09)

The separate `review` command reassesses all recognized Home Screen apps,
including apps inside folders, dock and pins. Offline rules remain default.
`review --cloud` explicitly sends all app names/IDs and current folder membership
in bounded OpenRouter batches, without any local-model probe. Current regional
membership is not an authoritative rule in this mode. Reports are advisory,
stored separately under `reviews/`, and rejected by `apply`; no full layout is
generated. Completed batches are privately cached for resumption. See the
[review design](2026-11-09-whole-inventory-review.md) for scope and validation.

After review, `review --recheck` validates saved candidates locally and
`plan --from-review` builds a separate regrouping preview. Known app identities,
independent region evidence, explicit local mappings and destination domains take
precedence over model confidence. Existing folders cannot be removed or emptied;
explicit local mappings alone may request a new folder. Optional device refresh
accepts only appended recognized icons and allowed bookkeeping changes. Any other
structure change requires a new review. All normal write gates remain mandatory.

Plan refinement may only reassign unresolved apps into eligible existing folders.
Whole-inventory review may recommend moves between existing folders but does not
apply them. Future extensions may:

- Suggest folder renames
- Reassign ambiguous apps
- Propose merge/split of thin folders

Model may **not**:

- Invent uninstalls
- Send data to cloud endpoints without explicit `--cloud` opt-in
- Bypass pins

Output is validated against the layout graph before merge into the Plan.

## Safety protocol

Every `apply` / mutating `restore`:

1. **Refuse** if no trusted device (unless fixture dry-run mode that never hits USB write)
2. **Backup** current `IconState` to `~/.sborganize/backups/`
3. **Confirm** — show summary (pages Δ, moves, new folders); require interactive yes unless `--yes`. Confirm before any write, including the unchanged round-trip; re-read after confirmation to reject concurrent changes.
4. **Round-trip** — write current state unchanged (or dedicated verify path), read back, compare structural fingerprint; abort on mismatch
5. **Write** plan’s target state
6. **Read-back check** — compare to expected; if diverge, keep backup and report clearly (iOS may reflow)

`restore` uses the same confirm + verify mindset; prefers the newest backup for the UDID unless a path is given.

## Scoring (v1)

Simple, explainable metrics — not a black box:

- **Page tax** — pages beyond a soft target (default 3–4)
- **Loose ratio** — icons on home screen outside dock/folders
- **Sparsity** — empty slots / half-empty pages
- **Folder bloat** — folders with many near-empty internal pages
- **Pin health** — pinned apps still findable on page 1 / dock

Print a 0–100 score plus 2–4 bullet diagnoses. Same tone in `demo`.

In existing-only mode, report the literal grouping percentage (recognized Home
Screen apps in folders / all recognized Home Screen apps, excluding dock). Label
it as a grouping rate and omit density/packing penalties. The general layout score
retains all five metrics. JSON includes scope and counts; saved plans retain the
policy used for the comparison.

## UX / visual language (CLI)

Nordic minimal, not “hacker neon”:

- Neutral palette; use color only for status (ok / warn / danger)
- Prefer whitespace and alignment over boxes and ASCII art
- One primary number (`score`), one short paragraph, then a scannable list
- Diffs: `move`, `into`, `folder+`, `page-` — verbs first
- English UI strings in v1; keep copy short (i18n later if needed)

## Privacy principles

See `PRIVACY.md`. Summary:

- USB layout only
- Local prefs/backups only
- Network opt-in for metadata
- `--smart` stays local (Apple → rules); cloud sharing needs separate explicit `--cloud`
- No telemetry

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| `set_icon_state` flaky across iOS versions | Round-trip gate; fixtures per iOS; document supported versions |
| iOS reflows after write | Read-back warning; easy restore; never claim pixel permanence |
| Folder/widget shapes we don’t understand | Opaque preserve; refuse plan that would drop unknown nodes |
| Local model hallucinates bad folders | Schema validation; pins; rules as floor |
| Users expect Unjiggle parity day one | Honest roadmap; `demo` first; write behind `apply` |

## Success criteria (v1)

- `demo` works with zero hardware
- `scan` + `score` on a real trusted iPhone
- `plan` produces a reviewable diff without network
- `apply` refuses without backup/round-trip/confirm
- `restore` recovers a known backup in tests
- Docs make privacy and safety obvious in under two minutes of reading

## Open questions (deferred)

- Exact Apple on-device hook (Foundation Models / other) — probe in implementation; soft-fail
- Whether App Library-only apps are in scope for planning
- Widget placement policy beyond “preserve”
- License final choice relative to `pymobiledevice3` (likely GPL-compatible; confirm in `LICENSE`)
