# Pipeline

1. Prompt / references
2. Base concept image
3. Six-view sheet
4. Annotated parts map
5. System sheet
6. Isolated part sheet
7. Export manifest / BOM

This release focuses on visual decomposition. It is not fabrication-ready CAD.

## Meta SAM 3.1
A single selected image and one noun phrase generate SAM masks. Raw packed masks and boxes are persisted for offline processing. The gallery image is a box preview, **not** the decoded mask. All outputs remain concept references and are not manufacturing CAD.

## Reference fidelity
When reference imagery is supplied for annotation, system or part sheets, the image identity supersedes any unrelated saved chat brief. The API verifies the active source belongs to the request references.
