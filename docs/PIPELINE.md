# UMI Model Production Pipeline (roadmap)

| Phase | Input | Output | State in v0.1 |
| --- | --- | --- | --- |
| Prompt | Natural language | Versioned brief | Implemented |
| Concepts | Prompt + references | 4 camera views | Implemented (independent renders) |
| Segmentation | References, part labels | Masks + confidence + landmarks | Planned |
| Alignment | Calibrated views | Camera poses + correspondences | Planned |
| Reconstruction | Mask, depth, view geometry | Meshes + UVs + provenance | Planned |
| Retopology | Meshes | Low-poly game meshes / LODs | Planned |
| CAD | Topology, dimensions, constraints | Parametric solids + joins | Planned |
| Fabrication | CAD, machine/material profiles | STL/3MF + fit/slicer tests | Planned |
| Runtime | Game mesh + rig + physics | GLB/FBX + simulator | Planned |

AI options to evaluate: **SAM 2/3** for mask proposals, **Grounding DINO** for text-to-box grounding, **Depth Anything** for relative depth, multi-view feature matching/SfM for camera pose, and image-to-3D models (e.g. TRELLIS / Hunyuan3D) for provisional surfaces. These are *candidates*, not implemented endpoints or guarantees. Integrate each behind the same model-router capability descriptor, independent of brand.

Every part has `id`, `assembly`, `label`, `mask`, `mesh`, `cad`, `dimensions_mm`, `tolerance_mm`, `attachment_points`, `material`, `status`, `confidence`, `printable`. Future steps add local transforms, joints, physical properties, license/provenance, manufacturing profile, and revision lineage.

The initial ontology has 16 systems and includes surfaces, wheels, cockpit, seats, motors, wiring, brakes and hidden parts. Hidden parts remain missing until a human design authority chooses their dimensions and layout.

Design principle: *a single-view concept mesh is a visual proxy, never a manufactured mechanical part*.
