"""Slot extraction from inbound messages (pure, no I/O).

Extraction is deterministic keyword and pattern matching, never a
model: the design's rule that decisions come from code, not prompts,
starts here. Everything in this module takes plain text (plus the
business pack where pack terms matter) and returns structured facts.

Design choices, documented because the design leaves the matching
rules open:

- Service matching is keyword-based on the service name: generic
  words (appointment, consultation, visit, service, treatment and
  the like) are dropped, and a service is a *full* match when every
  remaining word appears in the message, *related* when at least one
  does. When several services match, the one with the most matched
  words wins, ties broken by pack order. Synonyms (for example
  "toothache" for a crown) are not matched: that needs a synonym list
  per pack, which is a step 4 improvement, not silent guessing here.
- Timeline urgency ranks emergency pack terms first, then today
  phrases, then this week (tomorrow, weekday names, this weekend),
  then flexible phrases. A bare "emergency" word with no pack term
  counts as today, not emergency: only the pack's own terms trigger
  the emergency band.
- Name capture uses "my name is", "I'm", "I am" and "call me".
  "This is ..." is deliberately not a pattern: it misfires on "this
  is an emergency". Words that cannot be a name (pain, sick, free,
  emergency and the like) are rejected, so "I'm in pain" yields no
  name. Distress and symptom words (severe, bleeding, swelling and
  the like) are in the same list, and any captured word from the
  list rejects the whole capture, so "I'm in severe pain" and "I'm
  having severe pain" yield no name either: a distress phrase never
  becomes a captured name. Words that introduce distress ("having",
  "feeling", "getting") are in the list for the same reason.
- A phone number is any digit run of 7-15 digits, allowing spaces,
  dashes, brackets and a leading ``+``. An email is the usual
  ``local@domain.tld`` shape.
- Opt-out detection uses whole-word matching so "stopcock" never
  counts as STOP.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from first60.config import BusinessPack, Service

__all__ = [
    "ContactInfo",
    "Timeline",
    "detect_human_request",
    "detect_opt_out",
    "extract_contact",
    "extract_email",
    "extract_name",
    "extract_phone",
    "extract_timeline",
    "match_service",
]

# Words in a service name that carry no matching signal on their own.
_GENERIC_SERVICE_WORDS = frozenset(
    {
        "and",
        "for",
        "a",
        "an",
        "the",
        "appointment",
        "consultation",
        "visit",
        "session",
        "service",
        "treatment",
        "booking",
        "book",
        "call",
        "out",
        "therapy",
    }
)

_TODAY_PHRASES = (
    "today",
    "asap",
    "as soon as possible",
    "right now",
    "urgent",
    "urgently",
    "emergency",
)
_THIS_WEEK_PHRASES = ("tomorrow", "this week", "this weekend", "weekend")
_FLEXIBLE_PHRASES = (
    "next week",
    "next month",
    "flexible",
    "whenever",
    "no rush",
    "sometime",
    "in a few weeks",
)
_WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

_OPT_OUT_PHRASES = (
    "stop",
    "unsubscribe",
    "opt out",
    "opt-out",
    "do not message",
    "do not contact",
    "remove me",
    "take me off",
    "stop messaging",
    "stop texting",
)

_HUMAN_REQUEST_PHRASES = (
    "human",
    "real person",
    "speak to someone",
    "talk to someone",
    "speak to a person",
    "talk to a person",
    "speak to an agent",
    "talk to an agent",
    "real agent",
    "someone real",
    "person please",
    "human please",
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{5,}\d")

_NAME_PATTERNS = (
    re.compile(r"my name is\s+([A-Za-z][A-Za-z'’\- ]{1,40})", re.IGNORECASE),
    re.compile(r"\bi'?m\s+([A-Za-z][A-Za-z'’\- ]{1,40})", re.IGNORECASE),
    re.compile(r"\bi am\s+([A-Za-z][A-Za-z'’\- ]{1,40})", re.IGNORECASE),
    re.compile(r"call me\s+([A-Za-z][A-Za-z'’\- ]{1,40})", re.IGNORECASE),
)

# Words that end a captured name, or that can never be a name.
_NAME_STOPWORDS = frozenset(
    {
        "and",
        "i",
        "my",
        "the",
        "a",
        "an",
        "is",
        "am",
        "are",
        "looking",
        "for",
        "to",
        "need",
        "want",
        "here",
        "in",
        "on",
        "at",
        "with",
    }
)
# Words that can never be a name. The first group is the original
# step-2 list (states and filler); the second group is distress and
# symptom words added in build step 7, so a distress phrase such as
# "I'm in severe pain" never becomes a captured name; the third group
# is verbs that introduce distress ("I'm having severe pain").
_NON_NAME_WORDS = frozenset(
    {
        "pain",
        "sick",
        "ill",
        "ok",
        "okay",
        "fine",
        "good",
        "sorry",
        "not",
        "sure",
        "just",
        "really",
        "very",
        "so",
        "much",
        "emergency",
        "urgent",
        "worried",
        "tired",
        "busy",
        "free",
        "available",
        "interested",
        "hoping",
        "wondering",
        "afraid",
        "scared",
        "severe",
        "agony",
        "aching",
        "hurting",
        "hurt",
        "sore",
        "swollen",
        "swelling",
        "bleeding",
        "throbbing",
        "burning",
        "unbearable",
        "terrible",
        "awful",
        "dizzy",
        "nauseous",
        "vomiting",
        "fever",
        "infection",
        "bruised",
        "fractured",
        "sprained",
        "leaking",
        "flooding",
        "burst",
        "cracked",
        "damaged",
        "broken",
        "numb",
        "stuck",
        "having",
        "feeling",
        "getting",
        "experiencing",
        "suffering",
        "dealing",
    }
)


@dataclass(frozen=True)
class Timeline:
    """A requested timeline: urgency level plus the matched phrase."""

    urgency: str  # "emergency" | "today" | "this_week" | "flexible" | "unknown"
    detail: str = ""


@dataclass(frozen=True)
class ContactInfo:
    """Contact facts extracted from one message; any field may be None."""

    name: str | None = None
    phone: str | None = None
    email: str | None = None


def _normalize(text: str) -> str:
    """Lowercase and collapse every non-alphanumeric run to one space."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def _tokens(text: str) -> set[str]:
    return set(_normalize(text).split())


