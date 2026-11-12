"""The closed error-code set for First60 (build step 3).

Every error the store and calendar can raise carries one of these
codes, in the LeadPipe style: callers match on ``code``, never on the
message text. The pure core keeps its own exception
(:class:`first60.pipeline.stages.StageTransitionError`); the store
translates an illegal stage move into ``STAGE_TRANSITION_INVALID`` so
the code is stable across the store and calendar boundary.
"""

from __future__ import annotations

__all__ = [
    "APPOINTMENT_NOT_FOUND",
    "INVALID_WRITE_MODE",
    "LEAD_ALREADY_EXISTS",
    "LEAD_NOT_FOUND",
    "MALFORMED_PAYLOAD",
    "SLOT_UNAVAILABLE",
    "STAGE_TRANSITION_INVALID",
    "First60Error",
]

LEAD_NOT_FOUND = "LEAD_NOT_FOUND"
LEAD_ALREADY_EXISTS = "LEAD_ALREADY_EXISTS"
STAGE_TRANSITION_INVALID = "STAGE_TRANSITION_INVALID"
SLOT_UNAVAILABLE = "SLOT_UNAVAILABLE"
APPOINTMENT_NOT_FOUND = "APPOINTMENT_NOT_FOUND"
MALFORMED_PAYLOAD = "MALFORMED_PAYLOAD"
INVALID_WRITE_MODE = "INVALID_WRITE_MODE"


class First60Error(Exception):
    """An error with a stable machine-readable ``code``.

    ``detail`` is the human-readable explanation; ``code`` is one of
    the module-level constants and is the only thing callers should
    match on.
    """

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")
