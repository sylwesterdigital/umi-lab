# UMI LAB

UMI LAB is a 3D-first vehicle concept studio with authenticated Flask/SQLite storage.

## New in 0.1.9
- Six-view sheet generation
- Annotated parts-map generation
- System-sheet generation (Body, Doors, Glass, Lights, Cockpit, Steering, Seats, Wheels, Brakes, Suspension, Powertrain, Energy, Cabin, Underbody, Hardware, Electronics)
- Isolated part-sheet generation
- Export manifest with workflow summary for later CAD / 3D / printing stages

## Meta Model API (v0.1.11)
Select Meta Muse in Settings and store a Model API key. Supported hosted chat: Muse Wonder, Spark 1.1–1.3, Ember. Image: Muse Image 1.0 (with multi-reference editing). In Concepts select **Segment part · Meta SAM 3.1** and choose exactly one image and a short part noun phrase. The output records true packed SAM masks plus a clearly marked bounding-box preview. Masks can be decoded later with `meta-sam-parser`; image preview is not a pixel mask. The exported kit includes segmentation JSON. Muse Wonder Full needs Muse Code subscription; Muse Spark Open and Glimmer are self-hosted, not accessible through Meta Model API.

## Image editing (0.1.13)

Open any gallery thumbnail. Drag the preview window or resize its corner. Zoom with trackpad/wheel or +/-; drag rectangles using Free, 1:1, 3:2, 3:4, 4:3, or 16:9. Crop produces a new asset. For AI Edit, select an area, type an instruction, and use a configured image provider. Only selected pixels are composited back into the source; the unselected image stays unchanged.

The prompt can be dragged or docked beside the Concepts workspace. The UMI LAB wordmark restores the active session instead of clearing it.
