"""The demo scenario (build step 6, DESIGN.md section 9).

The release gate: :func:`first60.demo.run_demo` is the identical
script the CLI runs (``python -m first60 demo``), so this test is
the demo. It asserts the whole scenario end to end on the real
engine: the noon enquiry and its +4h follow-up booking, the
after-hours enquiry booked Thursday morning with its score
components, the same-lead re-message deduped, the STOP opt-out
with no further touches, and the Wednesday 08:00 summary. The
interactive console path and the summary rendering get their own
tests below, plus the booked-lead acknowledgement the demo exposed
in the engine (a re-message used to raise STAGE_TRANSITION_INVALID).
"""

from __future__ import annotations

import io
import sys
from datetime import UTC, datetime

import pytest

from first60 import cli
from first60.calendar.local import LocalCalendar
from first60.channels.console import ConsoleChannel
from first60.channels.simulated import SimulatedChannel
from first60.config import load_builtin_pack
from first60.demo import (
    SimulatedClock,
    build_demo_world,
    render_daily_summary,
    run_demo,
    run_interactive,
)
from first60.engine import ReceptionEngine
from first60.pipeline.stages import Stage
from first60.respond.rules import RuleResponder
from first60.store.memory import MemoryStore

PACK = load_builtin_pack("dental")
TUESDAY = datetime(2026, 11, 10, 21, 40, tzinfo=UTC)


def _lead_by_name(store, name):
    """Return the lead whose captured name is ``name``."""
    return next(lead for lead in store.list_leads() if lead.answers.get("name") == name)


# -- the release gate ------------------------------------------------


def test_demo_scenario_end_to_end():
    lines: list[str] = []
    result = run_demo(print_fn=lines.append)
    store = result.store

    # The transcript is the demo: every act prints in clock order.
    text = "\n".join(lines)
    assert "Tuesday 12:00" in text
    assert "Tuesday 16:00" in text
    assert "Tuesday 21:47" in text
    assert "Wednesday 08:00" in text
    assert "Thursday 09:00, Thursday 09:30, Thursday 11:00" in text
    assert "Sarah: stage NEW -> BOOKED, score 70 (WARM)" in text
    assert "Dedupe holds: 2 demo leads before, 2 after" in text
    assert "Sam opted out: audit shows opt_out, 0 further touches" in text

    # Priya: noon enquiry, quiet, touch 1 at 16:00, booked from it.
    priya = _lead_by_name(store, "Priya")
    assert priya.stage == Stage.BOOKED
    assert priya.score_total == 75
    assert priya.score_band == "WARM"
    assert [a.service for a in store.list_appointments() if a.lead_id == priya.id] == [
        "Teeth whitening"
    ]
    assert [a.start for a in store.list_appointments() if a.lead_id == priya.id] == [
        "2026-11-11T09:00:00"
    ]
    touch_1 = [
        row for row in store.list_followups(lead_id=priya.id) if row.touch_index == 1
    ]
    assert any(row.status == "sent" for row in touch_1)
    assert any(row.due_at == "2026-11-10T16:00:00+00:00" for row in touch_1)

    # Sarah: after-hours enquiry booked Thursday morning, score shown
    # with all six components, and the components add up to the total.
    sarah = _lead_by_name(store, "Sarah")
    assert sarah.stage == Stage.BOOKED
    assert sarah.score_total == 70
    assert sarah.score_band == "WARM"
    assert set(sarah.score_components) == {
        "service_fit",
        "urgency",
        "contact",
        "completeness",
        "value",
        "engagement",
    }
    assert sum(sarah.score_components.values()) == sarah.score_total
    assert [
        (a.service, a.start) for a in store.list_appointments() if a.lead_id == sarah.id
    ] == [("Crown fitting", "2026-11-12T09:00:00")]

    # The seeded busy block is real: Thursday 10:30 is taken, which
    # is why the crown offer skips 10:00 and 10:30.
    assert any(
        a.service == "Check-up and clean" and a.start == "2026-11-12T10:30:00"
        for a in store.list_appointments()
    )

    # Sam: STOP is audited and nothing further is scheduled for him.
    sam = _lead_by_name(store, "Sam")
    assert sam.state.get("opted_out") is True
    assert store.list_followups(lead_id=sam.id, status="scheduled") == []
    assert any(row.action == "opt_out" for row in store.list_audit(lead_id=sam.id))

    # Nothing is left dangling: no scheduled follow-up survives the
    # scenario (both bookings cancelled theirs, STOP cancelled his).
    assert store.list_followups(status="scheduled") == []

    # The Wednesday 08:00 summary: stages, bands, the booking list,
    # overdue and handed-off leads, and the opt-out.
    assert "Daily summary - BrightSmile Dental - Wednesday 2026-11-11" in text
    assert "BOOKED: 3" in result.summary
    assert "CONTACTED: 1" in result.summary
    assert "WARM: 2" in result.summary
    assert "Wednesday 09:00 - Teeth whitening - Priya" in result.summary
    assert "Thursday 09:00 - Crown fitting - Sarah" in result.summary
    assert "Thursday 10:30 - Check-up and clean - Existing patient" in result.summary
    assert "Overdue: none" in result.summary
    assert "Handed off: none" in result.summary
    assert "Opted out: Sam" in result.summary


def test_demo_is_deterministic():
    first = run_demo(print_fn=lambda line: None)
    second = run_demo(print_fn=lambda line: None)
    assert first.transcript == second.transcript
    assert first.summary == second.summary


# -- the booked-lead acknowledgement (found by the demo) -------------


