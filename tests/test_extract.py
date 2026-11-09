"""Tests for slot extraction from inbound messages."""

from __future__ import annotations

import pytest

from first60.config import load_builtin_pack
from first60.pipeline.extract import (
    detect_human_request,
    detect_opt_out,
    extract_contact,
    extract_email,
    extract_name,
    extract_phone,
    extract_timeline,
    match_service,
)


@pytest.fixture(scope="module")
def dental():
    return load_builtin_pack("dental")


@pytest.fixture(scope="module")
def plumber():
    return load_builtin_pack("plumber")


def test_match_service_full_name(dental) -> None:
    """The full service name is a full match."""
    service, kind = match_service("I need a crown fitting please", dental)
    assert service is not None
    assert service.name == "Crown fitting"
    assert kind == "full"


def test_match_service_partial_word_is_related(dental) -> None:
    """One distinctive word of a service name is a related match."""
    service, kind = match_service("my crown is aching", dental)
    assert service is not None
    assert service.name == "Crown fitting"
    assert kind == "related"


def test_match_service_prefers_most_words_matched(plumber) -> None:
    """When two services share a word, the one with more words matched wins."""
    service, kind = match_service("my boiler has broken, I need a repair", plumber)
    assert service is not None
    assert service.name == "Boiler repair"
    assert kind == "full"
    service, kind = match_service("just the boiler, please", plumber)
    assert service is not None
    assert service.name == "Boiler service"
    assert kind == "full"


def test_match_service_no_match_returns_none(dental) -> None:
    """A message naming no service matches nothing."""
    service, kind = match_service("hello, are you open today?", dental)
    assert service is None
    assert kind == "none"


@pytest.mark.parametrize(
    "text",
    ["I need something today", "ASAP please", "this is urgent", "right now"],
)
def test_timeline_today_phrases(text: str, dental) -> None:
    """Today phrases (today, ASAP, urgent, right now) map to today."""
    timeline = extract_timeline(text, dental)
    assert timeline.urgency == "today"


@pytest.mark.parametrize(
    "text,detail",
    [
        ("do you have anything Thursday morning?", "thursday"),
        ("can I come tomorrow?", "tomorrow"),
        ("sometime this week would work", "this week"),
    ],
)
def test_timeline_weekday_and_this_week(text: str, detail: str, dental) -> None:
    """Weekday names, tomorrow and this week map to this week."""
    timeline = extract_timeline(text, dental)
    assert timeline.urgency == "this_week"
    assert timeline.detail == detail


@pytest.mark.parametrize("text", ["next week is fine", "whenever suits", "no rush"])
def test_timeline_flexible_phrases(text: str, dental) -> None:
    """Next week, whenever and no rush map to flexible."""
    timeline = extract_timeline(text, dental)
    assert timeline.urgency == "flexible"


def test_timeline_pack_emergency_terms(plumber, dental) -> None:
    """A pack emergency term beats every other timeline signal."""
    assert extract_timeline("there is a gas smell in the kitchen", plumber).urgency == (
        "emergency"
    )
    assert extract_timeline("I have severe pain in my tooth", dental).urgency == (
        "emergency"
    )
    # A bare "emergency" word with no pack term is today, not emergency.
    assert extract_timeline("this is an emergency", dental).urgency == "today"


def test_timeline_unknown_when_no_signal(dental) -> None:
    """A message with no timeline wording is unknown."""
    timeline = extract_timeline("hello, I have a question", dental)
    assert timeline.urgency == "unknown"
    assert timeline.detail == ""


def test_extract_phone_and_email() -> None:
    """Phone numbers keep their formatting; emails are found anywhere."""
    assert extract_phone("call me on 07700 900123 please") == "07700 900123"
    assert extract_phone("my number is +44 7700 900 123") == "+44 7700 900 123"
    assert extract_phone("no number here") is None
    assert extract_email("reach me at sarah.jones@example.com") == (
        "sarah.jones@example.com"
    )
    assert extract_email("no email here") is None
    contact = extract_contact("I'm Sarah, 07700 900123, sarah@example.com")
    assert contact.name == "Sarah"
    assert contact.phone == "07700 900123"
    assert contact.email == "sarah@example.com"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Hi, my name is Sarah Jones", "Sarah Jones"),
        ("I'm John", "John"),
        ("I am Dr Patel", "Dr Patel"),
        ("call me Mike", "Mike"),
        ("I'm in pain", None),
        ("I'm free tomorrow", None),
        ("hello there", None),
    ],
)
def test_extract_name_patterns_and_rejections(text: str, expected: str | None) -> None:
    """Name patterns capture names and reject non-name wording."""
    assert extract_name(text) == expected


@pytest.mark.parametrize(
    "text",
    ["STOP", "stop messaging me", "please unsubscribe", "take me off your list"],
)
def test_detect_opt_out(text: str) -> None:
    """STOP, unsubscribe and stop-messaging wording opts the lead out."""
    assert detect_opt_out(text) is True


def test_detect_opt_out_ignores_stopcock() -> None:
    """Whole-word matching: 'stopcock' is not STOP."""
    assert detect_opt_out("turn off the water at the stopcock") is False
    assert detect_opt_out("hello, I have a question") is False


@pytest.mark.parametrize(
    "text",
    [
        "can I speak to a human please",
        "I want a real person",
        "let me talk to someone",
    ],
)
def test_detect_human_request(text: str) -> None:
    """Human-request wording is recognised in its common forms."""
    assert detect_human_request(text) is True


def test_detect_human_request_ignores_estate_agent() -> None:
    """'Estate agent' is a job title, not a request for a human."""
    assert detect_human_request("I am an estate agent") is False
    assert detect_human_request("hello, I have a question") is False
