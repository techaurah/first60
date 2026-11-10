"""Calendar and booking tests (build step 3).

Twelve cases per DESIGN.md section 11, on the dental pack
(BrightSmile Dental: Mon-Thu 09:00-17:30, Fri 09:00-17:00,
Sat 09:00-13:00, Sun closed, 30-minute slot grid). The clock is
injected, so "today" is fixed: Tuesday 2026-11-10 unless a test says
otherwise. 2026-11-10 is a Tuesday.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from first60.calendar.local import LocalCalendar
from first60.config import load_builtin_pack
from first60.errors import SLOT_UNAVAILABLE, First60Error
from first60.models import new_lead
from first60.store.memory import MemoryStore

TUESDAY = date(2026, 11, 10)
SUNDAY = date(2026, 11, 15)
MONDAY_NOON = datetime(2026, 11, 9, 12, 0)


@pytest.fixture
def calendar() -> LocalCalendar:
    """A calendar over a fresh memory store, clock fixed Monday noon."""
    store = MemoryStore()
    store.create_lead(
        new_lead(
            lead_id="lead-1",
            name="Sara Ahmed",
            email="sara@example.com",
            now="2026-11-09T12:00:00+00:00",
        )
    )
    store.create_lead(
        new_lead(
            lead_id="lead-2",
            name="Omar Khan",
            email="omar@example.com",
            now="2026-11-09T12:00:00+00:00",
        )
    )
    pack = load_builtin_pack("dental")
    return LocalCalendar(store, pack, clock=lambda: MONDAY_NOON)


def _book(
    calendar: LocalCalendar,
    lead_id: str = "lead-1",
    start: datetime = datetime(2026, 11, 10, 10, 0),
    duration: int = 30,
    key: str | None = None,
):
    """Book a slot with a deterministic idempotency key."""
    return calendar.book(
        lead_id,
        "Check-up and clean",
        start,
        duration,
        key or f"{lead_id}:{start.isoformat()}",
    )


def test_free_slots_open_day_grid(calendar: LocalCalendar) -> None:
    """An open day offers every 30-minute grid start that fits in hours."""
    slots = calendar.free_slots(TUESDAY, 30)
    assert len(slots) == 17  # 09:00 to 17:00 inclusive
    assert slots[0] == datetime(2026, 11, 10, 9, 0)
    assert slots[-1] == datetime(2026, 11, 10, 17, 0)


def test_free_slots_closed_day_is_empty(calendar: LocalCalendar) -> None:
    """Sunday is closed, so no slots are offered at all."""
    assert calendar.free_slots(SUNDAY, 30) == []


def test_free_slots_respect_duration(calendar: LocalCalendar) -> None:
    """A 60-minute service has fewer starts: the last one ends by close."""
    slots = calendar.free_slots(TUESDAY, 60)
    assert len(slots) == 16  # 09:00 to 16:30 inclusive
    assert slots[-1] == datetime(2026, 11, 10, 16, 30)
    assert len(calendar.free_slots(TUESDAY, 45)) == 16


def test_busy_appointment_blocks_overlapping_slots(calendar: LocalCalendar) -> None:
    """A booked 10:00-10:30 removes only the slots it overlaps."""
    _book(calendar, start=datetime(2026, 11, 10, 10, 0))
    slots = calendar.free_slots(TUESDAY, 30)
    assert datetime(2026, 11, 10, 10, 0) not in slots
    assert datetime(2026, 11, 10, 9, 30) in slots
    assert datetime(2026, 11, 10, 10, 30) in slots
    assert len(slots) == 16


def test_booking_is_visible_in_the_store(calendar: LocalCalendar) -> None:
    """A booking lands in the store as a booked appointment."""
    appointment = _book(calendar, start=datetime(2026, 11, 10, 11, 0))
    assert appointment.status == "booked"
    assert appointment.lead_id == "lead-1"
    assert appointment.start == "2026-11-10T11:00:00"
    stored = calendar._store.get_appointment(appointment.id)
    assert stored == appointment


def test_slot_taken_between_offer_and_confirm(calendar: LocalCalendar) -> None:
    """A slot free at offer time but taken since is refused at booking."""
    offered = calendar.free_slots(TUESDAY, 30)
    assert datetime(2026, 11, 10, 10, 0) in offered
    _book(calendar, lead_id="lead-2", start=datetime(2026, 11, 10, 10, 0))
    with pytest.raises(First60Error) as excinfo:
        _book(calendar, lead_id="lead-1", start=datetime(2026, 11, 10, 10, 0))
    assert excinfo.value.code == SLOT_UNAVAILABLE


def test_idempotent_rebook_returns_the_same_appointment(
    calendar: LocalCalendar,
) -> None:
    """Booking twice under one key returns the original, not a second."""
    first = _book(calendar, start=datetime(2026, 11, 10, 10, 0))
    again = _book(
        calendar,
        start=datetime(2026, 11, 10, 10, 0),
        key=f"lead-1:{datetime(2026, 11, 10, 10, 0).isoformat()}",
    )
    assert again.id == first.id
    assert len(calendar._store.list_appointments(TUESDAY)) == 1


def test_booking_outside_business_hours(calendar: LocalCalendar) -> None:
    """Before open, after close, and on a closed day are all refused."""
    for start in (
        datetime(2026, 11, 10, 8, 30),  # before open
        datetime(2026, 11, 10, 17, 30),  # ends after close
        datetime(2026, 11, 15, 10, 0),  # Sunday, closed
    ):
        with pytest.raises(First60Error) as excinfo:
            _book(calendar, start=start)
        assert excinfo.value.code == SLOT_UNAVAILABLE


def test_booking_in_the_past(calendar: LocalCalendar) -> None:
    """A slot before the injected clock is refused."""
    with pytest.raises(First60Error) as excinfo:
        _book(calendar, start=datetime(2026, 11, 9, 10, 0))
    assert excinfo.value.code == SLOT_UNAVAILABLE


def test_booking_off_the_grid(calendar: LocalCalendar) -> None:
    """A start that is not on the 30-minute grid is refused."""
    with pytest.raises(First60Error) as excinfo:
        _book(calendar, start=datetime(2026, 11, 10, 10, 15))
    assert excinfo.value.code == SLOT_UNAVAILABLE


def test_cancelled_appointment_frees_the_slot(calendar: LocalCalendar) -> None:
    """Cancelling returns the slot to the free list for another lead."""
    appointment = _book(calendar, start=datetime(2026, 11, 10, 10, 0))
    calendar._store.cancel_appointment(appointment.id)
    assert datetime(2026, 11, 10, 10, 0) in calendar.free_slots(TUESDAY, 30)
    booked = _book(
        calendar,
        lead_id="lead-2",
        start=datetime(2026, 11, 10, 10, 0),
    )
    assert booked.lead_id == "lead-2"


def test_free_slots_exclude_past_slots_today(calendar: LocalCalendar) -> None:
    """For today, slots at or before the clock are not offered."""
    pack = load_builtin_pack("dental")
    store = MemoryStore()
    morning = LocalCalendar(store, pack, clock=lambda: datetime(2026, 11, 10, 10, 0))
    slots = morning.free_slots(TUESDAY, 30)
    assert slots[0] == datetime(2026, 11, 10, 10, 30)
    assert len(slots) == 14  # 10:30 to 17:00 inclusive
