"""Full-conversation proof for build step 5 (DESIGN.md section 14).

The step-4 test-local driver is gone: these tests drive the real
:class:`first60.engine.ReceptionEngine` through the same scripted
conversation, once with the LLM path disabled (rule responder only)
and once with it stubbed. All decisions still come from the
pipeline; the responder only phrases them, and the engine audits
every side effect.
"""

import json
import threading
from datetime import UTC, date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from first60.calendar.local import LocalCalendar
from first60.channels.simulated import SimulatedChannel
from first60.config import load_builtin_pack
from first60.engine import ReceptionEngine
from first60.pipeline.stages import Stage
from first60.respond.base import FactSheet
from first60.respond.llm import LLMResponder
from first60.respond.rules import RuleResponder
from first60.store.memory import MemoryStore

PACK = load_builtin_pack("dental")
FACTS = FactSheet.from_pack(PACK)

# The demo scenario's clock: Tuesday 21:40, Thursday morning slots.
# Europe/London is on GMT in November, so local and UTC agree here.
TUESDAY = datetime(2026, 11, 10, 21, 40, tzinfo=UTC)
THURSDAY = date(2026, 11, 12)


def make_engine(responder):
    """Build an engine on a fresh store, calendar and simulated channel."""
    store = MemoryStore()
    channel = SimulatedChannel()
    calendar = LocalCalendar(store, PACK, clock=lambda: TUESDAY)
    engine = ReceptionEngine(
        pack=PACK,
        store=store,
        calendar=calendar,
        responder=responder,
        channel=channel,
        clock=lambda: TUESDAY,
    )
    return engine, store, channel


def lead_of(store):
    """Return the single lead in ``store`` (these tests run one lead)."""
    leads = store.list_leads()
    assert len(leads) == 1
    return leads[0]


def test_full_conversation_rules_only():
    engine, store, channel = make_engine(RuleResponder())
    first = engine.handle_inbound(
        "sarah", "do you have anything Thursday morning, my crown is aching"
    )
    assert first is not None
    assert "BrightSmile Dental" in first
    assert "What is your name?" in first

    second = engine.handle_inbound("sarah", "I'm Sarah")
    assert second is not None
    assert "What is the best phone number or email to reach you on?" in second

    third = engine.handle_inbound("sarah", "07123 456789")
    assert third is not None
    assert "Thursday 09:00" in third
    assert "Thursday 09:30" in third
    assert "Crown fitting" in third
    assert lead_of(store).stage == Stage.QUALIFIED
    assert lead_of(store).score_band in ("WARM", "HOT")

    fourth = engine.handle_inbound("sarah", "Thursday 09:00 works for me")
    assert fourth is not None
    assert "You're booked in for Crown fitting on Thursday 09:00." in fourth
    assert lead_of(store).stage == Stage.BOOKED
    appointments = store.list_appointments(THURSDAY)
    assert len(appointments) == 1
    assert appointments[0].service == "Crown fitting"
    lead = lead_of(store)
    assert lead.score_band in ("WARM", "HOT")
    assert lead.answers["name"] == "Sarah"
    # Every outbound reply went through the channel, in order.
    assert [text for _, text in channel.outbox] == [first, second, third, fourth]
    # The booking consented to reminders and cancelled the sequence.
    assert lead.state.get("reminders_consented") is True
    assert store.list_followups(status="scheduled") == []
    # The audit log answers what happened, in order.
    actions = [row.action for row in store.list_audit()]
    assert "reply_sent" in actions
    assert "stage_move" in actions
    assert "booking" in actions


class _StubHandler(BaseHTTPRequestHandler):
    responses: list[dict] = []

    def log_message(self, *args):  # keep test output clean
        pass

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        body = _StubHandler.responses.pop(0)
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _completion(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def test_full_conversation_llm_stubbed_with_fallback():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    _StubHandler.responses = [
        _completion("Hello! Thanks for messaging BrightSmile. What is your name?"),
        _completion("Lovely, Sarah. What is the best number to reach you on?"),
        _completion(
            "Thanks Sarah. For Crown fitting, these times are free: "
            "Thursday 09:00, Thursday 09:30, Thursday 10:00. "
            "Which works best for you?"
        ),
        _completion("That will be £450. Shall I book Thursday 09:00?"),
    ]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        reasons: list[str] = []
        responder = LLMResponder(
            f"http://127.0.0.1:{server.server_address[1]}",
            on_fallback=reasons.append,
        )
        engine, store, _ = make_engine(responder)
        first = engine.handle_inbound(
            "sarah", "do you have anything Thursday morning, my crown is aching"
        )
        assert first is not None
        assert first.startswith("Hello! Thanks for messaging BrightSmile.")
        engine.handle_inbound("sarah", "I'm Sarah")
        third = engine.handle_inbound("sarah", "07123 456789")
        assert third is not None
        assert "Thursday 09:00" in third
        fourth = engine.handle_inbound("sarah", "Thursday 09:00 works for me")
        # The stub invented a price, so the confirmation falls back to
        # the template, which still carries the booked slot verbatim.
        assert fourth is not None
        assert "You're booked in for Crown fitting on Thursday 09:00." in fourth
        assert reasons == ["price_not_on_fact_sheet"]
        assert lead_of(store).stage == Stage.BOOKED
    finally:
        server.shutdown()
        server.server_close()


def test_conversation_emergency_hands_off():
    engine, store, _ = make_engine(RuleResponder())
    reply = engine.handle_inbound("sarah", "I'm in severe pain and my face is swelling")
    assert reply is not None
    assert PACK.handoff.emergency_instruction in reply
    assert lead_of(store).state.get("automation_paused") is True
    # A paused lead hears nothing more from the engine.
    assert engine.handle_inbound("sarah", "hello, are you there?") is None
    assert store.list_followups(status="scheduled") == []


def test_conversation_opt_out_stops_automation():
    engine, store, _ = make_engine(RuleResponder())
    engine.handle_inbound("sarah", "do you have anything Thursday morning")
    reply = engine.handle_inbound("sarah", "STOP")
    assert reply is not None
    assert "stopped automated messages" in reply
    assert lead_of(store).state.get("opted_out") is True
    assert engine.handle_inbound("sarah", "actually, one more question") is None


def test_engine_dry_run_withholds_the_reply():
    engine, store, channel = make_engine(RuleResponder())
    engine.write_mode = "dry_run"
    reply = engine.handle_inbound(
        "sarah", "do you have anything Thursday morning, my crown is aching"
    )
    # Nothing was sent, so the caller gets no reply text either.
    assert reply is None
    assert channel.outbox == []
    # The would-be send is audited, and no outbound message is recorded:
    # a dry run must not reset the follow-up clock.
    actions = [row.action for row in store.list_audit()]
    assert "reply_would_send" in actions
    messages = store.list_messages(lead_of(store).id)
    assert messages and all(m.direction == "in" for m in messages)
