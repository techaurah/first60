"""The local calendar (build step 3).

Availability comes from the business pack's hours, minus the busy
blocks already in the store (booked appointments). A booking is
checked twice: once when the slot is offered (``free_slots``) and
again at booking time (``book``), so a slot taken between offer and
confirm is refused with ``SLOT_UNAVAILABLE`` instead of double-booked.

Design choices, documented because the design leaves the details open:

- Slots start on the pack's slot grid (``slot_minutes``, 30 by
  default) counted from opening time, and a slot must end by closing
  time: a 60-minute service on a 09:00-17:30 day has its last start
  at 16:30, never 17:00.
- The clock is injected (DESIGN.md rule 2): production passes the
  system clock, tests pass a fixed time. "Past" is judged against
  that clock, so a slot is only ever offered in the future. The
  clock may return an aware UTC datetime (the engine's clock) or a
  naive business-local one; an aware value is converted to
  business-local time before comparison, so one clock can serve
  both the engine and the calendar.
- Idempotency is keyed by the caller's ``idempotency_key`` (the
  recommended construction is ``f"{lead_id}:{start.isoformat()}"``).
  A second ``book`` under the same key returns the original
  appointment, even if the caller now asks for a different start:
  the key identifies the booking request, and re-booking the same
  request must never create a second appointment.
- Busy means a stored appointment with status ``booked``. A
  cancelled appointment frees its slot again.
- The calendar stores appointments through the store protocol, so
  the same booking logic works over SQLite and memory stores.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from first60.calendar.base import Calendar  # noqa: F401  (re-exported for callers)
from first60.config import BusinessPack
from first60.errors import SLOT_UNAVAILABLE, First60Error
from first60.models import Appointment, new_appointment
from first60.store.base import Store

__all__ = [
    "Calendar",
    "LocalCalendar",
]


def _parse_time(value: str) -> time:
    """Parse a pack ``HH:MM`` time string."""
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


class LocalCalendar:
    """Business-hours availability plus idempotent booking."""

    def __init__(
        self,
        store: Store,
        pack: BusinessPack,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._pack = pack
        self._clock = clock or datetime.now

    def _now_local(self) -> datetime:
        """Return the clock time as a naive business-local datetime.

        The calendar works in naive business-local time; an aware
        clock value (the engine's UTC clock) is converted through
        the pack timezone first, so one clock serves both.
        """
        now = self._clock()
        if now.tzinfo is None:
            return now
        try:
            zone = ZoneInfo(self._pack.timezone)
        except ZoneInfoNotFoundError:
            zone = ZoneInfo("UTC")
        return now.astimezone(zone).replace(tzinfo=None)

    def free_slots(self, day: date, duration_minutes: int) -> list[datetime]:
        """Return the free slot starts on ``day`` for this duration."""
        hours = self._pack.hours.get(day.strftime("%A").lower())
        if hours is None:
            return []
        open_time, close_time = _parse_time(hours[0]), _parse_time(hours[1])
        day_start = datetime.combine(day, open_time)
        day_end = datetime.combine(day, close_time)
        step = timedelta(minutes=self._pack.slot_minutes)
        duration = timedelta(minutes=duration_minutes)
        now = self._now_local()
        busy = self._busy_blocks(day)
        slots: list[datetime] = []
        start = day_start
        while start + duration <= day_end:
            if start > now and not _overlaps(start, start + duration, busy):
                slots.append(start)
            start += step
        return slots

    def book(
        self,
        lead_id: str,
        service: str,
        start: datetime,
        duration_minutes: int,
        idempotency_key: str,
    ) -> Appointment:
        """Book a slot, or raise SLOT_UNAVAILABLE."""
        existing = self._store.find_appointment_by_key(idempotency_key)
        if existing is not None:
            return existing
        # The lead must exist: a booking belongs to a real conversation.
        self._store.get_lead(lead_id)
        end = start + timedelta(minutes=duration_minutes)
        if start <= self._now_local():
            raise First60Error(
                SLOT_UNAVAILABLE, f"slot {start.isoformat()} is in the past"
            )
        hours = self._pack.hours.get(start.strftime("%A").lower())
        if hours is None:
            raise First60Error(
                SLOT_UNAVAILABLE,
                f"the business is closed on {start.date().isoformat()}",
            )
        open_time, close_time = _parse_time(hours[0]), _parse_time(hours[1])
        if start.time() < open_time or end.time() > close_time:
            raise First60Error(
                SLOT_UNAVAILABLE,
                f"slot {start.isoformat()} is outside business hours",
            )
        if (
            start.minute % self._pack.slot_minutes != 0
            or start.second != 0
            or start.microsecond != 0
        ):
            raise First60Error(
                SLOT_UNAVAILABLE,
                f"slot {start.isoformat()} is not on the booking grid",
            )
        if _overlaps(start, end, self._busy_blocks(start.date())):
            raise First60Error(
                SLOT_UNAVAILABLE, f"slot {start.isoformat()} is already taken"
            )
        appointment = new_appointment(
            lead_id=lead_id,
            service=service,
            start=start.isoformat(),
            duration_minutes=duration_minutes,
            idempotency_key=idempotency_key,
        )
        return self._store.save_appointment(appointment)

    def _busy_blocks(self, day: date) -> list[tuple[datetime, datetime]]:
        """Return the booked (start, end) blocks on ``day``."""
        blocks: list[tuple[datetime, datetime]] = []
        for appointment in self._store.list_appointments(day):
            if appointment.status != "booked":
                continue
            start = datetime.fromisoformat(appointment.start)
            end = start + timedelta(minutes=appointment.duration_minutes)
            blocks.append((start, end))
        return blocks


def _overlaps(
    start: datetime,
    end: datetime,
    blocks: list[tuple[datetime, datetime]],
) -> bool:
    """Return True when [start, end) overlaps any busy block."""
    return any(
        start < block_end and block_start < end for block_start, block_end in blocks
    )
