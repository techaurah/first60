"""Tests for pipeline stages, the transition map, and lead dedupe."""

from __future__ import annotations

import pytest

from first60.pipeline.stages import (
    Stage,
    StageTransitionError,
    dedupe_key,
    normalize_email,
    normalize_phone,
    transition,
)

ALLOWED = [
    (Stage.NEW, Stage.CONTACTED),
    (Stage.NEW, Stage.NURTURE),
    (Stage.NEW, Stage.LOST),
    (Stage.CONTACTED, Stage.QUALIFIED),
    (Stage.CONTACTED, Stage.NURTURE),
    (Stage.CONTACTED, Stage.LOST),
    (Stage.QUALIFIED, Stage.BOOKED),
    (Stage.QUALIFIED, Stage.NURTURE),
    (Stage.QUALIFIED, Stage.LOST),
    (Stage.BOOKED, Stage.NURTURE),
    (Stage.BOOKED, Stage.LOST),
    (Stage.NURTURE, Stage.CONTACTED),
    (Stage.NURTURE, Stage.LOST),
    (Stage.LOST, Stage.NURTURE),
]

ILLEGAL = [
    (Stage.NEW, Stage.QUALIFIED),
    (Stage.NEW, Stage.BOOKED),
    (Stage.CONTACTED, Stage.BOOKED),
    (Stage.CONTACTED, Stage.NEW),
    (Stage.QUALIFIED, Stage.NEW),
    (Stage.QUALIFIED, Stage.CONTACTED),
    (Stage.BOOKED, Stage.NEW),
    (Stage.BOOKED, Stage.CONTACTED),
    (Stage.BOOKED, Stage.QUALIFIED),
    (Stage.NURTURE, Stage.QUALIFIED),
    (Stage.NURTURE, Stage.BOOKED),
    (Stage.NURTURE, Stage.NEW),
    (Stage.LOST, Stage.NEW),
    (Stage.LOST, Stage.CONTACTED),
    (Stage.LOST, Stage.QUALIFIED),
    (Stage.LOST, Stage.BOOKED),
]


@pytest.mark.parametrize("current,target", ALLOWED)
def test_allowed_transitions(current: Stage, target: Stage) -> None:
    """Every transition in the design's map succeeds."""
    assert transition(current, target) == target


@pytest.mark.parametrize("current,target", [pair for pair in ILLEGAL])
def test_illegal_transitions_raise(current: Stage, target: Stage) -> None:
    """Any move outside the map raises the named error code."""
    with pytest.raises(StageTransitionError) as excinfo:
        transition(current, target)
    assert excinfo.value.code == "STAGE_TRANSITION_INVALID"
    assert excinfo.value.current == current
    assert excinfo.value.target == target


@pytest.mark.parametrize("stage", list(Stage))
def test_same_stage_is_noop_success(stage: Stage) -> None:
    """Moving to the stage a lead is already in succeeds unchanged."""
    assert transition(stage, stage) == stage


def test_lost_reactivates_only_to_nurture() -> None:
    """A lost lead can only come back through NURTURE, never forward."""
    assert transition(Stage.LOST, Stage.NURTURE) == Stage.NURTURE
    for target in (Stage.NEW, Stage.CONTACTED, Stage.QUALIFIED, Stage.BOOKED):
        with pytest.raises(StageTransitionError):
            transition(Stage.LOST, target)


def test_nurture_returns_to_contacted_not_qualified() -> None:
    """A nurtured lead re-enters at CONTACTED and re-earns qualification."""
    assert transition(Stage.NURTURE, Stage.CONTACTED) == Stage.CONTACTED
    with pytest.raises(StageTransitionError):
        transition(Stage.NURTURE, Stage.QUALIFIED)


def test_booked_never_moves_backwards() -> None:
    """A booked lead can go NURTURE or LOST, never back down the funnel."""
    assert transition(Stage.BOOKED, Stage.NURTURE) == Stage.NURTURE
    assert transition(Stage.BOOKED, Stage.LOST) == Stage.LOST
    for target in (Stage.NEW, Stage.CONTACTED, Stage.QUALIFIED):
        with pytest.raises(StageTransitionError):
            transition(Stage.BOOKED, target)


def test_dedupe_email_takes_precedence_over_phone() -> None:
    """The same email with a different phone is the same lead."""
    first = dedupe_key("sarah@example.com", "07700 900123")
    second = dedupe_key("sarah@example.com", "020 7946 0958")
    assert first == second == "email:sarah@example.com"


def test_dedupe_email_normalised() -> None:
    """Email dedupe ignores case and surrounding whitespace."""
    assert normalize_email("  Sarah@Example.COM ") == "sarah@example.com"
    assert normalize_email("   ") is None
    assert normalize_email(None) is None
    assert dedupe_key("Sarah@Example.com", None) == "email:sarah@example.com"


def test_dedupe_phone_formatting_variants() -> None:
    """Phone dedupe ignores spacing, dashes and a leading + or 00."""
    assert normalize_phone("+44 7700 900 123") == "447700900123"
    assert normalize_phone("+447700900123") == "447700900123"
    assert normalize_phone("0044 7700 900 123") == "447700900123"
    assert normalize_phone("(07700) 900-123") == "07700900123"
    assert normalize_phone("   ") is None
    assert normalize_phone(None) is None
    assert dedupe_key(None, "+44 7700 900123") == "phone:447700900123"


def test_dedupe_without_contact_returns_none() -> None:
    """With no email and no phone there is nothing to dedupe on."""
    assert dedupe_key(None, None) is None
    assert dedupe_key("", "  ") is None
