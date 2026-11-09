# Development

[Contributing](../CONTRIBUTING.md) · [Architecture](plans/2026-11-08-sborganize-design.md) · [Privacy](../PRIVACY.md)

## Setup

```sh
git clone https://github.com/tangfy97/sborganize.git
cd sborganize
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
ruff check .
ruff format --check .
python -m build
```

The device extra is optional. Normal tests use fake USB services and synthetic
fixtures; do not connect a personal phone for CI. No API key or model asset is needed.

## Package map

```text
src/sborganize/
  cli.py              command orchestration and explicit I/O choices
  local.py            config, guides, saved-plan inspection, backup listing
  terminal.py         restrained color, literal labels, plain redirected output
  guides.py           bundled offline manuals
  model.py            lossless graph, fingerprints and invariants
  planner.py          deterministic grouping and saved plans
  policy.py           exhaustive app policies and explicit folder edits
  reorganization.py   locally rechecked advice and strict additive refresh
  review.py           advisory inventory review, validation and cache
  device.py           self-owned pymobiledevice3 adapter and fixture device
  safety.py           backup, confirmation, round-trip and readback gate
  storage.py          private atomic files and selected-plan pointer
  apple.py            optional local bridge
  openrouter.py       explicitly opted-in metadata-only provider
```

Keep pure planning separate from device I/O. Changes to serialized plans must
preserve older optional-field defaults. New behavior needs semantic fixture tests,
not tests that merely repeat implementation details.

## Terminal and JSON contract

Human output goes through `terminal.py`. App labels are literal text, not Rich
markup. Remove control escapes before terminal rendering. JSON uses a separate
plain emitter and stderr for notices; never decorate stdout JSON.

A default preview groups destination changes and summarizes retained-group shifts.
`--details` exposes every position. Apply always shows the full reviewed changes.
Do not print a preview's “No phone writes” footer as an actual write status.

## Distribution

Build with `python -m build`, then run:

```sh
python scripts/smoke_wheel.py dist/sborganize-0.1.0a10-py3-none-any.whl
```

The script installs the wheel into a temporary environment and exercises the
packaged demo, config, guides and fixture apply/restore outside the checkout.
It installs dependencies from the configured package index, but does not call a
phone or model provider. CI performs the same check before uploading artifacts.

Version strings in pyproject.toml and `__init__.py` must match. Publish GitHub
prereleases with the wheel, source archive and SHA256SUMS. Never upload local
`.prototype`, backups, environment files, private policies or raw phone layouts.
See [release steps](RELEASING.md).

## Device verification

Read [safety](SAFETY.md), [compatibility](COMPATIBILITY.md) and the
[IconState research](research/springboard-icon-state.md) before hardware work.
Keep exact backups and make confirmation the last step before writes. Default
read adapters cannot write. A mismatch stops; never widen unknown-node exclusions
just to make a device pass. Restore needs the same gate.
