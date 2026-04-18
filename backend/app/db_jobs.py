"""Persistence for jobs (sync; call from async via asyncio.to_thread)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.database import SessionLocal
from app.job_types import JobRecord
from app.models import JobRow


def _now() -> datetime:
    return datetime.now(timezone.utc)


def insert_job_row(
    job_id: str,
    scenario: str,
    *,
    demo_mode: bool,
    webhook_url: str | None,
) -> None:
    with SessionLocal() as session:
        row = JobRow(
            id=job_id,
            scenario=scenario,
            status="queued",
            demo_mode=demo_mode,
            variants_json=[],
            webhook_url=webhook_url,
        )
        session.add(row)
        session.commit()


def update_job_row(job_id: str, **fields: Any) -> None:
    with SessionLocal() as session:
        row = session.get(JobRow, job_id)
        if not row:
            return
        for key, val in fields.items():
            if hasattr(row, key):
                setattr(row, key, val)
        row.updated_at = _now()
        session.commit()


def get_job_row(job_id: str) -> JobRow | None:
    with SessionLocal() as session:
        return session.get(JobRow, job_id)


def fetch_job_record(job_id: str) -> JobRecord | None:
    row = get_job_row(job_id)
    if not row:
        return None
    return row_to_record(row)


def row_to_record(row: JobRow) -> JobRecord:
    created = row.created_at
    updated = row.updated_at
    return JobRecord(
        id=row.id,
        scenario=row.scenario,
        status=row.status,
        created_at=created.isoformat() if created else "",
        updated_at=updated.isoformat() if updated else "",
        demo_mode=bool(row.demo_mode),
        variants=list(row.variants_json or []),
        recommendation=row.recommendation,
        recommended_label=row.recommended_label,
        error=row.error,
        webhook_url=row.webhook_url,
        export_s3_url=row.export_s3_url,
        export_s3_key=row.export_s3_key,
    )
