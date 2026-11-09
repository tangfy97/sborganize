# Optional model modes

[Home](../README.md) · [Privacy](../PRIVACY.md) · [Classification](CLASSIFICATION.md)

Rules are the default and require no credits. The demo, config, policy mode,
backups, saved-plan inspection and local rechecks do not make model requests.

## Apple on this Mac

`plan --smart` uses the native Foundation Models bridge when available. It never
calls Ollama or a hosted fallback. If unavailable, rules remain. `doctor --smart`
reports readiness; ordinary doctor does not probe models.

## Explicit OpenRouter opt-in

`plan --cloud` refines at most eight unresolved loose apps. It sends minimized
app metadata and folder summaries. `review --cloud` has broader scope: all
recognized Home Screen app names/IDs and current folder membership in batches
of 16, with up to 512 icons and 96 folders supported.

The optional model is configured by `[smart].openrouter_model`. The bundled
default is `qwen/qwen3.5-flash-02-23`; availability and prices can change.
Set spending limits in your provider account if needed. No live paid request
is needed merely to try or test this repository.

The key comes from `OPENROUTER_API_KEY` or hidden terminal input for the current
process only. It is never written into the config, plans or reports. Noninteractive
cloud runs need the environment variable. The key alone enables no network access.

## Results and resuming

Complete valid review batches are cached by model and request content. Repeating
the same run reuses them; `--refresh` deliberately requests them again. An invalid,
missing or duplicate app response is not cached as successful. The partial report
records coverage and exits unsuccessfully.

Schema completeness is not semantic correctness. Validate service region, actual
app identity and folder roles. Regional claims require independent evidence; a
Chinese publisher does not establish a mainland-local service. Advice cannot write
directly. Use `review --recheck` and then `plan --from-review` to convert saved
candidates into a separately reviewed plan, without another model request.

`--no-network` rejects cloud before any device read. There are no implicit cloud
fallbacks, provider/model fallbacks or automatic inference retries. Prompts exclude
raw IconState, device identity, widgets, screenshots, credentials and app contents.
Metadata such as app names can still reveal interests; read [PRIVACY.md](../PRIVACY.md).
