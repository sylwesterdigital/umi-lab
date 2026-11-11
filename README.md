# UMI LAB — Image Table v0.2.0

The interface has been rebuilt as a clean, freeform image table. One draggable vehicle photo anchors a family of independently generated angle and component images.

## Workflow

1. Open UMI LAB; enter a brief and choose a configured image model, or upload a reference.
2. Select the main photo and choose **Generate angles** (6 separate images).
3. Choose **Generate parts**, select a group, then confirm a sequence of individually billable images.
4. Drag photos on the board, pan empty space, zoom with the scroll wheel. Layouts persist across sessions.
5. Use **Workspace** for image library, projects, model credentials, appearance, activity, and release notes.

## Preservation

All existing users, projects, images and encrypted credentials remain in the same Flask / SQLite backend; the deployment process and watcher are unchanged. Existing projects without tabletop metadata open as blank canvases until a saved image is chosen from **Workspace → Images**.

## Limitations

Angle consistency and part accuracy depend on the selected model. Generated components are concept imagery, not guaranteed physical parts, segmentation masks, 3D meshes or ready-to-print CAD.


## v0.2.1

Create a parts plan without generating images. Choose Basic (12), Medium (up to 42), Advanced (up to 92), or Complete (222) or a system-specific collection. Click **Plan blank cards** to create placeholders, or select only the parts you want and **Generate selected**. The persistent queue pauses after the current request and can be resumed, including after a reload. Follow mode pans/zooms to each image.

New **Packs** tab and image search. **Make 3D** on a generated part uses Meshy image-to-3D if configured; tasks are tracked, and generated GLB files and an assembly manifest are exported. Geometry assembly and 3D-print readiness are not claimed.

Images remain private on the server in `/var/lib/umi-lab/media/`, mesh files in `/var/lib/umi-lab/meshes/`, and project metadata/queues in SQLite.


## 3D providers in v0.2.1

Workspace → 3D offers **Tripo v3**, **AHOLO Lux3D**, **Meshy**, and optional user-hosted **TripoSR/Hunyuan3D**. Only images selected for 3D are billed. Existing saved API keys are reused; no keys are included in exported files. Jobs are asynchronous and can be refreshed later.

The UMI LAB server stores completed GLB/ZIP files in its private persistent data directory, preserving them across releases. For Meshy, the estimate is 20 credits (untextured) or 30 credits (textured); Tripo/AHOLO and cloud GPU costs depend on model, account and compute. Full automatic assembly alignment, tolerance validation, and print readiness are not implied.

For self-hosted TripoSR and Hunyuan3D, see `docs/GPU_BRIDGE.md`. The bridge is an optional compatibility contract; no GPU or model weights are bundled/deployed with the UMI LAB update.
