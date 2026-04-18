# ScenarioSim

**Pitch:** ScenarioSim turns a short real-world situation into three quick “what if” video outcomes—best case, worst case, and an edge path—then stacks them side by side and names the trajectory that is most useful for decisions, storytelling, and alignment. It is built for demos: async jobs, clear progress, graceful fallbacks, and a deploy path that works the first time you try it.

## What you get

- React (Vite) + FastAPI, one scenario field, one **Generate** button.
- Async jobs: `POST /api/jobs` returns immediately; the UI polls `GET /api/jobs/{id}`.
- BytePlus Seedance integration behind a small adapter (create task → poll → video URL) with **demo mode** and **per-variant mock fallback** when the provider errors.
- Three variants: **Best case**, **Worst case**, **Edge case**; recommendation block highlights the preferred outcome card.
- **Persistent jobs**: SQLite by default (`scenariosim.db` in `backend/`), or **PostgreSQL** via `DATABASE_URL` (recommended on Render). Survives process restarts.
- **Webhooks**: optional `webhook_url` on `POST /api/jobs` / `batch` — server POSTs `job.completed` or `job.failed` with export links.
- **Optional S3/R2**: upload Track 4 JSON to a bucket for data-lake workflows.
- No auth (add your gateway in production).

## Track 4: Physical AI + simulation (structured export)

ScenarioSim fits **qualitative** simulation: synthetic **RGB** clips + **weak labels** for scenario libraries, red-teaming narratives, and pipeline prototyping—not a replacement for physics simulators (MuJoCo, Isaac, CARLA) or ground-truth dynamics.

**What we added**

| Capability | How |
| --- | --- |
| **Dataset-style JSON** | `GET /api/jobs/{id}/export` returns `scenariosim-track4-v1`: job metadata, each variant with `video_url`, full prompt, `generation_seed`, and `track4.outcome_axis` / `weak_supervision_label` (favorable / adverse / ambiguous). |
| **Provenance** | `provenance` block records model IDs, duration, resolution, LLM settings, optional seed base, and an explicit disclaimer. |
| **Reproducibility** | Set `SEEDANCE_SEED` (non-negative int). Variant *k* uses seed `SEEDANCE_SEED + k` when calling Seedance (if the API accepts `seed`). Omit for provider-random. |
| **Batch enqueue** | `POST /api/jobs/batch` with body `{"scenarios": ["...", "..."], "webhook_url": "https://..." (optional)}` enqueues up to `BATCH_JOBS_MAX` (default 25) independent jobs. |
| **Webhooks** | JSON POST to your URL when a job finishes: `event`, `job_id`, `status`, `export_api_url`, `export_s3_url` (if configured). Set **`PUBLIC_API_BASE_URL`** on the API so `export_api_url` is absolute. |
| **S3-compatible storage** | If `S3_BUCKET` + credentials are set, each completed run uploads `track4/{job_id}.json`; URL stored on the job and in export. |

**Honest limits**

- Single short clip per variant; no built-in depth/LiDAR/segmentation.
- Generative video is **not** physics-accurate; labels are **role hints** from scenario design, not measured outcomes.
- Provider safety filters may soften extreme “failure” visuals.

**Examples**

```bash
# After a job completes
curl -s "https://your-api.onrender.com/api/jobs/JOB_ID/export" | jq .

# Batch (then poll each job_id)
curl -s -X POST "https://your-api.onrender.com/api/jobs/batch" \
  -H "Content-Type: application/json" \
  -d '{"scenarios":["Scenario A...","Scenario B..."],"webhook_url":"https://example.com/hooks/scenariosim"}'

# Single job with webhook
curl -s -X POST "https://your-api.onrender.com/api/jobs" \
  -H "Content-Type: application/json" \
  -d '{"scenario":"Your scenario...","webhook_url":"https://example.com/hook"}'
```

The web UI links to **Export JSON** when results are shown.

## Sample scenarios (demo)

1. A startup has 30 days of runway and must choose between a risky enterprise pilot or a slower SMB growth path.
2. A city transit agency rolls out on-demand shuttles during a major sports weekend; operations are already understaffed.
3. A product team ships an AI feature under legal scrutiny; marketing wants to announce early, engineering wants more evals.

(These also appear in the UI via `GET /api/demo-scenarios`.)

## Local setup

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy ..\\.env.example .env   # or: cp ../.env.example .env — then edit keys
uvicorn app.main:app --reload --port 8000
```

Health check: `http://127.0.0.1:8000/api/health`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The dev server proxies `/api` to the backend on port 8000.

### Environment variables

See root `.env.example`. Minimum notes:

