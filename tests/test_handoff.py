"""Handoff rules (DESIGN.md section 8, test plan section 11).

Each trigger class, the safety template content, the automation
pause, and the owner summary contents.
"""

from first60.config import load_builtin_pack
from first60.pipeline.handoff import check_handoff
from first60.pipeline.qualify import apply_message, initial_state

PACK = load_builtin_pack("dental")


def _state_after(*messages: str):
    state = initial_state()
    for message in messages:
        state = apply_message(state, PACK, message)
    return state


def test_emergency_term_triggers_safety_template():
    state = _state_after("Hi, my crown is aching")
    decision = check_handoff(PACK, state, "I have severe pain and swelling")
    assert decision.triggered
    assert decision.reason == "emergency"
    assert decision.matched_term == "severe pain"
    assert decision.pause_automation
    # The pack's emergency instruction appears verbatim, never advice.
    assert PACK.handoff.emergency_instruction in decision.reply_text
    assert "BrightSmile Dental" in decision.reply_text
    assert "passed your message to the team" in decision.reply_text


def test_emergency_term_from_pack_not_bare_word():
    # "swelling" is a pack term; a bare "emergency" with no pack term
    # is not an emergency handoff by itself.
    state = initial_state()
    decision = check_handoff(PACK, state, "this is an emergency")
    assert not decision.triggered


def test_handoff_only_pack_item_triggers():
    state = _state_after("I need a crown fitting")
    decision = check_handoff(PACK, state, "this is about an insurance claim")
    assert decision.triggered
    assert decision.reason == "handoff_only"
    assert decision.matched_term == "insurance claim"
    assert decision.pause_automation
    assert "passed this to the team" in decision.reply_text


def test_complaint_and_refund_trigger():
    state = initial_state()
    decision = check_handoff(PACK, state, "I want a refund, this is unacceptable")
    assert decision.triggered
    assert decision.reason == "complaint"
    assert decision.matched_term == "unacceptable"
    assert decision.pause_automation


def test_legal_term_triggers():
    state = initial_state()
    decision = check_handoff(PACK, state, "my lawyer will be in touch")
    assert decision.triggered
    assert decision.reason == "complaint"
    assert decision.matched_term == "lawyer"


def test_human_request_triggers():
    state = initial_state()
    decision = check_handoff(PACK, state, "can I speak to a real person please")
    assert decision.triggered
    assert decision.reason == "human_request"
    assert decision.pause_automation


def test_stuck_conversation_triggers():
    # Two consecutive failures on the same structured question.
    state = _state_after("hello", "not saying")
    assert state.stuck
    decision = check_handoff(PACK, state, "not saying")
    assert decision.triggered
    assert decision.reason == "stuck"
    assert decision.pause_automation


def test_priority_emergency_beats_complaint():
    state = initial_state()
    decision = check_handoff(PACK, state, "this is terrible, I have severe pain")
    assert decision.reason == "emergency"


def test_no_trigger_returns_empty_decision():
    state = _state_after("do you have anything Thursday morning")
    decision = check_handoff(PACK, state, "do you have anything Thursday morning")
    assert not decision.triggered
    assert decision.reason is None
    assert decision.reply_text == ""
    assert decision.summary == ""
    assert not decision.pause_automation


def test_owner_summary_contents():
    state = _state_after(
        "Hi, I'm Sarah, my number is 07123 456789",
        "I need a crown fitting",
    )
    decision = check_handoff(PACK, state, "can I speak to a human please")
    assert "Handoff (human_request)" in decision.summary
    assert "Sarah" in decision.summary
    assert "07123 456789" in decision.summary
    assert "Crown fitting" in decision.summary
    assert "can I speak to a human please" in decision.summary
    assert "Automation paused for this lead." in decision.summary
