"""The store: one protocol, two implementations (build step 3).

SQLite is the durable store; the in-memory store is for the demo and
tests. Both satisfy :class:`first60.store.base.Store`, and the
contract tests run the same cases against both.
"""

from __future__ import annotations

from first60.store.base import Store
from first60.store.memory import MemoryStore
from first60.store.sqlite import SQLiteStore

__all__ = [
    "MemoryStore",
    "SQLiteStore",
    "Store",
]
