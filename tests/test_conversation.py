"""Full-conversation proof for build step 4 (DESIGN.md section 14).

The conversation engine itself lands in build step 5. Until then,
this module drives a scripted conversation through the real step-4
pieces (pipeline, handoff, calendar, store, responders) with a small
test-local driver, proving the pieces compose into a full
conversation: once with the LLM path disabled (rule responder only)
and once with it stubbed.

The driver is deliberately thin: it applies each message, checks
handoff and opt-out, asks the next question, offers real free slots
from the calendar, and books the chosen slot. All decisions come
from the pipeline; the responder only phrases them.
"""

import json
import threading
from dataclasses import asdict, replace
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from first60.calendar.local import LocalCalendar
from first60.config import load_builtin_pack
from first60.models import new_lead, new_message
from first60.pipeline.extract import detect_opt_out
from first60.pipeline.handoff import check_handoff
from first60.pipeline.qualify import (
    answered_required,
    apply_message,
    initial_state,
    is_qualified,
    next_question,
)
from first60.pipeline.scoring import ScoringInput, score_lead
from first60.pipeline.stages import Stage
from first60.respond.base import Decision, FactSheet
from first60.respond.llm import LLMResponder
from first60.respond.rules import RuleResponder
from first60.store.memory import MemoryStore

PACK = load_builtin_pack("dental")
FACTS = FactSheet.from_pack(PACK)

# The demo scenario's clock: Tuesday 21:40, Thursday morning slots.
TUESDAY = datetime(2026, 11, 10, 21, 40)
THURSDAY = date(2026, 11, 12)


class _Driver:
    """Test-local conversation driver (step-5 engine predecessor)."""

    def __init__(self, responder):
        self.responder = responder
        self.store = MemoryStore()
        self.calendar = LocalCalendar(self.store, PACK, clock=lambda: TUESDAY)
        self.state = initial_state()
        self.stage = Stage.NEW
        self.lead = self.store.create_lead(
            new_lead(lead_id="lead-1", channel="simulated")
        )
        self.replies: list[str] = []
        self.paused = False
        self.offered: tuple[str, ...] = ()
        self.booked_start: datetime | None = None
        self.score_band = ""

    def _move(self, target: Stage) -> None:
        if target != self.stage:
            self.lead = self.store.move_stage(self.lead.id, target)
            self.stage = target

    def _save_state(self) -> None:
        answered, total = answered_required(self.state, PACK)
        service = next((s for s in PACK.services if s.name == self.state.service), None)
        score = score_lead(
            ScoringInput(
                service_match=self.state.service_match,
                urgency=self.state.urgency,
                name_known="name" in self.state.answers,
                contact_known="contact" in self.state.answers,
                questions_answered=answered,
                questions_total=total,
                value_tier=service.value_tier if service else None,
            )
        )
        self.score_band = score.band
        self.lead = self.store.update_lead(
            replace(
                self.lead,
                answers=dict(self.state.answers),
                service=self.state.service,
                urgency=self.state.urgency,
                score_total=score.total,
                score_band=score.band,
                score_components=dict(score.components),
                state=asdict(self.state),
            )
        )

    def handle(self, text: str) -> str:
        """Handle one inbound message and return the reply sent."""
        assert not self.paused, "driver is paused after handoff/opt-out"
        self.store.add_message(
            new_message(lead_id=self.lead.id, direction="in", text=text)
        )
        self.state = apply_message(self.state, PACK, text)
        self._save_state()

        # Opt-out wins over every other check: a STOP is not a stuck
        # conversation, and the lead must hear the opt-out confirmation.
        if detect_opt_out(text):
            self.paused = True
            reply = self.responder.render(
                Decision(
                    kind="opt_out",
                    lead_name=self.state.answers.get("name", ""),
                ),
                FACTS,
            )
            return self._send(reply)

        handoff = check_handoff(PACK, self.state, text)
        if handoff.triggered:
            self.paused = True
            reply = self.responder.render(
                Decision(kind="handoff", handoff_text=handoff.reply_text), FACTS
            )
            return self._send(reply)

        if not is_qualified(self.state, PACK):
            question = next_question(self.state, PACK)
            kind = "greet" if self.state.replies == 1 else "ask"
            reply = self.responder.render(
                Decision(kind=kind, question=question.text if question else ""),
                FACTS,
            )
            self._move(Stage.CONTACTED)
            return self._send(reply)

        if self.booked_start is None:
            chosen = next((slot for slot in self.offered if slot in text), None)
            if chosen is None:
                service = next(s for s in PACK.services if s.name == self.state.service)
                slots = self.calendar.free_slots(THURSDAY, service.duration_minutes)
                self.offered = tuple(slot.strftime("%A %H:%M") for slot in slots[:3])
                reply = self.responder.render(
                    Decision(
                        kind="offer_slots",
                        service=self.state.service or "",
                        slots=self.offered,
                        lead_name=self.state.answers.get("name", ""),
                    ),
                    FACTS,
                )
                self._move(Stage.QUALIFIED)
                return self._send(reply)
            day = THURSDAY
            hour, minute = (int(part) for part in chosen.split()[1].split(":"))
            start = datetime(day.year, day.month, day.day, hour, minute)
            service = next(s for s in PACK.services if s.name == self.state.service)
            appointment = self.calendar.book(
                lead_id=self.lead.id,
                service=service.name,
                start=start,
                duration_minutes=service.duration_minutes,
                idempotency_key=f"{self.lead.id}-{chosen}",
            )
            self.booked_start = start
            reply = self.responder.render(
                Decision(
                    kind="confirm_booking",
                    service=service.name,
                    appointment=start.strftime("%A %H:%M"),
                ),
                FACTS,
            )
            self._move(Stage.BOOKED)
            assert appointment.start == start.isoformat()
            return self._send(reply)

        reply = self.responder.render(
            Decision(kind="acknowledge", detail="Thanks, we'll see you then."),
            FACTS,
        )
        return self._send(reply)

    def _send(self, reply: str) -> str:
        self.store.add_message(
            new_message(lead_id=self.lead.id, direction="out", text=reply)
        )
        self.replies.append(reply)
        return reply


