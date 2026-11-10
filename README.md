# UMI LAB — Universal Modelling Intelligence

**Version 0.1.3 | Foundation**

One-page Flask/SQLite studio for vehicle concepts, image references, provider-agnostic conversation, 4-view concept generation, a procedural 3D preview, and a structured component catalogue. Future vehicle classes share the same ontology-driven scene-graph architecture.

## Local macOS setup

The supplied `watcher-umi-lab.sh` goes in the repository root, not in `updates/`. Download `UMI_LAB_UPDATE_v0.1.3.zip` to `updates/`. On an existing empty repository, the watcher runs local checks then pushes and deploys. To preview locally without deploying, install the Python dependencies and initialize a **local-only** administrator:

```bash
cd /Users/smielniczuk/Documents/works/umi-lab
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
UMI_ENABLE_SETUP=1 python3 -m backend.app
# http://127.0.0.1:5057
```

Local profile creation requires a 12+ character password. For production, local setup is OFF. On the first deployment to a new server database, the watcher **asks for the initial admin password once**, directly on the macOS terminal (it is not saved in its settings or printed). Subsequent deployments require no password entry.

## UI

- Prompt/chat and personal projects persisted in SQLite.
- Provider drawer for OpenAI, xAI, Gemini, Anthropic, OpenRouter, DeepSeek, Groq, Together/Meta, Fireworks, Cerebras, Mistral, Perplexity, Kimi, NVIDIA, SiliconFlow, Hugging Face, Ollama, LM Studio, vLLM, custom OpenAI-compatible router.
- Server-side encrypted API keys. Toggles enable/disable providers; model/endpoint fields editable.
- Real chat adapters: OpenAI-compatible Chat Completions, native Gemini `generateContent`, Anthropic Messages.
- Real image generation for OpenAI, xAI and Gemini. Generates four independent views, may incur four provider charges. Current release does **not** guarantee multi-view geometric consistency.
- Uploaded JPG/PNG/WebP references; concept gallery with explicit selection.
- Procedural Three.js vehicle proxy for orbit/colour/ride-height/wheel-size/exploded view. **Not reconstructed from an image**.
- Ontology covering 16 assemblies; concept BOM, JSON manifest, design reference archive.

## Endpoints

`GET /api/health`, `GET /api/session`, `POST /api/setup` (only when explicitly enabled, loopback only), `POST /api/login`, `POST /api/logout`, `GET|PUT /api/profile`, `GET /api/parts`, `GET|POST /api/projects`, `GET|PATCH|DELETE /api/projects/<id>`, `GET /api/projects/<id>/manifest`, `GET /api/projects/<id>/export`, `GET|PUT /api/providers[/<id>]`, `POST /api/chat`, `POST /api/assets/upload`, `GET /api/media/<id>`, `POST /api/concepts/generate`.

## Model & fabrication boundaries

The parts manifest marks all parts `concept`, with absent dimensions, meshes, CAD, masks and attachment constraints. A real print pipeline requires calibrated multi-view input or a validated human-defined CAD design, segmentation/masks, camera alignment, watertight meshes, parametric surfaces, attachment planes, fit tolerances, materials, slicer checks and hardware verification. An image alone cannot reveal concealed hardware or reliable engineering dimensions.

## Deployment

Place `watcher-umi-lab.sh` at repo root and `UMI_LAB_UPDATE_v0.1.3.zip` in `updates/`. For `--dry-run` nothing is pushed or deployed. An actual deployment requires repository `main`, correct Git origin, access to the Ubuntu SSH target, a public DNS A/AAAA record for `umi-lab.top`, suitable administrator credentials and an interactive initial admin password for a fresh install. The installer makes a new isolated Gunicorn service, picks a free 127.0.0.1 port, writes a dedicated nginx vhost, uses Let's Encrypt only when cert paths already exist or certbot is explicitly available/configured, verifies nginx with `nginx -t`, keeps backups, and never modifies another application vhost.

**No environment exports needed.** The watcher defaults to `root@46.62.232.64:333` and writes persistent non-secret settings to `.umi-lab/watcher-config.json` (mode 0600). Optionally run `./watcher-umi-lab.sh --configure` once to change server details; run `--show-config` to inspect. See `docs/DEPLOY.md`.

## Limits / planned expansion

No automatic segmentation, photogrammetry, image-to-CAD, game physics, multi-user invite, email recovery, industrial tolerancing, paid-model cost tracking or distributed task queue in v0.1.3. No fabricated STL output is claimed.

**Local validation fix:** v0.1.2 imports `requests` only on inference calls, so the macOS watcher can check provider metadata without the Flask dependencies installed. Runtime inference still requires the pinned requirements.

**SSH compatibility fix (v0.1.2):** Default SSH port is 333, matching the supplied Meta Vehicle Lab watcher on the shared Ubuntu host. Override with `UMI_SSH_PORT` if SSH is moved. This is separate from the isolated Flask port selected by the installer.

**Persistent configuration (v0.1.3):** Settings remain after macOS restarts. The bootstrap admin password is requested from `/dev/tty` only if the server reports no prior UMI database. Do not store passwords in repository files or JSON settings. SSH key authentication still uses the normal macOS SSH agent/keychain configuration.
