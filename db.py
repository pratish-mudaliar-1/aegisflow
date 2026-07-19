"""
AegisFlow :: db.py
==================
Lightweight SQLite persistence layer for:
- Scheduler jobs (cron definitions + run history)
- Encrypted notes vault (AES-256-GCM metadata)
- Budget request audit log
- Workflow session history (read-only mirror)

All database operations are synchronous (SQLite doesn't benefit from async).
Thread-safety is handled by connection-per-call pattern.

Zero external dependencies beyond Python stdlib + cryptography.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger("aegisflow.db")

# ---------------------------------------------------------------------------
# Database file location — stored next to this file
# ---------------------------------------------------------------------------
DB_PATH: Path = Path(__file__).parent / "aegisflow.db"


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Context manager that yields a SQLite connection and commits/rolls back."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # WAL mode for concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS scheduler_jobs (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    cron_expression TEXT NOT NULL,
    task_command    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at_utc  TEXT NOT NULL,
    last_run_utc    TEXT,
    next_run_label  TEXT,
    run_count       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scheduler_runs (
    id              TEXT PRIMARY KEY,
    job_id          TEXT NOT NULL REFERENCES scheduler_jobs(id),
    started_at_utc  TEXT NOT NULL,
    finished_at_utc TEXT,
    status          TEXT NOT NULL DEFAULT 'running',
    output_preview  TEXT,
    session_id      TEXT
);

CREATE TABLE IF NOT EXISTS encrypted_notes (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    category        TEXT NOT NULL DEFAULT 'general',
    ciphertext_b64  TEXT NOT NULL,
    nonce_b64       TEXT NOT NULL,
    created_at_utc  TEXT NOT NULL,
    updated_at_utc  TEXT NOT NULL,
    is_locked       INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS budget_requests (
    id                   TEXT PRIMARY KEY,
    session_id           TEXT NOT NULL,
    department           TEXT NOT NULL,
    requested_amount_usd REAL NOT NULL,
    justification        TEXT,
    status               TEXT NOT NULL DEFAULT 'PENDING_APPROVAL',
    created_at_utc       TEXT NOT NULL,
    reviewed_at_utc      TEXT
);

CREATE TABLE IF NOT EXISTS session_history (
    session_id         TEXT PRIMARY KEY,
    user_input_preview TEXT NOT NULL,
    inference_route    TEXT,
    validation_status  TEXT,
    total_tokens       INTEGER DEFAULT 0,
    created_at_utc     TEXT NOT NULL,
    completed_at_utc   TEXT
);
"""


def init_db() -> None:
    """Create all tables and seed demo data if the DB is empty."""
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)

    _seed_scheduler_if_empty()
    _seed_notes_if_empty()
    logger.info("AegisFlow SQLite database initialized at %s", DB_PATH)


def _seed_scheduler_if_empty() -> None:
    """Insert default scheduler jobs if table is empty."""
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM scheduler_jobs").fetchone()[0]
        if count > 0:
            return

        now = datetime.now(timezone.utc).isoformat()
        jobs = [
            ("job-001", "Daily Audit Digest",   "0 9 * * 1-5", "aegisflow.run('generate daily audit summary')", "active", now, None, "Mon-Fri 09:00", 0),
            ("job-002", "DB Health Check",       "*/15 * * * *","aegisflow.run('check database connectivity and latency')", "active", now, None, "Every 15 min", 0),
            ("job-003", "Weekly Report Gen",     "0 18 * * 5",  "aegisflow.run('compile weekly performance report')", "paused", now, None, "Fri 18:00", 0),
            ("job-004", "Token Budget Reset",    "0 0 1 * *",   "aegisflow.run('reset monthly token budget counters')", "active", now, None, "1st of month", 0),
        ]
        conn.executemany(
            "INSERT INTO scheduler_jobs VALUES (?,?,?,?,?,?,?,?,?)", jobs
        )


