"""Human handoff rules (pure, no I/O).

A lead is handed to the human owner, with automation paused for that
lead and a summary written for the owner, when any of the DESIGN.md
section 8 triggers fires:

- emergency terms from the pack (the reply is a fixed safety template
  carrying the pack's own emergency instruction, never advice),
- complaint, anger, refund or legal signals,
- the lead asks for a human, in any wording the extractor recognises,
- two consecutive extraction failures on the same question (stuck),
- anything the pack marks ``handoff_only``.

Priority is fixed: emergency beats handoff-only beats complaint beats
a human request beats stuck. Rules decide; the responder only phrases
the decision, and the engine (build step 5) enforces the pause.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from first60.config import BusinessPack
from first60.pipeline.extract import detect_human_request
from first60.pipeline.qualify import ConversationState

__all__ = [
    "HANDOFF_REASONS",
    "HandoffDecision",
    "check_handoff",
]

HANDOFF_REASONS = (
    "emergency",
    "complaint",
    "human_request",
    "stuck",
    "handoff_only",
)

# Complaint, anger, refund and legal signals. Matched as whole words or
# phrases so "disgusted" fires but "disgust" inside another word does
# not, and "sue" never fires inside "pursue".
_COMPLAINT_PHRASES = (
    "complaint",
    "complain",
    "complaining",
    "terrible",
    "awful",
    "horrible",
    "disgusted",
    "disgusting",
    "unacceptable",
    "outraged",
    "furious",
    "angry",
    "worst",
    "never again",
    "report you",
    "reporting you",
    "refund",
    "money back",
    "chargeback",
    "sue",
    "suing",
    "lawyer",
    "solicitor",
    "legal action",
    "compensation",
    "trading standards",
    "ombudsman",
)


def _normalize(text: str) -> str:
    """Lowercase and collapse every non-alphanumeric run to one space."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def _contains_phrase(normalized: str, phrase: str) -> bool:
    return re.search(rf"\b{re.escape(phrase)}\b", normalized) is not None


def _matches_any(text: str, terms: tuple[str, ...]) -> str | None:
    """Return the first term found in ``text``, or None."""
    normalized = _normalize(text)
    for term in terms:
        if _contains_phrase(normalized, _normalize(term)):
            return term
    return None


@dataclass(frozen=True)
class HandoffDecision:
    """The outcome of the handoff check for one inbound message.

    ``reply_text`` is what the lead is sent (the fixed safety template
    for an emergency, a handoff notice otherwise); ``summary`` is the
    owner-facing handoff note. Both are empty when nothing triggered.
    ``pause_automation`` is True exactly when a handoff triggered: the
    engine stops automated replies and follow-ups for that lead.
    """

    triggered: bool
    reason: str | None = None
    matched_term: str | None = None
    reply_text: str = ""
    summary: str = ""
    pause_automation: bool = False


def _safety_reply(pack: BusinessPack) -> str:
    """The fixed emergency reply: framing plus the pack's instruction.

    The instruction is the pack's own words, quoted verbatim. No
    advice is ever added: First60 never gives medical or trade advice.
    """
    instruction = pack.handoff.emergency_instruction
    return (
        f"I'm the automated receptionist for {pack.name}. {instruction} "
        "I've passed your message to the team and paused automated "
        "replies, and someone will get back to you as soon as possible."
    )


def _handoff_reply(pack: BusinessPack) -> str:
    """The neutral handoff notice for non-emergency triggers."""
    return (
        f"Thanks for letting me know. I've passed this to the team at "
        f"{pack.name} and paused automated replies for now. Someone "
        "will get back to you directly."
    )


def _owner_summary(
    pack: BusinessPack,
    state: ConversationState,
    text: str,
    reason: str,
    matched_term: str | None,
) -> str:
    """Build the owner-facing summary: who, what, and why."""
    name = state.answers.get("name", "")
    contact = state.answers.get("contact", "")
    service = state.service or "not stated"
    lines = [f"Handoff ({reason}" + (f": {matched_term}" if matched_term else "") + ")"]
    lines.append(f"Lead: {name or 'name not given'}")
    if contact:
        lines.append(f"Contact: {contact}")
    lines.append(f"Service: {service}")
    lines.append(f"Urgency: {state.urgency}")
    lines.append(f"Last message: {text.strip()}")
    lines.append("Automation paused for this lead.")
    return "\n".join(lines)


def check_handoff(
    pack: BusinessPack, state: ConversationState, text: str
) -> HandoffDecision:
    """Check one inbound message against the handoff rules.

    ``state`` is the conversation state *after* the message was
    applied, so the stuck check sees the current failure count.
    Triggers are checked in priority order and the first hit wins.
    """
    stripped = text.strip()

    matched = _matches_any(stripped, pack.handoff.emergency_terms)
    if matched is not None:
        return HandoffDecision(
            triggered=True,
            reason="emergency",
            matched_term=matched,
            reply_text=_safety_reply(pack),
            summary=_owner_summary(pack, state, stripped, "emergency", matched),
            pause_automation=True,
        )

    matched = _matches_any(stripped, pack.handoff.handoff_only)
    if matched is not None:
        return HandoffDecision(
            triggered=True,
            reason="handoff_only",
            matched_term=matched,
            reply_text=_handoff_reply(pack),
            summary=_owner_summary(pack, state, stripped, "handoff_only", matched),
            pause_automation=True,
        )

    matched = _matches_any(stripped, _COMPLAINT_PHRASES)
    if matched is not None:
        return HandoffDecision(
            triggered=True,
            reason="complaint",
            matched_term=matched,
            reply_text=_handoff_reply(pack),
            summary=_owner_summary(pack, state, stripped, "complaint", matched),
            pause_automation=True,
        )

    if detect_human_request(stripped):
        return HandoffDecision(
            triggered=True,
            reason="human_request",
            matched_term=None,
            reply_text=_handoff_reply(pack),
            summary=_owner_summary(pack, state, stripped, "human_request", None),
            pause_automation=True,
        )

    if state.stuck:
        return HandoffDecision(
            triggered=True,
            reason="stuck",
            matched_term=None,
            reply_text=_handoff_reply(pack),
            summary=_owner_summary(pack, state, stripped, "stuck", None),
            pause_automation=True,
        )

    return HandoffDecision(triggered=False)
