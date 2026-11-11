"""Deterministic template responder (the default).

Renders every decision kind from the pack's own words and the
decision's fields: no model, no keys, fully deterministic, and the
mode the demo and the entire test suite run in. A rule responder
never invents a price, a service, a time or a fact: slots appear
verbatim, the handoff text is passed through untouched, and a
question is the pack's own question text.
"""

from __future__ import annotations

from first60.respond.base import Decision, FactSheet

__all__ = ["RuleResponder"]


class RuleResponder:
    """Render decisions from fixed templates and pack facts."""

    def render(self, decision: Decision, facts: FactSheet) -> str:
        """Return the message text for ``decision`` using ``facts``."""
        if decision.kind == "greet":
            return self._greet(decision, facts)
        if decision.kind == "ask":
            return decision.question
        if decision.kind == "offer_slots":
            return self._offer_slots(decision, facts)
        if decision.kind == "confirm_booking":
            return self._confirm_booking(decision)
        if decision.kind == "handoff":
            return decision.handoff_text
        if decision.kind == "follow_up":
            return self._follow_up(decision, facts)
        if decision.kind == "acknowledge":
            return decision.detail or "Thanks, noted."
        if decision.kind == "opt_out":
            return self._opt_out(decision)
        raise ValueError(f"unknown decision kind: {decision.kind!r}")

    def _greet(self, decision: Decision, facts: FactSheet) -> str:
        greeting = f"Hi, thanks for messaging {facts.business_name}."
        if decision.question:
            return f"{greeting} {decision.question}"
        return f"{greeting} How can I help?"

    def _offer_slots(self, decision: Decision, facts: FactSheet) -> str:
        name = f" {decision.lead_name}" if decision.lead_name else ""
        slots = ", ".join(decision.slots)
        return (
            f"Thanks{name}. For {decision.service}, these times are "
            f"free: {slots}. Which works best for you?"
        )

    def _confirm_booking(self, decision: Decision) -> str:
        return (
            f"You're booked in for {decision.service} on "
            f"{decision.appointment}. We'll send a reminder before "
            "your appointment. Reply STOP at any time to stop messages."
        )

    def _follow_up(self, decision: Decision, facts: FactSheet) -> str:
        name = f" {decision.lead_name}" if decision.lead_name else ""
        service = f" about {decision.service}" if decision.service else ""
        detail = f" {decision.detail}" if decision.detail else ""
        return (
            f"Hi{name}, just checking in{service}.{detail} Let us know "
            f"if you'd still like to come in, or reply STOP to stop "
            "messages."
        )

    def _opt_out(self, decision: Decision) -> str:
        name = f", {decision.lead_name}" if decision.lead_name else ""
        return (
            f"No problem{name}. We've stopped automated messages. You "
            "can message us again any time if you'd like to restart."
        )
