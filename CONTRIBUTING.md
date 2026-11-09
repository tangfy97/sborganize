# Contributing

sborganize is an open-source CLI for careful iPhone Home Screen organization.

Start with the [development guide](docs/DEVELOPMENT.md), [design](docs/plans/2026-11-08-sborganize-design.md),
[privacy](PRIVACY.md) and [safety protocol](docs/SAFETY.md).

## Local checks

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
ruff check .
ruff format --check .
python -m build
```

Tests require no phone, key or model assets. Use synthetic fixtures and mocked
services. Run the installed-wheel smoke test described in the development guide
when changing packaging or bundled resources.

## Changes that are welcome

- Clearer CLI flows and actionable errors without noisy terminal dashboards.
- Narrow, source-backed app-identity rules; exact bundle IDs when names collide.
- Better explicit policy workflows and explainable classification.
- Reproducible compatibility reports with redacted platform information.
- Meaningful tests for safety gates, serialization, JSON and no-network behavior.

## Review expectations

Keep changes focused and update documentation when behavior changes. Explain the
problem, resulting behavior and validation. New planner behavior needs a synthetic
example; every device-write path needs safety-gate coverage. Source folders may
only be renamed/reordered through explicit policy declarations. App payloads,
dock, pins and unknown nodes remain protected.

Default and Apple-only modes must never send cloud requests, even if a key is
configured. OpenRouter needs explicit opt-in. No analytics or raw layout uploads.

Do not commit private device snapshots, backups, policies, API keys or full personal
inventories. Public app facts are fine; private dumps are not suitable fixtures.
See [SECURITY.md](SECURITY.md) for sensitive reports.
