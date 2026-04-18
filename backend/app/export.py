"""Track 4 — structured export for synthetic video runs (weak labels + provenance)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import Settings
from app.jobs import JobRecord

TRACK4_EXPORT_FORMAT = "scenariosim-track4-v1"

# Weak supervision hints for physical-AI / simulation pipelines (not ground truth).
OUTCOME_META: dict[str, dict[str, str]] = {
    "best_case": {"outcome_axis": "favorable", "weak_supervision_label": "success_prone"},
    "worst_case": {"outcome_axis": "adverse", "weak_supervision_label": "failure_prone"},
    "edge_case": {"outcome_axis": "ambiguous", "weak_supervision_label": "mixed"},
}


def _enrich_variant(v: dict[str, Any], index: int) -> dict[str, Any]:
    key = str(v.get("variant_key") or "")
    meta = OUTCOME_META.get(
        key,
        {"outcome_axis": "unknown", "weak_supervision_label": "unknown"},
    )
    row = {**v, "variant_index": index}
    row["track4"] = {
        "outcome_axis": meta["outcome_axis"],
        "weak_supervision_label": meta["weak_supervision_label"],
        "notes": "Generative video; not physics simulation. Labels are scenario-role hints only.",
    }
    return row


def build_track4_export(job: JobRecord, settings: Settings) -> dict[str, Any]:
    variants = [_enrich_variant(v, i) for i, v in enumerate(job.variants)]
    return {
        "export_format": TRACK4_EXPORT_FORMAT,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "job": {
            "id": job.id,
            "scenario": job.scenario,
            "status": job.status,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "demo_mode": job.demo_mode,
            "recommendation": job.recommendation,
            "recommended_label": job.recommended_label,
            "error": job.error,
        },
        "variants": variants,
        "provenance": {
            "scenariosim_api_version": "0.2.0",
            "seedance_model": settings.seedance_model,
            "video_duration_sec": settings.video_duration,
            "video_resolution": settings.video_resolution,
            "video_ratio": settings.video_ratio,
            "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
            "seedance_seed_base": settings.seedance_seed,
            "seed_note": "When seedance_seed_base is null, BytePlus uses random seeds. "
            "When set, each variant uses base + variant_index.",
            "byteplus_base_url": settings.byteplus_base_url,
            "disclaimer": "Synthetic RGB video from a generative model. "
            "Suitable for qualitative simulation, scenario libraries, and weak labels—not dynamics-grounded robot training.",
        },
    }
