"""The follow-up engine (build step 5).

DESIGN.md section 7: scheduled touches with caps, business-hours
awareness, stop-on-reply, opt-out handling, and appointment
reminders, all on the injected clock. This module is pure logic
over the store: it decides what is due, what must be suppressed,
and when a touch moves to the next waking window. The engine
(:mod:`first60.engine`) calls it, renders the text, sends it, and
writes the audit rows.

Cadence (from the business pack, defaults touch 1 at +4h, touch 2
at +24h, touch 3 at +72h, maximum 3 touches):

- The delays are chained: each touch is due that many hours after
  the most recent outbound message, so touch 2 is due 24 hours
  after touch 1 fired, not 24 hours after the original reply. The
  chain restarts from every outbound, which is what "after last
  outbound with no reply" means when the previous touch is itself
  an outbound.
- A touch is only ever *scheduled* by the engine after an outbound
  reply leaves the conversation open (not booked, not handed off,
  not opted out). The scheduler never invents a sequence for a
  lead that never heard from the business.

Stop conditions are checked at fire time, not schedule time, so a
reply, booking, opt-out or handoff that lands after scheduling
still stops the touch:

- ``opted_out``: the lead opted out (state flag, or an opt-out
  message in the conversation).
- ``stage_lost``: the lead's stage is LOST.
- ``automation_paused``: a handoff paused automation for the lead.
- ``already_booked``: the lead is BOOKED or holds a booked
  appointment.
- ``replied``: an inbound message arrived after the last outbound.

The check order above is the reason priority: an opt-out outranks
a booking, a booking outranks a plain reply.

Waking window: a touch due outside the pack's window (default
08:00-21:00 business-local) is deferred, not suppressed: its due
time moves to the next window start and the deferral is audited.
A touch is never sent while the business is closed, and a
deferral never consumes the touch.

Appointment reminders are separate from the follow-up sequence:
24 hours and 2 hours before a confirmed appointment, only where
the lead consented to reminders at booking time
(``lead.state["reminders_consented"]``). Sent reminders are
tracked by audit rows (action ``reminder_sent``), so a restart
never double-sends one.

Every fired or suppressed touch writes an audit row with its
reason, so "why did this lead get / not get a message" is always
answerable from the log. All times are timezone-aware UTC
datetimes; the waking window is evaluated in the pack's timezone
via :mod:`zoneinfo` (an unknown timezone falls back to UTC).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from first60.config import BusinessPack, FollowUpPolicy
from first60.models import (
    Appointment,
    FollowUp,
    Lead,
    new_audit_row,
    new_followup,
)
from first60.pipeline.stages import Stage
from first60.store.base import Store

__all__ = [
    "as_utc",
    "audit_reminder_sent",
    "cancel_scheduled",
    "due_followups",
    "due_reminders",
    "has_reply_since",
    "in_waking_window",
    "local_now",
    "next_window_start",
    "schedule_first_touch",
    "schedule_next_touch",
    "stop_reason",
]

REMINDER_WINDOWS: tuple[tuple[str, timedelta], ...] = (
    ("24h", timedelta(hours=24)),
    ("2h", timedelta(hours=2)),
)


def _parse_iso(value: str) -> datetime:
    """Parse an ISO 8601 timestamp; naive values are read as UTC."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def as_utc(value: datetime) -> datetime:
    """Return ``value`` as an aware UTC datetime."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def local_now(pack: BusinessPack, now: datetime) -> datetime:
    """Return ``now`` in the pack's timezone (UTC fallback if unknown)."""
    try:
        zone = ZoneInfo(pack.timezone)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return as_utc(now).astimezone(zone)


def _window_times(policy: FollowUpPolicy) -> tuple[time, time]:
    start_hour, start_minute = (
        int(part) for part in policy.waking_window_start.split(":")
    )
    end_hour, end_minute = (int(part) for part in policy.waking_window_end.split(":"))
    return time(start_hour, start_minute), time(end_hour, end_minute)


