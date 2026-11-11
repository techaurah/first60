# First60 build step 4: responders and handoff

Date: 2026-11-11. Author: TechAura (@techaurah).

## What was built

DESIGN.md section 14 step 4: "RuleResponder for every decision type;
LLMResponder with validation and template fallback against a stub
server; handoff rules with safety templates."

- `src/first60/pipeline/handoff.py`: the section 8 escalation rules
  (pure, no I/O). Triggers in fixed priority order: emergency terms
  from the pack, pack `handoff_only` items, complaint / anger /
  refund / legal signals, a human request (via the extractor's
  existing `detect_human_request`), two consecutive extraction
  failures (`state.stuck`). An emergency reply is the fixed safety
  template: framing plus the pack's own emergency instruction quoted
  verbatim, never advice. Other triggers get a neutral handoff notice.
  Every decision carries the owner summary (who, contact, service,
  urgency, last message) and `pause_automation=True`; the engine
  (step 5) enforces the pause.
- `src/first60/respond/base.py`: the responder interface. A
  `Decision` carries one of eight kinds (greet, ask, offer_slots,
  confirm_booking, handoff, follow_up, acknowledge, opt_out) with
  typed fields; slots are display strings that must appear verbatim,
  and `handoff_text` is passed through untouched. A `FactSheet` is the
  only facts a responder may state: business name, bookable services,
  hours, emergency instruction. It carries no prices, because no pack
  publishes any.
- `src/first60/respond/rules.py`: the deterministic template
  responder (default). Every decision kind renders from the pack's own
  words and the decision's fields; nothing is invented.
- `src/first60/respond/llm.py`: the optional LLM responder. Any
  OpenAI-compatible endpoint via stdlib `urllib` (no SDK), off unless
  `FIRST60_LLM_BASE_URL` is set (`from_env` returns None otherwise).
  Output is validated before sending: empty, over the 600-character
  cap, offered slots not verbatim, any price, or a service offered
  that is not named exactly as the fact sheet lists it. Any failure
  falls back to the template rendering of the same decision and
  reports the reason through `on_fallback` so the engine can
  audit-log it. Validation is a safety net, not a proof: an invented
  service phrased in some other way can slip through, which is why
  the LLM path stays off by default.

## Verification (local, before publish)

- 227 pytest passed (192 existing + 35 new: 10 handoff, 21 responder,
  4 conversation).
- `ruff check .` clean, `ruff format --check .` clean, `mypy
  src/first60` clean (25 source files).
- The handoff tests cover the section 11 handoff set: each trigger
  class, safety template content (instruction verbatim), automation
  pause, owner summary contents, and priority (emergency beats
  complaint).
- The responder tests cover the section 11 responder set: template
  rendering of every decision type, plus the LLM responder against a
  stub HTTP server (no network): valid output used verbatim,
  slot-verbatim violation, invented price, invented service, known
  service passing, empty, overlong, HTTP error, and the fallback
  callback.
- The conversation tests prove the pieces compose: a test-local
  driver (the step-5 engine's predecessor) runs the demo enquiry end
  to end: greet, qualify in three questions, offer real free slots
  from the calendar, book Thursday 09:00, confirm, stage
  NEW -> CONTACTED -> QUALIFIED -> BOOKED, score band WARM or HOT,
  appointment in the store. It runs once with the LLM path disabled
  and once with it stubbed, including a stubbed price-inventing reply
  that falls back to the template confirmation. An emergency message
  hands off with the safety template; STOP opts out.

## One fix found by the tests

The first run of the opt-out conversation test failed: STOP hit the
"stuck" handoff before the opt-out check, because the lead had two
consecutive extraction failures on the service question. Opt-out now
wins over every other check in the driver, so STOP never reads as a
stuck conversation. The ordering rule is recorded here for the step-5
engine: opt-out first, then handoff, then the normal flow.

## Done-condition status

DESIGN.md section 14 step 4 done condition: "responder and handoff
tests pass; the engine completes a full conversation with the LLM
path disabled and with it stubbed."

- Responder tests: 21 pass (8 template kinds + 13 LLM/stub cases).
- Handoff tests: 10 pass.
- Full conversation: the test-local driver completes it with the LLM
  path disabled (rule responder) and with it stubbed (stub server),
  including the price-fallback path.

## Open items for step 5

The driver in `tests/test_conversation.py` is test-only and thin: it
hard-codes the demo clock and Thursday as the booking day, and it
does not write audit rows for replies or fallbacks. The step-5
engine replaces it with the real conversation engine, the channel
protocol, and the follow-up scheduler, and must keep the ordering
rule above (opt-out, then handoff, then the normal flow) and the
fallback audit row the LLM responder reports through `on_fallback`.
