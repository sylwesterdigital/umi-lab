## 0.2.21 — Repair Ubuntu Blender verification environment
- Fix the v0.2.20 deployment failure: the root installer no longer imports Pillow-dependent backend code using system Python.
- Keep Pillow and image-processing dependencies exclusively in UMI LAB's release virtualenv.
- Maintain service-user Blender GLB smoke checks, missing-module diagnosis and safe rollback.
- Add regression testing that blocks Pillow imports during installer verification.

## 0.2.20 — Working WebP & Draco encoder recovery
- Native WebP colour-texture encoding using Pillow and Khronos EXT_texture_webp, without glTF Transform; original geometry and noncolour textures unchanged.
- Blender Draco remains preferred, with verified glTF Transform fallback when the Ubuntu Blender build lacks a native Draco library.
- Optional Node 22 runtime installed only under /opt/umi-lab/tools if the system runtime is missing or too old; system-wide Node untouched.
- Clear status: native Draco, fallback Draco, WebP encoder, and optional KTX2/Meshopt. No pretend active codecs.
- All outputs remain separate from originals and model asset ownership checks remain in place.

## 0.2.19 — Native Draco compression
- Fixed Draco being disabled when glTF Transform is absent.
- Blender native glTF exporter now supports compression level 0–6, and five quantization controls; verifies capability by exporting an actual Draco GLB.
- Native Draco, Meshopt, and texture codecs are tested and selected independently. Original models remain untouched.

## v0.2.18 — Imported 3D, animation and independent textures
- Drag/drop GLB directly onto the canvas, or import FBX, OBJ, STL, PLY, COLLADA (DAE), embedded glTF, USD and USDZ with Blender conversion when supported by the installed importer.
- Original uploads and preview GLBs are stored separately and privately, owned by the project and available as standalone 3D cards.
- Animated GLBs show lightweight clip selection and play/pause controls in the card and full-size viewer. Rigged models without clips display a Rigged indicator.
- Import limits: 64 MB for source, 60 MB for viewable GLB. Embedded-only glTF; OBJ textures should be embedded in a GLB before upload. No remote fetching or embedded script execution.

- Texture-only optimisation is available without Blender: select exact 1×, 2×, 4×, 8× or 16× dimension reduction and native PNG/JPEG. No mesh, rig or animation modification is required.
- Export embedded PNG/JPEG materials to a ZIP, edit them externally, and reimport the ZIP to a NEW GLB. Original geometry, animations and models remain unchanged.
- Separate geometry-only, textures-only and combined modes. WebP, KTX2, Draco and Meshopt are enabled only when glTF Transform is installed; the UI explains the codec requirement rather than disabling PNG/JPEG.
- 3D importer covers GLB, embedded glTF, FBX, OBJ, STL, PLY, DAE and USD variants subject to Blender importer support and existing per-user security limits.

## v0.2.17 — 3D optimisation workbench and clean model cards

- Move per-model actions into one minimal three-dot menu; retain direct orbit interaction and card dragging.
- Display original GLB size on each model card; optimized variants show original/output sizes and reduction percentage.
- Show a temporary 3D processing card with elapsed time during the synchronous Blender request; no fabricated progress percentage.
- Offer presets Good quality, Balanced, Small and Ultra, plus an Advanced tab for polygon ratio, texture size, loose geometry, merge distance, recalculated normals, smooth shading and weighted normals.
- Optionally apply glTF Transform texture encoding (PNG/JPEG/WebP/KTX2) or Draco/Meshopt compression when the server tool is available; keep compatibility-safe settings by default.
- Keep every original GLB unchanged; persist optimisation settings and measured byte counts for each resulting model in SQLite.
- Ubuntu installer attempts optional glTF Transform installation in an isolated UMI-owned tool directory; failure cannot disable Blender-only presets.

## v0.2.16 — Blender Python modules and reliable optimisation preflight

- Run the real Blender GLB importer, decimator and exporter under the UMI service user before activating the release.
- Detect the specific `ModuleNotFoundError` instead of hiding it behind generic failure messages.
- Repair a short allowlist of missing Blender Python dependencies via Ubuntu APT when applicable; fail safely with the exact missing module otherwise.
- Strip Flask virtualenv Python variables from the isolated Blender process.
- Preserve saved models, projects, API keys, SQLite and existing optimised results.

## v0.2.15 — Native drag selection fix and 3D optimisation diagnostics

- Browser text selection is disabled on draggable canvas surfaces, while document editors and text inputs remain selectable.
- 3D optimisation checks Blender state under the running service and reports explicit failure codes.
- Safe optimisation from saved ZIP models containing a valid GLB; no paid generation required.
- Operation-level server logs show errors and durations without exposing credentials.

## v0.2.14 — Draggable 3D cards and automatic Blender provisioning
- Drag 3D result cards using any noninteractive portion, including the outer white frame and title; rotating/zooming the model stays independent.
- Release installer installs Blender from Ubuntu APT when missing, verifies headless glTF/GLB processing and enables it for the UMI service.
- Removed misleading optimisation messaging that tells the user to install or configure Blender manually.
- Existing SQLite data and previously generated GLB assets remain untouched.

## v0.2.13 — Stable folder view and pointer add menu

- Shift+A positions the Add menu at the mouse pointer, right edge aligned to cursor, clamped to the viewport.
- Opening, closing, and press-and-hold previewing an envelope never change the current canvas pan or zoom.
- Preserves existing photos, envelopes, generation queues, SQLite data, and watcher configuration.

## v0.2.12 — Folder focus and safe generation
- Keep the selected envelope visible while showing its contents. Click to open/close; hold to peek and release to restore the prior canvas.
- Reuse completed angles from the same source image; generate only missing views.
- Add explicit Cancel batch separate from Pause, preserving completed images and aborting the local request when possible.
- Envelope media conversions also have a cancel control, while keeping completed outputs.
- Canceled queues do not auto-resume; remote providers may still bill work already accepted.

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
