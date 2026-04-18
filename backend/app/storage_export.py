"""Optional S3-compatible upload for Track 4 JSON artifacts."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)


def upload_track4_export_if_configured(settings: Settings, job_id: str, payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """
    Returns (public_or_presigned_url, object_key) if configured; else (None, None).
    Uses boto3 when S3_BUCKET and credentials are set.
    """
    bucket = (settings.s3_bucket or "").strip()
    if not bucket:
        return None, None
    try:
        import boto3  # type: ignore
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        logger.warning("boto3 not installed; skip S3 upload")
        return None, None

    prefix = (settings.s3_key_prefix or "scenariosim").strip().strip("/")
    key = f"{prefix}/track4/{job_id}.json"

    endpoint = settings.s3_endpoint_url.strip() or None
    client_kw: dict[str, Any] = {}
    if settings.s3_region:
        client_kw["region_name"] = settings.s3_region
    session = boto3.session.Session(
        aws_access_key_id=settings.s3_access_key or None,
        aws_secret_access_key=settings.s3_secret_key or None,
    )
    client = session.client("s3", endpoint_url=endpoint, **client_kw)
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    try:
        client.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
    except (ClientError, BotoCoreError) as e:
        logger.warning("S3 put_object failed: %s", e)
        return None, None

    url: str | None = None
    if settings.s3_public_base_url.strip():
        base = settings.s3_public_base_url.rstrip("/")
        url = f"{base}/{key}"
    else:
        try:
            url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=settings.s3_presign_seconds,
            )
        except Exception as e:
            logger.warning("Could not presign S3 URL: %s", e)

    return url, key
