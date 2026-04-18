"""SQLAlchemy models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class JobRow(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    demo_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    variants_json: Mapped[list] = mapped_column(JSON, default=list)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    webhook_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    export_s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    export_s3_url: Mapped[str | None] = mapped_column(Text, nullable=True)
