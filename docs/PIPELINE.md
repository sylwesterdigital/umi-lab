# UMI LAB Image-first pipeline

Prompt or upload → main photo → individual angles → individual component concepts → export manifest.

The single main image is always the sole reference for angle/component requests. Photo layouts and selected source IDs are saved with the project. All view generation calls and component calls produce one file apiece. The queue is sequential; it avoids multi-panel sheets and allows stopping after an in-flight image finishes. Components hidden in the source photo cannot be recovered with engineering precision; generation is conceptual. No CAD or STL validation is claimed.


Current stage: individual component meshes through Meshy, Tripo, AHOLO or a configured GPU bridge. Assembly transforms and print validation follow separately.


## Object-agnostic source flow
Source image -> subject selection -> candidate inventory -> selective image-to-image isolated component requests -> optional 3D task. A catalogue entry does not imply visual detection or factual product identification. Brand and price verification require external evidence, and personal age is not inferred from images.

## v0.2.17 GLB optimisation

- A completed 3D task opens **... → Optimise**. Presets: Quality (100% geometry/texture), Balanced (80%/75%), Small (55%/50%), Ultra (30%/25%). Results depend on geometry and material payload; no size reduction is guaranteed.
- Advanced controls use Blender geometry decimation, remove loose, merge by distance (in original model units), recalculate normals, smooth face/edge flags, and optional weighted normals. By default rigs and shape-key meshes are protected from destructive simplification.
- Optional glTF Transform codecs: JPEG/WebP only for color/emissive slots, PNG, KTX2 ETC1S/UASTC and Draco/Meshopt. The CLI must be installed; viewer decoders and glTF extension support must be validated separately. Do not re-compress an already compressed copy without reason.
- The original provider model is never modified. Optimized GLBs are added as separate tasks with an SQLite record of source ID, settings, before/after bytes. Native progress UI displays elapsed time, not synthetic percent completion. A restarted browser should refresh model tasks to discover completed results.
- Compare original and optimized models visually, including material alpha, rigging, UV seams, normals, and animations, before using for games or printing. Optimisation does not make a mesh watertight or suitable for 3D printing.
