import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl

from app.config import get_settings
from app.database import db_ping, init_db
from app.export import build_track4_export
from app.jobs import create_job, create_jobs_batch, get_job

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="ScenarioSim API", version="0.3.0", lifespan=lifespan)

_settings = get_settings()
_origins = [o.strip() for o in _settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateJobBody(BaseModel):
    scenario: str = Field(min_length=3, max_length=4000)
    webhook_url: HttpUrl | None = Field(default=None, description="POST job.completed | job.failed when the run ends")


class BatchJobsBody(BaseModel):
    scenarios: list[str] = Field(min_length=1, description="Each string is one independent scenario job")
    webhook_url: HttpUrl | None = Field(default=None, description="Applied to every job in this batch")


@app.get("/")
async def root():
    """Avoid 404 when opening the service URL in a browser; all API routes live under /api/."""
    return {
        "service": "ScenarioSim API",
        "version": "0.3.0",
        "docs": "/docs",
        "health": "/api/health",
        "track4_export": "/api/jobs/{job_id}/export",
        "batch_jobs": "POST /api/jobs/batch",
    }


@app.get("/api/health")
async def health():
    s = get_settings()
    demo = s.demo_mode or not s.byteplus_api_key.strip()
    return {
        "ok": True,
        "demo_mode": demo,
        "database": db_ping(),
    }


@app.post("/api/jobs")
async def post_job(body: CreateJobBody):
    wh = str(body.webhook_url) if body.webhook_url else None
    job = await create_job(body.scenario, webhook_url=wh)
    return {
        "job_id": job.id,
        "status": job.status,
        "demo_mode": job.demo_mode,
        "export_path": f"/api/jobs/{job.id}/export",
    }


@app.post("/api/jobs/batch")
async def post_jobs_batch(body: BatchJobsBody):
    cleaned: list[str] = []
    for raw in body.scenarios:
        s = (raw or "").strip()
        if len(s) < 3:
            raise HTTPException(status_code=400, detail="Each scenario must be at least 3 characters")
        if len(s) > 4000:
            raise HTTPException(status_code=400, detail="Each scenario must be at most 4000 characters")
        cleaned.append(s)
    if not cleaned:
        raise HTTPException(status_code=400, detail="at least one non-empty scenario required")
    wh = str(body.webhook_url) if body.webhook_url else None
    try:
        return await create_jobs_batch(cleaned, webhook_url=wh)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/jobs/{job_id}")
async def read_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "scenario": job.scenario,
        "status": job.status,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "demo_mode": job.demo_mode,
        "variants": job.variants,
        "recommendation": job.recommendation,
        "recommended_label": job.recommended_label,
        "error": job.error,
        "export_s3_url": job.export_s3_url,
    }


@app.get("/api/jobs/{job_id}/export")
async def export_job(job_id: str):
    """Track 4: JSON bundle with weak labels + provenance for pipeline / dataset tooling."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return build_track4_export(job, get_settings())


@app.get("/api/demo-scenarios")
async def demo_scenarios():
    return {
        "scenarios": [
            "A startup has 30 days of runway and must choose between a risky enterprise pilot or a slower SMB growth path.",
            "A city transit agency rolls out on-demand shuttles during a major sports weekend; operations are already understaffed.",
            "A product team ships an AI feature under legal scrutiny; marketing wants to announce early, engineering wants more evals.",
        ]
    }
