"""Shared job DTO (API + export + persistence)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    webhook_url: str | None = None
    export_s3_url: str | None = None
    export_s3_key: str | None = None
