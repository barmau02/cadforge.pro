"""App settings: API keys in SQLite; other prefs in config.toml."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import secrets_store as secrets

SETTING_KEYS = (
    "ai_provider",
    "api_url",
    "model",
    "grok_image_model",
    "grok_api_url",
    "image_gen_enabled",
)


def public_settings(cfg: dict[str, str]) -> dict[str, Any]:
    secret_status = secrets.public_secret_status()
    return {
        "ai_provider": cfg.get("ai_provider", "ollama_cloud"),
        "api_url": cfg.get("api_url", "https://ollama.com"),
        "model": cfg.get("model", ""),
        **secret_status,
        "grok_image_model": cfg.get("grok_image_model", "grok-imagine-image"),
        "grok_api_url": cfg.get("grok_api_url", "https://api.x.ai/v1"),
        "image_gen_enabled": (cfg.get("image_gen_enabled") or "false").lower() in ("1", "true", "yes", "on"),
        "ollama_key_url": "https://ollama.com/settings/keys",
        "grok_key_url": "https://console.x.ai/",
    }


def apply_settings_update(
    payload: dict[str, Any],
    *,
    load_config: Callable[[], dict[str, str]],
    save_config_value: Callable[[str, str], None],
    config_file: Path,
) -> dict[str, Any]:
    """Persist settings from API request. Empty string clears a key."""
    updated: list[str] = []

    if "ollama_api_key" in payload:
        val = str(payload["ollama_api_key"] or "").strip()
        if val:
            secrets.set_secret(secrets.OLLAMA_KEY, val)
        else:
            secrets.delete_secret(secrets.OLLAMA_KEY)
        _remove_config_keys(config_file, ("ollama_api_key", "api_key"))
        updated.append("ollama_api_key")

    if "grok_api_key" in payload:
        val = str(payload["grok_api_key"] or "").strip()
        if val:
            secrets.set_secret(secrets.GROK_KEY, val)
        else:
            secrets.delete_secret(secrets.GROK_KEY)
        _remove_config_keys(config_file, ("grok_api_key",))
        updated.append("grok_api_key")

    for key in ("ai_provider", "api_url", "model", "grok_image_model", "grok_api_url"):
        if key in payload and payload[key] is not None:
            save_config_value(key, str(payload[key]).strip())
            updated.append(key)

    if "image_gen_enabled" in payload:
        save_config_value(
            "image_gen_enabled",
            "true" if payload["image_gen_enabled"] else "false",
        )
        updated.append("image_gen_enabled")

    cfg = load_config()
    return {"updated": updated, "settings": public_settings(cfg)}


def _remove_config_keys(config_file: Path, keys: tuple[str, ...]) -> None:
    if not config_file.exists():
        return
    key_set = set(keys)
    lines = config_file.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            out.append(line)
            continue
        k, _, _ = stripped.partition("=")
        if k.strip() in key_set:
            continue
        out.append(line)
    config_file.write_text("\n".join(out) + "\n", encoding="utf-8")
