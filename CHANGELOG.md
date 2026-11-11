# UMI LAB — Development Updates

## v0.1.14 — 2026-11-11 02:00 UTC · Reference-first image editing
- Small version number next to the gradient-text UMI LAB logo.
- First-open release notes window with scrollable dated history; reopen through version/Tools.
- Press G to move a selected image rectangle; R returns to rectangle drawing.
- AI edit and concept generation show local progress, model and elapsed time, with animated borders.
- Clicking a gallery image focuses it as the generation source; annotation/system/part generation uses that image.
- The current visual reference overrides unrelated saved project/chat prompts.

# UMI LAB Changelog

## 0.1.13
## 0.1.12
- Fixed SAM 3.1 unit tests for clean macOS Python environments without requests; no change to production inference.

## 0.1.11
- Added Meta Muse hosted chat models, Muse Image 1.0 and reference editing.
- Added SAM 3.1 segmentation action with saved mask tokens, boxes and a bounding-box preview.
- Updated Settings for compact Meta model selection and provider key checks.
- Preserved existing projects, credentials and watcher compatibility.

# UMI LAB Changelog

## 0.1.10
- Repackaged the parts-workflow update with source files only (no compiled Python caches).
- Added safe watcher recovery for byte-identical files from failed releases.
- Added copy preflight and rollback to prevent partial Git working-tree changes.
- Preserved the 0.1.9 dissection, system-sheet and isolated-part workflows.

## 0.1.9
- Added vehicle dissection workflow: Annotated parts map, System sheet and Isolated part generation.
- Concepts workflow can now target a selected system or part name, using selected gallery images as references.
- Project manifest/export now includes parts workflow summary and derived concept outputs.
- Gallery footnotes, prompts and last-run summaries updated for breakdown-driven work.

## 0.1.8
- Restored previous project and chat state, improved gallery references and six-view sheet generation.
