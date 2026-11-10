"""Store contract tests (build step 3).

The same cases run against both implementations — the in-memory
store and the SQLite store — so a behaviour that differs between
them fails here. This is the parity set DESIGN.md section 11 asks
for (8 cases), plus the list/filter cases the summary and the
follow-up engine will need.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from first60.errors import (
    APPOINTMENT_NOT_FOUND,
    LEAD_ALREADY_EXISTS,
    LEAD_NOT_FOUND,
    STAGE_TRANSITION_INVALID,
    First60Error,
)
from first60.models import (
    new_appointment,
    new_audit_row,
    new_followup,
    new_lead,
    new_message,
)
from first60.pipeline.stages import Stage
from first60.store.base import Store
from first60.store.memory import MemoryStore
from first60.store.sqlite import SQLiteStore

NOW = "2026-11-10T08:00:00+00:00"


@pytest.fixture(params=["memory", "sqlite"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Store:
    """One store per implementation, fresh for each test."""
    if request.param == "memory":
        return MemoryStore()
    return SQLiteStore(str(tmp_path / "first60.db"))


def _lead(**overrides: object) -> object:
    """Build a lead with fixed ids and timestamps for assertions."""
    values: dict[str, object] = {
        "lead_id": "lead-1",
        "name": "Sara Ahmed",
        "email": "sara@example.com",
        "phone": "+44 7700 900123",
        "channel": "web",
        "now": NOW,
    }
    values.update(overrides)
    return new_lead(**values)  # type: ignore[arg-type]


def test_create_and_get_round_trip(store: Store) -> None:
    """A created lead reads back with every field intact."""
    lead = _lead()
    stored = store.create_lead(lead)  # type: ignore[arg-type]
    assert stored.email == "sara@example.com"
    assert stored.phone == "447700900123"  # normalised to digits
    fetched = store.get_lead("lead-1")
    assert fetched == stored
    assert fetched.stage is Stage.NEW
    assert fetched.score_total == 0
    assert fetched.score_band == "LOW"


def test_duplicate_create_raises(store: Store) -> None:
    """Creating the same lead id twice raises LEAD_ALREADY_EXISTS."""
    store.create_lead(_lead())  # type: ignore[arg-type]
    with pytest.raises(First60Error) as excinfo:
        store.create_lead(_lead())  # type: ignore[arg-type]
    assert excinfo.value.code == LEAD_ALREADY_EXISTS


def test_get_missing_lead_raises(store: Store) -> None:
    """Getting an unknown lead raises LEAD_NOT_FOUND."""
    with pytest.raises(First60Error) as excinfo:
        store.get_lead("no-such-lead")
    assert excinfo.value.code == LEAD_NOT_FOUND


def test_find_by_email_and_phone_with_formatting_variants(store: Store) -> None:
    """Dedupe lookups match formatting variants of the same contact."""
    store.create_lead(_lead())  # type: ignore[arg-type]
    assert store.find_lead_by_email("  SARA@Example.COM ") is not None
    assert store.find_lead_by_email("someone-else@example.com") is None
    assert store.find_lead_by_phone("07700 900123") is None  # trunk 0 differs
    assert store.find_lead_by_phone("+44-7700-900-123") is not None
    assert store.find_lead_by_phone("00447700900123") is not None
    assert store.find_lead_by_email("") is None
    assert store.find_lead_by_phone("") is None


def test_move_stage_legal_and_illegal(store: Store) -> None:
    """Legal moves persist; illegal moves raise and change nothing."""
    store.create_lead(_lead())  # type: ignore[arg-type]
    moved = store.move_stage("lead-1", Stage.CONTACTED)
    assert moved.stage is Stage.CONTACTED
    assert store.get_lead("lead-1").stage is Stage.CONTACTED
    with pytest.raises(First60Error) as excinfo:
        store.move_stage("lead-1", Stage.BOOKED)  # CONTACTED -> BOOKED skips a step
    assert excinfo.value.code == STAGE_TRANSITION_INVALID
    assert store.get_lead("lead-1").stage is Stage.CONTACTED
    same = store.move_stage("lead-1", Stage.CONTACTED)  # same-stage no-op
    assert same.stage is Stage.CONTACTED


def test_messages_in_insertion_order_per_lead(store: Store) -> None:
    """Messages list in the order they arrived, isolated per lead."""
    store.create_lead(_lead())  # type: ignore[arg-type]
    store.create_lead(_lead(lead_id="lead-2", email="omar@example.com"))  # type: ignore[arg-type]
    store.add_message(
        new_message(lead_id="lead-1", direction="in", text="hello", now=NOW)
    )
    store.add_message(
        new_message(lead_id="lead-1", direction="out", text="hi there", now=NOW)
    )
    store.add_message(
        new_message(lead_id="lead-2", direction="in", text="other lead", now=NOW)
    )
    store.add_message(
        new_message(lead_id="lead-1", direction="in", text="thanks", now=NOW)
    )
    texts = [item.text for item in store.list_messages("lead-1")]
    assert texts == ["hello", "hi there", "thanks"]
    assert [item.text for item in store.list_messages("lead-2")] == ["other lead"]
    assert store.list_messages("no-such-lead") == []
    with pytest.raises(First60Error) as excinfo:
        store.add_message(
            new_message(lead_id="ghost", direction="in", text="x", now=NOW)
        )
    assert excinfo.value.code == LEAD_NOT_FOUND


def test_appointment_save_get_find_and_cancel(store: Store) -> None:
    """Appointments round-trip, are findable by key, and cancel frees."""
    from datetime import date

    store.create_lead(_lead())  # type: ignore[arg-type]
    appointment = new_appointment(
        lead_id="lead-1",
        service="Check-up and clean",
        start="2026-11-10T09:00:00",
        duration_minutes=30,
        idempotency_key="lead-1:2026-11-10T09:00:00",
        appointment_id="appt-1",
        now=NOW,
    )
    store.save_appointment(appointment)
    assert store.get_appointment("appt-1") == appointment
    assert store.find_appointment_by_key("lead-1:2026-11-10T09:00:00") == appointment
    assert store.find_appointment_by_key("unknown-key") is None
    assert len(store.list_appointments(date(2026, 11, 10))) == 1
    assert store.list_appointments(date(2026, 11, 11)) == []
    cancelled = store.cancel_appointment("appt-1")
    assert cancelled.status == "cancelled"
    assert store.get_appointment("appt-1").status == "cancelled"
    assert store.cancel_appointment("appt-1").status == "cancelled"  # idempotent
    with pytest.raises(First60Error) as excinfo:
        store.get_appointment("no-such-appointment")
    assert excinfo.value.code == APPOINTMENT_NOT_FOUND


def test_followups_save_and_filter(store: Store) -> None:
    """Follow-ups save and filter by lead and by status."""
    store.create_lead(_lead())  # type: ignore[arg-type]
    first = new_followup(
        lead_id="lead-1", touch_index=1, due_at="2026-11-10T12:00:00+00:00", now=NOW
    )
    second = new_followup(
        lead_id="lead-1", touch_index=2, due_at="2026-11-11T08:00:00+00:00", now=NOW
    )
    store.save_followup(first)
    store.save_followup(second)
    assert [item.touch_index for item in store.list_followups(lead_id="lead-1")] == [
        1,
        2,
    ]
    assert len(store.list_followups(status="scheduled")) == 2
    # Saving under the same id replaces the row instead of duplicating it.
    from dataclasses import replace

    store.save_followup(replace(first, status="sent", reason="delivered"))
    assert len(store.list_followups(lead_id="lead-1")) == 2
    assert [item.status for item in store.list_followups(status="sent")] == ["sent"]
    assert store.list_followups(lead_id="lead-2") == []


def test_audit_append_and_filter(store: Store) -> None:
    """Audit rows append in order and filter per lead; never updated."""
    store.append_audit(
        new_audit_row(
            lead_id="lead-1",
            action="reply_sent",
            mode="demo",
            detail="first reply",
            now=NOW,
        )
    )
    store.append_audit(
        new_audit_row(
            lead_id="lead-1",
            action="stage_move",
            mode="demo",
            detail="NEW -> CONTACTED",
            now=NOW,
        )
    )
    store.append_audit(
        new_audit_row(
            lead_id="", action="summary", mode="demo", detail="daily summary", now=NOW
        )
    )
    assert [row.action for row in store.list_audit()] == [
        "reply_sent",
        "stage_move",
        "summary",
    ]
    assert [row.action for row in store.list_audit("lead-1")] == [
        "reply_sent",
        "stage_move",
    ]
    assert store.list_audit("lead-2") == []


def test_list_leads_by_stage(store: Store) -> None:
    """list_leads filters to one stage when asked."""
    store.create_lead(_lead())  # type: ignore[arg-type]
    store.create_lead(_lead(lead_id="lead-2", email="omar@example.com"))  # type: ignore[arg-type]
    store.move_stage("lead-2", Stage.CONTACTED)
    assert len(store.list_leads()) == 2
    assert [lead.id for lead in store.list_leads(Stage.NEW)] == ["lead-1"]
    assert [lead.id for lead in store.list_leads(Stage.CONTACTED)] == ["lead-2"]
    assert store.list_leads(Stage.BOOKED) == []


def test_update_lead_persists_score_and_state(store: Store) -> None:
    """Score components, answers and the conversation state round-trip."""
    from dataclasses import replace

    lead = _lead()  # type: ignore[arg-type]
    store.create_lead(lead)
    updated = replace(
        lead,
        score_total=82,
        score_band="HOT",
        score_components={"service_fit": 25, "urgency": 20},
        answers={"service": "Check-up and clean", "name": "Sara Ahmed"},
        service="Check-up and clean",
        urgency="today",
        state={"answers": {"service": "Check-up and clean"}, "replies": 2},
        updated_at="2026-11-10T09:00:00+00:00",
    )
    store.update_lead(updated)
    fetched = store.get_lead("lead-1")
    assert fetched.score_total == 82
    assert fetched.score_band == "HOT"
    assert fetched.score_components == {"service_fit": 25, "urgency": 20}
    assert fetched.answers == {"service": "Check-up and clean", "name": "Sara Ahmed"}
    assert fetched.state == {"answers": {"service": "Check-up and clean"}, "replies": 2}
    with pytest.raises(First60Error) as excinfo:
        store.update_lead(replace(lead, id="ghost"))
    assert excinfo.value.code == LEAD_NOT_FOUND