def test_booked_lead_re_message_is_acknowledged_not_reoffered():
    engine, store, _ = build_demo_world(SimulatedChannel())
    engine.handle_inbound(
        "sarah", "do you have anything Thursday morning, my crown is aching"
    )
    engine.handle_inbound("sarah", "I'm Sarah")
    engine.handle_inbound("sarah", "07123 456789")
    engine.handle_inbound("sarah", "Thursday 09:00 works for me")
    sarah = _lead_by_name(store, "Sarah")
    assert sarah.stage == Stage.BOOKED

    reply = engine.handle_inbound("sarah", "Thanks! See you Thursday")
    assert reply is not None
    assert "already booked in for Crown fitting on Thursday 09:00" in reply
    # No re-offer, no second appointment, no new follow-up sequence.
    assert "these times are free" not in reply
    assert _lead_by_name(store, "Sarah").stage == Stage.BOOKED
    assert len([a for a in store.list_appointments() if a.lead_id == sarah.id]) == 1
    assert store.list_followups(lead_id=sarah.id, status="scheduled") == []


def test_booked_lead_saying_stop_still_opts_out():
    engine, store, _ = build_demo_world(SimulatedChannel())
    engine.handle_inbound(
        "sarah", "do you have anything Thursday morning, my crown is aching"
    )
    engine.handle_inbound("sarah", "I'm Sarah")
    engine.handle_inbound("sarah", "07123 456789")
    engine.handle_inbound("sarah", "Thursday 09:00 works for me")
    reply = engine.handle_inbound("sarah", "STOP")
    assert reply is not None
    assert "stopped automated messages" in reply
    assert _lead_by_name(store, "Sarah").state.get("opted_out") is True


# -- interactive mode ------------------------------------------------


def test_demo_interactive_books_through_console():
    script = "\n".join(
        [
            "do you have anything Thursday morning, my crown is aching",
            "I'm Alex",
            "alex@example.com",
            "Thursday 09:00 works for me",
            "",
        ]
    )
    output = io.StringIO()
    console = ConsoleChannel(io.StringIO(script), output)
    engine, store, _ = build_demo_world(SimulatedChannel())
    assert (
        run_interactive(engine=engine, console=console, print_fn=lambda line: None) == 0
    )
    shown = output.getvalue()
    assert "You're booked in for Crown fitting on Thursday 09:00." in shown
    alex = _lead_by_name(store, "Alex")
    assert alex.stage == Stage.BOOKED
    assert [
        (a.service, a.start) for a in store.list_appointments() if a.lead_id == alex.id
    ] == [("Crown fitting", "2026-11-12T09:00:00")]


def test_demo_interactive_eof_ends_session():
    output = io.StringIO()
    console = ConsoleChannel(io.StringIO(""), output)
    engine, _, _ = build_demo_world(SimulatedChannel())
    assert (
        run_interactive(engine=engine, console=console, print_fn=lambda line: None) == 0
    )
    assert output.getvalue() == ""


# -- the daily summary -----------------------------------------------


def _summary_engine():
    """Build an engine on a fresh store with a mutable clock."""
    holder = {"now": TUESDAY}
    store = MemoryStore()
    calendar = LocalCalendar(store, PACK, clock=lambda: holder["now"])
    engine = ReceptionEngine(
        pack=PACK,
        store=store,
        calendar=calendar,
        responder=RuleResponder(),
        channel=SimulatedChannel(),
        clock=lambda: holder["now"],
    )
    return engine, store


def test_daily_summary_lists_overdue_and_handed_off_leads():
    engine, store = _summary_engine()
    engine.handle_inbound("mia", "Hi, I'm Mia. I'd like a check-up")
    engine.handle_inbound(
        "omar", "Hi, I'm Omar. I'm in severe pain and my face is swelling"
    )
    summary = render_daily_summary(engine)
    assert "CONTACTED: 1" in summary
    assert "Overdue: Mia" in summary
    assert "Handed off: Omar" in summary
    assert "Opted out: none" in summary


def test_daily_summary_empty_store():
    engine, _ = _summary_engine()
    summary = render_daily_summary(engine)
    assert "BOOKED: 0" in summary
    assert "Bookings:\n  none" in summary
    assert "Overdue: none" in summary


# -- the simulated clock ----------------------------------------------


def test_simulated_clock_set_and_now():
    clock = SimulatedClock(TUESDAY)
    assert clock.now() == TUESDAY
    later = datetime(2026, 11, 11, 8, 0, tzinfo=UTC)
    clock.set(later)
    assert clock.now() == later


# -- the CLI ----------------------------------------------------------


def test_demo_cli_runs_scripted_scenario(capsys):
    assert cli.main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "First60 demo - BrightSmile Dental (fictional)." in out
    assert "You're booked in for Crown fitting on Thursday 09:00." in out
    assert "Daily summary - BrightSmile Dental - Wednesday 2026-11-11" in out


def test_demo_cli_interactive(monkeypatch, capsys):
    script = "\n".join(
        [
            "do you have anything Thursday morning, my crown is aching",
            "I'm Alex",
            "alex@example.com",
            "Thursday 09:00 works for me",
            "",
        ]
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(script))
    assert cli.main(["demo", "--interactive"]) == 0
    out = capsys.readouterr().out
    assert "First60 demo - interactive mode." in out
    assert "You're booked in for Crown fitting on Thursday 09:00." in out


def test_summary_cli_on_empty_store(tmp_path, capsys):
    db = tmp_path / "empty.db"
    assert cli.main(["summary", "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "Daily summary - BrightSmile Dental" in out
    assert "BOOKED: 0" in out
    assert db.exists()


def test_summary_cli_invalid_pack():
    from first60.config import PackError

    with pytest.raises(PackError, match="pack"):
        cli.main(["summary", "--pack", "no-such-pack"])
