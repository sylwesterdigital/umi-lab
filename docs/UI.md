# UMI LAB studio design

Initial view: full-viewport interactive Three.js scene, only `UMI LAB` animated gradient text, a single vehicle question, and a bottom message composer. No marketing text, fake progress, empty samples, badges or nonfunctional buttons. Drawers and overlays are opened only by explicit controls.

Persistent state: SQLite stores users, guest/secure identities, profile metadata, project data, images, provider configuration and per-user activity logs. Client localStorage stores appearance settings and font selection. Client IndexedDB stores a locally selected font file.

Log window: drag via the header, resize via lower-right corner, collapse via title controls, adjust text size and copy visible entries. Authenticated non-admins receive only their own HTTP-action audit history. Admin can switch to the sanitised UMI application log file. Logs never include request content, passwords, tokens, provider keys or system journals.

Privacy: only private accounts store email or telephone metadata. Neither channel is verified. Signing up is optional for viewing the 3D scene. Posting an idea requires name-only guest creation or credentials-based sign-in.
