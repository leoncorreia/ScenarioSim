from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.config import Settings, get_settings
from app.recommend import llm_recommendation, rule_based_recommendation
from app.seedance import MockVideoGenerator, VideoGenerator, get_generator, poll_until_video

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


VARIANT_DEFS = [
    {
        "variant_key": "best_case",
        "label": "Best case",
        "suffix": (
            "Simulate the most favorable realistic resolution: stakeholders align, timing works, "
            "and the outcome clearly succeeds. Cinematic, grounded, documentary tone."
        ),
    },
    {
        "variant_key": "worst_case",
        "label": "Worst case",
        "suffix": (
            "Simulate a plausible failure mode: miscommunication, delay, or key risk materializes. "
            "Keep it realistic, not cartoonish. Show consequences clearly."
        ),
    },
    {
        "variant_key": "edge_case",
        "label": "Edge case",
        "suffix": (
            "Simulate an unusual but realistic edge scenario: a rare constraint, odd timing, or "
            "ambiguous signal changes the trajectory. Show how the situation evolves."
        ),
    },
]


def build_prompts(scenario: str) -> list[dict[str, str]]:
    out = []
    for v in VARIANT_DEFS:
        prompt = (
            f"Scenario: {scenario.strip()}\n\n"
            f"Variant intent: {v['label']}.\n{v['suffix']}\n\n"
            "Output: a single coherent short scene (no narration text on screen required)."
        )
        out.append(
            {
                "variant_key": v["variant_key"],
                "label": v["label"],
                "prompt": prompt,
            }
        )
    return out


@dataclass
class JobRecord:
    id: str
    scenario: str
    status: str
    created_at: str
    updated_at: str
    demo_mode: bool
    variants: list[dict[str, Any]] = field(default_factory=list)
    recommendation: str | None = None
    recommended_label: str | None = None
    error: str | None = None


JOBS: dict[str, JobRecord] = {}
_LOCK = asyncio.Lock()


async def create_job(scenario: str) -> JobRecord:
    settings = get_settings()
    job_id = uuid.uuid4().hex
    now = _utc_now()
    demo = settings.demo_mode or not settings.byteplus_api_key.strip()
    record = JobRecord(
        id=job_id,
        scenario=scenario.strip(),
        status="queued",
        created_at=now,
        updated_at=now,
        demo_mode=demo,
        variants=[],
    )
    async with _LOCK:
        JOBS[job_id] = record
    asyncio.create_task(_run_job(job_id))
    return record


def get_job(job_id: str) -> JobRecord | None:
    return JOBS.get(job_id)


async def _run_job(job_id: str) -> None:
    settings = get_settings()
    record = JOBS.get(job_id)
    if not record:
        return

    def touch() -> None:
        record.updated_at = _utc_now()

    try:
        record.status = "running"
        touch()
        gen = get_generator(settings)
        prompts = build_prompts(record.scenario)
        results: list[dict[str, Any]] = []

        for p in prompts:
            variant: dict[str, Any] = {
                "variant_key": p["variant_key"],
                "label": p["label"],
                "prompt": p["prompt"],
                "status": "pending",
                "video_url": None,
                "provider_task_id": None,
                "error": None,
                "mock_fallback": False,
            }
            results.append(variant)
            record.variants = list(results)
            touch()

            async def run_variant(active_gen: VideoGenerator) -> None:
                if isinstance(active_gen, MockVideoGenerator):
                    await asyncio.sleep(0.1)
                task_id = await active_gen.create_text_to_video_task(p["prompt"])
                variant["provider_task_id"] = task_id
                variant["status"] = "generating"
                record.variants = list(results)
                touch()

                snap = await poll_until_video(
                    active_gen,
                    task_id,
                    interval=settings.poll_interval_sec,
                    max_attempts=settings.poll_max_attempts,
                )
                if snap.video_url:
                    variant["status"] = "ok"
                    variant["video_url"] = snap.video_url
                else:
                    variant["status"] = "failed"
                    variant["error"] = snap.error or snap.status or "unknown failure"

            try:
                await run_variant(gen)
            except Exception as e:
                logger.exception("Variant failed")
                variant["status"] = "failed"
                variant["error"] = str(e)

            if (
                variant["status"] != "ok"
                and settings.fallback_mock_on_error
                and not isinstance(gen, MockVideoGenerator)
            ):
                variant["mock_fallback"] = True
                variant["error"] = variant.get("error")
                try:
                    mock_gen = MockVideoGenerator(settings)
                    variant["status"] = "pending"
                    await run_variant(mock_gen)
                except Exception as e2:
                    variant["status"] = "failed"
                    variant["error"] = str(e2)

            record.variants = list(results)
            touch()

        llm_text = await llm_recommendation(settings, record.scenario, results)
        summary, label = rule_based_recommendation(record.scenario, results)
        record.recommendation = llm_text or summary
        record.recommended_label = label
        record.status = "completed"
        touch()
    except Exception as e:
        logger.exception("Job failed")
        record.status = "failed"
        record.error = str(e)
        touch()
