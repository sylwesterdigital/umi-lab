# UMI LAB — Universal Modelling Intelligence

UMI LAB v0.1.7 builds on the 3D-first studio foundation. It deliberately opens with no dashboard, sidebar or signup wall: a full-screen Three.js scene, the gradient-text UMI LAB wordmark, and a single vehicle design prompt. All additional controls have a real implementation.

## Controls

- **Design prompt** starts a project and stores conversation. Offline responses label their limitations; live LLM calls require configured model providers.
- **+** accepts JPG, PNG or WebP. Dropped images are processed and stored as references for the current project.
- **Gallery** displays uploaded or generated image concepts. Generation requires an enabled image-capable provider and explicit charge confirmation.
- **Parts** searches the ontology and exports a non-printable production manifest.
- **Edit** changes colour, ride height, wheel scale and exploded view for the procedural prototype.
- **Drive** activates cannon-es RaycastVehicle; W/Up accelerate, S/Down reverse, A/D steer, Space brake, Reset returns to origin.
- **Garage** selects and creates saved vehicle projects.
- **Settings** configures AI providers, interface appearance, custom fonts, and user profile.
- **Logs** opens a drag-and-resize window with scalable text, refresh and copy. Session logs are per-user audit records created on the server. Administrator-only App server log shows sanitised HTTP activity for this UMI deployment; it does *not* read system-wide journal logs.
- **Profile** can begin as a name-only guest (no password/email/phone) and later be protected with a username/password and optional email/phone. Existing protected accounts can sign in. Profile photos upload through authenticated, image-validated endpoints.

## Privacy and limitations

- Guest sessions persist as a signed browser cookie for up to 14 days but can be lost when cookies are cleared. Protect the profile to enable credentials-based recovery via username/password.
- User-supplied API keys are encrypted at rest in server SQLite. No passwords, keys, request bodies or contact details enter application logs.
- Application server logs are restricted to the administrative account. Anonymous and regular profiles may view and copy only their own activity.
- No external login, email verification, SMS verification or password-recovery service is implemented; fields are metadata, not verified contact channels.
- Imported fonts are retained *only in the current browser* using IndexedDB. No font files are uploaded to the server.
- The 3D model is a procedural preview, not a reconstruction of a reference photo or valid STL. Physics is a simulator prototype, not certified vehicle dynamics.
- AI segmentation and manufacturing-ready CAD/STL remain future stages and are deliberately not exposed as working actions.

## Deployment

Place `UMI_LAB_UPDATE_v0.1.7.zip` inside the `updates/` folder. Watcher v0.1.2 can validate/deploy it directly; persistent SSH config already defaults to port 333. Do not put secrets or API keys in ZIP releases. Leave `./watcher-umi-lab.sh` running to deploy new ZIPs automatically. The one-shot/dry-run flags remain optional.

The release migration is forward-only and retains existing users, projects and assets. The deployer installs dependencies and runs Flask integration tests on Ubuntu before enabling the release. HTTPS, nginx and Gunicorn remain confined to the UMI vhost/service.


## v0.1.6 browser and model setup
The embedded Three.js import map is explicitly CSP-hashed. Do not change the import-map bytes without updating the hash in backend/app.py. Settings -> Models displays one provider form at a time. Test uses non-billable endpoints only; balance is displayed for Tripo and Meshy when available. "Keep in tab" uses browser sessionStorage and never persists the key in SQLite; "Save on server" encrypts keys in SQLite. Image generation starts from a prompt only when an image provider has been configured and Images is selected. Manual four-view generation requires confirmation. No provider key is logged. Tripo, AHOLO, and Meshy are discoverable in 3D credentials settings; automated 3D mesh task submission is not claimed in this release.
