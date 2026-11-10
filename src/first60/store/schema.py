"""The SQLite schema for the store (build step 3).

Schema version 1. ``ensure_schema`` is idempotent: it creates the
tables and the ``meta`` row on first use and leaves an existing
database untouched, so reopening a store never loses data. Migrations
are a later step's problem; the version row exists so that step can
tell a v1 file from anything newer.

Datetimes are stored as ISO 8601 text. Dict fields
(``score_components``, ``answers``, ``state``) are stored as JSON
text, so the SQLite rows and the in-memory dicts hold the same values.
"""

from __future__ import annotations

import sqlite3

__all__ = [
    "SCHEMA_VERSION",
    "ensure_schema",
]

SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL DEFAULT '',
    stage TEXT NOT NULL,
    score_total INTEGER NOT NULL DEFAULT 0,
    score_band TEXT NOT NULL DEFAULT 'LOW',
    score_components TEXT NOT NULL DEFAULT '{}',
    answers TEXT NOT NULL DEFAULT '{}',
    service TEXT,
    urgency TEXT NOT NULL DEFAULT 'unknown',
    state TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads (email);
CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads (phone);
CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads (stage);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads (id),
    direction TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_lead ON messages (lead_id);

CREATE TABLE IF NOT EXISTS appointments (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads (id),
    service TEXT NOT NULL,
    start TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'booked',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_appointments_start ON appointments (start);

CREATE TABLE IF NOT EXISTS followups (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads (id),
    touch_index INTEGER NOT NULL,
    due_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_followups_lead ON followups (lead_id);
CREATE INDEX IF NOT EXISTS idx_followups_status ON followups (status);

CREATE TABLE IF NOT EXISTS audit (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    mode TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_lead ON audit (lead_id);
"""


def ensure_schema(connection: sqlite3.Connection) -> None:
    """Create the v1 tables and meta row if they do not exist yet."""
    connection.executescript(_DDL)
    connection.execute(
        "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    connection.commit()
