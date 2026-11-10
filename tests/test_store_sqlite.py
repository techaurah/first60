"""SQLite-only store tests (build step 3).

These cover what the in-memory store cannot: data survives closing
and reopening the file, and the schema version row exists for future
migrations.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from first60.models import new_lead
from first60.store.schema import SCHEMA_VERSION
from first60.store.sqlite import SQLiteStore


def test_sqlite_data_survives_reopen(tmp_path: Path) -> None:
    """A lead written, closed and reopened is still there."""
    path = str(tmp_path / "first60.db")
    store = SQLiteStore(path)
    store.create_lead(
        new_lead(
            lead_id="lead-1",
            name="Sara Ahmed",
            email="sara@example.com",
            now="2026-11-10T08:00:00+00:00",
        )
    )
    store.close()
    reopened = SQLiteStore(path)
    assert reopened.get_lead("lead-1").name == "Sara Ahmed"
    reopened.close()


def test_sqlite_schema_version_recorded(tmp_path: Path) -> None:
    """The meta table records the schema version on first use."""
    path = str(tmp_path / "first60.db")
    store = SQLiteStore(path)
    connection = sqlite3.connect(path)
    row = connection.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    assert row is not None
    assert int(row[0]) == SCHEMA_VERSION
    connection.close()
    store.close()