| Variable | Purpose |
| --- | --- |
| `BYTEPLUS_API_KEY` or `ARK_API_KEY` | BytePlus ModelArk key for Seedance |
| `BYTEPLUS_BASE_URL` | Default `https://ark.ap-southeast.bytepluses.com/api/v3` |
| `SEEDANCE_MODEL` | Dreamina Seedance 2.0 IDs from the [model list](https://docs.byteplus.com/en/docs/ModelArk/1330310): e.g. `dreamina-seedance-2-0-260128` or `dreamina-seedance-2-0-fast-260128` |
| `VIDEO_DURATION` | Optional override; default **6** s (Seedance 2.0 allows 4–15). Longer clips can show a clearer beginning-to-end arc. |
| `DEMO_MODE` | `true` forces mock clips end-to-end |
| `FALLBACK_MOCK_ON_ERROR` | `true` swaps failed variants to sample MP4s |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins |
| `LLM_PROVIDER` | `byteplus` (default): same `BYTEPLUS_API_KEY` and `BYTEPLUS_BASE_URL`, `POST .../chat/completions`. `openai`: use `LLM_API_KEY` + `LLM_BASE_URL`. |
| `LLM_MODEL` | Default `seed-2-0-lite-260228` (ModelArk text model). For `openai`, e.g. `gpt-4o-mini`. **Do not** use a Seedance video ID here. |
| `LLM_API_KEY` / `OPENAI_API_KEY` | Only when `LLM_PROVIDER=openai` |
| `LLM_BASE_URL` | Only when `LLM_PROVIDER=openai` (default OpenAI v1 base) |
| `SEEDANCE_SEED` | Optional int ≥ 0 for reproducible clips (`+ variant_index` per branch). Omit for random. |
| `BATCH_JOBS_MAX` | Cap for `POST /api/jobs/batch` (default 25). |
| `DATABASE_URL` | Default `sqlite:///./scenariosim.db`. On Render, use the **PostgreSQL** connection string from the dashboard. |
| `PUBLIC_API_BASE_URL` | Public origin of this API (e.g. `https://scenariosim-api.onrender.com`) — used in webhook payloads for absolute `export_api_url`. |
| `S3_BUCKET`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION` | Optional; R2/AWS/MinIO. Set `S3_PUBLIC_BASE_URL` if objects are public, else a presigned GET URL is stored (see `S3_PRESIGN_SECONDS`). |
| `S3_KEY_PREFIX` | Object key prefix (default `scenariosim`). |

Frontend build (production): set `VITE_API_URL` to your backend origin, e.g. `https://your-api.onrender.com` (no trailing slash).

## GitHub repository

Git is initialized in this folder. `GitHub CLI` is not required—create the remote from the GitHub website:

1. New repository → name it `ScenarioSim` (or any name) → do not add a README (this project already has one).
2. Push:

```bash
cd ScenarioSim
git commit -m "Initial ScenarioSim MVP"
git branch -M main
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git push -u origin main
```

## Render deployment

**Option A — Blueprint (`render.yaml` in repo)**

1. Push this repo to GitHub.
2. In Render: **New** → **Blueprint** → connect the repo and apply.
3. After the first deploy:
   - Set **Web Service** env `CORS_ORIGINS` to your static site URL (e.g. `https://scenariosim-web.onrender.com`).
   - Set **Static Site** env `VITE_API_URL` to the API URL (e.g. `https://scenariosim-api.onrender.com`).
4. Trigger a **rebuild** of the static site so `VITE_API_URL` is baked into the bundle.

**Option B — Manual**

1. **Web Service**: Root directory `backend`, build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, runtime Python 3.12.
2. **Static Site**: Root directory `frontend`, build `npm install && npm run build`, publish `frontend/dist`.
3. Add the same env vars as in Option A.

## BytePlus / Seedance docs

ScenarioSim targets **Dreamina Seedance 2.0** via the ModelArk video generation API.

| Topic | Doc |
| --- | --- |
| Model list (video IDs, **4–15 s**, **480p / 720p**, regions) | [Model list](https://docs.byteplus.com/en/docs/ModelArk/1330310) |
| Seedance 2.0 tutorial (basic usage, `content` array, `generate_audio`, polling `succeeded` / `failed`) | [Seedance 2.0 series tutorial](https://docs.byteplus.com/en/docs/ModelArk/2291680#basic-usage) |
| HTTP reference | [Create task](https://docs.byteplus.com/en/docs/ModelArk/1520757), [Retrieve task](https://docs.byteplus.com/en/docs/ModelArk/1521309) |

**Regions (from the model list):** `ap-southeast-1` → `https://ark.ap-southeast.bytepluses.com/api/v3`; `eu-west-1` → `https://ark.eu-west.bytepluses.com/api/v3`. Set `BYTEPLUS_BASE_URL` to match the region where your key and model are enabled.

Generation is asynchronous: `POST /api/jobs` returns immediately; the backend polls BytePlus until each variant finishes or times out. If the retrieve payload differs for your account, adjust URL extraction in `backend/app/seedance.py` (see TODO there).

## License

Use and modify freely for demos and internal tools.
