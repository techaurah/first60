"""Pipeline stages, the transition map, and lead dedupe (pure, no I/O).

Stages follow DESIGN.md section 5: the front-desk subset of the LeadPipe
stage vocabulary (the sales stages PROPOSAL / NEGOTIATION / WON stay in
LeadPipe's domain). The transition map is the design's sequential flow
NEW -> CONTACTED -> QUALIFIED -> BOOKED, with NURTURE and LOST reachable
from any live stage, and reactivation LOST -> NURTURE only.

Design choices, documented because the design leaves them open:

- A stage move is never allowed to skip a step: CONTACTED -> BOOKED is
  illegal, so a lead is only booked after it has been qualified. This
  keeps the pipeline table in the README true by construction.
- A booked lead can still go NURTURE (no-show, reschedule) or LOST, but
  never backwards to CONTACTED or QUALIFIED.
- A nurtured lead re-enters at CONTACTED, not QUALIFIED: re-engagement
  restarts the conversation, and qualification is re-earned.
- Dedupe matches formatting variants of the same dial string (spaces,
  dashes, a leading ``+``), not international/trunk equivalents: ``+44
  7700 900123`` and ``020 7946 0958`` are different digit strings, so
  they are different leads. Cross-format phone matching needs country
  knowledge the pack does not carry, so it is out of scope here.
"""

from __future__ import annotations

import re
from enum import StrEnum

__all__ = [
    "Stage",
    "StageTransitionError",
    "allowed_transitions",
    "dedupe_key",
    "normalize_email",
    "normalize_phone",
    "transition",
]


class Stage(StrEnum):
    """A pipeline stage for a lead."""

    NEW = "NEW"
    CONTACTED = "CONTACTED"
    QUALIFIED = "QUALIFIED"
    BOOKED = "BOOKED"
    NURTURE = "NURTURE"
    LOST = "LOST"


class StageTransitionError(ValueError):
    """An illegal stage transition was attempted.

    ``code`` is the closed error code ``STAGE_TRANSITION_INVALID`` from
    DESIGN.md section 5; ``current`` and ``target`` name the stages.
    """

    code = "STAGE_TRANSITION_INVALID"

    def __init__(self, current: Stage, target: Stage) -> None:
        self.current = current
        self.target = target
        super().__init__(f"illegal stage transition {current.value} -> {target.value}")


# The transition map: each stage lists the stages it may move to.
# Same-stage is a no-op success and is not listed here.
_TRANSITIONS: dict[Stage, frozenset[Stage]] = {
    Stage.NEW: frozenset({Stage.CONTACTED, Stage.NURTURE, Stage.LOST}),
    Stage.CONTACTED: frozenset({Stage.QUALIFIED, Stage.NURTURE, Stage.LOST}),
    Stage.QUALIFIED: frozenset({Stage.BOOKED, Stage.NURTURE, Stage.LOST}),
    Stage.BOOKED: frozenset({Stage.NURTURE, Stage.LOST}),
    Stage.NURTURE: frozenset({Stage.CONTACTED, Stage.LOST}),
    Stage.LOST: frozenset({Stage.NURTURE}),
}


def allowed_transitions(stage: Stage) -> frozenset[Stage]:
    """Return the stages ``stage`` may move to (excluding itself)."""
    return _TRANSITIONS[stage]


def transition(current: Stage, target: Stage) -> Stage:
    """Move a lead from ``current`` to ``target``.

    A same-stage move is a no-op success and returns the stage
    unchanged. Any other illegal move raises :class:`StageTransitionError`.
    """
    if target == current:
        return current
    if target in _TRANSITIONS[current]:
        return target
    raise StageTransitionError(current, target)


def normalize_email(email: str | None) -> str | None:
    """Lowercase and strip an email address; blank input gives ``None``."""
    if email is None:
        return None
    cleaned = email.strip().lower()
    return cleaned or None


def normalize_phone(phone: str | None) -> str | None:
    """Reduce a phone number to its digits; blank input gives ``None``.

    A leading ``00`` international prefix is dropped so ``0044...``
    and ``+44...`` dedupe together. A leading trunk ``0`` is kept, so
    ``+44...`` and ``020...`` do not dedupe together (see the module
    docstring for why).
    """
    if phone is None:
        return None
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("00"):
        digits = digits[2:]
    return digits or None


def dedupe_key(email: str | None, phone: str | None) -> str | None:
    """Return the dedupe key for a lead, or ``None`` with no contact.

    Email takes precedence over phone, exactly as LeadPipe specifies:
    a lead with a known email dedupes on the email even when the phone
    differs. With no email, the phone is the key. With neither, there
    is nothing to dedupe on.
    """
    normalized_email = normalize_email(email)
    if normalized_email is not None:
        return f"email:{normalized_email}"
    normalized_phone = normalize_phone(phone)
    if normalized_phone is not None:
        return f"phone:{normalized_phone}"
    return None
