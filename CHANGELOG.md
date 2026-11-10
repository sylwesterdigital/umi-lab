# Changelog

## v0.1.3 — 2026-11-10

- Persist SSH host, SSH port (333 by default), server IP and Certbot email in a private local config.
- Ask for initial admin password once, securely via macOS terminal, with no exports required.
- Add `--configure` and `--show-config`; preserve old deployments and ZIP validation logic.

## v0.1.2 — 2026-11-10
- Fix UMI watcher default SSH port to 333 (shared Ubuntu host), instead of 22.
- Keep SSH port configurable via UMI_SSH_PORT; preserve isolated Flask port selection.
- Update deployment documentation and version markers.

## v0.1.1 — 2026-11-10

- Fix macOS watcher dry-run failure on Python without `requests` installed.
- Lazy-load provider HTTP transport only when real inference is requested.
- Add dependency-free import regression test (`python -S`).
- Align app, health, export and release version markers at v0.1.1.

## v0.1.0 — 2026-11-10

- First UMI LAB Flask/SQLite release with one-page studio, 16-part-system taxonomy and profile authentication.
- Encrypted provider configuration, user-selectable chat models, Gemini/Anthropic/OpenAI-compatible chat adapters.
- Four-view image generation for OpenAI, xAI and Gemini, local image uploads and gallery reference selection.
- Procedural 3D vehicle playground, manifest and concept BOM ZIP export.
- macOS ZIP watcher, verified Git push and isolated Ubuntu/nginx deployment with upgrade/rollback logic.
