# Release checklist

Releases are GitHub prereleases until broad hardware compatibility and restore
are validated. Do not publish to PyPI without a separate deliberate decision.

1. Update matching versions in pyproject.toml and `src/sborganize/__init__.py`.
2. Update the changelog, current installation tag examples and compatibility notes.
3. Run pytest, Ruff, formatting and `python -m build`.
4. Run `python scripts/smoke_wheel.py dist/sborganize-VERSION-py3-none-any.whl`.
5. Run `python scripts/check_dist.py`; inspect artifacts and SHA256SUMS.
6. Inspect the git diff and tracked file list for private layouts, keys and host paths.
7. Push the reviewed commit; wait for Linux/macOS CI and the clean-wheel job.
8. Tag that exact commit `vVERSION` and create a GitHub prerelease with the wheel,
   source archive and SHA256SUMS. Explain limitations and where to start.

The release must not contain `.prototype`, local data roots, API keys, private
policies, raw scans or backups. Only synthetic samples belong in fixtures.
Use a body file for multiline release notes to preserve exact formatting.
Do not probe or write a maintainer's phone merely to make a release.
