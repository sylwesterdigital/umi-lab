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
