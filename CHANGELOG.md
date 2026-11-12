# UMI LAB Changes

## 0.2.11 — Universal media and sharing foundation (2026-11-12)
- Accept UTF-8 Markdown and TXT as editable canvas documents, preserving source downloads.
- Add video/audio non-destructive processing (trim, speed, compress, scale, GIF, mute, audio mix/replace) and image conversion; original AV files retained.
- Serve authenticated four-second HLS media segments with MP4/MP3 fallback.
- Add webcam and microphone recording panels with live monitoring and on-canvas saved results.
- Add typed action menus for documents, media and images; optional OpenAI audio transcription.
- Add opt-in per-item sharing via public, PIN or approval-required `/share/<token>` links, with owner request controls and revocation.
- Add Shift+A canvas add menu; nested folders, pack color, collect/expose, ZIP export and bounded batch conversion.
- Add 3D share/selection support and optional server-enabled Blender mesh decimation.

## 0.2.10
- Fix Ubuntu WAV media upload type validation for audio/x-wav and standard aliases.
- Replace browser confirmation prompts with an accessible in-app dialog.
- Show connected 3D providers and actionable request errors before submitting.
- Prevent canvas drag/zoom handlers from hijacking 3D model viewer orbit controls.


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
