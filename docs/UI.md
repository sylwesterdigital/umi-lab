# UMI LAB studio design

Initial view: full-viewport interactive Three.js scene, only `UMI LAB` animated gradient text, a single vehicle question, and a bottom message composer. No marketing text, fake progress, empty samples, badges or nonfunctional buttons. Drawers and overlays are opened only by explicit controls.

Persistent state: SQLite stores users, guest/secure identities, profile metadata, project data, images, provider configuration and per-user activity logs. Client localStorage stores appearance settings and font selection. Client IndexedDB stores a locally selected font file.

Log window: drag via the header, resize via lower-right corner, collapse via title controls, adjust text size and copy visible entries. Authenticated non-admins receive only their own HTTP-action audit history. Admin can switch to the sanitised UMI application log file. Logs never include request content, passwords, tokens, provider keys or system journals.

Privacy: only private accounts store email or telephone metadata. Neither channel is verified. Signing up is optional for viewing the 3D scene. Posting an idea requires name-only guest creation or credentials-based sign-in.

v0.1.8 image workflow:
- Last-open project, chat history and unsent draft resume in the same browser/account.
- When a saved project has a conversation but no images, a configured chat provider can ask one follow-up automatically; the follow-up is recorded once to avoid repeated costs on reload.
- Chat bubbles are selectable, each with Copy and expand controls.
- Floating Concepts is draggable, resizable and collapsible. Check up to five gallery images for use as image references; click a thumbnail for a large image overlay.
- Generate defaults to ONE six-panel sheet (front, rear, side, top, front and rear 3/4), or a single chosen viewpoint. Selected image bytes are sent to provider image-edit endpoints, not merely described in text.
- Generation progress displays provider, current stage and elapsed time; session/server logs record stages, outcome, duration and reference counts, not secrets or inference prompts.
- The last generation report is stored with the project for re-entry. The Three.js model remains procedural proxy geometry; images are not converted into CAD in this release.
