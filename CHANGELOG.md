# v0.1.6 — 2026-11-10
- Fix CSP by hashing the embedded Three.js import map; avoid unsafe-inline.
- Fix Settings Models/Appearance/Profile navigation and password-form browser warnings.
- Compact API provider selector with connection check, credit balance where documented, browser-tab-only keys, encrypted server keys, and clear.
- Add Tripo, AHOLO, Meshy provider configuration and non-billable API verification.
- Contextual model selection with browser-local preferences; auto-generate a concept image for a submitted vehicle prompt when enabled.
- Gallery uses real image elements; same-origin image markdown in conversation renders as images.

# UMI LAB changelog

## 0.1.5 — Administrator provisioning and secure logs

- Fix initial administrator accounts being created with the default regular-user role.
- Explicitly assign `admin` only in the locally restricted setup endpoint and Ubuntu provisioning step.
- Keep server-level application logs admin-only; guests and other registered users remain denied.
- Add both database and Flask integration regressions for admin and regular-user log permissions.
- Preserve all existing SQLite records, provider keys, profiles and projects during upgrade.
- Retain watcher v0.1.2 and persistent SSH configuration (port 333).


## 0.1.4 — 3D-first studio and identity controls

- Replaced the three-column dashboard with a clean full-screen Three.js workspace and a single starting question.
- Kept only the animated gradient-text `UMI LAB` logo, not an app icon.
- Moved projects, parts, procedural model adjustments and concept galleries behind functional controls.
- Integrated `cannon-es` RaycastVehicle simulation with driving, braking, steering and reset controls.
- Added a movable, collapsible, resizable application-log window with font size, refresh and copy.
- Added per-user server-stored audit events; administrator-only global application logs, with no request payload or credential logging.
- Added name-only guests, private accounts, conversion from guest to protected account, protected contact data, avatar upload, bio and vehicle focus.
- Added saved theme, accent and text colours, interface scaling, installed font names, and browser-local font upload.
- Migrates existing SQLite users without deleting or replacing admin accounts, projects, provider keys, or assets.
- No unimplemented AI segmentation or CAD controls are shown.
- Preserves watchdog/deployment format and remote isolated Gunicorn/nginx service.

## 0.1.3 — Persistent watcher settings

- Watcher configuration persists in a local user-controlled file; default SSH port is 333.
