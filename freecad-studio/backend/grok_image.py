"""xAI Grok Imagine image generation and editing (https://docs.x.ai)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

GROK_API_URL = "https://api.x.ai/v1"
DEFAULT_IMAGE_MODEL = "grok-imagine-image"
QUALITY_IMAGE_MODEL = "grok-imagine-image-quality"


import secrets_store as secrets


def resolve_grok_config(cfg: dict[str, str] | None = None) -> dict[str, Any]:
    cfg = cfg or {}
    api_key = (
        secrets.get_secret(secrets.GROK_KEY)
        or cfg.get("grok_api_key")
        or os.environ.get("XAI_API_KEY")
        or os.environ.get("GROK_API_KEY")
    )
    model = (cfg.get("grok_image_model") or DEFAULT_IMAGE_MODEL).strip()
    enabled = (cfg.get("image_gen_enabled") or "false").strip().lower() in ("1", "true", "yes", "on")
    return {
        "api_key": api_key,
        "api_url": (cfg.get("grok_api_url") or GROK_API_URL).rstrip("/"),
        "model": model,
        "enabled": enabled,
        "configured": bool(api_key),
    }


def _http_json(url: str, payload: dict, headers: dict[str, str], timeout: float = 120) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Grok image API failed ({exc.code}): {body}") from exc


def _mime_to_data_url(image_b64: str, mime: str = "image/png") -> str:
    clean = image_b64.strip()
    if clean.startswith("data:"):
        return clean
    return f"data:{mime};base64,{clean}"


def _extract_b64(data: dict) -> str:
    items = data.get("data") or []
    if not items:
        raise RuntimeError(f"Grok returned no images: {data}")
    item = items[0]
    if item.get("b64_json"):
        return str(item["b64_json"]).strip()
    url = item.get("url")
    if not url:
        raise RuntimeError(f"Grok image item missing b64_json/url: {item}")
    if url.startswith("data:") and "," in url:
        return url.split(",", 1)[1]
    raise RuntimeError("Grok returned a temporary URL — set response_format=b64_json")


def edit_image(
    *,
    source_b64: str,
    prompt: str,
    cfg: dict[str, str] | None = None,
    mime: str = "image/png",
    model: str | None = None,
    n: int = 1,
) -> list[str]:
    """Edit or re-view a source image. Returns base64 PNG strings."""
    grok = resolve_grok_config(cfg)
    if not grok["configured"]:
        raise RuntimeError(
            "Grok API key not configured. Add grok_api_key in Settings or set XAI_API_KEY."
        )

    payload: dict[str, Any] = {
        "model": model or grok["model"],
        "prompt": prompt,
        "image": {
            "url": _mime_to_data_url(source_b64, mime),
            "type": "image_url",
        },
        "response_format": "b64_json",
        "n": max(1, min(n, 4)),
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {grok['api_key']}",
    }
    data = _http_json(f"{grok['api_url']}/images/edits", payload, headers)
    out: list[str] = []
    for item in data.get("data") or []:
        if item.get("b64_json"):
            out.append(str(item["b64_json"]).strip())
    if not out:
        out.append(_extract_b64(data))
    return out


def generate_image(
    *,
    prompt: str,
    cfg: dict[str, str] | None = None,
    model: str | None = None,
    n: int = 1,
    aspect_ratio: str | None = None,
) -> list[str]:
    """Text-to-image via Grok Imagine."""
    grok = resolve_grok_config(cfg)
    if not grok["configured"]:
        raise RuntimeError("Grok API key not configured.")

    payload: dict[str, Any] = {
        "model": model or grok["model"],
        "prompt": prompt,
        "response_format": "b64_json",
        "n": max(1, min(n, 4)),
    }
    if aspect_ratio:
        payload["aspect_ratio"] = aspect_ratio

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {grok['api_key']}",
    }
    data = _http_json(f"{grok['api_url']}/images/generations", payload, headers)
    out: list[str] = []
    for item in data.get("data") or []:
        if item.get("b64_json"):
            out.append(str(item["b64_json"]).strip())
    if not out:
        out.append(_extract_b64(data))
    return out