def test_full_conversation_rules_only():
    driver = _Driver(RuleResponder())
    first = driver.handle("do you have anything Thursday morning, my crown is aching")
    assert "BrightSmile Dental" in first
    assert "What is your name?" in first

    second = driver.handle("I'm Sarah")
    assert "What is the best phone number or email to reach you on?" in second

    third = driver.handle("07123 456789")
    assert "Thursday 09:00" in third
    assert "Thursday 09:30" in third
    assert "Crown fitting" in third
    assert driver.stage == Stage.QUALIFIED
    assert driver.score_band in ("WARM", "HOT")

    fourth = driver.handle("Thursday 09:00 works for me")
    assert "You're booked in for Crown fitting on Thursday 09:00." in fourth
    assert driver.stage == Stage.BOOKED
    assert driver.booked_start == datetime(2026, 11, 12, 9, 0)
    appointments = driver.store.list_appointments(THURSDAY)
    assert len(appointments) == 1
    assert appointments[0].service == "Crown fitting"
    lead = driver.store.get_lead("lead-1")
    assert lead.score_band == driver.score_band
    assert lead.answers["name"] == "Sarah"


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
        driver = _Driver(responder)
        first = driver.handle(
            "do you have anything Thursday morning, my crown is aching"
        )
        assert first.startswith("Hello! Thanks for messaging BrightSmile.")
        driver.handle("I'm Sarah")
        third = driver.handle("07123 456789")
        assert "Thursday 09:00" in third
        fourth = driver.handle("Thursday 09:00 works for me")
        # The stub invented a price, so the confirmation falls back to
        # the template, which still carries the booked slot verbatim.
        assert "You're booked in for Crown fitting on Thursday 09:00." in fourth
        assert reasons == ["price_not_on_fact_sheet"]
        assert driver.stage == Stage.BOOKED
    finally:
        server.shutdown()
        server.server_close()


def test_conversation_emergency_hands_off():
    driver = _Driver(RuleResponder())
    reply = driver.handle("I'm in severe pain and my face is swelling")
    assert PACK.handoff.emergency_instruction in reply
    assert driver.paused
    assert driver.stage == Stage.NEW


def test_conversation_opt_out_stops_automation():
    driver = _Driver(RuleResponder())
    driver.handle("do you have anything Thursday morning")
    reply = driver.handle("STOP")
    assert "stopped automated messages" in reply
    assert driver.paused
