"""The qualification question flow (pure, no I/O).

A :class:`ConversationState` is the whole state of one lead's
qualification: which of the pack's questions are answered, which
service matched, the strongest urgency seen, and how many times the
lead failed to answer the current question in a row. Every function
here takes a state and returns a new state; nothing is mutated and
nothing touches I/O.

Design choices, documented because the design leaves the flow rules
open:

- Questions are asked in pack order, first unanswered first. The
  packs already list required questions before optional ones.
- A message is mined opportunistically: a service mention, a timeline
  phrase, a name or a contact fills the matching question even when
  it is not the one just asked, so a lead that volunteers everything
  up front is qualified without being asked the same thing twice.
  This is what lets the demo enquiry ("do you have anything Thursday
  morning, my crown is aching") answer the service and timeline
  questions in a single message. Only questions the pack actually
  asks are ever filled: a plumber pack with an "urgency" question and
  no "timeline" question never gains a stray "timeline" answer.
- Structured questions (service, timeline, name, contact) need a
  successful extraction; a free-text question (address, budget,
  symptoms and the like) accepts any non-empty reply as its answer.
  Success or failure is judged against the question the lead was
  asked *before* the message arrived, so a message that answers two
  questions at once is progress, not a failure on the next question.
- A reply that does not answer the current structured question counts
  as one extraction failure. Two consecutive failures mark the
  conversation stuck, which is the handoff trigger in DESIGN.md
  section 8. Any successful answer resets the failure count.
- Urgency only ever escalates inside a conversation: a later "it can
  wait" never downgrades an earlier "today".
- A matched service can upgrade (related to full) on a later, more
  specific message, but it never downgrades or switches: the first
  matched service stands unless a later message names it fully.
"""

from __future__ import annotations

from dataclasses import dataclass

from first60.config import BusinessPack, QualifyingQuestion
from first60.pipeline.extract import (
    extract_contact,
    extract_timeline,
    match_service,
)

__all__ = [
    "ConversationState",
    "answered_required",
    "apply_message",
    "completeness",
    "initial_state",
    "is_qualified",
    "next_question",
    "required_questions",
]

# Questions answered by extraction, not by taking the raw reply.
_STRUCTURED_QUESTIONS = frozenset({"service", "timeline", "name", "contact"})

# Two consecutive extraction failures on the same question: stuck.
_MAX_CONSECUTIVE_FAILURES = 2

_URGENCY_RANK = {
    "unknown": 0,
    "flexible": 1,
    "this_week": 2,
    "today": 3,
    "emergency": 4,
}


@dataclass(frozen=True)
class ConversationState:
    """The qualification state of one lead's conversation."""

    answers: dict[str, str]
    service: str | None = None
    service_match: str = "none"  # "full" | "related" | "none"
    # "emergency" | "today" | "this_week" | "flexible" | "unknown"
    urgency: str = "unknown"
    timeline_detail: str = ""
    consecutive_failures: int = 0
    stuck: bool = False
    replies: int = 0


def initial_state() -> ConversationState:
    """Return a fresh conversation state: nothing answered yet."""
    return ConversationState(answers={})


def required_questions(pack: BusinessPack) -> tuple[QualifyingQuestion, ...]:
    """Return the pack's required questions, in pack order."""
    return tuple(question for question in pack.questions if question.required)


def next_question(
    state: ConversationState, pack: BusinessPack
) -> QualifyingQuestion | None:
    """Return the first unanswered question in pack order, or None."""
    for question in pack.questions:
        if question.id not in state.answers:
            return question
    return None


def is_qualified(state: ConversationState, pack: BusinessPack) -> bool:
    """Return True when every required question has an answer."""
    return all(question.id in state.answers for question in required_questions(pack))


def answered_required(state: ConversationState, pack: BusinessPack) -> tuple[int, int]:
    """Return ``(required answered, required total)`` for scoring."""
    required = required_questions(pack)
    answered = sum(1 for question in required if question.id in state.answers)
    return answered, len(required)


def completeness(state: ConversationState, pack: BusinessPack) -> float:
    """Return the share of required questions answered, 0.0 to 1.0."""
    answered, total = answered_required(state, pack)
    if total == 0:
        return 1.0
    return answered / total


def _stronger_urgency(current: str, seen: str) -> str:
    if _URGENCY_RANK[seen] > _URGENCY_RANK[current]:
        return seen
    return current


def apply_message(
    state: ConversationState, pack: BusinessPack, text: str
) -> ConversationState:
    """Apply one inbound message and return the new state.

    Empty messages are ignored entirely. Otherwise the message is
    mined for service, timeline, name and contact, the matching
    questions are filled opportunistically, and the current question
    is then answered (free-text questions take the raw reply) or
    counted as one more extraction failure.
    """
    stripped = text.strip()
    if not stripped:
        return state

    answers = dict(state.answers)
    service = state.service
    service_match = state.service_match
    urgency = state.urgency
    timeline_detail = state.timeline_detail
    failures = state.consecutive_failures

    # The question the lead was asked: judged before the fill below,
    # so a message that answers two questions at once is progress,
    # not a failure on the next question.
    current = next_question(state, pack)

    matched_service, match_kind = match_service(stripped, pack)
    timeline = extract_timeline(stripped, pack)
    contact = extract_contact(stripped)
    question_ids = {question.id for question in pack.questions}

    # Opportunistic fill: volunteer facts answer their question early,
    # but only for questions the pack actually asks.
    if (
        matched_service is not None
        and "service" in question_ids
        and "service" not in answers
    ):
        answers["service"] = matched_service.name
        service = matched_service.name
        service_match = match_kind
    elif (
        matched_service is not None
        and match_kind == "full"
        and service_match == "related"
        and service == matched_service.name
    ):
        # A later, more specific message upgrades related to full.
        service_match = "full"
    if (
        timeline.urgency != "unknown"
        and "timeline" in question_ids
        and "timeline" not in answers
    ):
        answers["timeline"] = timeline.detail or timeline.urgency
    if contact.name is not None and "name" in question_ids and "name" not in answers:
        answers["name"] = contact.name
    if (
        (contact.phone is not None or contact.email is not None)
        and "contact" in question_ids
        and "contact" not in answers
    ):
        answers["contact"] = contact.phone or contact.email or ""
    urgency = _stronger_urgency(urgency, timeline.urgency)
    if timeline.urgency != "unknown":
        timeline_detail = timeline.detail

    # The question the lead was asked: answered, or one more failure.
    if current is None:
        failures = 0
    elif current.id in answers:
        failures = 0
    elif current.id in _STRUCTURED_QUESTIONS:
        failures += 1
    else:
        # A free-text question accepts any non-empty reply.
        answers[current.id] = stripped
        failures = 0

    return ConversationState(
        answers=answers,
        service=service,
        service_match=service_match,
        urgency=urgency,
        timeline_detail=timeline_detail,
        consecutive_failures=failures,
        stuck=failures >= _MAX_CONSECUTIVE_FAILURES,
        replies=state.replies + 1,
    )
