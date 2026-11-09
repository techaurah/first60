"""The pure core (build step 2): stages, scoring, extraction, qualification.

No I/O anywhere in this package: rules decide, responders phrase.
The store, calendar, channels and demo arrive in later build steps.
"""

from first60.pipeline.extract import (
    ContactInfo,
    Timeline,
    detect_human_request,
    detect_opt_out,
    extract_contact,
    extract_email,
    extract_name,
    extract_phone,
    extract_timeline,
    match_service,
)
from first60.pipeline.qualify import (
    ConversationState,
    answered_required,
    apply_message,
    completeness,
    initial_state,
    is_qualified,
    next_question,
    required_questions,
)
from first60.pipeline.scoring import Score, ScoringInput, band_for, score_lead
from first60.pipeline.stages import (
    Stage,
    StageTransitionError,
    allowed_transitions,
    dedupe_key,
    normalize_email,
    normalize_phone,
    transition,
)

__all__ = [
    "ContactInfo",
    "ConversationState",
    "Score",
    "ScoringInput",
    "Stage",
    "StageTransitionError",
    "Timeline",
    "allowed_transitions",
    "answered_required",
    "apply_message",
    "band_for",
    "completeness",
    "dedupe_key",
    "detect_human_request",
    "detect_opt_out",
    "extract_contact",
    "extract_email",
    "extract_name",
    "extract_phone",
    "extract_timeline",
    "initial_state",
    "is_qualified",
    "match_service",
    "next_question",
    "normalize_email",
    "normalize_phone",
    "required_questions",
    "score_lead",
    "transition",
]
