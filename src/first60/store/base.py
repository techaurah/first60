"""The store protocol (build step 3).

One contract for both stores: the SQLite store (durable, the
production default) and the in-memory store (demo and tests). The
contract tests in ``tests/test_store_parity.py`` run the same cases
against both implementations, so a behaviour that differs between
them is a bug, not a dialect difference.

Design rules:

- The store is dumb persistence. It never decides anything: stage
  moves go through :func:`first60.pipeline.stages.transition`, so an
  illegal move raises ``STAGE_TRANSITION_INVALID`` here, and dedupe
  lookups normalise through the pipeline's helpers. The engine (build
  step 5) owns decisions; the store owns rows.
- ``create_lead`` with an id that already exists raises
  ``LEAD_ALREADY_EXISTS``; lookups for a missing id raise
  ``LEAD_NOT_FOUND``. Callers dedupe before creating (see
  :func:`first60.pipeline.stages.dedupe_key`).
- Lists come back in insertion order. Messages for a lead are
  therefore already in conversation order; no timestamp sort is
  applied.
- The store never invents ids or timestamps: factories in
  :mod:`first60.models` do that, so tests can pass explicit values.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from first60.errors import First60Error  # noqa: F401  (re-exported for callers)
from first60.models import Appointment, AuditRow, FollowUp, Lead, Message
from first60.pipeline.stages import Stage

__all__ = [
    "Store",
]


@runtime_checkable
class Store(Protocol):
    """Persistence for leads, messages, appointments, follow-ups, audit."""

    # -- leads -----------------------------------------------------
    def create_lead(self, lead: Lead) -> Lead:
        """Insert ``lead``; raises LEAD_ALREADY_EXISTS on a duplicate id."""
        ...

    def get_lead(self, lead_id: str) -> Lead:
        """Return the lead, or raise LEAD_NOT_FOUND."""
        ...

    def find_lead_by_email(self, email: str) -> Lead | None:
        """Return the lead with this email (case-insensitive), or None."""
        ...

    def find_lead_by_phone(self, phone: str) -> Lead | None:
        """Return the lead with this phone (digits only), or None."""
        ...

    def update_lead(self, lead: Lead) -> Lead:
        """Replace the stored lead; raises LEAD_NOT_FOUND when absent."""
        ...

    def move_stage(self, lead_id: str, target: Stage) -> Lead:
        """Move a lead through the transition map; illegal moves raise.

        A same-stage move is a no-op success and returns the lead
        unchanged. The move is persisted before returning.
        """
        ...

    def list_leads(self, stage: Stage | None = None) -> list[Lead]:
        """Return all leads, optionally filtered to one stage."""
        ...

    # -- messages --------------------------------------------------
    def add_message(self, message: Message) -> Message:
        """Append a message; the lead must already exist."""
        ...

    def list_messages(self, lead_id: str) -> list[Message]:
        """Return a lead's messages in insertion order."""
        ...

    # -- appointments ----------------------------------------------
    def save_appointment(self, appointment: Appointment) -> Appointment:
        """Insert or replace an appointment by id."""
        ...

    def get_appointment(self, appointment_id: str) -> Appointment:
        """Return the appointment, or raise APPOINTMENT_NOT_FOUND."""
        ...

    def find_appointment_by_key(self, idempotency_key: str) -> Appointment | None:
        """Return the appointment booked under this key, or None."""
        ...

    def cancel_appointment(self, appointment_id: str) -> Appointment:
        """Mark an appointment cancelled; the slot becomes free again."""
        ...

    def list_appointments(self, day: date | None = None) -> list[Appointment]:
        """Return appointments, optionally only those starting on ``day``."""
        ...

    # -- follow-ups -------------------------------------------------
    def save_followup(self, followup: FollowUp) -> FollowUp:
        """Insert or replace a follow-up by id."""
        ...

    def list_followups(
        self, lead_id: str | None = None, status: str | None = None
    ) -> list[FollowUp]:
        """Return follow-ups, optionally filtered by lead and status."""
        ...

    # -- audit ------------------------------------------------------
    def append_audit(self, row: AuditRow) -> AuditRow:
        """Append one audit row. Audit rows are never updated or deleted."""
        ...

    def list_audit(self, lead_id: str | None = None) -> list[AuditRow]:
        """Return audit rows, optionally only for one lead."""
        ...

    # -- lifecycle ---------------------------------------------------
    def close(self) -> None:
        """Release the store's resources (closes the SQLite connection)."""
        ...
