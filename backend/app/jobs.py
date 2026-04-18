from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from app.config import Settings, get_settings
from app.db_jobs import fetch_job_record, insert_job_row, update_job_row
from app.export import build_track4_export
from app.job_types import JobRecord
from app.recommend import llm_recommendation, rule_based_recommendation
from app.seedance import MockVideoGenerator, VideoGenerator, get_generator, poll_until_video
from app.storage_export import upload_track4_export_if_configured
from app.webhooks import deliver_job_webhook

logger = logging.getLogger(__name__)


# Reduces “random B-roll”: Seedance only sees text—constraints must be explicit in the prompt.
_VISUAL_GROUNDING = (
    "Visual fidelity: Depict exactly what the scenario describes (place, weather, stakes). "
    "Use coherent real-world layout—lanes, curbs, crosswalk markings, traffic lights—when the scene is a city street. "
    "Do not substitute unrelated generic footage."
)

VARIANT_DEFS = [
    {
        "variant_key": "best_case",
        "label": "Best case",
        "suffix": (
            "Simulate the most favorable realistic resolution: timing works and the outcome clearly succeeds. "
            "Show the full arc from setup through completion—the viewer must see the successful end state on screen. "
            "For crossings and traffic, show the **safest plausible, rule-compliant** behavior the scenario implies "
            "(e.g. marked crosswalk and walk signal for a successful lawful crossing—not mid-block jaywalking). "
            "Cinematic, grounded, documentary tone."
        ),
    },
    {
        "variant_key": "worst_case",
        "label": "Worst case",
        "suffix": (
            "**This variant must show the BAD outcome only—do not depict a safe or successful resolution.** "
            "If the scenario involves crossing traffic, you must **not** show a calm, uneventful crossing on a green "
            "walk signal; show concrete peril: e.g. conflict with a moving vehicle, near-miss, loss of footing in rain, "
            "stepping as a car turns, running a stale signal, or another visible failure tied to the scenario. "
            "The viewer should clearly see **what went wrong** by the end of the clip. Realistic, not cartoon gore."
        ),
    },
    {
        "variant_key": "edge_case",
        "label": "Edge case",
        "suffix": (
            "Simulate an unusual but realistic edge scenario: a rare constraint, odd timing, or "
            "ambiguous signal changes the trajectory. Show how the situation evolves without contradicting "
            "the scenario’s setting."
        ),
    },
]


def video_seed_for_variant(settings: Settings, variant_index: int) -> int | None:
    base = settings.seedance_seed
    if base is None or base < 0:
        return None
    return base + variant_index


def build_prompts(scenario: str) -> list[dict[str, str]]:
    out = []
    for v in VARIANT_DEFS:
        prompt = (
            f"Scenario: {scenario.strip()}\n\n"
            f"{_VISUAL_GROUNDING}\n\n"
            f"Variant intent: {v['label']}.\n{v['suffix']}\n\n"
            "Output: one coherent short scene with a clear beginning, middle, and end so the result is visible "
            "before the clip ends. No on-screen captions or subtitles."
        )
        out.append(
            {
                "variant_key": v["variant_key"],
                "label": v["label"],
                "prompt": prompt,
            }
        )
    return out


async def _persist(job_id: str, **fields: Any) -> None:
    await asyncio.to_thread(update_job_row, job_id, **fields)


async def create_job(scenario: str, webhook_url: str | None = None) -> JobRecord:
    settings = get_settings()
    job_id = uuid.uuid4().hex
    demo = settings.demo_mode or not settings.byteplus_api_key.strip()
    await asyncio.to_thread(insert_job_row, job_id, scenario.strip(), demo_mode=demo, webhook_url=webhook_url)
    asyncio.create_task(_run_job(job_id))
    rec = fetch_job_record(job_id)
    if not rec:
        raise RuntimeError("failed to persist job")
    return rec


def get_job(job_id: str) -> JobRecord | None:
    return fetch_job_record(job_id)


async def create_jobs_batch(scenarios: list[str], webhook_url: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    if len(scenarios) > settings.batch_jobs_max:
        raise ValueError(
            f"at most {settings.batch_jobs_max} scenarios per batch (set BATCH_JOBS_MAX to raise)"
        )
    jobs_out: list[dict[str, Any]] = []
    for s in scenarios:
        job = await create_job(s, webhook_url=webhook_url)
        jobs_out.append(
            {
                "job_id": job.id,
                "status": job.status,
                "demo_mode": job.demo_mode,
                "export_path": f"/api/jobs/{job.id}/export",
            }
        )
    return {"batch_size": len(jobs_out), "jobs": jobs_out}


async def _run_job(job_id: str) -> None:
    settings = get_settings()
    record = fetch_job_record(job_id)
    if not record:
        return

    async def touch_variants(results: list[dict[str, Any]], status: str | None = None) -> None:
        payload: dict[str, Any] = {"variants_json": list(results)}
        if status is not None:
            payload["status"] = status
        await _persist(job_id, **payload)

    try:
        await _persist(job_id, status="running")

        gen = get_generator(settings)
        prompts = build_prompts(record.scenario)
        results: list[dict[str, Any]] = []

        for variant_index, p in enumerate(prompts):
            seed_used = video_seed_for_variant(settings, variant_index)
            variant: dict[str, Any] = {
                "variant_key": p["variant_key"],
                "label": p["label"],
                "prompt": p["prompt"],
                "status": "pending",
                "video_url": None,
                "provider_task_id": None,
                "error": None,
                "mock_fallback": False,
                "generation_seed": seed_used,
            }
            results.append(variant)
            await touch_variants(results)

            async def run_variant(active_gen: VideoGenerator) -> None:
                if isinstance(active_gen, MockVideoGenerator):
                    await asyncio.sleep(0.1)
                task_id = await active_gen.create_text_to_video_task(
                    p["prompt"],
                    seed=seed_used,
                )
                variant["provider_task_id"] = task_id
                variant["status"] = "generating"
                await touch_variants(results)

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

            await touch_variants(results)

        llm_text = await llm_recommendation(settings, record.scenario, results)
        summary, label = rule_based_recommendation(record.scenario, results)
        await _persist(
            job_id,
            status="completed",
            variants_json=results,
            recommendation=llm_text or summary,
            recommended_label=label,
        )

        rec_done = fetch_job_record(job_id)
        if rec_done:
            export_payload = build_track4_export(rec_done, settings)
            s3_url, s3_key = await asyncio.to_thread(
                upload_track4_export_if_configured, settings, job_id, export_payload
            )
            if s3_url:
                await _persist(job_id, export_s3_url=s3_url, export_s3_key=s3_key)

        await deliver_job_webhook(job_id, "job.completed", settings)
    except Exception as e:
        logger.exception("Job failed")
        await _persist(job_id, status="failed", error=str(e))
        await deliver_job_webhook(job_id, "job.failed", settings)
