"""SQLite-only store tests (build step 3).

These cover what the in-memory store cannot: data survives closing
and reopening the file, and the schema version row exists for future
migrations. The thread test covers the build step 5 server: one
store shared across request threads.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from first60.models import new_lead, new_message
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


def test_sqlite_store_is_thread_safe(tmp_path: Path) -> None:
    """Concurrent threads share one store without errors or lost rows.

    This is the build step 5 server shape: the threaded HTTP server
    calls the same store from many request threads. Before the lock
    this raised ``sqlite3.ProgrammingError`` (connection created in
    another thread).
    """
    path = str(tmp_path / "first60.db")
    store = SQLiteStore(path)
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            lead_id = f"lead-{index}"
            store.create_lead(
                new_lead(
                    lead_id=lead_id,
                    name=f"Lead {index}",
                    now="2026-11-10T08:00:00+00:00",
                )
            )
            for number in range(5):
                store.add_message(
                    new_message(
                        lead_id=lead_id,
                        direction="in" if number % 2 == 0 else "out",
                        text=f"message {number}",
                        now="2026-11-10T08:00:00+00:00",
                    )
                )
            assert len(store.list_messages(lead_id)) == 5
        except BaseException as exc:  # noqa: BLE001 - collected for the assert
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len(store.list_leads()) == 8
    store.close()
