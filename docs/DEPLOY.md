# Deployment & watcher

## Files and staging

- Install `watcher-umi-lab.sh` at repo root and `chmod +x watcher-umi-lab.sh`.
- Download `UMI_LAB_UPDATE_v0.1.7.zip` into `updates/`.
- The watcher defaults to SSH `root@46.62.232.64:333` using the shared server setting from the supplied Vehicle Lab watcher.
- Network settings are persisted in `.umi-lab/watcher-config.json` (mode 0600), not shell exports.
- SSH public-key authentication must already work from macOS, and host key must be pinned in `~/.ssh/known_hosts`.
- DNS must resolve `umi-lab.top` to the expected host before a live deploy.

```bash
# No exports required. Set host/port/email only once if the defaults change:
./watcher-umi-lab.sh --configure   # optional, interactive
./watcher-umi-lab.sh --show-config

# Verify, then deploy
./watcher-umi-lab.sh --dry-run
./watcher-umi-lab.sh --once
```

On a **brand-new installation**, `--once` asks for a 12+ character initial admin password twice directly in the terminal. This secret stays in memory for that deployment, is sent over SSH to provision the first user, and is never written into the watcher JSON config or Git. Existing deployed databases never trigger the prompt. In unattended mode, an unprovisioned server stops with clear instructions instead of hanging waiting for input. The legacy environment overrides remain optional but are not required.

`--once` processes one ZIP and exits. Omit it to watch the updates folder continuously. `--status` reports local release state. `--tail` shows the latest release log. `--verbose` enables diagnostic logging (but not secrets). `--dry-run` verifies Python, Node syntax, tests, hash manifest and watcher, without touching GitHub or Ubuntu.

## Server layout

- Source: `/opt/umi-lab/releases/<version>`, active symlink `/opt/umi-lab/current`.
- Data & encrypted keys: `/var/lib/umi-lab` (SQLite/media and secret files never in repo).
- Virtualenv per release: `/opt/umi-lab/releases/<version>/.venv`.
- Systemd unit: `/etc/systemd/system/umi-lab.service`.
- Nginx: `/etc/nginx/sites-available/umi-lab.top` + a new link in `sites-enabled`.
- Loopback port: picked from 5057–5099 only after checking listeners, systemd services and nginx upstream usage; existing app services are never touched.
- TLS certificate: pre-existing `/etc/letsencrypt/live/umi-lab.top/` or a certbot provisioning step after successful HTTP deployment.
- Nginx changed only for the UMI dedicated vhost. Installer retains previous UMI files and rolls back on error.

## HTTPS

The watcher will not mark deployment public-verified unless `https://umi-lab.top/api/health` and `https://umi-lab.top/version.json` respond with the exact release. If no valid certificate exists, operator must establish one for this newly configured domain and rerun the watcher (or `sudo certbot --nginx -d umi-lab.top` after verifying DNS). The watcher never modifies an unrelated certificate or existing vhost.

## Security

Keys are encrypted with Fernet and stored only server-side in SQLite. The key is saved as a protected file under `/var/lib/umi-lab`. Browser sessions have SameSite Strict cookies and per-session CSRF headers. Admin password is scrypt-hashed. Nginx limits uploads; Gunicorn binds only loopback. Do not expose dev Flask, the SQLite directory or the local model ports publicly.

## Recoveries

Each deployment preserves prior UMI service/vhost/current symlink files and snapshots the SQLite database before upgrading. Watcher never resets/stashes user changes. A failed deployment does not delete your data; report the latest watcher log. The watcher refuses unknown ZIP files, unmanifested paths, invalid checksums, downgrades and unexpected Git origin.


This release adds new concepts-generation modes only; no watcher changes are required.


## v0.2.0 design table

The frontend now loads only `/static/js/app.js`; retained the unused viewer module solely for watcher v0.1.3 compatibility; the image-editor and release-notes modules are removed. Existing SQLite data and provider keys remain untouched. Angular/part image series are initiated client-side as individually billable requests; stopping pauses after the in-flight provider call.
