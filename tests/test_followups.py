"""Follow-up engine tests (build step 5).

DESIGN.md section 11 calls for 14 follow-up tests: schedule
times, waking-window deferral, cap enforcement, each stop
condition, the reminder consent gate, and suppression audit
reasons, all on the injected clock. The pure rules are tested
directly against the store; the engine-level tests drive the real
conversation and then run :meth:`ReceptionEngine.process_due`.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from first60.calendar.local import LocalCalendar
from first60.channels.simulated import SimulatedChannel
from first60.config import load_builtin_pack
from first60.engine import ReceptionEngine
from first60.followups import (
    cancel_scheduled,
    due_reminders,
    in_waking_window,
    schedule_first_touch,
    stop_reason,
)
from first60.models import new_lead, new_message
from first60.pipeline.stages import Stage
from first60.respond.rules import RuleResponder
from first60.store.memory import MemoryStore

PACK = load_builtin_pack("dental")

# Tuesday 21:40 UTC. Europe/London is on GMT in November, so the
# business-local clock agrees with UTC in these tests.
TUESDAY = datetime(2026, 11, 10, 21, 40, tzinfo=UTC)


def make_engine(now: datetime = TUESDAY):
    """Build an engine on a fresh store with a mutable clock."""
    holder = {"now": now}
    store = MemoryStore()
    channel = SimulatedChannel()
    calendar = LocalCalendar(store, PACK, clock=lambda: holder["now"])
    engine = ReceptionEngine(
        pack=PACK,
        store=store,
        calendar=calendar,
        responder=RuleResponder(),
        channel=channel,
        clock=lambda: holder["now"],
    )
    return engine, store, channel, holder


def book_lead(engine, store):
    """Drive one lead to a Thursday 09:00 booking; return the lead."""
    engine.handle_inbound(
        "sarah", "do you have anything Thursday morning, my crown is aching"
    )
    engine.handle_inbound("sarah", "I'm Sarah")
    engine.handle_inbound("sarah", "07123 456789")
    engine.handle_inbound("sarah", "Thursday 09:00 works for me")
    lead = store.list_leads()[0]
    assert lead.stage == Stage.BOOKED
    return lead


def offer_lead(engine, store):
    """Drive one lead to the slot offer; return the lead."""
    engine.handle_inbound(
        "sarah", "do you have anything Thursday morning, my crown is aching"
    )
    engine.handle_inbound("sarah", "I'm Sarah")
    engine.handle_inbound("sarah", "07123 456789")
    lead = store.list_leads()[0]
    assert lead.stage == Stage.QUALIFIED
    return lead


def lead_with_outbound(store, lead_id, outbound_at, **overrides):
    """Hand-build a lead with one outbound message at ``outbound_at``."""
    lead = store.create_lead(
        new_lead(lead_id=lead_id, channel="simulated", now=outbound_at.isoformat())
    )
    store.add_message(
        new_message(
            lead_id=lead_id,
            direction="out",
            text="Hello",
            now=outbound_at.isoformat(),
        )
    )
    if overrides:
        lead = store.update_lead(replace(lead, **overrides))
    return lead


# -- schedule times ------------------------------------------------


def test_touch_1_due_four_hours_after_last_outbound_in_window():
    _, store, _, _ = make_engine()
    outbound_at = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    lead = lead_with_outbound(store, "lead-1", outbound_at)
    row = schedule_first_touch(store, lead, PACK, outbound_at)
    assert row is not None
    assert row.touch_index == 1
    assert row.due_at == "2026-11-10T14:00:00+00:00"


def test_touch_1_deferred_outside_waking_window():
    _, store, _, _ = make_engine()
    outbound_at = datetime(2026, 11, 10, 20, 30, tzinfo=UTC)
    lead = lead_with_outbound(store, "lead-1", outbound_at)
    row = schedule_first_touch(store, lead, PACK, outbound_at)
    assert row is not None
    # 20:30 + 4h is 00:30, outside 08:00-21:00: deferred to 08:00.
    assert row.due_at == "2026-11-11T08:00:00+00:00"


def test_in_waking_window_boundaries():
    policy = PACK.followups
    assert in_waking_window(policy, datetime(2026, 11, 10, 8, 0, tzinfo=UTC))
    assert in_waking_window(policy, datetime(2026, 11, 10, 20, 59, tzinfo=UTC))
    assert not in_waking_window(policy, datetime(2026, 11, 10, 7, 59, tzinfo=UTC))
    assert not in_waking_window(policy, datetime(2026, 11, 10, 21, 0, tzinfo=UTC))


def test_touch_chain_and_cap():
    engine, store, _, holder = make_engine()
    offer_lead(engine, store)
    # Last outbound Tuesday 21:40 -> touch 1 due 01:40, deferred to 08:00.
    first = store.list_followups(status="scheduled")[0]
    assert first.due_at == "2026-11-11T08:00:00+00:00"
    holder["now"] = datetime(2026, 11, 11, 8, 0, tzinfo=UTC)
    assert engine.process_due() != []
    second = store.list_followups(status="scheduled")[0]
    assert second.touch_index == 2
    assert second.due_at == "2026-11-12T08:00:00+00:00"
    holder["now"] = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
    assert engine.process_due() != []
    third = store.list_followups(status="scheduled")[0]
    assert third.touch_index == 3
    assert third.due_at == "2026-11-15T08:00:00+00:00"
    holder["now"] = datetime(2026, 11, 15, 8, 0, tzinfo=UTC)
    assert engine.process_due() != []
    # The sequence is complete: no fourth touch is ever scheduled.
    assert store.list_followups(status="scheduled") == []
    assert len(store.list_followups(status="sent")) == 3


def test_schedule_first_touch_is_idempotent_while_one_is_scheduled():
    _, store, _, _ = make_engine()
    outbound_at = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    lead = lead_with_outbound(store, "lead-1", outbound_at)
    first = schedule_first_touch(store, lead, PACK, outbound_at)
    assert first is not None
    assert schedule_first_touch(store, lead, PACK, outbound_at) is None
    assert len(store.list_followups(lead_id="lead-1")) == 1


# -- stop conditions (pure rules) ----------------------------------


def _scheduled_touch(store, lead, outbound_at):
    row = schedule_first_touch(store, lead, PACK, outbound_at)
    assert row is not None
    return row


def test_stop_reason_replied():
    _, store, _, _ = make_engine()
    outbound_at = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    lead = lead_with_outbound(store, "lead-1", outbound_at)
    row = _scheduled_touch(store, lead, outbound_at)
    store.add_message(
        new_message(
            lead_id="lead-1",
            direction="in",
            text="sorry, I was busy",
            now="2026-11-10T12:00:00+00:00",
        )
    )
    assert stop_reason(store, lead, row) == "replied"


def test_stop_reason_already_booked():
    _, store, _, _ = make_engine()
    outbound_at = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    lead = lead_with_outbound(store, "lead-1", outbound_at, stage=Stage.BOOKED)
    row = _scheduled_touch(store, lead, outbound_at)
    assert stop_reason(store, lead, row) == "already_booked"


def test_stop_reason_opted_out():
    _, store, _, _ = make_engine()
    outbound_at = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    lead = lead_with_outbound(store, "lead-1", outbound_at, state={"opted_out": True})
    row = _scheduled_touch(store, lead, outbound_at)
    assert stop_reason(store, lead, row) == "opted_out"


def test_stop_reason_stage_lost():
    _, store, _, _ = make_engine()
    outbound_at = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    lead = lead_with_outbound(store, "lead-1", outbound_at, stage=Stage.LOST)
    row = _scheduled_touch(store, lead, outbound_at)
    assert stop_reason(store, lead, row) == "stage_lost"


def test_stop_reason_automation_paused():
    _, store, _, _ = make_engine()
    outbound_at = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    lead = lead_with_outbound(
        store, "lead-1", outbound_at, state={"automation_paused": True}
    )
    row = _scheduled_touch(store, lead, outbound_at)
    assert stop_reason(store, lead, row) == "automation_paused"


def test_stop_reason_priority_opt_out_over_booking():
    _, store, _, _ = make_engine()
    outbound_at = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    lead = lead_with_outbound(
        store, "lead-1", outbound_at, stage=Stage.BOOKED, state={"opted_out": True}
    )
    row = _scheduled_touch(store, lead, outbound_at)
    assert stop_reason(store, lead, row) == "opted_out"


def test_stop_reason_none_when_open_and_silent():
    _, store, _, _ = make_engine()
    outbound_at = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    lead = lead_with_outbound(store, "lead-1", outbound_at)
    row = _scheduled_touch(store, lead, outbound_at)
    assert stop_reason(store, lead, row) is None


def test_cancel_scheduled_cancels_all_with_reason():
    _, store, _, _ = make_engine()
    outbound_at = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    lead = lead_with_outbound(store, "lead-1", outbound_at)
    _scheduled_touch(store, lead, outbound_at)
    assert cancel_scheduled(store, "lead-1", "booked") == 1
    rows = store.list_followups(lead_id="lead-1")
    assert rows[0].status == "cancelled"
    assert rows[0].reason == "booked"


# -- engine-level behaviour -----------------------------------------


def test_engine_reply_resets_followup_clock():
    engine, store, _, holder = make_engine()
    lead = offer_lead(engine, store)
    first = store.list_followups(status="scheduled")[0]
    assert first.due_at == "2026-11-11T08:00:00+00:00"
    holder["now"] = datetime(2026, 11, 11, 7, 0, tzinfo=UTC)
    engine.handle_inbound("sarah", "thanks")
    rows = store.list_followups(lead_id=lead.id)
    superseded = [row for row in rows if row.reason == "superseded_by_new_outbound"]
    scheduled = [row for row in rows if row.status == "scheduled"]
    # Each of the three earlier replies superseded the touch before
    # it, and the "thanks" reply superseded the third: 3 cancelled.
    assert len(superseded) == 3
    assert len(scheduled) == 1
    # New outbound 07:00 + 4h = 11:00, inside the window.
    assert scheduled[0].due_at == "2026-11-11T11:00:00+00:00"


def test_booking_cancels_scheduled_touch():
    engine, store, _, _ = make_engine()
    offer_lead(engine, store)
    assert len(store.list_followups(status="scheduled")) == 1
    engine.handle_inbound("sarah", "Thursday 09:00 works for me")
    assert store.list_followups(status="scheduled") == []
    booked = [
        row
        for row in store.list_followups()
        if row.status == "cancelled" and row.reason == "booked"
    ]
    assert len(booked) == 1


def test_process_due_fires_touch_and_writes_audit():
    engine, store, channel, holder = make_engine()
    offer_lead(engine, store)
    holder["now"] = datetime(2026, 11, 11, 8, 0, tzinfo=UTC)
    sent = engine.process_due()
    assert len(sent) == 1
    assert "just checking in" in sent[0]
    assert channel.outbox[-1][1] == sent[0]
    fired = [row for row in store.list_followups() if row.status == "sent"]
    assert len(fired) == 1
    assert fired[0].touch_index == 1
    actions = [row.action for row in store.list_audit()]
    assert "followup_sent" in actions


def test_process_due_suppresses_after_reply_and_audits_reason():
    engine, store, _, holder = make_engine()
    offer_lead(engine, store)
    # The reply arrives while the write mode withholds the engine's
    # answer, so the follow-up clock is NOT reset: at fire time the
    # stop check sees the reply and suppresses the touch as replied.
    engine.write_mode = "dry_run"
    holder["now"] = datetime(2026, 11, 11, 7, 0, tzinfo=UTC)
    engine.handle_inbound("sarah", "thanks")
    assert len(store.list_followups(status="scheduled")) == 1
    holder["now"] = datetime(2026, 11, 11, 8, 0, tzinfo=UTC)
    assert engine.process_due() == []
    suppressed = [row for row in store.list_followups() if row.status == "suppressed"]
    assert len(suppressed) == 1
    assert suppressed[0].reason == "replied"
    actions = [row.action for row in store.list_audit()]
    assert "followup_suppressed" in actions


def test_dry_run_followup_is_held_not_sent():
    engine, store, channel, holder = make_engine()
    offer_lead(engine, store)
    engine.write_mode = "dry_run"
    holder["now"] = datetime(2026, 11, 11, 8, 0, tzinfo=UTC)
    assert engine.process_due() == []
    suppressed = [row for row in store.list_followups() if row.status == "suppressed"]
    assert len(suppressed) == 1
    assert suppressed[0].reason == "held_by_write_mode"
    assert not any("just checking in" in text for _, text in channel.outbox)


# -- reminders -------------------------------------------------------


def test_reminders_need_consent():
    engine, store, _, _ = make_engine()
    lead = book_lead(engine, store)
    wednesday_9am = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
    assert due_reminders(store, lead, wednesday_9am, PACK) != []
    # The same appointment without consent produces no reminder.
    no_consent = store.update_lead(
        replace(lead, state={**lead.state, "reminders_consented": False})
    )
    assert due_reminders(store, no_consent, wednesday_9am, PACK) == []


def test_reminders_fire_24h_and_2h_each_once():
    engine, store, channel, holder = make_engine()
    book_lead(engine, store)
    holder["now"] = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
    sent_24h = engine.process_due()
    assert len(sent_24h) == 1
    assert "24h reminder" in sent_24h[0]
    # A second sweep at the same time sends nothing new.
    assert engine.process_due() == []
    holder["now"] = datetime(2026, 11, 12, 7, 0, tzinfo=UTC)
    sent_2h = engine.process_due()
    assert len(sent_2h) == 1
    assert "2h reminder" in sent_2h[0]
    assert engine.process_due() == []
    assert len(channel.outbox) == 4 + 2  # 4 conversation replies + 2 reminders


def test_no_reminder_after_opt_out():
    engine, store, _, holder = make_engine()
    book_lead(engine, store)
    engine.handle_inbound("sarah", "STOP")
    lead = store.list_leads()[0]
    assert lead.state.get("opted_out") is True
    holder["now"] = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
    # The lead is paused, so the engine's sweep skips it entirely:
    # no reminder goes out even though the 24h mark has passed.
    assert engine.process_due() == []
