# UMI LAB · Universal media studio (0.2.11)

## Ready in this release

- Markdown / TXT UTF-8 imports become editable canvas documents; original UTF-8 files are stored in authenticated media.
- PDF import and text extraction; SVG validation; GIF previews.
- Audio/video imports are converted to MP3/MP4, the uploaded originals retained, and private HLS VOD segments created by FFmpeg when available. HLS.js is used in browsers without native HLS support; MP4/MP3 remains a fallback.
- Webcam and microphone recording require explicit browser permission and explicit Record click; recordings are uploaded to the current private project when stopped.
- Audio: trim, speed preserving pitch, denoise, compress, MP3/M4A, optional paid OpenAI transcription; video: trim, speed, scale, compress, short GIF, mute, mix/replace audio, MP4/WebM.
- Images: WebP, JPEG, PNG, scale/shrink; all processes are additive and preserve source files.
- Sharing: owner-created per-file public, PIN, and manual approval links, with revocation and a Workspace Shares approval view.
- Canvas envelopes: nested by drop, optional collect/expose, color, ZIP (including notes and linked GLB models), bounded batch conversions.
- GLB optimisation: optional Blender-only. Disabled by default; requires an operator to install Blender and set UMI_ENABLE_BLENDER=1 for UMI service. This is not run automatically on the production machine.

## Constraints / not yet connected

- ElevenLabs voice conversion, multilingual dubbing and voice-cloning API are *not connected yet*. A separate paid-provider approval, permissions and async job lifecycle will be needed.
- AI video upscaling, AI video generation, subtitle alignment, rigging and motion transfer are not implemented.
- Batch processing is bounded to 12 compatible files per request; media uploads 22 MB maximum; long recordings require a chunked upload workflow.
- HLS is encoded into TS segments; it is not live streaming.
- HTTP 200 from 3D task submission does not mean a GLB is ready: use the linked model status/viewer.
- Public links give access only to the selected item. Private links require PIN or a request approved from the owner's Workspace.
- HLS.js and model-viewer load from the existing jsDelivr allowance. Browsers without access can fall back to MP4/MP3.

## Maintenance

Data under /var/lib/umi-lab is preserved by the installer; deployment does not modify other applications. Do not share API keys or original customer data via public links.