def in_waking_window(policy: FollowUpPolicy, local_dt: datetime) -> bool:
    """Return True when business-local ``local_dt`` is inside the window."""
    start, end = _window_times(policy)
    current = local_dt.time().replace(second=0, microsecond=0)
    return start <= current < end


def next_window_start(policy: FollowUpPolicy, local_dt: datetime) -> datetime:
    """Return the next waking-window start at or after ``local_dt``.

    When ``local_dt`` is before today's start, that is today at the
    start time; otherwise it is tomorrow at the start time. The
    result keeps the pack timezone.
    """
    start, _ = _window_times(policy)
    today_start = local_dt.replace(
        hour=start.hour, minute=start.minute, second=0, microsecond=0
    )
    if local_dt < today_start:
        return today_start
    return today_start + timedelta(days=1)


def has_reply_since(store: Store, lead_id: str, since_iso: str) -> bool:
    """Return True when an inbound message arrived after ``since_iso``."""
    since = _parse_iso(since_iso)
    for message in store.list_messages(lead_id):
        if message.direction == "in" and _parse_iso(message.created_at) > since:
            return True
    return False


def _last_outbound_iso(store: Store, lead_id: str) -> str | None:
    """Return the newest outbound message time for the lead, or None."""
    latest: str | None = None
    for message in store.list_messages(lead_id):
        if message.direction == "out":
            if latest is None or _parse_iso(message.created_at) > _parse_iso(latest):
                latest = message.created_at
    return latest


def _defer_to_window(pack: BusinessPack, due: datetime) -> tuple[datetime, bool]:
    """Move ``due`` to the next waking-window start when outside it.

    Returns ``(due_time, was_deferred)``. A due time already inside
    the window is returned unchanged.
    """
    local_due = local_now(pack, due)
    if in_waking_window(pack.followups, local_due):
        return as_utc(due), False
    deferred = next_window_start(pack.followups, local_due)
    return as_utc(deferred), True


def _save_touch(
    store: Store,
    lead: Lead,
    pack: BusinessPack,
    touch_index: int,
    due: datetime,
    now: datetime,
) -> FollowUp:
    """Persist one scheduled touch, deferring out-of-window due times."""
    due_utc, _ = _defer_to_window(pack, due)
    row = new_followup(
        lead_id=lead.id,
        touch_index=touch_index,
        due_at=due_utc.isoformat(),
        now=as_utc(now).isoformat(),
    )
    return store.save_followup(row)


def schedule_first_touch(
    store: Store,
    lead: Lead,
    pack: BusinessPack,
    now: datetime,
) -> FollowUp | None:
    """Schedule touch 1 for ``lead`` after its last outbound message.

    Returns the scheduled row, or ``None`` when the lead already has
    a scheduled touch, has used its touches, or has no outbound
    message to measure from. The due time is the last outbound plus
    the first delay; a due time outside the waking window is moved
    to the next window start.
    """
    policy = pack.followups
    if store.list_followups(lead_id=lead.id, status="scheduled"):
        return None
    sent = [
        row for row in store.list_followups(lead_id=lead.id) if row.status == "sent"
    ]
    if len(sent) >= policy.max_touches:
        return None
    last_outbound = _last_outbound_iso(store, lead.id)
    if last_outbound is None:
        return None
    due = _parse_iso(last_outbound) + timedelta(hours=policy.touch_delays_hours[0])
    return _save_touch(store, lead, pack, 1, due, now)


def schedule_next_touch(
    store: Store,
    lead: Lead,
    pack: BusinessPack,
    fired_touch_index: int,
    fired_at: datetime,
) -> FollowUp | None:
    """Schedule the touch after ``fired_touch_index`` from its fire time.

    Returns the scheduled row, or ``None`` when the sequence is
    complete (the fired touch was the last one the policy allows).
    The due time is the fire time plus the next delay, moved to the
    next waking window start when it falls outside the window.
    """
    policy = pack.followups
    next_index = fired_touch_index + 1
    if next_index > policy.max_touches:
        return None
    delay = policy.touch_delays_hours[next_index - 1]
    due = as_utc(fired_at) + timedelta(hours=delay)
    return _save_touch(store, lead, pack, next_index, due, fired_at)


