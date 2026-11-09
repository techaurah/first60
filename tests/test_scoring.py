"""Tests for qualification scoring and bands."""

from __future__ import annotations

import inspect

import pytest

from first60.pipeline.scoring import Score, ScoringInput, band_for, score_lead


@pytest.mark.parametrize(
    "total,expected",
    [
        (0, "LOW"),
        (49, "LOW"),
        (50, "NURTURE"),
        (64, "NURTURE"),
        (65, "WARM"),
        (79, "WARM"),
        (80, "HOT"),
        (100, "HOT"),
    ],
)
def test_band_boundaries(total: int, expected: str) -> None:
    """Bands use LeadPipe's thresholds: 50, 65, 80."""
    assert band_for(total) == expected


@pytest.mark.parametrize(
    "service_match,expected",
    [("full", 25), ("related", 15), ("none", 5)],
)
def test_service_fit_points(service_match: str, expected: int) -> None:
    """Service fit: full 25, related 15, unclassifiable 5."""
    score = score_lead(ScoringInput(service_match=service_match))
    assert score.components["service_fit"] == expected


@pytest.mark.parametrize(
    "urgency,expected",
    [
        ("emergency", 20),
        ("today", 15),
        ("this_week", 10),
        ("flexible", 5),
        ("unknown", 0),
    ],
)
def test_urgency_points(urgency: str, expected: int) -> None:
    """Urgency: emergency 20, today 15, this week 10, flexible 5, unknown 0."""
    score = score_lead(ScoringInput(urgency=urgency))
    assert score.components["urgency"] == expected


def test_contact_name_only_is_5() -> None:
    """A known name alone is worth 5 of the 15 contact points."""
    score = score_lead(ScoringInput(name_known=True))
    assert score.components["contact"] == 5


def test_contact_channel_only_is_10() -> None:
    """A reachable contact alone is worth 10 of the 15 contact points."""
    score = score_lead(ScoringInput(contact_known=True))
    assert score.components["contact"] == 10


def test_contact_name_and_channel_is_15() -> None:
    """Name plus a reachable contact is the full 15 contact points."""
    score = score_lead(ScoringInput(name_known=True, contact_known=True))
    assert score.components["contact"] == 15


@pytest.mark.parametrize(
    "answered,total,expected",
    [(0, 4, 0), (1, 4, 3), (2, 4, 7), (3, 4, 11), (4, 4, 15)],
)
def test_completeness_scales_with_required_answered(
    answered: int, total: int, expected: int
) -> None:
    """Completeness is 15 points scaled by the share of required answered."""
    score = score_lead(ScoringInput(questions_answered=answered, questions_total=total))
    assert score.components["completeness"] == expected


def test_completeness_with_no_required_questions_is_full() -> None:
    """A pack with no required questions counts a lead as fully complete."""
    score = score_lead(ScoringInput(questions_answered=0, questions_total=0))
    assert score.components["completeness"] == 15


@pytest.mark.parametrize(
    "value_tier,expected",
    [("high", 15), ("standard", 10), ("low", 5)],
)
def test_value_tier_points(value_tier: str, expected: int) -> None:
    """Value follows the matched service's configured tier."""
    score = score_lead(ScoringInput(value_tier=value_tier))
    assert score.components["value"] == expected


def test_value_job_size_signal_without_service_is_10() -> None:
    """A stated job size is worth 10 when no service matched."""
    score = score_lead(ScoringInput(job_size_known=True))
    assert score.components["value"] == 10


def test_value_no_service_no_signal_is_0() -> None:
    """No matched service and no job-size signal scores nothing on value."""
    score = score_lead(ScoringInput())
    assert score.components["value"] == 0


@pytest.mark.parametrize(
    "replies,expected",
    [(0, 0), (1, 2), (3, 6), (5, 10), (9, 10)],
)
def test_engagement_points_cap_at_five_replies(replies: int, expected: int) -> None:
    """Engagement is 2 points per reply, capped at 5 replies (10 points)."""
    score = score_lead(ScoringInput(replies=replies))
    assert score.components["engagement"] == expected


def test_perfect_lead_scores_100_and_hot() -> None:
    """A lead at the maximum of every component scores 100 and HOT."""
    score = score_lead(
        ScoringInput(
            service_match="full",
            urgency="emergency",
            name_known=True,
            contact_known=True,
            questions_answered=4,
            questions_total=4,
            value_tier="high",
            replies=5,
        )
    )
    assert score.components == {
        "service_fit": 25,
        "urgency": 20,
        "contact": 15,
        "completeness": 15,
        "value": 15,
        "engagement": 10,
    }
    assert score.total == 100
    assert score.band == "HOT"


def test_total_is_computed_not_accepted() -> None:
    """A total can never be passed in: scoring has no total input."""
    assert "total" not in inspect.signature(ScoringInput).parameters
    assert "total" not in inspect.signature(score_lead).parameters
    with pytest.raises(TypeError):
        ScoringInput(total=100)  # type: ignore[call-arg]
    empty = score_lead(ScoringInput())
    assert isinstance(empty, Score)
    # 5 for the unclassifiable-service floor plus 15 for completeness:
    # with no required questions the lead is fully complete.
    assert empty.total == 20
    assert empty.band == "LOW"