def _seed_notes_if_empty() -> None:
    """Insert placeholder encrypted notes metadata if table is empty."""
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM encrypted_notes").fetchone()[0]
        if count > 0:
            return

        now = datetime.now(timezone.utc).isoformat()
        # Placeholder entries — real content is encrypted on first write
        notes = [
            ("note-001", "API Key Inventory",    "security",  "PLACEHOLDER", "PLACEHOLDER", now, now, 1),
            ("note-002", "Operator Playbook",    "ops",       "PLACEHOLDER", "PLACEHOLDER", now, now, 1),
            ("note-003", "Incident Runbooks",    "ops",       "PLACEHOLDER", "PLACEHOLDER", now, now, 1),
            ("note-004", "Governance Policies",  "compliance","PLACEHOLDER", "PLACEHOLDER", now, now, 1),
        ]
        conn.executemany(
            "INSERT INTO encrypted_notes VALUES (?,?,?,?,?,?,?,?)", notes
        )


# ---------------------------------------------------------------------------
# Scheduler CRUD
# ---------------------------------------------------------------------------

def get_all_jobs() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduler_jobs ORDER BY created_at_utc DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_job_by_id(job_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM scheduler_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None


def create_job(
    job_id: str,
    name: str,
    cron_expression: str,
    task_command: str,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO scheduler_jobs (id, name, cron_expression, task_command,
               status, created_at_utc, next_run_label)
               VALUES (?, ?, ?, ?, 'active', ?, 'Calculating...')""",
            (job_id, name, cron_expression, task_command, now),
        )
    return get_job_by_id(job_id)


def update_job_status(job_id: str, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE scheduler_jobs SET status = ? WHERE id = ?", (status, job_id)
        )


def record_job_run(
    job_id: str,
    run_id: str,
    session_id: Optional[str] = None,
    output_preview: Optional[str] = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO scheduler_runs (id, job_id, started_at_utc, status, output_preview, session_id)
               VALUES (?, ?, ?, 'running', ?, ?)""",
            (run_id, job_id, now, output_preview, session_id),
        )
        conn.execute(
            "UPDATE scheduler_jobs SET last_run_utc = ?, run_count = run_count + 1 WHERE id = ?",
            (now, job_id),
        )


# ---------------------------------------------------------------------------
# Notes CRUD (metadata only — ciphertext stored as base64 blobs)
# ---------------------------------------------------------------------------

def get_all_note_metadata() -> List[Dict[str, Any]]:
    """Return note metadata WITHOUT the ciphertext or nonce."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, title, category, is_locked, created_at_utc, updated_at_utc
               FROM encrypted_notes ORDER BY updated_at_utc DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_note(
    note_id: str,
    title: str,
    category: str,
    ciphertext_b64: str,
    nonce_b64: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO encrypted_notes (id, title, category, ciphertext_b64, nonce_b64,
               created_at_utc, updated_at_utc)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 title = excluded.title,
                 ciphertext_b64 = excluded.ciphertext_b64,
                 nonce_b64 = excluded.nonce_b64,
                 updated_at_utc = excluded.updated_at_utc""",
            (note_id, title, category, ciphertext_b64, nonce_b64, now, now),
        )


def get_note_full(note_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM encrypted_notes WHERE id = ?", (note_id,)
        ).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Budget requests
# ---------------------------------------------------------------------------

def create_budget_request(
    request_id: str,
    session_id: str,
    department: str,
    amount_usd: float,
    justification: str,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO budget_requests (id, session_id, department,
               requested_amount_usd, justification, status, created_at_utc)
               VALUES (?, ?, ?, ?, ?, 'PENDING_APPROVAL', ?)""",
            (request_id, session_id, department, amount_usd, justification, now),
        )
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM budget_requests WHERE id = ?", (request_id,)
        ).fetchone()
        return dict(row)


# ---------------------------------------------------------------------------
# Session history
# ---------------------------------------------------------------------------

def record_session(
    session_id: str,
    user_input_preview: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO session_history
               (session_id, user_input_preview, created_at_utc)
               VALUES (?, ?, ?)""",
            (session_id, user_input_preview, now),
        )


def update_session_complete(
    session_id: str,
    inference_route: Optional[str],
    validation_status: Optional[str],
    total_tokens: int,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """UPDATE session_history SET
               inference_route = ?, validation_status = ?,
               total_tokens = ?, completed_at_utc = ?
               WHERE session_id = ?""",
            (inference_route, validation_status, total_tokens, now, session_id),
        )


def get_session_history(limit: int = 50) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM session_history ORDER BY created_at_utc DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