def cancel_scheduled(store: Store, lead_id: str, reason: str) -> int:
    """Cancel every scheduled follow-up for the lead; return how many."""
    cancelled = 0
    for row in store.list_followups(lead_id=lead_id, status="scheduled"):
        store.save_followup(replace(row, status="cancelled", reason=reason))
        cancelled += 1
    return cancelled


def stop_reason(store: Store, lead: Lead, followup: FollowUp) -> str | None:
    """Return the suppression reason for ``followup``, or None to fire.

    Checked at fire time, in reason priority order: opt-out, stage
    LOST, automation paused, already booked, replied since the last
    outbound. A lead that opted out never hears from the engine
    again, whatever else is true.
    """
    state = lead.state or {}
    if state.get("opted_out") is True:
        return "opted_out"
    if lead.stage == Stage.LOST:
        return "stage_lost"
    if state.get("automation_paused") is True:
        return "automation_paused"
    if lead.stage == Stage.BOOKED:
        return "already_booked"
    for appointment in store.list_appointments():
        if appointment.lead_id == lead.id and appointment.status == "booked":
            return "already_booked"
    last_outbound = _last_outbound_iso(store, lead.id)
    if last_outbound is not None and has_reply_since(store, lead.id, last_outbound):
        return "replied"
    return None


def due_followups(store: Store, now: datetime) -> list[FollowUp]:
    """Return scheduled follow-ups whose due time has arrived, oldest first."""
    now_utc = as_utc(now)
    due: list[FollowUp] = []
    for row in store.list_followups(status="scheduled"):
        if _parse_iso(row.due_at) <= now_utc:
            due.append(row)
    due.sort(key=lambda row: _parse_iso(row.due_at))
    return due


def due_reminders(
    store: Store, lead: Lead, now: datetime, pack: BusinessPack
) -> list[tuple[Appointment, str]]:
    """Return ``(appointment, window)`` pairs whose reminder is due.

    A reminder is due when ``now`` is at or past the window mark
    (24h or 2h before the appointment start) and before the
    appointment itself, the lead consented to reminders at booking,
    and no ``reminder_sent`` audit row exists for that appointment
    and window yet. Consent lives in ``lead.state``; without it no
    reminder is ever sent.
    """
    if (lead.state or {}).get("reminders_consented") is not True:
        return []
    sent_windows: set[tuple[str, str]] = set()
    for row in store.list_audit(lead_id=lead.id):
        if row.action == "reminder_sent":
            parts = row.detail.split(":", 1)
            if len(parts) == 2:
                sent_windows.add((parts[0], parts[1]))
    now_utc = as_utc(now)
    try:
        zone = ZoneInfo(pack.timezone)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    due: list[tuple[Appointment, str]] = []
    for appointment in store.list_appointments():
        if appointment.lead_id != lead.id or appointment.status != "booked":
            continue
        # Appointment starts are business-local naive datetimes.
        start = _parse_iso(appointment.start)
        if start.tzinfo is None:
            start = start.replace(tzinfo=zone).astimezone(UTC)
        for window, offset in REMINDER_WINDOWS:
            mark = start - offset
            if (appointment.id, window) not in sent_windows and mark <= now_utc < start:
                due.append((appointment, window))
    return due


def audit_reminder_sent(
    store: Store,
    lead_id: str,
    appointment_id: str,
    window: str,
    mode: str,
    now: datetime,
) -> None:
    """Append the audit row that marks one reminder as sent."""
    store.append_audit(
        new_audit_row(
            lead_id=lead_id,
            action="reminder_sent",
            mode=mode,
            detail=f"{appointment_id}:{window}",
            now=as_utc(now).isoformat(),
        )
    )
