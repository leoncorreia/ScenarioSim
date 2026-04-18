from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


def rule_based_recommendation(
    scenario: str,
    variants: list[dict[str, Any]],
) -> tuple[str, str | None]:
    """Return (summary, recommended_label)."""
    ok = [v for v in variants if v.get("status") == "ok" and v.get("video_url")]
    if not ok:
        return (
            "No variants completed successfully. Try again or enable demo mode with a valid scenario.",
            None,
        )
    preferred_order = ["best_case", "edge_case", "worst_case"]
    for key in preferred_order:
        for v in ok:
            if v.get("variant_key") == key:
                label = v.get("label") or key
                body = (
                    f'Compared outcomes for your scenario. "{label}" balances upside and feasibility '
                    "for most planning and communication use cases."
                )
                return body, label
    first = ok[0]
    label = first.get("label") or "Outcome"
    return (
        f'"{label}" is the strongest available completed outcome for this run.',
        label,
    )


async def llm_recommendation(
    settings: Settings,
    scenario: str,
    variants: list[dict[str, Any]],
) -> str | None:
    provider = (settings.llm_provider or "byteplus").strip().lower()
    if provider == "byteplus":
        if not settings.byteplus_api_key.strip():
            return None
        url = f"{settings.byteplus_base_url.rstrip('/')}/chat/completions"
        api_key = settings.byteplus_api_key
    else:
        if not settings.llm_api_key.strip():
            return None
        url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
        api_key = settings.llm_api_key

    payload_variants = [
        {
            "label": v.get("label"),
            "variant_key": v.get("variant_key"),
            "prompt": v.get("prompt"),
            "status": v.get("status"),
            "error": v.get("error"),
        }
        for v in variants
    ]
    system = (
        "You compare simulated scenario outcomes. Respond with 2-3 short sentences: "
        "what differs across variants, then which single outcome you recommend and why. "
        "No markdown headings; plain text."
    )
    user = json.dumps({"scenario": scenario, "variants": payload_variants}, ensure_ascii=False)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.post(url, headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning("LLM recommendation skipped: %s", e)
        return None
