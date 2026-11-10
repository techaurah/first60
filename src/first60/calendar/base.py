"""The calendar protocol (build step 3).

One contract for availability and booking. The local calendar is the
v0 implementation; a Google Calendar adapter (a v0.2 candidate) drops
in behind this same protocol. Slots are business-local naive
datetimes: the pack carries the business timezone and the calendar
works in local time, so a slot offered at 09:00 is 09:00 on the wall
clock, not a UTC conversion.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol, runtime_checkable

from first60.models import Appointment

__all__ = [
    "Calendar",
]


@runtime_checkable
class Calendar(Protocol):
    """Availability and idempotent booking for one business."""

    def free_slots(self, day: date, duration_minutes: int) -> list[datetime]:
        """Return the free slot starts on ``day`` for this duration.

        Slots start on the pack's slot grid and must fit entirely
        inside business hours. Past slots are excluded for today.
        """
        ...

    def book(
        self,
        lead_id: str,
        service: str,
        start: datetime,
        duration_minutes: int,
        idempotency_key: str,
    ) -> Appointment:
        """Book a slot, or raise SLOT_UNAVAILABLE.

        The slot is re-checked at booking time: a slot that was free
        when offered but taken since raises ``SLOT_UNAVAILABLE``.
        Booking twice under the same ``idempotency_key`` returns the
        original appointment instead of creating a second one.
        """
        ...
