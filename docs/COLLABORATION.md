# UMI LAB collaboration (v0.2.27)

## Getting started

In **Workspace → Projects**, create a named blank board or switch to another. The owner can generate invitation links by setting a 6–12 digit PIN, choosing a 24-hour or 7-day lifetime, and copying the link. Share the PIN separately. A link may be used by up to 25 people and is shown once. The token is stored hashed; it is carried in the URL fragment rather than the request query. The owner can revoke invitations or remove members (revoking the link does not remove existing members). After five incorrect PIN attempts a link is locked for 15 minutes. There can be at most 10 active links per project.

The invited person signs in or creates a guest identity, follows the link, and enters the PIN under Projects. Guests and registered accounts use the same board switcher. Editors can upload media, edit canvas items and see 3D models. AI generation, 3D processing, project configuration and deletion stay owner-only. No provider credentials are shared.

The **Link boards** shortcut connects two boards owned by the same person for navigation. It does not merge media or change permissions. True canvas content merging, QR-code creation, mobile app pairing and granular access roles are not in this release.

## Concurrent work

Every tab has its own random client ID. Presence expires after about 18 seconds; editing leases after 15 seconds. Pointer movement posts at most once per 850 milliseconds and a light state query runs every 2.8 seconds while the tab is visible; heartbeat refreshes are approximately every six seconds. These are normal Flask endpoints with short SQLite WAL transactions; no extra sockets, services or global environment changes.

Canvas changes are compared by object ID against the snapshot the editor originally loaded and merged inside `BEGIN IMMEDIATE`. Independent changes are preserved; a second edit on the same node/pack returns HTTP 409. Held objects reject conflicting writes with HTTP 423. Global board metadata also uses optimistic checks. Refresh from Workspace after a conflict instead of overwriting. Shared board global undo/redo is disabled because old snapshots could erase another editor's changes.

## Deployment boundary

The application update adds private SQLite tables and one additive column; it does not require new system-level dependencies. To protect other live projects on a shared Ubuntu host, this release disables the installer's inherited automatic Ubuntu APT installation and repair by default. If Blender or its system modules are missing, deployment stops *before* UMI LAB activation. Only an explicit operator setting, `UMI_ALLOW_SYSTEM_APT=1`, enables system-wide APT provisioning. Existing UMI-specific deployment still creates/restarts the `umi-lab` systemd service, updates the UMI-specific Nginx virtual host, tests/reloads the shared Nginx service, and may download packages into UMI-owned directories. Consequently an operator should review this installer before unattended deployment on a shared host. UMI's own SQLite data is backed up and other virtual-host configuration files are not intentionally modified. No deployment runs as part of preparing the ZIP.

## Known limits

The polling design fits small teams. Held locks are automatic and time-limited. Some older generation/editing operations remain owner-only. A slow tab may require manual refresh after a conflict. Sharing a link + PIN is not identity verification; use private communication to distribute invitations. Larger team installations should consider a dedicated real-time transport after capacity planning.
