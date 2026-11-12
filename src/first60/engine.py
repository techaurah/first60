"""The reception engine (build step 5).

The engine is the actor layer: it takes one inbound message, runs
it through the pure pipeline (extract, qualify, score, stage
moves, handoff), renders the reply through a responder, sends it
through a channel, and audits every side effect. It is the
promotion of the test-local driver from build step 4 into the real
module; the conversation behaviour is unchanged, and the step-4
conversation tests now drive this engine.

DESIGN.md rules that hold here:

- **Rules decide, responders phrase.** Every decision (greet,
  ask, offer slots, book, hand off, follow up, opt out) is
  computed by deterministic code; the responder only renders it.
- **A clock is injected everywhere.** The engine takes
  ``clock: Callable[[], datetime]`` returning an aware UTC
  datetime; production passes the system clock, demo and tests
  pass a simulated one. A naive clock value is read as UTC.
- **Every side effect is audited.** Each reply, stage move,
  booking, follow-up and reminder is an append-only audit row
  with its write mode.
- **No silent sends, ever.** ``write_mode`` gates every outbound
  send: ``demo`` and ``direct`` send through the channel;
  ``dry_run`` audits ``reply_would_send`` and sends nothing;
  ``approval`` audits ``reply_pending_approval`` and sends
  nothing. In the two held modes :meth:`handle_inbound` returns
  ``None`` so the caller (server, console) cannot deliver a reply
  the engine withheld.

Conversation flow, in priority order:

1. A lead whose automation is paused (handoff) or who opted out
   hears nothing more from the engine: the message is audited as
   ``message_held_for_human`` and ``None`` is returned.
2. An opt-out wins over every other check: a STOP is not a stuck
   conversation. The lead is paused, scheduled follow-ups are
   cancelled, and the opt-out confirmation is sent.
3. A handoff trigger pauses automation, cancels scheduled
   follow-ups, and sends the safety template or handoff notice.
4. An unqualified lead is asked the next question (a greeting on
   the first reply) and moves to CONTACTED.
5. A qualified lead with no booking is offered the next free
   slots (QUALIFIED); a reply naming one of the offered slots
   books it (BOOKED), consents to reminders, and cancels the
   follow-up sequence.
6. A booked lead who writes again gets an acknowledgement.

Follow-ups: after every outbound reply that leaves the
conversation open, the follow-up clock resets (any scheduled touch
is cancelled and touch 1 is re-scheduled from the new last
outbound). :meth:`process_due` fires due touches and reminders;
see :mod:`first60.followups` for the cadence and stop rules.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta

from first60.calendar.base import Calendar
from first60.channels.base import Channel
from first60.config import BusinessPack
from first60.errors import INVALID_WRITE_MODE, First60Error
from first60.followups import (
    as_utc,
    audit_reminder_sent,
    cancel_scheduled,
    due_followups,
    due_reminders,
    in_waking_window,
    local_now,
    next_window_start,
    schedule_first_touch,
    schedule_next_touch,
    stop_reason,
)
from first60.models import (
    Appointment,
    FollowUp,
    Lead,
    new_audit_row,
    new_lead,
    new_message,
)
from first60.pipeline.extract import detect_opt_out, extract_contact
from first60.pipeline.handoff import check_handoff
from first60.pipeline.qualify import (
    ConversationState,
    answered_required,
    apply_message,
    initial_state,
    is_qualified,
    next_question,
)
from first60.pipeline.scoring import ScoringInput, score_lead
from first60.pipeline.stages import Stage
from first60.respond.base import Decision, FactSheet, Responder
from first60.store.base import Store

__all__ = [
    "ReceptionEngine",
    "WRITE_MODES",
]

WRITE_MODES = ("demo", "direct", "dry_run", "approval")

_WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

# ConversationState fields: everything else in a stored state dict is
# engine bookkeeping (pause flags, consent, offered slots).
_STATE_FIELDS = frozenset(
    {
        "answers",
        "service",
        "service_match",
        "urgency",
        "timeline_detail",
        "consecutive_failures",
        "stuck",
        "replies",
    }
)


def _system_clock() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


class ReceptionEngine:
    """One receptionist: pack + store + calendar + responder + channel."""

    def __init__(
        self,
        *,
        pack: BusinessPack,
        store: Store,
        calendar: Calendar,
        responder: Responder,
        channel: Channel,
        clock: Callable[[], datetime] | None = None,
        write_mode: str = "demo",
    ) -> None:
        if write_mode not in WRITE_MODES:
            raise First60Error(
                INVALID_WRITE_MODE,
                f"write_mode must be one of {', '.join(WRITE_MODES)}",
            )
        self.pack = pack
        self.store = store
        self.calendar = calendar
        self.responder = responder
        self.channel = channel
        self.facts = FactSheet.from_pack(pack)
        self.clock = clock or _system_clock
        self.write_mode = write_mode
        # (channel name, sender handle) -> lead id. Single-process
        # dedupe: a restart re-dedupes by extracted contact (email,
        # then phone); a sender with neither gets a fresh lead.
        self._handles: dict[tuple[str, str], str] = {}

    # -- inbound ---------------------------------------------------

    def handle_inbound(
        self, sender: str, text: str, channel_name: str | None = None
    ) -> str | None:
        """Handle one inbound message; return the reply sent, or None.

        ``None`` means no automated reply went out: the lead is
        paused or opted out, or the write mode withheld the send.
        """
        now = as_utc(self.clock())
        channel = channel_name or self.channel.name
        lead = self._find_or_create_lead(sender, text, channel, now)
        self.store.add_message(
            new_message(
                lead_id=lead.id,
                direction="in",
                text=text,
                now=now.isoformat(),
            )
        )
        state = self._load_state(lead)

        if self._is_paused(lead):
            self._audit(lead.id, "message_held_for_human", now, channel)
            return None

        state = apply_message(state, self.pack, text)
        self._save_state(lead, state, now)

        # Opt-out wins over every other check.
        if detect_opt_out(text):
            reply = self.responder.render(
                Decision(
                    kind="opt_out",
                    lead_name=state.answers.get("name", ""),
                ),
                self.facts,
            )
            self._pause_lead(lead, state, opted_out=True)
            cancel_scheduled(self.store, lead.id, "opted_out")
            self._audit(lead.id, "opt_out", now, channel)
            return self._send(lead, reply, now, schedule_followups=False)

        handoff = check_handoff(self.pack, state, text)
        if handoff.triggered:
            reply = self.responder.render(
                Decision(kind="handoff", handoff_text=handoff.reply_text),
                self.facts,
            )
            self._pause_lead(lead, state, opted_out=False)
            cancel_scheduled(self.store, lead.id, "handoff")
            self._audit(lead.id, "handoff", now, channel, detail=handoff.reason or "")
            return self._send(lead, reply, now, schedule_followups=False)

        if not is_qualified(state, self.pack):
            question = next_question(state, self.pack)
            kind = "greet" if state.replies == 1 else "ask"
            reply = self.responder.render(
                Decision(kind=kind, question=question.text if question else ""),
                self.facts,
            )
            self._move_stage(lead, Stage.CONTACTED, now)
            return self._send(lead, reply, now)

        offered = self._offered_slots(lead)
        chosen = next((slot for slot in offered if slot in text), None)
        if chosen is None:
            return self._offer_slots(lead, state, now)
        return self._book(lead, state, chosen, now)

    # -- due work ----------------------------------------------------

    def process_due(self, now: datetime | None = None) -> list[str]:
        """Fire due follow-ups and reminders; return the texts sent."""
        moment = as_utc(now) if now is not None else as_utc(self.clock())
        sent: list[str] = []
        for followup in due_followups(self.store, moment):
            text = self._fire_followup(followup, moment)
            if text is not None:
                sent.append(text)
        for lead in self.store.list_leads():
            if self._is_paused(lead):
                continue
            reminders = due_reminders(self.store, lead, moment, self.pack)
            for appointment, window in reminders:
                text = self._fire_reminder(lead, appointment, window, moment)
                if text is not None:
                    sent.append(text)
        return sent

    # -- internals ---------------------------------------------------

    def _fire_followup(self, followup: FollowUp, now: datetime) -> str | None:
        """Fire or suppress one due touch; return the text sent, or None."""
        lead = self.store.get_lead(followup.lead_id)
        reason = stop_reason(self.store, lead, followup)
        if reason is not None:
            self.store.save_followup(
                replace(followup, status="suppressed", reason=reason)
            )
            self._audit(
                lead.id,
                "followup_suppressed",
                now,
                self.channel.name,
                detail=f"touch {followup.touch_index}: {reason}",
            )
            return None
        local = local_now(self.pack, now)
        policy = self.pack.followups
        if not in_waking_window(policy, local):
            deferred = next_window_start(policy, local).astimezone(UTC)
            self.store.save_followup(replace(followup, due_at=deferred.isoformat()))
            self._audit(
                lead.id,
                "followup_deferred",
                now,
                self.channel.name,
                detail=(
                    f"touch {followup.touch_index} deferred to {deferred.isoformat()}"
                ),
            )
            return None
        state = self._load_state(lead)
        reply = self.responder.render(
            Decision(
                kind="follow_up",
                service=lead.service or "",
                lead_name=state.answers.get("name", ""),
                detail="We still have times available this week.",
            ),
            self.facts,
        )
        sent_text = self._send(lead, reply, now, schedule_followups=False)
        if sent_text is None:
            # The write mode withheld the send: the touch stays
            # unsent and is recorded as held, not as sent.
            self.store.save_followup(
                replace(followup, status="suppressed", reason="held_by_write_mode")
            )
            self._audit(
                lead.id,
                "followup_suppressed",
                now,
                self.channel.name,
                detail=f"touch {followup.touch_index}: held_by_write_mode",
            )
            return None
        self.store.save_followup(replace(followup, status="sent"))
        self._audit(
            lead.id,
            "followup_sent",
            now,
            self.channel.name,
            detail=f"touch {followup.touch_index}",
        )
        schedule_next_touch(self.store, lead, self.pack, followup.touch_index, now)
        return sent_text

    def _fire_reminder(
        self, lead: Lead, appointment: Appointment, window: str, now: datetime
    ) -> str | None:
        """Send one due appointment reminder; return the text, or None."""
        start = datetime.fromisoformat(appointment.start)
        reply = self.responder.render(
            Decision(
                kind="follow_up",
                service=appointment.service,
                lead_name=self._load_state(lead).answers.get("name", ""),
                detail=(
                    f"Your appointment is on {start.strftime('%A %H:%M')} "
                    f"({window} reminder)."
                ),
            ),
            self.facts,
        )
        sent_text = self._send(lead, reply, now, schedule_followups=False)
        if sent_text is not None:
            audit_reminder_sent(
                self.store, lead.id, appointment.id, window, self.write_mode, now
            )
        return sent_text

    def _offer_slots(
        self, lead: Lead, state: ConversationState, now: datetime
    ) -> str | None:
        """Offer the next free slots for the lead's service and day."""
        service = next((s for s in self.pack.services if s.name == state.service), None)
        if service is None:
            reply = self.responder.render(
                Decision(
                    kind="acknowledge",
                    detail="Thanks, we'll check availability and come back to you.",
                ),
                self.facts,
            )
            return self._send(lead, reply, now)
        day = self._pick_day(state)
        slots: list[datetime] = []
        if day is not None:
            slots = self.calendar.free_slots(day, service.duration_minutes)
        if day is None or not slots:
            reply = self.responder.render(
                Decision(
                    kind="acknowledge",
                    detail=(
                        "We don't have any free slots in the next week. "
                        "A member of the team will message you shortly."
                    ),
                ),
                self.facts,
            )
            return self._send(lead, reply, now)
        offered = tuple(slot.strftime("%A %H:%M") for slot in slots[:3])
        self._save_state(
            lead,
            state,
            now,
            extra={"offered_slots": list(offered), "offered_day": day.isoformat()},
        )
        reply = self.responder.render(
            Decision(
                kind="offer_slots",
                service=service.name,
                slots=offered,
                lead_name=state.answers.get("name", ""),
            ),
            self.facts,
        )
        self._move_stage(lead, Stage.QUALIFIED, now)
        return self._send(lead, reply, now)

    def _book(
        self, lead: Lead, state: ConversationState, chosen: str, now: datetime
    ) -> str | None:
        """Book the chosen offered slot; return the confirmation, or None."""
        service = next(s for s in self.pack.services if s.name == state.service)
        offered_day = (lead.state or {}).get("offered_day")
        if offered_day:
            day = date.fromisoformat(str(offered_day))
        else:
            day = as_utc(now).date()
        hour, minute = (int(part) for part in chosen.split()[1].split(":"))
        start = datetime(day.year, day.month, day.day, hour, minute)
        appointment = self.calendar.book(
            lead_id=lead.id,
            service=service.name,
            start=start,
            duration_minutes=service.duration_minutes,
            idempotency_key=f"{lead.id}-{chosen}",
        )
        self._save_state(
            lead,
            state,
            now,
            extra={"reminders_consented": True, "offered_slots": [], "offered_day": ""},
        )
        cancel_scheduled(self.store, lead.id, "booked")
        reply = self.responder.render(
            Decision(
                kind="confirm_booking",
                service=service.name,
                appointment=start.strftime("%A %H:%M"),
            ),
            self.facts,
        )
        self._move_stage(lead, Stage.BOOKED, now)
        self._audit(
            lead.id,
            "booking",
            now,
            self.channel.name,
            detail=f"{service.name} {start.isoformat()}",
        )
        assert appointment.start == start.isoformat()
        return self._send(lead, reply, now, schedule_followups=False)

    def _pick_day(self, state: ConversationState) -> date | None:
        """Return the first day with a free slot, from the named weekday.

        The lead's requested weekday (from the timeline detail) wins
        when present; otherwise today. Up to 7 days are tried, so a
        fully booked week reports no slots instead of offering a
        stale day.
        """
        local_today = local_now(self.pack, self.clock()).date()
        start = local_today
        detail = (state.timeline_detail or "").strip().lower()
        if detail in _WEEKDAYS:
            target = _WEEKDAYS.index(detail)
            while start.weekday() != target:
                start += timedelta(days=1)
        service = next((s for s in self.pack.services if s.name == state.service), None)
        if service is None:
            return None
        for offset in range(7):
            day = start + timedelta(days=offset)
            if self.calendar.free_slots(day, service.duration_minutes):
                return day
        return None

    def _send(
        self, lead: Lead, reply: str, now: datetime, schedule_followups: bool = True
    ) -> str | None:
        """Record and deliver one outbound reply; return it, or None held.

        A withheld reply (``dry_run`` / ``approval``) is audited but
        never recorded as an outbound message: it did not go out, so
        it must not reset the follow-up clock or count as a reply.
        """
        if self.write_mode in ("dry_run", "approval"):
            action = (
                "reply_would_send"
                if self.write_mode == "dry_run"
                else "reply_pending_approval"
            )
            self._audit(lead.id, action, now, self.channel.name, detail=reply[:80])
            return None
        self.store.add_message(
            new_message(
                lead_id=lead.id, direction="out", text=reply, now=now.isoformat()
            )
        )
        self.channel.send(lead.id, reply)
        self._audit(lead.id, "reply_sent", now, self.channel.name)
        if schedule_followups and not self._is_paused(lead):
            cancel_scheduled(self.store, lead.id, "superseded_by_new_outbound")
            scheduled = schedule_first_touch(self.store, lead, self.pack, now)
            if scheduled is not None:
                self._audit(
                    lead.id,
                    "followup_scheduled",
                    now,
                    self.channel.name,
                    detail=f"touch 1 due {scheduled.due_at}",
                )
        return reply

    def _audit(
        self,
        lead_id: str,
        action: str,
        now: datetime,
        channel: str,
        detail: str = "",
    ) -> None:
        """Append one audit row for a side effect."""
        self.store.append_audit(
            new_audit_row(
                lead_id=lead_id,
                action=action,
                mode=self.write_mode,
                detail=detail or channel,
                now=now.isoformat(),
            )
        )

    def _move_stage(self, lead: Lead, target: Stage, now: datetime) -> Lead:
        """Move the lead's stage, auditing the move when it changes."""
        if lead.stage == target:
            return lead
        moved = self.store.move_stage(lead.id, target)
        self._audit(
            lead.id,
            "stage_move",
            now,
            self.channel.name,
            detail=f"{lead.stage.value}->{target.value}",
        )
        return moved

    def _find_or_create_lead(
        self, sender: str, text: str, channel: str, now: datetime
    ) -> Lead:
        """Dedupe by channel handle, then extracted contact, then create."""
        lead_id = self._handles.get((channel, sender))
        if lead_id is not None:
            return self.store.get_lead(lead_id)
        contact = extract_contact(text)
        found: Lead | None = None
        if contact.email:
            found = self.store.find_lead_by_email(contact.email)
        if found is None and contact.phone:
            found = self.store.find_lead_by_phone(contact.phone)
        if found is not None:
            self._handles[(channel, sender)] = found.id
            return found
        lead = self.store.create_lead(
            new_lead(
                name=contact.name or "",
                email=contact.email or "",
                phone=contact.phone or "",
                channel=channel,
                now=now.isoformat(),
            )
        )
        self._handles[(channel, sender)] = lead.id
        return lead

    def _load_state(self, lead: Lead) -> ConversationState:
        """Rebuild the conversation state from the stored dict.

        The stored dict is JSON-friendly (it round-trips through the
        store), so each field is re-checked on the way back in; a
        value of the wrong shape falls back to its default instead
        of crashing the conversation.
        """
        stored = dict(lead.state or {})
        fields = {key: stored[key] for key in _STATE_FIELDS if key in stored}
        if not fields:
            return initial_state()
        answers = fields.get("answers")
        service = fields.get("service")
        failures = fields.get("consecutive_failures")
        replies = fields.get("replies")
        return ConversationState(
            answers=dict(answers) if isinstance(answers, dict) else {},
            service=service if isinstance(service, str) else None,
            service_match=str(fields.get("service_match", "none")),
            urgency=str(fields.get("urgency", "unknown")),
            timeline_detail=str(fields.get("timeline_detail", "")),
            consecutive_failures=failures if isinstance(failures, int) else 0,
            stuck=fields.get("stuck") is True,
            replies=replies if isinstance(replies, int) else 0,
        )

    def _save_state(
        self,
        lead: Lead,
        state: ConversationState,
        now: datetime,
        extra: dict[str, object] | None = None,
    ) -> Lead:
        """Persist state, score and stage denormalisations for the lead."""
        answered, total = answered_required(state, self.pack)
        service = next((s for s in self.pack.services if s.name == state.service), None)
        score = score_lead(
            ScoringInput(
                service_match=state.service_match,
                urgency=state.urgency,
                name_known="name" in state.answers,
                contact_known="contact" in state.answers,
                questions_answered=answered,
                questions_total=total,
                value_tier=service.value_tier if service else None,
            )
        )
        stored = dict(lead.state or {})
        stored.update(asdict(state))
        if extra:
            stored.update(extra)
        updated = replace(
            lead,
            answers=dict(state.answers),
            service=state.service,
            urgency=state.urgency,
            score_total=score.total,
            score_band=score.band,
            score_components=dict(score.components),
            state=stored,
            updated_at=now.isoformat(),
        )
        return self.store.update_lead(updated)

    def _pause_lead(
        self, lead: Lead, state: ConversationState, *, opted_out: bool
    ) -> None:
        """Mark the lead paused (and opted out when given) in its state."""
        extra: dict[str, object] = {"automation_paused": True}
        if opted_out:
            extra["opted_out"] = True
        self._save_state(lead, state, as_utc(self.clock()), extra=extra)

    def _is_paused(self, lead: Lead) -> bool:
        """Return True when automation is paused or the lead opted out."""
        state = lead.state or {}
        return state.get("automation_paused") is True or state.get("opted_out") is True

    def _offered_slots(self, lead: Lead) -> tuple[str, ...]:
        """Return the slots currently offered to the lead, if any."""
        offered = (lead.state or {}).get("offered_slots")
        if not isinstance(offered, list):
            return ()
        return tuple(str(slot) for slot in offered)
