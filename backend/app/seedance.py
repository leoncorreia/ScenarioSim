"""
BytePlus ModelArk / Seedance video generation (HTTP adapter).

Official docs:
- Model IDs, regions, and base URLs: https://docs.byteplus.com/en/docs/ModelArk/1330310
- Seedance 2.0 (basic usage, content shape, polling): https://docs.byteplus.com/en/docs/ModelArk/2291680#basic-usage
- Video API — create task: https://docs.byteplus.com/en/docs/ModelArk/1520757
- Video API — retrieve task: https://docs.byteplus.com/en/docs/ModelArk/1521309

REST path used here: POST/GET {base}/contents/generations/tasks (same contract as SDK `content_generation.tasks`).

TODO: Confirm completed-task JSON for your account; the video URL may be nested under output/content.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

# Public sample MP4s for demo when APIs fail or DEMO_MODE is on.
MOCK_VIDEOS = [
    "https://storage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
    "https://storage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4",
    "https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
]


@dataclass
class TaskSnapshot:
    status: str
    video_url: str | None
    raw: dict[str, Any] | None
    error: str | None = None


class VideoGenerator(ABC):
    @abstractmethod
    async def create_text_to_video_task(self, prompt: str, *, seed: int | None = None) -> str:
        """Return provider task id. Optional seed for reproducibility (provider-dependent)."""

    @abstractmethod
    async def get_task(self, task_id: str) -> TaskSnapshot:
        """Return normalized snapshot."""


def _extract_video_url(payload: dict[str, Any]) -> str | None:
    """Best-effort extraction; TODO: align with official response schema."""

    candidates: list[str] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, str) and obj.startswith("http"):
            candidates.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(payload)
    for c in candidates:
        if c.lower().split("?", 1)[0].endswith(".mp4"):
            return c
    return candidates[0] if candidates else None


def _normalize_status(payload: dict[str, Any]) -> str:
    status = (
        payload.get("status")
        or payload.get("task_status")
        or payload.get("state")
        or ""
    )
    return str(status).lower()


class MockVideoGenerator(VideoGenerator):
    def __init__(self, settings: Settings):
        self._settings = settings

    async def create_text_to_video_task(self, prompt: str, *, seed: int | None = None) -> str:
        await asyncio.sleep(0.4 + random.random() * 0.4)
        return f"mock-{uuid.uuid4().hex[:12]}"

    async def get_task(self, task_id: str) -> TaskSnapshot:
        await asyncio.sleep(0.2)
        idx = hash(task_id) % len(MOCK_VIDEOS)
        return TaskSnapshot(
            status="succeeded",
            video_url=MOCK_VIDEOS[idx],
            raw={"id": task_id, "status": "succeeded", "mock": True},
            error=None,
        )


class BytePlusSeedanceGenerator(VideoGenerator):
    def __init__(self, settings: Settings):
        self._settings = settings
        self._base = settings.byteplus_base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        key = self._settings.byteplus_api_key
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    async def create_text_to_video_task(self, prompt: str, *, seed: int | None = None) -> str:
        url = f"{self._base}/contents/generations/tasks"
        body: dict[str, Any] = {
            "model": self._settings.seedance_model,
            "content": [{"type": "text", "text": prompt}],
            "ratio": self._settings.video_ratio,
            "duration": self._settings.video_duration,
            "resolution": self._settings.video_resolution,
            "generate_audio": self._settings.generate_audio,
        }
        if seed is not None:
            body["seed"] = seed
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, headers=self._headers(), json=body)
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.warning("Seedance create failed: %s %s", r.status_code, r.text[:500])
                raise
            data = r.json()
        task_id = data.get("id") or data.get("task_id")
        if not task_id:
            raise RuntimeError(f"Unexpected create response: {json.dumps(data)[:800]}")
        return str(task_id)

    async def get_task(self, task_id: str) -> TaskSnapshot:
        url = f"{self._base}/contents/generations/tasks/{task_id}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(url, headers=self._headers())
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.warning("Seedance poll failed: %s %s", r.status_code, r.text[:500])
                return TaskSnapshot(
                    status="failed",
                    video_url=None,
                    raw=None,
                    error=f"HTTP {r.status_code}",
                )
            data = r.json()
        status = _normalize_status(data)
        terminal_ok = status in ("succeeded", "success", "completed", "done")
        terminal_bad = status in ("failed", "canceled", "cancelled", "error")
        video_url = _extract_video_url(data) if terminal_ok else None
        err = None
        if terminal_bad:
            err = str(data.get("error") or data.get("message") or "task failed")
        return TaskSnapshot(
            status=status,
            video_url=video_url,
            raw=data,
            error=err,
        )


def get_generator(settings: Settings) -> VideoGenerator:
    if settings.demo_mode or not settings.byteplus_api_key.strip():
        return MockVideoGenerator(settings)
    return BytePlusSeedanceGenerator(settings)


async def poll_until_video(
    gen: VideoGenerator,
    task_id: str,
    *,
    interval: float,
    max_attempts: int,
) -> TaskSnapshot:
    for attempt in range(max_attempts):
        snap = await gen.get_task(task_id)
        if snap.error and snap.status in ("failed", "canceled", "cancelled", "error"):
            return snap
        if snap.video_url:
            return snap
        if snap.status in ("failed", "canceled", "cancelled", "error"):
            return TaskSnapshot(
                status=snap.status,
                video_url=None,
                raw=snap.raw,
                error=snap.error or "failed",
            )
        await asyncio.sleep(interval)
    return TaskSnapshot(
        status="timeout",
        video_url=None,
        raw=None,
        error="Polling timed out",
    )
