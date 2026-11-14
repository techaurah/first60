# First60 build step 3: store and calendar

Date: 2026-11-10. Author: TechAura (@techaurah).

## What was built

DESIGN.md section 14 step 3: "Store protocol with sqlite and memory
implementations under one contract test set; LocalCalendar
availability and idempotent booking."

- `src/first60/errors.py`: the closed error-code set
  (`LEAD_NOT_FOUND`, `LEAD_ALREADY_EXISTS`,
  `STAGE_TRANSITION_INVALID`, `SLOT_UNAVAILABLE`,
  `APPOINTMENT_NOT_FOUND`) on one `First60Error` exception.
- `src/first60/models.py`: the stored records as frozen JSON-friendly
  dataclasses - `Lead`, `Message`, `Appointment`, `FollowUp`,
  `AuditRow` - plus `new_*` factories that generate ids and UTC
  timestamps. A lead carries its qualification state as the plain
  `state` dict (the pipeline's `ConversationState` as `asdict`), plus
  denormalised `stage`, `score_total` and `score_band` for the daily
  summary.
- `src/first60/store/`: the `Store` protocol (`base.py`), the v1 DDL
  with a `meta` schema-version row (`schema.py`), the durable
  `SQLiteStore` (stdlib `sqlite3`, dict fields as JSON text) and the
  `MemoryStore` (dicts, deep-copied on read and write so callers can
  never mutate stored state). The store is dumb persistence: stage
  moves go through `pipeline.stages.transition`, dedupe lookups
  normalise through the pipeline helpers, email/phone are stored in
  their normalised form.
- `src/first60/calendar/`: the `Calendar` protocol (`base.py`) and
  `LocalCalendar` (`local.py`). Availability is the pack's business
  hours minus booked appointments in the store; slots start on the
  pack's slot grid and must end by closing time. `book` re-checks the
  slot at booking time (a slot taken between offer and confirm raises
  `SLOT_UNAVAILABLE`), refuses past, off-hours and off-grid starts,
  and is idempotent: booking twice under one key returns the original
  appointment. The clock is injected (DESIGN.md rule 2).

## Verification (local, before publish)

- 192 pytest passed (156 existing + 36 new: 11 contract tests x 2
  implementations, 2 SQLite-only tests, 12 calendar tests).
- `ruff check .` clean, `ruff format --check .` clean, `mypy
  src/first60` clean (21 source files).
- The 12 calendar tests cover the DESIGN.md section 11 booking set:
  open-day grid (17 slots), closed day (0), duration handling,
  busy-block exclusion, booking visible in the store, slot taken
  between offer and confirm, idempotent re-book, outside-hours,
  past, off-grid, cancel frees the slot, past slots excluded today.
- The contract tests cover the section 11 store parity set (8 cases)
  plus list/filter cases: round trip, duplicate create, missing lead,
  dedupe lookups with formatting variants, legal/illegal stage moves,
  messages in order, appointment save/get/find-by-key/cancel,
  follow-up save/filter, audit append/filter, list by stage,
  score/state round trip. SQLite-only: data survives reopen, schema
  version recorded.

## Done-condition status

DESIGN.md section 14 step 3 done condition: "parity tests and booking
tests pass, including slot-taken-between-offer-and-confirm."

- Parity tests: 11 contract cases pass on both stores, identical
  behaviour. Booking tests: all 12 pass, including
  `test_slot_taken_between_offer_and_confirm` and
  `test_idempotent_rebook_returns_the_same_appointment`.

## Open items for step 4

None from this step. The store and calendar are complete and tested.
Step 4 (responders and handoff) builds on `LocalCalendar` for slot
offers and on the store for the audit trail; the engine in step 5
will write the audit rows this step's `append_audit` accepts.
