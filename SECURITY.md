# Security

Report vulnerabilities through the repository's **Security → Report a vulnerability**
channel when available. Do not post exploit details, credentials or raw device
backups in a public issue. If private reporting is unavailable, open a minimal
issue requesting a private contact route without including sensitive material.

## Sensitive boundaries

- A trusted USB relationship is powerful. Treat the host Mac and local data root
  as sensitive. Device I/O uses our adapter directly through pinned pymobiledevice3.
- Apply/restore preserve raw backups and require freshness, confirmation, unchanged
  round-trip and target readback. A transport error may occur after a write;
  automatic retries and rollback are deliberately absent.
- Default, policy and Apple-only modes make no cloud calls. OpenRouter requires
  explicit `--cloud`. Model prompts must never include raw IconState, device IDs,
  screenshots, credentials or app-container data.
- Cloud full review shares a broader metadata scope than unresolved-only planning.
  Local reports and caches contain sensitive app metadata. Keep them out of git.
- Explicit folder edits may change only declared names and positions. Other folder
  metadata, app payloads, dock, pins and opaque nodes retain strict validation.
- App labels are untrusted terminal text. Do not evaluate Rich markup or terminal
  escape sequences from them.

Keys come from local environment variables or hidden ephemeral terminal input.
They never belong in config, plans, error bodies, fixtures or application logs.

Security fixes target the latest main/alpha release until a stable version exists.
See [PRIVACY.md](PRIVACY.md) and [the write protocol](docs/SAFETY.md).
