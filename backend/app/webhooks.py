"""POST completion/failure callbacks to customer URLs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.config import Settings, get_settings
from app.db_jobs import get_job_row, update_job_row

logger = logging.getLogger(__name__)


async def deliver_job_webhook(job_id: str, event: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    row = get_job_row(job_id)
    if not row or not (row.webhook_url or "").strip():
        return

    base = (settings.public_api_base_url or "").rstrip("/")
    export_api = f"{base}/api/jobs/{job_id}/export" if base else f"/api/jobs/{job_id}/export"

    payload = {
        "event": event,
        "job_id": job_id,
        "status": row.status,
        "scenario": row.scenario[:500],
        "demo_mode": row.demo_mode,
        "export_api_url": export_api,
        "export_s3_url": row.export_s3_url,
        "completed_at": row.updated_at.isoformat() if row.updated_at else None,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                row.webhook_url.strip(),
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-ScenarioSim-Event": event,
                    "User-Agent": "ScenarioSim-Webhook/0.3",
                },
            )
        if r.is_success:
            update_job_row(
                job_id,
                webhook_delivered_at=datetime.now(timezone.utc),
                webhook_last_error=None,
            )
        else:
            update_job_row(
                job_id,
                webhook_last_error=f"HTTP {r.status_code}: {r.text[:500]}",
            )
    except Exception as e:
        logger.warning("Webhook delivery failed: %s", e)
        update_job_row(job_id, webhook_last_error=str(e)[:2000])
