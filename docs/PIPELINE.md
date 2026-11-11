# UMI LAB Image-first pipeline

Prompt or upload → main photo → individual angles → individual component concepts → export manifest.

The single main image is always the sole reference for angle/component requests. Photo layouts and selected source IDs are saved with the project. All view generation calls and component calls produce one file apiece. The queue is sequential; it avoids multi-panel sheets and allows stopping after an in-flight image finishes. Components hidden in the source photo cannot be recovered with engineering precision; generation is conceptual. No CAD or STL validation is claimed.


Current stage: individual component meshes through Meshy, Tripo, AHOLO or a configured GPU bridge. Assembly transforms and print validation follow separately.


## Object-agnostic source flow
Source image -> subject selection -> candidate inventory -> selective image-to-image isolated component requests -> optional 3D task. A catalogue entry does not imply visual detection or factual product identification. Brand and price verification require external evidence, and personal age is not inferred from images.
