"""SQLite-backed storage for API keys and other secrets (not config.toml)."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DB_FILE = ROOT / "jobs" / "secrets.db"

OLLAMA_KEY = "ollama_api_key"
GROK_KEY = "grok_api_key"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_secrets (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def get_secret(name: str) -> str | None:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM app_secrets WHERE name = ?", (name,)).fetchone()
    if not row:
        return None
    value = str(row["value"] or "").strip()
    return value or None


def set_secret(name: str, value: str) -> None:
    text = (value or "").strip()
    if not text:
        delete_secret(name)
        return
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO app_secrets (name, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (name, text, time.time()),
        )


def delete_secret(name: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM app_secrets WHERE name = ?", (name,))


def migrate_from_config(cfg: dict[str, str]) -> list[str]:
    """Import API keys from legacy config.toml into the secrets database."""
    migrated: list[str] = []
    ollama = (cfg.get("ollama_api_key") or cfg.get("api_key") or "").strip()
    if ollama and not get_secret(OLLAMA_KEY):
        set_secret(OLLAMA_KEY, ollama)
        migrated.append(OLLAMA_KEY)
    grok = (cfg.get("grok_api_key") or "").strip()
    if grok and not get_secret(GROK_KEY):
        set_secret(GROK_KEY, grok)
        migrated.append(GROK_KEY)
    return migrated


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    v = value.strip()
    if len(v) <= 8:
        return "••••••••"
    return f"{'•' * (len(v) - 4)}{v[-4:]}"


def public_secret_status() -> dict[str, Any]:
    ollama = get_secret(OLLAMA_KEY)
    grok = get_secret(GROK_KEY)
    return {
        "ollama_api_key_set": bool(ollama),
        "ollama_api_key_masked": mask_secret(ollama),
        "grok_api_key_set": bool(grok),
        "grok_api_key_masked": mask_secret(grok),
    }
