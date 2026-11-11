# Optional GPU image-to-3D bridge

UMI LAB can talk to a separately deployed HTTPS bridge that runs **TripoSR** or **Hunyuan3D** on Hugging Face dedicated Inference Endpoints or any suitable GPU cloud. The app does not bundle GPU models or launch them automatically. Use Workspace → Models to enable `GPU · TripoSR` or `GPU · Hunyuan3D`, enter the HTTPS bridge base URL and access token, then select that provider in Workspace → 3D. Do not point UMI LAB directly at an arbitrary Hugging Face Space with an incompatible API.

The expected REST contract for a trusted gateway is:

````
POST /v1/image-to-3d
Authorization: Bearer <token>
Content-Type: application/json
{ "model": "TripoSR" | "Hunyuan3D", "image": "data:image/png;base64,...", "textured": false }

201 { "task_id": "random-task-id", "status": "queued" }

GET /v1/image-to-3d/tasks/<task_id>
Authorization: Bearer <token>
200 { "status": "queued" | "running" | "completed" | "failed", "model_url": "https://<same-host>/output/<task-id>.glb" }

GET /health
200 { "ok": true }
````

The bridge must implement authentication, rate limiting, task ownership checks, persistent async jobs, secure artifact hosting, and compatible GLB exports. If the bridge runs on the same Ubuntu host as UMI LAB, an HTTP `127.0.0.1` base URL may be used. Public bridges must use HTTPS. A GPU that isn't configured will not be used.

## 3D assembly notes

Downloaded meshes are design-stage assets, not aligned parts. The exported `assembly_parts.json` records each part's mesh filename, but its transform remains `null` until it is manually aligned/validated in a future 3D assembly editor. Do not use these models directly for fabrication without inspection and mechanical tolerance work.
