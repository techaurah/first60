"""Qualification scoring and bands (pure, no I/O).

Scoring follows DESIGN.md section 5: the server computes the score from
extracted signals, never accepts a total as input, and never lets an
LLM produce it. Components total 0-100, and bands use LeadPipe's
thresholds so the two projects read identically: HOT 80-100, WARM
65-79, NURTURE 50-64, LOW below 50.

Design choices, documented because the design leaves the per-signal
points open:

- ``service_fit``: full match 25, related (partial) match 15,
  unclassifiable 5. An unclassifiable enquiry still scores a little,
  because the lead did contact the business; it is the other
  components that keep it out of HOT.
- ``urgency``: emergency 20, today 15, this week 10, flexible 5,
  unknown 0. "Tomorrow" and weekday names count as this week (10):
  they are soon, but the slot is not needed today.
- ``contact``: name known 5, a reachable contact (phone, email or
  channel handle) captured 10. Either alone is worth its part.
- ``completeness``: 15 points scaled by the share of the pack's
  *required* questions answered, rounded down. Optional questions do
  not count: a lead that answered everything required is fully
  complete, even if it skipped an optional question.
- ``value``: the matched service's configured tier (high 15, standard
  10, low 5). With no service matched, a stated job-size signal is
  worth 10; with neither, 0.
- ``engagement``: 2 points per lead reply, capped at 5 replies (10
  points). A long conversation is a warm lead, but chatter alone must
  never push a lead to HOT.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "Score",
    "ScoringInput",
    "band_for",
    "score_lead",
]

SERVICE_FIT_POINTS = {"full": 25, "related": 15, "none": 5}
URGENCY_POINTS = {
    "emergency": 20,
    "today": 15,
    "this_week": 10,
    "flexible": 5,
    "unknown": 0,
}
VALUE_TIER_POINTS = {"high": 15, "standard": 10, "low": 5}

_CONTACT_NAME_POINTS = 5
_CONTACT_CHANNEL_POINTS = 10
_COMPLETENESS_MAX = 15
_JOB_SIZE_POINTS = 10
_ENGAGEMENT_PER_REPLY = 2
_ENGAGEMENT_MAX_REPLIES = 5

_BANDS = (
    (80, "HOT"),
    (65, "WARM"),
    (50, "NURTURE"),
)


@dataclass(frozen=True)
class ScoringInput:
    """The extracted signals a score is computed from.

    There is deliberately no ``total`` field: a total is computed by
    :func:`score_lead` and never accepted as input.
    """

    service_match: str = "none"  # "full" | "related" | "none"
    # "emergency" | "today" | "this_week" | "flexible" | "unknown"
    urgency: str = "unknown"
    name_known: bool = False
    contact_known: bool = False
    questions_answered: int = 0
    questions_total: int = 0
    value_tier: str | None = None  # "high" | "standard" | "low"
    job_size_known: bool = False
    replies: int = 0


@dataclass(frozen=True)
class Score:
    """A computed score: per-component points, total, and band."""

    components: dict[str, int] = field(default_factory=dict)
    total: int = 0
    band: str = "LOW"


def band_for(total: int) -> str:
    """Return the band for a total: HOT 80+, WARM 65+, NURTURE 50+, else LOW."""
    for threshold, band in _BANDS:
        if total >= threshold:
            return band
    return "LOW"


def _service_fit_points(service_match: str) -> int:
    if service_match not in SERVICE_FIT_POINTS:
        raise ValueError(f"unknown service_match {service_match!r}")
    return SERVICE_FIT_POINTS[service_match]


def _urgency_points(urgency: str) -> int:
    if urgency not in URGENCY_POINTS:
        raise ValueError(f"unknown urgency {urgency!r}")
    return URGENCY_POINTS[urgency]


def _contact_points(name_known: bool, contact_known: bool) -> int:
    points = 0
    if name_known:
        points += _CONTACT_NAME_POINTS
    if contact_known:
        points += _CONTACT_CHANNEL_POINTS
    return points


def _completeness_points(answered: int, total: int) -> int:
    if answered < 0 or total < 0 or answered > total:
        raise ValueError(
            f"questions_answered {answered} must be between 0 and "
            f"questions_total {total}"
        )
    if total == 0:
        # Nothing required to answer: the lead is fully complete.
        return _COMPLETENESS_MAX
    return (answered * _COMPLETENESS_MAX) // total


def _value_points(
    value_tier: str | None, job_size_known: bool, service_match: str
) -> int:
    if value_tier is not None:
        if value_tier not in VALUE_TIER_POINTS:
            raise ValueError(f"unknown value_tier {value_tier!r}")
        return VALUE_TIER_POINTS[value_tier]
    if service_match == "none" and job_size_known:
        return _JOB_SIZE_POINTS
    return 0


def _engagement_points(replies: int) -> int:
    if replies < 0:
        raise ValueError(f"replies {replies} must not be negative")
    return min(replies, _ENGAGEMENT_MAX_REPLIES) * _ENGAGEMENT_PER_REPLY


def score_lead(signals: ScoringInput) -> Score:
    """Compute the qualification score from extracted signals.

    The total is the sum of the six components (0-100) and the band
    follows :func:`band_for`. Component scores are kept per lead so a
    human can always see why a lead is HOT.
    """
    components = {
        "service_fit": _service_fit_points(signals.service_match),
        "urgency": _urgency_points(signals.urgency),
        "contact": _contact_points(signals.name_known, signals.contact_known),
        "completeness": _completeness_points(
            signals.questions_answered, signals.questions_total
        ),
        "value": _value_points(
            signals.value_tier, signals.job_size_known, signals.service_match
        ),
        "engagement": _engagement_points(signals.replies),
    }
    total = sum(components.values())
    return Score(components=components, total=total, band=band_for(total))
