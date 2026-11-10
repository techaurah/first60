"""The in-memory store (build step 3).

The same contract as :class:`first60.store.sqlite.SQLiteStore`, held
in dicts: the demo and the tests run against it with no files. Every
record is deep-copied on the way in and on the way out, so callers
can never mutate stored state through a returned object — the same
guarantee the SQLite store gives by rebuilding dataclasses from rows.
"""

from __future__ import annotations

import copy
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

__all__ = [
    "MemoryStore",
]


def _normalised_lead(lead: Lead) -> Lead:
    """Return ``lead`` with email/phone in their dedupe (normalised) form."""
    email = normalize_email(lead.email) or ""
    phone = normalize_phone(lead.phone) or ""
    if email == lead.email and phone == lead.phone:
        return copy.deepcopy(lead)
    return Lead(
        id=lead.id,
        name=lead.name,
        email=email,
        phone=phone,
        channel=lead.channel,
        stage=lead.stage,
        score_total=lead.score_total,
        score_band=lead.score_band,
        score_components=copy.deepcopy(lead.score_components),
        answers=copy.deepcopy(lead.answers),
        service=lead.service,
        urgency=lead.urgency,
        state=copy.deepcopy(lead.state),
        created_at=lead.created_at,
        updated_at=lead.updated_at,
    )


class MemoryStore:
    """A :class:`first60.store.base.Store` held in memory."""

    def __init__(self) -> None:
        self._leads: dict[str, Lead] = {}
        self._messages: dict[str, list[Message]] = {}
        self._appointments: dict[str, Appointment] = {}
        self._followups: dict[str, FollowUp] = {}
        self._audit: list[AuditRow] = []

    # -- leads -----------------------------------------------------
    def create_lead(self, lead: Lead) -> Lead:
        if lead.id in self._leads:
            raise First60Error(LEAD_ALREADY_EXISTS, f"lead {lead.id!r} already exists")
        stored = _normalised_lead(lead)
        self._leads[stored.id] = stored
        self._messages.setdefault(stored.id, [])
        return copy.deepcopy(stored)

    def get_lead(self, lead_id: str) -> Lead:
        lead = self._leads.get(lead_id)
        if lead is None:
            raise First60Error(LEAD_NOT_FOUND, f"no lead with id {lead_id!r}")
        return copy.deepcopy(lead)

    def find_lead_by_email(self, email: str) -> Lead | None:
        cleaned = normalize_email(email)
        if cleaned is None:
            return None
        for lead in self._leads.values():
            if lead.email == cleaned:
                return copy.deepcopy(lead)
        return None

    def find_lead_by_phone(self, phone: str) -> Lead | None:
        cleaned = normalize_phone(phone)
        if cleaned is None:
            return None
        for lead in self._leads.values():
            if lead.phone == cleaned:
                return copy.deepcopy(lead)
        return None

    def update_lead(self, lead: Lead) -> Lead:
        if lead.id not in self._leads:
            raise First60Error(LEAD_NOT_FOUND, f"no lead with id {lead.id!r}")
        stored = _normalised_lead(lead)
        self._leads[stored.id] = stored
        return copy.deepcopy(stored)

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
        leads = list(self._leads.values())
        if stage is not None:
            leads = [lead for lead in leads if lead.stage == stage]
        return copy.deepcopy(leads)

    # -- messages --------------------------------------------------
    def add_message(self, message: Message) -> Message:
        self.get_lead(message.lead_id)
        stored = copy.deepcopy(message)
        self._messages.setdefault(stored.lead_id, []).append(stored)
        return copy.deepcopy(stored)

    def list_messages(self, lead_id: str) -> list[Message]:
        return copy.deepcopy(self._messages.get(lead_id, []))

    # -- appointments ----------------------------------------------
    def save_appointment(self, appointment: Appointment) -> Appointment:
        stored = copy.deepcopy(appointment)
        self._appointments[stored.id] = stored
        return copy.deepcopy(stored)

    def get_appointment(self, appointment_id: str) -> Appointment:
        appointment = self._appointments.get(appointment_id)
        if appointment is None:
            raise First60Error(
                APPOINTMENT_NOT_FOUND,
                f"no appointment with id {appointment_id!r}",
            )
        return copy.deepcopy(appointment)

    def find_appointment_by_key(self, idempotency_key: str) -> Appointment | None:
        for appointment in self._appointments.values():
            if appointment.idempotency_key == idempotency_key:
                return copy.deepcopy(appointment)
        return None

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
        appointments = sorted(self._appointments.values(), key=lambda item: item.start)
        if day is None:
            return copy.deepcopy(appointments)
        return [
            item
            for item in copy.deepcopy(appointments)
            if item.start[:10] == day.isoformat()
        ]

    # -- follow-ups -------------------------------------------------
    def save_followup(self, followup: FollowUp) -> FollowUp:
        stored = copy.deepcopy(followup)
        self._followups[stored.id] = stored
        return copy.deepcopy(stored)

    def list_followups(
        self, lead_id: str | None = None, status: str | None = None
    ) -> list[FollowUp]:
        followups = sorted(
            self._followups.values(), key=lambda item: (item.due_at, item.id)
        )
        if lead_id is not None:
            followups = [item for item in followups if item.lead_id == lead_id]
        if status is not None:
            followups = [item for item in followups if item.status == status]
        return copy.deepcopy(followups)

    # -- audit ------------------------------------------------------
    def append_audit(self, row: AuditRow) -> AuditRow:
        stored = copy.deepcopy(row)
        self._audit.append(stored)
        return copy.deepcopy(stored)

    def list_audit(self, lead_id: str | None = None) -> list[AuditRow]:
        rows = self._audit
        if lead_id is not None:
            rows = [row for row in rows if row.lead_id == lead_id]
        return copy.deepcopy(rows)

    # -- lifecycle ---------------------------------------------------
    def close(self) -> None:
        """No-op: there is nothing to release."""
