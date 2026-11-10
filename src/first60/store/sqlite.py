"""The durable SQLite store (build step 3).

One SQLite file, stdlib ``sqlite3`` only. Rows map one-to-one onto the
dataclasses in :mod:`first60.models`; dict fields travel as JSON text
and come back as dicts, so a lead read from SQLite equals the lead
that was written. ``path`` may be a file path or ``":memory:"`` for a
throwaway database (the contract tests use a real temp file; the
in-memory store is the separate :mod:`first60.store.memory` class).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date

from first60.errors import (
    APPOINTMENT_NOT_FOUND,
    LEAD_ALREADY_EXISTS,
    LEAD_NOT_FOUND,
    STAGE_TRANSITION_INVALID,
    First60Error,
)
from first60.models import Appointment, AuditRow, FollowUp, Lead, Message
from first60.pipeline.stages import (
    Stage,
    StageTransitionError,
    normalize_email,
    normalize_phone,
    transition,
)
from first60.store.schema import ensure_schema

__all__ = [
    "SQLiteStore",
]


def _normalised_lead(lead: Lead) -> Lead:
    """Return ``lead`` with email/phone in their dedupe (normalised) form."""
    email = normalize_email(lead.email) or ""
    phone = normalize_phone(lead.phone) or ""
    if email == lead.email and phone == lead.phone:
        return lead
    return Lead(
        id=lead.id,
        name=lead.name,
        email=email,
        phone=phone,
        channel=lead.channel,
        stage=lead.stage,
        score_total=lead.score_total,
        score_band=lead.score_band,
        score_components=lead.score_components,
        answers=lead.answers,
        service=lead.service,
        urgency=lead.urgency,
        state=lead.state,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
    )


def _lead_from_row(row: sqlite3.Row) -> Lead:
    """Rebuild a Lead from a SQLite row."""
    return Lead(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        phone=row["phone"],
        channel=row["channel"],
        stage=Stage(row["stage"]),
        score_total=row["score_total"],
        score_band=row["score_band"],
        score_components=json.loads(row["score_components"]),
        answers=json.loads(row["answers"]),
        service=row["service"],
        urgency=row["urgency"],
        state=json.loads(row["state"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _appointment_from_row(row: sqlite3.Row) -> Appointment:
    """Rebuild an Appointment from a SQLite row."""
    return Appointment(
        id=row["id"],
        lead_id=row["lead_id"],
        service=row["service"],
        start=row["start"],
        duration_minutes=row["duration_minutes"],
        idempotency_key=row["idempotency_key"],
        status=row["status"],
        created_at=row["created_at"],
    )


def _followup_from_row(row: sqlite3.Row) -> FollowUp:
    """Rebuild a FollowUp from a SQLite row."""
    return FollowUp(
        id=row["id"],
        lead_id=row["lead_id"],
        touch_index=row["touch_index"],
        due_at=row["due_at"],
        status=row["status"],
        reason=row["reason"],
        created_at=row["created_at"],
    )


def _audit_from_row(row: sqlite3.Row) -> AuditRow:
    """Rebuild an AuditRow from a SQLite row."""
    return AuditRow(
        id=row["id"],
        lead_id=row["lead_id"],
        action=row["action"],
        mode=row["mode"],
        detail=row["detail"],
        created_at=row["created_at"],
    )


class SQLiteStore:
    """A :class:`first60.store.base.Store` backed by one SQLite file."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        ensure_schema(self._connection)

    # -- leads -----------------------------------------------------
    def create_lead(self, lead: Lead) -> Lead:
        # Email and phone are stored in their normalised (dedupe) form
        # so lookups match whatever formatting the caller used.
        stored = _normalised_lead(lead)
        try:
            self._connection.execute(
                """
                INSERT INTO leads (id, name, email, phone, channel, stage,
                    score_total, score_band, score_components, answers,
                    service, urgency, state, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stored.id,
                    stored.name,
                    stored.email,
                    stored.phone,
                    stored.channel,
                    stored.stage.value,
                    stored.score_total,
                    stored.score_band,
                    json.dumps(stored.score_components),
                    json.dumps(stored.answers),
                    stored.service,
                    stored.urgency,
                    json.dumps(stored.state),
                    stored.created_at,
                    stored.updated_at,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise First60Error(
                LEAD_ALREADY_EXISTS, f"lead {lead.id!r} already exists"
            ) from exc
        self._connection.commit()
        return stored

    def get_lead(self, lead_id: str) -> Lead:
        row = self._connection.execute(
            "SELECT * FROM leads WHERE id = ?", (lead_id,)
        ).fetchone()
        if row is None:
            raise First60Error(LEAD_NOT_FOUND, f"no lead with id {lead_id!r}")
        return _lead_from_row(row)

    def find_lead_by_email(self, email: str) -> Lead | None:
        cleaned = normalize_email(email)
        if cleaned is None:
            return None
        row = self._connection.execute(
            "SELECT * FROM leads WHERE email = ? ORDER BY rowid LIMIT 1",
            (cleaned,),
        ).fetchone()
        return _lead_from_row(row) if row is not None else None

    def find_lead_by_phone(self, phone: str) -> Lead | None:
        cleaned = normalize_phone(phone)
        if cleaned is None:
            return None
        row = self._connection.execute(
            "SELECT * FROM leads WHERE phone = ? ORDER BY rowid LIMIT 1",
            (cleaned,),
        ).fetchone()
        return _lead_from_row(row) if row is not None else None

    def update_lead(self, lead: Lead) -> Lead:
        stored = _normalised_lead(lead)
        cursor = self._connection.execute(
            """
            UPDATE leads SET name = ?, email = ?, phone = ?, channel = ?,
                stage = ?, score_total = ?, score_band = ?,
                score_components = ?, answers = ?, service = ?,
                urgency = ?, state = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                stored.name,
                stored.email,
                stored.phone,
                stored.channel,
                stored.stage.value,
                stored.score_total,
                stored.score_band,
                json.dumps(stored.score_components),
                json.dumps(stored.answers),
                stored.service,
                stored.urgency,
                json.dumps(stored.state),
                stored.updated_at,
                stored.id,
            ),
        )
        if cursor.rowcount == 0:
            raise First60Error(LEAD_NOT_FOUND, f"no lead with id {lead.id!r}")
        self._connection.commit()
        return stored

    def move_stage(self, lead_id: str, target: Stage) -> Lead:
        lead = self.get_lead(lead_id)
        try:
            new_stage = transition(lead.stage, target)
        except StageTransitionError as exc:
            raise First60Error(
                STAGE_TRANSITION_INVALID,
                f"illegal stage transition {lead.stage.value} -> {target.value}",
            ) from exc
        if new_stage == lead.stage:
            return lead
        moved = Lead(
            id=lead.id,
            name=lead.name,
            email=lead.email,
            phone=lead.phone,
            channel=lead.channel,
            stage=new_stage,
            score_total=lead.score_total,
            score_band=lead.score_band,
            score_components=lead.score_components,
            answers=lead.answers,
            service=lead.service,
            urgency=lead.urgency,
            state=lead.state,
            created_at=lead.created_at,
            updated_at=lead.updated_at,
        )
        return self.update_lead(moved)

    def list_leads(self, stage: Stage | None = None) -> list[Lead]:
        if stage is None:
            rows = self._connection.execute(
                "SELECT * FROM leads ORDER BY rowid"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM leads WHERE stage = ? ORDER BY rowid",
                (stage.value,),
            ).fetchall()
        return [_lead_from_row(row) for row in rows]

    # -- messages --------------------------------------------------
    def add_message(self, message: Message) -> Message:
        self.get_lead(message.lead_id)
        self._connection.execute(
            """
            INSERT INTO messages (id, lead_id, direction, text, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                message.id,
                message.lead_id,
                message.direction,
                message.text,
                message.created_at,
            ),
        )
        self._connection.commit()
        return message

    def list_messages(self, lead_id: str) -> list[Message]:
        rows = self._connection.execute(
            "SELECT * FROM messages WHERE lead_id = ? ORDER BY rowid",
            (lead_id,),
        ).fetchall()
        return [
            Message(
                id=row["id"],
                lead_id=row["lead_id"],
                direction=row["direction"],
                text=row["text"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    # -- appointments ----------------------------------------------
    def save_appointment(self, appointment: Appointment) -> Appointment:
        self._connection.execute(
            """
            INSERT INTO appointments (id, lead_id, service, start,
                duration_minutes, idempotency_key, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                lead_id = excluded.lead_id,
                service = excluded.service,
                start = excluded.start,
                duration_minutes = excluded.duration_minutes,
                idempotency_key = excluded.idempotency_key,
                status = excluded.status,
                created_at = excluded.created_at
            """,
            (
                appointment.id,
                appointment.lead_id,
                appointment.service,
                appointment.start,
                appointment.duration_minutes,
                appointment.idempotency_key,
                appointment.status,
                appointment.created_at,
            ),
        )
        self._connection.commit()
        return appointment

    def get_appointment(self, appointment_id: str) -> Appointment:
        row = self._connection.execute(
            "SELECT * FROM appointments WHERE id = ?", (appointment_id,)
        ).fetchone()
        if row is None:
            raise First60Error(
                APPOINTMENT_NOT_FOUND, f"no appointment with id {appointment_id!r}"
            )
        return _appointment_from_row(row)

    def find_appointment_by_key(self, idempotency_key: str) -> Appointment | None:
        row = self._connection.execute(
            "SELECT * FROM appointments WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return _appointment_from_row(row) if row is not None else None

    def cancel_appointment(self, appointment_id: str) -> Appointment:
        appointment = self.get_appointment(appointment_id)
        if appointment.status == "cancelled":
            return appointment
        cancelled = Appointment(
            id=appointment.id,
            lead_id=appointment.lead_id,
            service=appointment.service,
            start=appointment.start,
            duration_minutes=appointment.duration_minutes,
            idempotency_key=appointment.idempotency_key,
            status="cancelled",
            created_at=appointment.created_at,
        )
        return self.save_appointment(cancelled)

    def list_appointments(self, day: date | None = None) -> list[Appointment]:
        rows = self._connection.execute(
            "SELECT * FROM appointments ORDER BY start, rowid"
        ).fetchall()
        appointments = [_appointment_from_row(row) for row in rows]
        if day is None:
            return appointments
        return [item for item in appointments if item.start[:10] == day.isoformat()]

    # -- follow-ups -------------------------------------------------
    def save_followup(self, followup: FollowUp) -> FollowUp:
        self._connection.execute(
            """
            INSERT INTO followups (id, lead_id, touch_index, due_at,
                status, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                lead_id = excluded.lead_id,
                touch_index = excluded.touch_index,
                due_at = excluded.due_at,
                status = excluded.status,
                reason = excluded.reason,
                created_at = excluded.created_at
            """,
            (
                followup.id,
                followup.lead_id,
                followup.touch_index,
                followup.due_at,
                followup.status,
                followup.reason,
                followup.created_at,
            ),
        )
        self._connection.commit()
        return followup

    def list_followups(
        self, lead_id: str | None = None, status: str | None = None
    ) -> list[FollowUp]:
        query = "SELECT * FROM followups"
        clauses: list[str] = []
        params: list[str] = []
        if lead_id is not None:
            clauses.append("lead_id = ?")
            params.append(lead_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY due_at, rowid"
        rows = self._connection.execute(query, params).fetchall()
        return [_followup_from_row(row) for row in rows]

    # -- audit ------------------------------------------------------
    def append_audit(self, row: AuditRow) -> AuditRow:
        self._connection.execute(
            """
            INSERT INTO audit (id, lead_id, action, mode, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (row.id, row.lead_id, row.action, row.mode, row.detail, row.created_at),
        )
        self._connection.commit()
        return row

    def list_audit(self, lead_id: str | None = None) -> list[AuditRow]:
        if lead_id is None:
            rows = self._connection.execute(
                "SELECT * FROM audit ORDER BY rowid"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM audit WHERE lead_id = ? ORDER BY rowid",
                (lead_id,),
            ).fetchall()
        return [_audit_from_row(row) for row in rows]

    # -- lifecycle ---------------------------------------------------
    def close(self) -> None:
        """Close the SQLite connection."""
        self._connection.close()
