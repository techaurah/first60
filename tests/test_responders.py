"""Responders (DESIGN.md section 6, test plan section 11).

Template rendering of every decision type, plus the LLM responder
against a stub HTTP server (no network): slot-verbatim validation,
fact-sheet violation fallback, empty/overlong fallback, and the
fallback audit callback.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from first60.config import load_builtin_pack
from first60.respond.base import Decision, FactSheet
from first60.respond.llm import LLMResponder
from first60.respond.rules import RuleResponder

PACK = load_builtin_pack("dental")
FACTS = FactSheet.from_pack(PACK)
RULES = RuleResponder()


def _decision(**kwargs) -> Decision:
    base = {
        "kind": "ask",
        "question": "Which treatment are you interested in?",
        "service": "Crown fitting",
        "slots": ("Thursday 09:00", "Thursday 09:30", "Thursday 10:00"),
        "appointment": "Thursday 09:00",
        "lead_name": "Sarah",
        "handoff_text": "Safety template text.",
        "detail": "we still have Thursday morning free",
    }
    base.update(kwargs)
    return Decision(**base)


# -- RuleResponder: every decision type ------------------------------


def test_rule_greet_with_first_question():
    text = RULES.render(_decision(kind="greet"), FACTS)
    assert text.startswith("Hi, thanks for messaging BrightSmile Dental.")
    assert "Which treatment are you interested in?" in text


def test_rule_greet_without_question():
    text = RULES.render(_decision(kind="greet", question=""), FACTS)
    assert text == ("Hi, thanks for messaging BrightSmile Dental. How can I help?")


def test_rule_ask_returns_pack_question_verbatim():
    text = RULES.render(_decision(kind="ask"), FACTS)
    assert text == "Which treatment are you interested in?"


def test_rule_offer_slots_verbatim():
    text = RULES.render(_decision(kind="offer_slots"), FACTS)
    assert "Crown fitting" in text
    for slot in ("Thursday 09:00", "Thursday 09:30", "Thursday 10:00"):
        assert slot in text


def test_rule_confirm_booking():
    text = RULES.render(_decision(kind="confirm_booking"), FACTS)
    assert "You're booked in for Crown fitting on Thursday 09:00." in text
    assert "Reply STOP" in text


def test_rule_handoff_passes_safety_text_through():
    text = RULES.render(_decision(kind="handoff"), FACTS)
    assert text == "Safety template text."


def test_rule_follow_up():
    text = RULES.render(_decision(kind="follow_up"), FACTS)
    assert "Hi Sarah, just checking in about Crown fitting." in text
    assert "we still have Thursday morning free" in text
    assert "reply STOP" in text


def test_rule_acknowledge():
    assert RULES.render(_decision(kind="acknowledge"), FACTS) == (
        "we still have Thursday morning free"
    )
    assert RULES.render(_decision(kind="acknowledge", detail=""), FACTS) == (
        "Thanks, noted."
    )


def test_rule_opt_out():
    text = RULES.render(_decision(kind="opt_out"), FACTS)
    assert text.startswith("No problem, Sarah.")
    assert "stopped automated messages" in text


def test_rule_unknown_kind_raises():
    with pytest.raises(ValueError, match="unknown decision kind"):
        RULES.render(_decision(kind="teleport"), FACTS)


def test_fact_sheet_from_pack():
    assert FACTS.business_name == "BrightSmile Dental"
    assert "Crown fitting" in FACTS.services
    assert "Monday 09:00-17:30" in FACTS.hours_text
    assert "Sunday closed" in FACTS.hours_text
    assert FACTS.emergency_instruction == PACK.handoff.emergency_instruction


# -- LLMResponder: stub server ---------------------------------------


class _StubHandler(BaseHTTPRequestHandler):
    """Returns the next canned body from the server's ``responses`` list."""

    responses: list[tuple[int, dict]] = []
    requests: list[dict] = []

    def log_message(self, *args):  # keep test output clean
        pass

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        _StubHandler.requests.append(json.loads(self.rfile.read(length)))
        status, body = _StubHandler.responses.pop(0)
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _completion(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


@pytest.fixture()
def stub_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    _StubHandler.responses = []
    _StubHandler.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _llm(base_url: str, **kwargs) -> LLMResponder:
    return LLMResponder(base_url, **kwargs)


def test_llm_valid_output_used_verbatim(stub_server):
    _StubHandler.responses = [
        (
            200,
            _completion(
                "Hi Sarah, for your crown fitting these times are free: "
                "Thursday 09:00, Thursday 09:30, Thursday 10:00."
            ),
        )
    ]
    responder = _llm(stub_server)
    text = responder.render(_decision(kind="offer_slots"), FACTS)
    assert text == (
        "Hi Sarah, for your crown fitting these times are free: "
        "Thursday 09:00, Thursday 09:30, Thursday 10:00."
    )
    assert responder.last_fallback_reason is None


def test_llm_missing_slot_falls_back_to_template(stub_server):
    _StubHandler.responses = [
        (200, _completion("Thursday morning looks good, let me know."))
    ]
    reasons: list[str] = []
    responder = _llm(stub_server, on_fallback=reasons.append)
    text = responder.render(_decision(kind="offer_slots"), FACTS)
    assert "Thursday 09:00" in text and "Thursday 09:30" in text
    assert reasons == ["slots_missing"]
    assert responder.last_fallback_reason == "slots_missing"


def test_llm_invented_price_falls_back(stub_server):
    _StubHandler.responses = [
        (200, _completion("A crown fitting costs £450. Shall I book you in?"))
    ]
    responder = _llm(stub_server)
    text = responder.render(_decision(kind="ask"), FACTS)
    assert text == "Which treatment are you interested in?"
    assert responder.last_fallback_reason == "price_not_on_fact_sheet"


def test_llm_invented_service_falls_back(stub_server):
    _StubHandler.responses = [
        (200, _completion("We also offer teeth straightening and botox."))
    ]
    responder = _llm(stub_server)
    text = responder.render(_decision(kind="ask"), FACTS)
    assert text == "Which treatment are you interested in?"
    assert responder.last_fallback_reason == "service_not_on_fact_sheet"


def test_llm_known_service_passes(stub_server):
    _StubHandler.responses = [
        (200, _completion("We also offer teeth whitening if you'd like."))
    ]
    responder = _llm(stub_server)
    text = responder.render(_decision(kind="ask"), FACTS)
    assert text == "We also offer teeth whitening if you'd like."
    assert responder.last_fallback_reason is None


def test_llm_empty_output_falls_back(stub_server):
    _StubHandler.responses = [(200, _completion("   "))]
    responder = _llm(stub_server)
    text = responder.render(_decision(kind="ask"), FACTS)
    assert text == "Which treatment are you interested in?"
    assert responder.last_fallback_reason == "empty_response"


def test_llm_overlong_output_falls_back(stub_server):
    _StubHandler.responses = [(200, _completion("x" * 601))]
    responder = _llm(stub_server)
    text = responder.render(_decision(kind="ask"), FACTS)
    assert text == "Which treatment are you interested in?"
    assert responder.last_fallback_reason == "overlong_response"


def test_llm_http_error_falls_back(stub_server):
    _StubHandler.responses = [(500, {"error": "boom"})]
    responder = _llm(stub_server)
    text = responder.render(_decision(kind="ask"), FACTS)
    assert text == "Which treatment are you interested in?"
    assert responder.last_fallback_reason is not None
    assert responder.last_fallback_reason.startswith("llm_request_failed")


def test_llm_from_env_unset_returns_none(monkeypatch):
    monkeypatch.delenv("FIRST60_LLM_BASE_URL", raising=False)
    assert LLMResponder.from_env() is None


def test_llm_from_env_set_returns_responder(monkeypatch):
    monkeypatch.setenv("FIRST60_LLM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("FIRST60_LLM_MODEL", "stub-model")
    responder = LLMResponder.from_env()
    assert responder is not None
    assert responder.model == "stub-model"
