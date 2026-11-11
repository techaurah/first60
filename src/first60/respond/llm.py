"""Optional LLM responder, caged (DESIGN.md section 6).

Any OpenAI-compatible endpoint via stdlib ``urllib`` (no SDK
dependency), configured by environment variables, off unless set. It
receives only the decision object and the allowed-facts sheet: it
never decides, never extracts, never scores.

Its output is validated before sending. Any failure falls back to
the template rendering of the same decision, and the fallback is
reported through ``on_fallback`` so the engine can audit-log it
(the audit row itself is the engine's job, build step 5). The
checks, in order:

- empty output,
- over the length cap,
- a booking decision whose offered slots do not appear verbatim,
- a price anywhere in the output (the fact sheet carries no prices,
  so any price is invented),
- a service offered or provided that is not on the fact sheet
  (``we offer X`` / ``we provide X`` / ``including X`` phrasing),
- any request, transport or response error.

Validation is a safety net, not a proof: an invented service phrased
in some other way can slip through, which is why the LLM path stays
off by default and the template fallback exists at all.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable

from first60.respond.base import Decision, FactSheet
from first60.respond.rules import RuleResponder

__all__ = ["LLMResponder"]

_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_MAX_CHARS = 600
_DEFAULT_TIMEOUT_SECONDS = 10.0

_PRICE_RE = re.compile(
    r"[£$€]\s?\d|\b\d+\s?(pounds|gbp|usd|dollars|euros)\b", re.IGNORECASE
)
_OFFER_RE = re.compile(
    r"\b(?:we (?:also )?offer|we provide|including|we do)\s+"
    r"([a-z][a-z '\-]{2,60})",
    re.IGNORECASE,
)


class LLMResponder:
    """Render decisions through an OpenAI-compatible endpoint.

    ``base_url`` is the endpoint root (``/chat/completions`` is
    appended); ``api_key`` may be empty for a local stub server.
    Pass ``fallback`` to choose the template responder used on
    validation failure (a plain :class:`RuleResponder` by default).
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        model: str = _DEFAULT_MODEL,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        max_chars: int = _DEFAULT_MAX_CHARS,
        fallback: RuleResponder | None = None,
        on_fallback: Callable[[str], None] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_chars = max_chars
        self._fallback = fallback or RuleResponder()
        self._on_fallback = on_fallback
        self.last_fallback_reason: str | None = None

    @classmethod
    def from_env(
        cls,
        fallback: RuleResponder | None = None,
        on_fallback: Callable[[str], None] | None = None,
    ) -> LLMResponder | None:
        """Build from env vars, or None when the LLM path is not set.

        ``FIRST60_LLM_BASE_URL`` switches the path on; without it the
        responder is off and callers use the rule responder directly.
        """
        base_url = os.environ.get("FIRST60_LLM_BASE_URL", "").strip()
        if not base_url:
            return None
        return cls(
            base_url=base_url,
            api_key=os.environ.get("FIRST60_LLM_API_KEY", ""),
            model=os.environ.get("FIRST60_LLM_MODEL", _DEFAULT_MODEL),
            fallback=fallback,
            on_fallback=on_fallback,
        )

    def render(self, decision: Decision, facts: FactSheet) -> str:
        """Return the model's text, or the template on any failure."""
        try:
            text = self._call_model(decision, facts)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return self._fall_back(decision, facts, f"llm_request_failed: {exc}")
        reason = self._validate(decision, facts, text)
        if reason is not None:
            return self._fall_back(decision, facts, reason)
        return text

    def _fall_back(self, decision: Decision, facts: FactSheet, reason: str) -> str:
        self.last_fallback_reason = reason
        if self._on_fallback is not None:
            self._on_fallback(reason)
        return self._fallback.render(decision, facts)

    def _call_model(self, decision: Decision, facts: FactSheet) -> str:
        system = (
            "You are the receptionist for "
            f"{facts.business_name}. Reply with only the message text "
            "to send, nothing else. Use only these facts: services: "
            f"{', '.join(facts.services)}; hours: {facts.hours_text}. "
            "Never invent a price, a service, a time or any other fact. "
            f"Keep the reply under {self.max_chars} characters."
        )
        user = (
            f"Decision kind: {decision.kind}. "
            f"Service: {decision.service or 'none'}. "
            f"Question: {decision.question or 'none'}. "
            f"Offered slots: {', '.join(decision.slots) or 'none'}. "
            f"Appointment: {decision.appointment or 'none'}. "
            f"Lead name: {decision.lead_name or 'not known'}. "
            f"Detail: {decision.detail or 'none'}."
        )
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        if self.api_key:
            request.add_header("Authorization", f"Bearer {self.api_key}")
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        return str(body["choices"][0]["message"]["content"])

    def _validate(self, decision: Decision, facts: FactSheet, text: str) -> str | None:
        """Return a failure reason, or None when the text is usable."""
        stripped = text.strip()
        if not stripped:
            return "empty_response"
        if len(stripped) > self.max_chars:
            return "overlong_response"
        if decision.kind == "offer_slots":
            for slot in decision.slots:
                if slot not in stripped:
                    return "slots_missing"
        if _PRICE_RE.search(stripped):
            return "price_not_on_fact_sheet"
        offered = _OFFER_RE.search(stripped)
        if offered is not None:
            candidate = offered.group(1).strip().lower()
            known = {service.lower() for service in facts.services}
            if not any(service in candidate for service in known):
                return "service_not_on_fact_sheet"
        return None
