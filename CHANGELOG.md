# UMI LAB changelog

## 0.2.7
- Prefer direct viewer-ready AHOLO GLB, including for URLs with signed/no-extension paths.
- Recover previews for already successful ZIP-only tasks without repeating generation; keep archive downloads.
- Advertise preview links only for viewable GLB artifacts, show recovery and reliable status on canvas.
- Allow narrowly scoped model-viewer source-map requests to jsDelivr without opening general external connections.

## 0.2.6
- Packs are freeform canvas objects, with persistent world coordinates.
- Corrected per-photo three-dot alignment.
- Full image analysis and generation metadata are saved as per-image SQLite documents and exported.
- Generated 3D tasks appear as linked canvas cards, with a preview and scene option when a GLB is ready.
- AHOLO 3D status remains clearly queued until the file is actually downloaded.
- Image-view prompts are more explicit about distinct views.

# UMI LAB changelog

## v0.2.4 — Universal scene intelligence and recoverable canvas
- Removed the visible hardcoded subject picker; optional image analysis creates a free-form inventory of visible items, materials and likely components via an already configured vision model.
- Added rectangular multi-select, Shift-click selection and group dragging.
- Added Move to pack, Copy with image metadata, Remove from graph (preserving source images), and Delete pack listing.
- Added persistent SQLite canvas revisions and Undo/Redo shortcuts.
- Scoped pending queues to the relevant main image and moved queue status away from bottom controls.
- Refusals or failed analysis do not block unrelated projects or source photos.
- No unverified age identification, product-brand verification or price estimates are presented as facts.

## 0.2.3 — Universal workspace
- Place new uploads in empty photo space without resetting previous images.
- Show/hide packs using eye buttons on envelope covers and Packs drawer.
- Arrange visible photos using Grid, Orbit, Fountain or Fit.
- Generate views and parts for people, rooms, products, machines, and general objects.
- Add editable custom candidate objects and preserve per-image scene category in saved layout.
- Preserve server images, per-project layout, parts workflow and 3D gateway.

# UMI LAB Changelog

## 0.2.5
- Added compact three-dot per-image contextual actions and image-grounded AI prompt composer.
- Added photo image variations plus vision model descriptions, storyboard plans, avatar rig plans and fictional persona concepts.
- Improved selection visibility, G grab mode, draggable prompt/selection bar and photo envelope drag/drop sorting.
- Added archive/trash handling for image and envelope canvas items, preserving source assets for undo/recovery.
- Hid inactive blank angle placeholders, deduplicated stale planned-angle slots, and preserved existing generated photos.



## 0.2.2
- Fixed startup crash caused by missing Activity log handler.
- Restored session/admin activity rendering, refresh and copy actions.
- Added startup and control-binding regression tests.

## 0.2.1
- Basic, Medium, Advanced and Complete plans (222 catalogue components); save ungenerated placeholders without paying for them.
- Persistent per-image generation queue with Pause, Resume, Retry and Follow camera.
- Visual image packs with names, notes and saved collection metadata.
- Searchable image library and filters for angles, components and references.
- Per-part 3D tasks for Meshy, Tripo v3, AHOLO Lux3D, and optional TripoSR/Hunyuan3D GPU bridge; status refresh and private model downloads.
- Meshy credit estimator; variable provider/GPU costs are shown as unquoted until verified.
- Existing v0.2.0 generated photos are reused and can be grouped into legacy packs.

## v0.2.0 — Fresh image table (2026-11-11)

- Replaced the crowded gallery/editor with an open draggable image canvas.
- Prompt or reference → one main photo in the centre, framed like a photo print.
- Six angle views are generated as six separate image jobs, each tied to the same reference.
- Part groups generate individual component images (not contact sheets) with explicit billable-job counts.
- Photos can be moved, panned, zoomed, and arranged with thin connections. Positions persist in SQLite project settings.
- Added compact workspace drawer for projects, saved images, model settings, logs, profile, and appearance.
- Retained backend, existing accounts, data, model credentials, and deployment configuration.

Earlier releases: v0.1.0–v0.1.16.
