import logging

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.config import get_settings
from app.jobs import create_job, get_job

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="ScenarioSim API", version="0.1.0")

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


@app.get("/api/health")
async def health():
    s = get_settings()
    demo = s.demo_mode or not s.byteplus_api_key.strip()
    return {"ok": True, "demo_mode": demo}


@app.post("/api/jobs")
async def post_job(body: CreateJobBody):
    job = await create_job(body.scenario)
    return {"job_id": job.id, "status": job.status, "demo_mode": job.demo_mode}


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
    }


@app.get("/api/demo-scenarios")
async def demo_scenarios():
    return {
        "scenarios": [
            "A startup has 30 days of runway and must choose between a risky enterprise pilot or a slower SMB growth path.",
            "A city transit agency rolls out on-demand shuttles during a major sports weekend; operations are already understaffed.",
            "A product team ships an AI feature under legal scrutiny; marketing wants to announce early, engineering wants more evals.",
        ]
    }