def _contains_phrase(normalized: str, phrase: str) -> bool:
    return re.search(rf"\b{re.escape(phrase)}\b", normalized) is not None


def _distinctive_words(service: Service) -> set[str]:
    """The service-name words that carry matching signal."""
    return {
        word for word in _tokens(service.name) if word not in _GENERIC_SERVICE_WORDS
    }


def match_service(text: str, pack: BusinessPack) -> tuple[Service | None, str]:
    """Match a message against the pack's services.

    Returns ``(service, kind)`` where kind is ``"full"`` (every
    distinctive word of the service name appears), ``"related"`` (at
    least one does) or ``"none"`` (no service word appears). When
    several services match, the one with the most matched words wins;
    ties break by pack order.
    """
    words = _tokens(text)
    best_full: Service | None = None
    best_full_count = 0
    best_related: Service | None = None
    best_related_count = 0
    for service in pack.services:
        distinctive = _distinctive_words(service)
        if not distinctive:
            continue
        matched = len(distinctive & words)
        if matched == 0:
            continue
        if matched == len(distinctive):
            if matched > best_full_count:
                best_full, best_full_count = service, matched
        elif matched > best_related_count:
            best_related, best_related_count = service, matched
    if best_full is not None:
        return best_full, "full"
    if best_related is not None:
        return best_related, "related"
    return None, "none"


def extract_timeline(text: str, pack: BusinessPack) -> Timeline:
    """Extract the requested timeline and its urgency level.

    Pack emergency terms rank first, then today phrases, then this
    week (tomorrow, weekday names, this weekend), then flexible
    phrases. A message with no timeline signal is ``"unknown"``.
    """
    normalized = _normalize(text)
    for term in pack.handoff.emergency_terms:
        if _contains_phrase(normalized, _normalize(term)):
            return Timeline(urgency="emergency", detail=term)
    for phrase in _TODAY_PHRASES:
        if _contains_phrase(normalized, phrase):
            return Timeline(urgency="today", detail=phrase)
    for day in _WEEKDAYS:
        if _contains_phrase(normalized, day):
            return Timeline(urgency="this_week", detail=day)
    for phrase in _THIS_WEEK_PHRASES:
        if _contains_phrase(normalized, phrase):
            return Timeline(urgency="this_week", detail=phrase)
    for phrase in _FLEXIBLE_PHRASES:
        if _contains_phrase(normalized, phrase):
            return Timeline(urgency="flexible", detail=phrase)
    return Timeline(urgency="unknown", detail="")


def extract_name(text: str) -> str | None:
    """Extract a name from "my name is / I'm / I am / call me" phrasing.

    Returns the name title-cased, or ``None`` when no name pattern
    matches or the captured words cannot be a name.
    """
    for pattern in _NAME_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        words: list[str] = []
        for raw_word in match.group(1).split():
            word = raw_word.strip(" '’")
            if not word.isalpha():
                break
            lowered = word.lower()
            if lowered in _NAME_STOPWORDS:
                if words:
                    break
                continue
            words.append(word)
            if len(words) == 3:
                break
        if not words:
            return None
        # Any captured word that cannot be a name rejects the whole
        # capture: "I'm in severe pain" must not become "Severe Pain",
        # and "I'm having severe pain" must not become a name either.
        if any(word.lower() in _NON_NAME_WORDS for word in words):
            return None
        return " ".join(word.capitalize() for word in words)
    return None


def extract_phone(text: str) -> str | None:
    """Extract the first phone number: 7-15 digits, formatting allowed."""
    for match in _PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if 7 <= len(digits) <= 15:
            return match.group(0).strip()
    return None


def extract_email(text: str) -> str | None:
    """Extract the first email address, or ``None`` when there is none."""
    match = _EMAIL_RE.search(text)
    return match.group(0) if match else None


def extract_contact(text: str) -> ContactInfo:
    """Extract name, phone and email from one message, together."""
    return ContactInfo(
        name=extract_name(text),
        phone=extract_phone(text),
        email=extract_email(text),
    )


def detect_opt_out(text: str) -> bool:
    """Return True when the message opts out (STOP, unsubscribe, ...)."""
    normalized = _normalize(text)
    return any(_contains_phrase(normalized, phrase) for phrase in _OPT_OUT_PHRASES)


def detect_human_request(text: str) -> bool:
    """Return True when the lead asks for a human (any wording we know)."""
    normalized = _normalize(text)
    return any(
        _contains_phrase(normalized, phrase) for phrase in _HUMAN_REQUEST_PHRASES
    )
