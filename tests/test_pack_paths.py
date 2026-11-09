"""Scripted qualification paths: every pack completes a conversation.

Each pack gets one scripted enquiry that runs through the pure core
end to end: messages in, qualification out, a score with components,
and the stage walk NEW -> CONTACTED -> QUALIFIED. These are the
step-2 proof of DESIGN.md section 15's requirement that all five
packs each complete a scripted qualification conversation in tests.
"""

from __future__ import annotations

import pytest

from first60.config import BusinessPack, load_builtin_pack
from first60.pipeline.qualify import (
    answered_required,
    apply_message,
    initial_state,
    is_qualified,
)
from first60.pipeline.scoring import ScoringInput, score_lead
from first60.pipeline.stages import Stage, transition

PACK_NAMES = ["dental", "plumber", "med-spa", "clinic", "real-estate"]

# One scripted conversation per pack: (messages, expected service).
SCRIPTS = {
    "dental": (
        [
            "do you have anything Thursday morning, my crown is aching",
            "my name is Sarah Jones",
            "07700 900123",
        ],
        "Crown fitting",
    ),
    "plumber": (
        [
            "my boiler has broken down, I need a repair",
            "today please, there is water everywhere",
            "12 Oak Road, Springfield",
            "my name is Tom Baker",
            "07700 900456",
        ],
        "Boiler repair",
    ),
    "med-spa": (
        [
            "I'd like to book a facial",
            "next Saturday if you have anything",
            "my name is Emma Wilson",
            "emma.wilson@example.com",
        ],
        "Signature facial",
    ),
    "clinic": (
        [
            "I need a blood test",
            "tomorrow morning",
            "my name is James Carter",
            "07700 900789",
        ],
        "Blood test",
    ),
    "real-estate": (
        [
            "I'd like to view a property this weekend",
            "my name is Aisha Khan",
            "aisha.khan@example.com",
        ],
        "Property viewing",
    ),
}


def _score_from_state(state, pack: BusinessPack):
    answered, total = answered_required(state, pack)
    tier = None
    for service in pack.services:
        if service.name == state.service:
            tier = service.value_tier
    return score_lead(
        ScoringInput(
            service_match=state.service_match,
            urgency=state.urgency,
            name_known="name" in state.answers,
            contact_known="contact" in state.answers,
            questions_answered=answered,
            questions_total=total,
            value_tier=tier,
            replies=state.replies,
        )
    )


@pytest.mark.parametrize("name", PACK_NAMES)
def test_pack_completes_scripted_qualification(name: str) -> None:
    """A scripted enquiry qualifies the lead and scores it, per pack."""
    pack = load_builtin_pack(name)
    messages, expected_service = SCRIPTS[name]
    state = initial_state()
    for message in messages:
        state = apply_message(state, pack, message)

    assert state.service == expected_service
    assert is_qualified(state, pack) is True
    assert state.stuck is False

    score = _score_from_state(state, pack)
    assert score.total >= 50  # every scripted path reaches at least NURTURE
    assert score.components["service_fit"] >= 15
    assert score.components["contact"] == 15
    assert score.components["completeness"] == 15
    assert score.band in {"HOT", "WARM", "NURTURE"}

    # The stage walk the conversation engine will drive in step 5.
    stage = transition(Stage.NEW, Stage.CONTACTED)
    stage = transition(stage, Stage.QUALIFIED)
    assert stage == Stage.QUALIFIED
