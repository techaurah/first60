"""Responder package (build step 4).

Rules decide; responders only phrase. The rule responder renders
every decision from fixed templates; the LLM responder is optional,
off by default, and falls back to the template on any validation
failure.
"""

from first60.respond.base import DECISION_KINDS, Decision, FactSheet, Responder
from first60.respond.llm import LLMResponder
from first60.respond.rules import RuleResponder

__all__ = [
    "DECISION_KINDS",
    "Decision",
    "FactSheet",
    "LLMResponder",
    "Responder",
    "RuleResponder",
]
