# UMI LAB Image Table (v0.2.0)

A simple, unbounded photo canvas replaces the legacy gallery/3D editor stack.

- The centre **main** photo is generated from a brief or uploaded.
- **Generate angles** makes six **separate** images, in a sequence, using only the main photo as visual reference.
- **Generate parts** offers exterior, cabin, running gear, or the full parts catalogue; every item is a **separate paid image call**.
- Derivatives appear as loose photo prints around the main photo with subtle connecting lines; drag them anywhere.
- Positions are stored in each project's SQLite-backed settings. Old image assets remain accessible via Workspace → Images.
- Progress displays the currently generated image, provider and count. Stop completes the current call then halts the rest.
- No annotation sheets, feature panels, chat transcript or 3D proxy car appear on the starting screen.

Photo outputs are visual concepts, not reconstructed 3D meshes or validated manufacturing parts. Provider-dependent image fidelity varies.


## Universal workspace (0.2.3)
- Drop a photo on any occupied region: the new photo is moved to a nearby free location and becomes the active source. Earlier photo positions are not reset.
- Use envelope eye button to hide/show a generated pack without deleting its assets.
- Arrange -> Grid / Orbit / Fountain to automatically position visible photos, or Fit to view the visible group. Dragging a photo afterward retains the manual position.
- Set the active subject in the photo toolbar, and choose the same subject in the component planner. Person, room, product, machine and general-object catalogues list **candidates**, not verified detections. Add a custom item to request something specific.

## Canvas edit mode (v0.2.4)
Select tool → marquee → multi-photo action bar. Move to pack creates or reuses an envelope. Pack removal archives the graph placement only; the underlying media remains. History is stored in SQLite with a bounded 60-revision timeline and redo cursor, visible by the two arrow buttons.

AI scene analysis is opt-in and does not force a predetermined object category. Its output is uncertain visual metadata, not a price, brand, age, or engineering certification.


## v0.2.6
- Envelopes are part of the infinite canvas, so they pan and zoom with photos and persist world coordinates.
- Per-image documents store full AI descriptions/model attribution in SQLite and are exportable.
- A 3D task submitted to AHOLO, Tripo, Meshy or a configured GPU creates a linked status card; the result is not ready until the provider finishes and UMI downloads the file.
- Completed GLB models can be previewed in-browser and optionally shown as a background scene. Provider ZIP results expose a bounded GLB preview when present.
- Uploaded MP4/WebM files have a basic viewer; UMI does not render videos through provider APIs in this release.
