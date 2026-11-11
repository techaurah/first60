"""Responder interface (pure types, no I/O).

Rules decide, responders phrase. A responder receives a
:class:`Decision` (what the receptionist decided) and a
:class:`FactSheet` (the only facts it may state) and returns the text
to send. The decision kinds are the engine's outbound moves from
DESIGN.md section 4: greet, ask, offer slots, confirm a booking,
hand off, follow up, acknowledge, opt out.

The fact sheet is the whole truth a responder may use: the business
name, its bookable services, its hours, and the pack's emergency
instruction. It carries no prices, because no pack publishes any:
any price in rendered output is invented, and the LLM responder
treats it as a validation failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from first60.config import BusinessPack

__all__ = [
    "DECISION_KINDS",
    "Decision",
    "FactSheet",
    "Responder",
]

DECISION_KINDS = (
    "greet",
    "ask",
    "offer_slots",
    "confirm_booking",
    "handoff",
    "follow_up",
    "acknowledge",
    "opt_out",
)


@dataclass(frozen=True)
class Decision:
    """One outbound move the receptionist has decided to make.

    Only the fields a kind needs are set; the rest stay empty. ``slots``
    holds display strings (for example ``"Thursday 09:00"``) exactly as
    they must appear in the message, so a responder never reformats a
    time. ``handoff_text`` carries the safety template or handoff
    notice verbatim: a responder must not rephrase it.
    """

    kind: str
    question: str = ""
    service: str = ""
    slots: tuple[str, ...] = ()
    appointment: str = ""
    lead_name: str = ""
    handoff_text: str = ""
    detail: str = ""


@dataclass(frozen=True)
class FactSheet:
    """The only facts a responder may state about the business."""

    business_name: str
    services: tuple[str, ...] = ()
    hours_text: str = ""
    emergency_instruction: str = ""

    @classmethod
    def from_pack(cls, pack: BusinessPack) -> FactSheet:
        """Build the fact sheet from a validated business pack."""
        hours_parts = []
        for day in (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ):
            hours = pack.hours.get(day)
            label = day.capitalize()
            if hours is None:
                hours_parts.append(f"{label} closed")
            else:
                hours_parts.append(f"{label} {hours[0]}-{hours[1]}")
        return cls(
            business_name=pack.name,
            services=tuple(service.name for service in pack.services),
            hours_text=", ".join(hours_parts),
            emergency_instruction=pack.handoff.emergency_instruction,
        )


class Responder(Protocol):
    """Renders a decision into the text to send."""

    def render(self, decision: Decision, facts: FactSheet) -> str:
        """Return the message text for ``decision`` using ``facts``."""
        ...
