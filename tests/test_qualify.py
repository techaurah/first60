"""Tests for the qualification question flow."""

from __future__ import annotations

import pytest

from first60.config import load_builtin_pack
from first60.pipeline.qualify import (
    answered_required,
    apply_message,
    completeness,
    initial_state,
    is_qualified,
    next_question,
)


@pytest.fixture(scope="module")
def dental():
    return load_builtin_pack("dental")


@pytest.fixture(scope="module")
def plumber():
    return load_builtin_pack("plumber")


def test_next_question_follows_pack_order(dental) -> None:
    """Questions are asked in pack order, first unanswered first."""
    state = initial_state()
    assert next_question(state, dental).id == "service"
    state = apply_message(state, dental, "I need a crown fitting")
    assert next_question(state, dental).id == "timeline"
    state = apply_message(state, dental, "Thursday morning please")
    assert next_question(state, dental).id == "name"


def test_first_message_answers_service_and_timeline(dental) -> None:
    """One volunteered message can answer two questions at once."""
    state = apply_message(
        initial_state(),
        dental,
        "do you have anything Thursday morning, my crown is aching",
    )
    assert state.answers["service"] == "Crown fitting"
    assert state.service == "Crown fitting"
    assert state.service_match == "related"
    assert state.answers["timeline"] == "thursday"
    assert state.urgency == "this_week"
    assert state.consecutive_failures == 0
    assert state.stuck is False


def test_free_text_question_accepts_any_reply(plumber) -> None:
    """Address, budget and symptom questions take the raw reply."""
    state = initial_state()
    for message in [
        "my boiler has broken, I need a repair",
        "today please",
        "12 Oak Road, Springfield",
    ]:
        state = apply_message(state, plumber, message)
    assert state.answers["address"] == "12 Oak Road, Springfield"
    assert state.consecutive_failures == 0


def test_two_failures_on_same_question_marks_stuck(dental) -> None:
    """Two replies that dodge the current question mark the lead stuck."""
    state = initial_state()
    state = apply_message(state, dental, "hello")
    assert state.consecutive_failures == 1
    assert state.stuck is False
    state = apply_message(state, dental, "are you open on Sundays?")
    assert state.consecutive_failures == 2
    assert state.stuck is True


def test_failure_count_resets_on_success(dental) -> None:
    """One good answer clears the failure count."""
    state = initial_state()
    state = apply_message(state, dental, "hello")
    assert state.consecutive_failures == 1
    state = apply_message(state, dental, "I need a check-up and clean")
    assert state.consecutive_failures == 0
    assert state.stuck is False


def test_is_qualified_needs_all_required(dental) -> None:
    """Optional questions never block qualification."""
    state = initial_state()
    for message in [
        "I need teeth whitening",
        "next week",
        "my name is Sarah Jones",
        "07700 900123",
    ]:
        state = apply_message(state, dental, message)
    assert is_qualified(state, dental) is True
    assert completeness(state, dental) == 1.0
    assert answered_required(state, dental) == (4, 4)
    # The optional pain question is still open, but the lead is qualified.
    assert next_question(state, dental).id == "pain"


def test_urgency_only_escalates(dental) -> None:
    """A later 'it can wait' never downgrades an earlier 'today'."""
    state = apply_message(initial_state(), dental, "I need a check-up today")
    assert state.urgency == "today"
    state = apply_message(state, dental, "actually next week is fine too")
    assert state.urgency == "today"


def test_service_upgrades_related_to_full(dental) -> None:
    """A later message naming the service fully upgrades the match."""
    state = apply_message(initial_state(), dental, "my crown is aching")
    assert state.service_match == "related"
    state = apply_message(state, dental, "yes, a crown fitting")
    assert state.service == "Crown fitting"
    assert state.service_match == "full"


def test_empty_messages_are_ignored(dental) -> None:
    """Blank messages change nothing, not even the reply count."""
    state = apply_message(initial_state(), dental, "   ")
    assert state == initial_state()
