# CLI reference

[Home](../README.md) · [Quick start](QUICKSTART.md) · [Policy workflow](POLICY.md)

Run `sborganize` for a short starting point, `sborganize --help` for command groups,
or `sborganize COMMAND --help` for flags. Most work begins with `demo`, `doctor`,
`plan` and `show`.

## Global options

- `--data-dir PATH`: choose local plans, backups, cache and preferences.
- `--config FILE`: choose another TOML config.
- `--no-color`: disable colors. The `NO_COLOR` environment variable also works.
- `--version`: print the version.
- `--install-completion`: install completion for the current shell.

Put these **before** the command: `sborganize --data-dir ./local-data plan`.

## Start here

`demo` uses bundled synthetic data. `--details` adds the source layout and every
move. `--save` saves `examples/demo.json` and a fixture plan for offline rehearsal;
use a separate data directory to keep it apart from phone plans.

`guide [TOPIC]` reads an offline guide: `start`, `offline`, `config`, `policy`,
`cloud`, `safety`.

`doctor` checks trusted USB read access. `--fixture FILE` uses a local sample.
Only `doctor --smart` probes Apple model availability.

## Inspect and plan

`scan` prints the current dock, pages and folders.

`score` explains a layout score. `--existing-only` reports the literal grouping
percentage instead, excluding the dock and page-density penalties.

`plan` creates a rules preview. Important flags:

- `--existing-only`: retain already grouped apps, avoid new folders and repacking.
- `--device-ready`: prepare an XML-compatible target and expose slot compaction.
- `--details`: list every position change rather than summarize retained groups.
- `--cloud` or `--smart`: explicitly select optional refinement; cannot be mixed.
- `--no-network`: blocks cloud before reading a device or making requests.
- `--policy FILE`: deliberate exhaustive emoji redesign; see [policies](POLICY.md).
- `--from-review FILE`: locally validate saved cloud candidates and create a
  separate regrouping plan. `--source-plan FILE` supplies its original snapshot.
- `--refresh-device`: with the preceding two flags, allow only appended recognized
  icons and known app bookkeeping changes. Other structural changes refuse.

`show` inspects the selected plan without USB or inference. `--after` shows the
full proposed layout; `--details` lists every move; `--plan FILE` selects a file.

`review` creates an advisory all-app report. `--cloud` shares all recognized app
names/IDs and current folder membership. Complete batches are cached privately.
`--refresh` bypasses cache; `--recheck FILE` revalidates saved candidates locally.
An advisory review cannot be passed directly to apply.

`--fixture FILE` replaces USB for scan, score, plan, review, backup and doctor.
`--udid ID` explicitly selects among trusted USB phones. They cannot be combined.

## Local files

`config init` creates commented defaults and never overwrites an existing file.
`config path` prints its path; `config show` prints effective preferences.

`policy export` writes an editable draft and paired source snapshot. Input may be
USB, `--fixture FILE`, or `--from-plan FILE`. `--output FILE.json` changes the
destination; existing files, backup storage and plan storage are protected.

`backup` saves the exact current source and never rearranges it.
`backups` lists recent local backups, including source, app/page counts and paths.
`--limit N` controls the list. Invalid backups are reported separately.

## Write with confirmation

`apply` uses the selected plan; `--plan FILE` overrides it.
`restore --backup FILE` uses an exact backup; without a file it selects the newest
backup for the connected source and device.

Live operations need `--experimental-write`. Fixture operations need
`--fixture FILE` and save separate simulation output. These modes cannot be mixed.
`--yes` skips the confirmation prompt only. All other gates remain mandatory.
`--output FILE` changes simulation output and is refused for live writes.

## Scripts and output

`--json` is supported on demo, scan, score, plan, show, review, doctor, backup,
backups and config show. Human notices/progress use stderr when JSON is requested.
JSON stdout is a single parseable value and contains no terminal styling.

Exit 0 means the command completed; exit 1 reports an operational failure or
incomplete review; exit 2 is invalid CLI usage. Errors go to stderr. Plans and JSON
scans can contain sensitive device metadata; do not post them publicly.

## Storage

The default root is `~/.sborganize/`:

```text
config.toml                 your preferences
plans/latest.json           normal rules/refinement plan
plans/reorganization.json   converted saved review
plans/domain-policy.json    explicit policy plan
plans/selected.json         most recently generated plan selection
backups/                    exact raw source backups
reviews/                    advice, audits and rejection diagnostics
policies/                   editable policy drafts and source snapshots
cache/                      model bridge and successful cloud-review batches
examples/                   explicitly saved synthetic demo
simulations/                fixture-only apply/restore output
```

New data files are private. Moving or editing a snapshot does not change the phone.
