# Troubleshooting

[Home](../README.md) · [Safety](SAFETY.md) · [CLI reference](CLI.md)

## Command not found

For a checkout install, activate `.venv` or run `.venv/bin/sborganize` directly.
For pipx, run `pipx ensurepath` and open a new terminal. Python 3.11+ is required.
This alpha is installed from GitHub; an unrelated PyPI package is not a substitute.

## No USB device or trust error

Connect with a data-capable cable, unlock the phone, and choose Trust This
Computer. Check the phone in Finder, then run `sborganize doctor` again.
If explicit pairing is needed, use `python -m pymobiledevice3 lockdown pair`
inside the same environment that has the `[device]` extra installed.

More than one phone requires `--udid ID` on the device command. Wi-Fi devices
are not silently selected. USB reads have a 15-second timeout.

If the error says macOS denied USB service access, run in a local terminal with
access to usbmuxd. Sandboxed applications may need their own permission; pairing
again does not fix an OS access denial.

## Optional device package is missing

Install the source with `python -m pip install '.[device]'`, or use the documented
pipx spec with the `[device]` extra. The adapter is pinned to pymobiledevice3
11.50.2; using a different version is refused rather than guessed at runtime.
The offline demo does not need that dependency.

## No saved plan, or the wrong plan is selected

Run `sborganize plan`, then `sborganize show`. Successful plans select themselves,
including policy and review-derived plans. `show --plan FILE` and
`apply --plan FILE` explicitly choose another plan. A corrupted selection file
requires generating a fresh plan; paths outside plan storage are not followed.

## Layout changed since preview

Do not edit raw fingerprints. Re-read the phone and create/review a fresh plan.
App installs, manual icon moves and app bookkeeping can invalidate a source.
Automatic additive refresh is limited to the documented review-conversion mode.

## Anchored gaps cannot be encoded

The USB API uses XML plists. An empty slot before a fixed widget/folder/pin may
not have a supported representation. The tool refuses instead of inventing a
marker or moving the protected node. Try a less invasive existing-only plan;
some layouts need manual preparation before USB writes can be supported.

## Unknown app or unexpected category

Check the bundle ID locally with `scan --json`. Add an exact category and folder
map, or review a complete explicit policy. Names such as BankID, Nomad or CZ are
easy to misinterpret. Existing folder membership is context, not proof of purpose.
See [classification](CLASSIFICATION.md).

## Apple unavailable, or no model credits

Use ordinary rules commands. Apple is probed only with `--smart`; no Ollama setup
is needed and no cloud fallback occurs. Optional cloud requests require `--cloud`
and your own key. Missing credits never prevent offline rules or local inspection.

## Cloud review stops partway

Rerun the same command to reuse complete cached batches. Do not add `--refresh`
unless you intend new requests. Rejected fields have private diagnostics under
`reviews/rejected/`. An incomplete report is not an apply plan. Never paste a key,
raw backup or full inventory into an issue. See [model modes](MODELS.md).

## Readback differs after a write

Inspect the stage, phone and retained undo backup. Keep current state for diagnosis
and avoid concurrent edits. iOS may reflow or normalize fields. There is no automatic
retry/rollback. See the [recovery workflow](SAFETY.md).
