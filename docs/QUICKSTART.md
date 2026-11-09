# Quick start

[Home](../README.md) · [中文](../README.zh-CN.md) · [CLI reference](CLI.md)

## Start with the bundled example

```sh
sborganize demo
sborganize demo --details
```

These commands need no phone, key or network and save nothing. The synthetic
example reduces five pages to three and groups 19 loose apps. One unknown app
remains for review. The score is a heuristic, not a quality guarantee.

## Rehearse the write protocol without USB

```sh
sborganize --data-dir /tmp/sborganize-demo demo --save
cd /tmp/sborganize-demo
sborganize --data-dir . show --after
sborganize --data-dir . apply --fixture examples/demo.json
sborganize --data-dir . backups
sborganize --data-dir . restore --fixture simulations/latest.json
```

Answer yes at the fixture prompts. The fixture remains unchanged; results go to
`simulations/`. Even the unchanged write and readback checks run against the fake
device. No USB connection or network request occurs.

## Connect an iPhone

1. Connect by USB, unlock it and trust this computer.
2. Run `sborganize doctor`.
3. Run `sborganize scan` to inspect the current layout.
4. Run `sborganize plan --existing-only --device-ready`.
5. Run `sborganize show --after`, then `sborganize show --details` if needed.

There have still been no phone writes. Existing-only mode keeps already grouped
apps in place and does not create or repack folders. For intentional whole-layout
changes, use [an explicit policy](POLICY.md).

## Apply a reviewed plan

```sh
sborganize apply --experimental-write
```

The latest successfully generated plan is selected, whether it came from rules,
review conversion or a policy. `--plan PATH` selects a different saved plan.
The default confirmation is No. Keep the phone unlocked and avoid concurrent edits.
An exact source backup is verified before the first write.

The stages are shown in the terminal: unchanged round-trip, approved write,
target readback. A mismatch stops the operation and preserves the backup.
There is no automatic retry or rollback. See [safety](SAFETY.md).

## Keep preferences

```sh
sborganize config init
sborganize config path
sborganize config show
```

Edit the printed TOML file to add pins, app categories and target folder names.
`init` never overwrites it. Start from [the example](examples/config.toml).

All of this works without model credits. Optional [cloud advice](MODELS.md) must
be explicitly selected and is subject to review.
