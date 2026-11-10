"""The records the store persists (build step 3).

These are plain frozen dataclasses with JSON-friendly fields, so the
SQLite store and the in-memory store hold exactly the same values and
the contract tests can compare them directly. All timestamps are ISO
8601 strings in UTC; the business-local date and time of an
appointment live in :class:`Appointment.start`, which is the
business-local naive datetime in ISO form (the pack carries the
business timezone, and the calendar works in local time).

A :class:`Lead` carries the qualification state as the plain ``state``
dict (the :class:`first60.pipeline.qualify.ConversationState` as
``dataclasses.asdict``), plus the denormalised ``stage``,
``score_total`` and ``score_band`` the daily summary reads. The store
never interprets the state dict; the pipeline owns its shape.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from first60.pipeline.stages import Stage

__all__ = [
    "Appointment",
    "AuditRow",
    "FollowUp",
    "Lead",
    "Message",
    "new_appointment",
    "new_audit_row",
    "new_followup",
    "new_lead",
    "new_message",
]


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    """Return a fresh record id (32 hex chars, no dashes)."""
    return uuid.uuid4().hex


@dataclass(frozen=True)
class Lead:
    """One person who contacted the business."""

    id: str
    name: str = ""
    email: str = ""
    phone: str = ""
    channel: str = ""
    stage: Stage = Stage.NEW
    score_total: int = 0
    score_band: str = "LOW"
    score_components: dict[str, int] = field(default_factory=dict)
    answers: dict[str, str] = field(default_factory=dict)
    service: str | None = None
    urgency: str = "unknown"
    state: dict[str, object] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class Message:
    """One message in a lead's conversation, inbound or outbound."""

    id: str
    lead_id: str
    direction: str  # "in" | "out"
    text: str
    created_at: str = ""


@dataclass(frozen=True)
class Appointment:
    """One booked appointment."""

    id: str
    lead_id: str
    service: str
    start: str  # business-local naive datetime, ISO 8601
    duration_minutes: int
    idempotency_key: str
    status: str = "booked"  # "booked" | "cancelled"
    created_at: str = ""


@dataclass(frozen=True)
class FollowUp:
    """One scheduled follow-up touch for a lead."""

    id: str
    lead_id: str
    touch_index: int
    due_at: str  # UTC ISO 8601
    status: str = "scheduled"  # "scheduled" | "sent" | "suppressed" | "cancelled"
    reason: str = ""
    created_at: str = ""


@dataclass(frozen=True)
class AuditRow:
    """One append-only audit row for a side effect.

    ``mode`` is the write mode the side effect ran under
    (``direct`` / ``dry_run`` / ``approval`` / ``demo``); ``action``
    names the side effect (``reply_sent``, ``stage_move``,
    ``booking`` and so on). ``lead_id`` is empty for business-wide
    rows.
    """

    id: str
    lead_id: str
    action: str
    mode: str
    detail: str
    created_at: str = ""


def new_lead(
    *,
    name: str = "",
    email: str = "",
    phone: str = "",
    channel: str = "",
    lead_id: str | None = None,
    now: str | None = None,
) -> Lead:
    """Build a fresh lead in stage NEW with a generated id."""
    stamp = now or _now_iso()
    return Lead(
        id=lead_id or _new_id(),
        name=name,
        email=email,
        phone=phone,
        channel=channel,
        created_at=stamp,
        updated_at=stamp,
    )


def new_message(
    *,
    lead_id: str,
    direction: str,
    text: str,
    message_id: str | None = None,
    now: str | None = None,
) -> Message:
    """Build a message for ``lead_id`` with a generated id."""
    return Message(
        id=message_id or _new_id(),
        lead_id=lead_id,
        direction=direction,
        text=text,
        created_at=now or _now_iso(),
    )


def new_appointment(
    *,
    lead_id: str,
    service: str,
    start: str,
    duration_minutes: int,
    idempotency_key: str,
    appointment_id: str | None = None,
    now: str | None = None,
) -> Appointment:
    """Build a booked appointment with a generated id."""
    return Appointment(
        id=appointment_id or _new_id(),
        lead_id=lead_id,
        service=service,
        start=start,
        duration_minutes=duration_minutes,
        idempotency_key=idempotency_key,
        created_at=now or _now_iso(),
    )


def new_followup(
    *,
    lead_id: str,
    touch_index: int,
    due_at: str,
    followup_id: str | None = None,
    now: str | None = None,
) -> FollowUp:
    """Build a scheduled follow-up touch with a generated id."""
    return FollowUp(
        id=followup_id or _new_id(),
        lead_id=lead_id,
        touch_index=touch_index,
        due_at=due_at,
        created_at=now or _now_iso(),
    )


def new_audit_row(
    *,
    lead_id: str,
    action: str,
    mode: str,
    detail: str,
    row_id: str | None = None,
    now: str | None = None,
) -> AuditRow:
    """Build an audit row with a generated id."""
    return AuditRow(
        id=row_id or _new_id(),
        lead_id=lead_id,
        action=action,
        mode=mode,
        detail=detail,
        created_at=now or _now_iso(),
    )
