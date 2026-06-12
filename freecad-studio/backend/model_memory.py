"""SQLite memory for AI build iterations — the loop's thinking log.

Every generate/execute/critique/fix step is recorded so future builds can
learn from past successes and failures.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DB_FILE = ROOT / "jobs" / "model_memory.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS build_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    prompt TEXT NOT NULL,
    model TEXT,
    started_at REAL NOT NULL,
    finished_at REAL,
    iterations INTEGER DEFAULT 0,
    final_status TEXT DEFAULT 'running',   -- running | approved | max_iters | error
    final_score INTEGER,
    final_code TEXT
);

CREATE TABLE IF NOT EXISTS build_iterations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES build_runs(id),
    iteration INTEGER NOT NULL,
    phase TEXT NOT NULL,                   -- generate | execute | critique | fix
    code TEXT,
    error TEXT,
    critique_json TEXT,
    score INTEGER,
    solids INTEGER,
    duration_sec REAL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_iter_run ON build_iterations(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_job ON build_runs(job_id);
"""


def _connect() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def start_run(job_id: str, prompt: str, model: str | None = None) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO build_runs (job_id, prompt, model, started_at) VALUES (?, ?, ?, ?)",
            (job_id, prompt, model, time.time()),
        )
        return int(cur.lastrowid)


def log_iteration(
    run_id: int,
    iteration: int,
    phase: str,
    *,
    code: str | None = None,
    error: str | None = None,
    critique: dict[str, Any] | None = None,
    score: int | None = None,
    solids: int | None = None,
    duration_sec: float | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO build_iterations
               (run_id, iteration, phase, code, error, critique_json, score, solids, duration_sec, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                iteration,
                phase,
                code,
                error,
                json.dumps(critique) if critique else None,
                score,
                solids,
                duration_sec,
                time.time(),
            ),
        )


def finish_run(run_id: int, status: str, iterations: int, score: int | None, code: str | None) -> None:
    with _connect() as conn:
        conn.execute(
            """UPDATE build_runs
               SET finished_at = ?, final_status = ?, iterations = ?, final_score = ?, final_code = ?
               WHERE id = ?""",
            (time.time(), status, iterations, score, code, run_id),
        )


def past_lessons(prompt: str, limit: int = 3, job_id: str | None = None) -> list[dict[str, Any]]:
    """Return critique issues from past runs with similar prompts (simple keyword overlap)."""
    words = {w.lower() for w in prompt.split() if len(w) > 3}
    if not words and not job_id:
        return []
    lessons: list[dict[str, Any]] = []
    with _connect() as conn:
        if job_id:
            rows = conn.execute(
                """SELECT r.prompt, i.critique_json, i.error, r.final_status
                   FROM build_runs r
                   JOIN build_iterations i ON i.run_id = r.id
                   WHERE r.job_id = ? AND i.phase IN ('critique', 'execute')
                     AND (i.critique_json IS NOT NULL OR i.error IS NOT NULL)
                   ORDER BY r.id DESC LIMIT 80""",
                (job_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT r.prompt, i.critique_json, i.error, r.final_status
                   FROM build_runs r
                   JOIN build_iterations i ON i.run_id = r.id
                   WHERE i.phase IN ('critique', 'execute') AND (i.critique_json IS NOT NULL OR i.error IS NOT NULL)
                   ORDER BY r.id DESC LIMIT 200"""
            ).fetchall()
    for row in rows:
        if job_id:
            overlap = 1
        else:
            past_words = {w.lower() for w in (row["prompt"] or "").split() if len(w) > 3}
            overlap = len(words & past_words)
            if overlap < 2:
                continue
        entry: dict[str, Any] = {"prompt": row["prompt"], "overlap": overlap}
        if row["critique_json"]:
            try:
                crit = json.loads(row["critique_json"])
                issues = crit.get("issues") or []
                if not issues:
                    continue
                entry["issues"] = issues[:4]
            except Exception:
                continue
        elif row["error"]:
            entry["issues"] = [f"execution error: {row['error'][:200]}"]
        lessons.append(entry)
        if len(lessons) >= limit:
            break
    return lessons


def run_history(job_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    with _connect() as conn:
        if job_id:
            rows = conn.execute(
                "SELECT * FROM build_runs WHERE job_id = ? ORDER BY id DESC LIMIT ?",
                (job_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM build_runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def run_iterations(run_id: int) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM build_iterations WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]
