"""The calendar: availability and idempotent booking (build step 3).

``LocalCalendar`` reads business hours from the pack and busy blocks
from the store. A Google Calendar adapter is a v0.2 candidate behind
the same :class:`first60.calendar.base.Calendar` protocol.
"""

from __future__ import annotations

from first60.calendar.base import Calendar
from first60.calendar.local import LocalCalendar

__all__ = [
    "Calendar",
    "LocalCalendar",
]
