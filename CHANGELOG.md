# Changelog

All notable changes to First60 will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to
Semantic Versioning.

## [0.1.0] - Unreleased

### Added
- Repository skeleton (build step 1): `pyproject.toml` with zero required
  dependencies, `src` layout, MIT license, contributing and security docs,
  and a GitHub Actions CI workflow (Python 3.11 and 3.12, pytest, ruff,
  mypy non-strict).
- Business pack loader (`first60.config`): loads and validates a pack
  from TOML using stdlib `tomllib`, raising `PackError` naming the broken
  field on any invalid pack.
- Five validated business packs in `packs/`: dental (fictional
  BrightSmile Dental), plumber, med spa, clinic and real estate. Each
  pack carries services, qualifying questions, business hours,
  follow-up policy defaults (touches at +4h, +24h, +72h, max 3, waking
  window 08:00-21:00) and emergency handoff terms.
- CLI entry points: `first60` console script and `python -m first60`
  with `--help` and `--version`. The `demo`, `serve`, `summary` and
  `init` commands are stubs until their build steps land.
- Pure core (build step 2): stages and transition map
  (`first60.pipeline.stages`, including `STAGE_TRANSITION_INVALID` and
  email-then-phone lead dedupe), deterministic qualification scoring
  (`first60.pipeline.scoring`, six components, LeadPipe bands HOT 80+,
  WARM 65+, NURTURE 50+, LOW below 50), slot extraction from messages
  (`first60.pipeline.extract`, service matching, timeline and urgency,
  name/phone/email capture, opt-out and human-request detection), and
  the qualification question flow (`first60.pipeline.qualify`,
  opportunistic answers, two-failure stuck detection). No I/O anywhere
  in the pure core; 127 new tests, all five packs complete a scripted
  qualification conversation in tests.
- Store and calendar (build step 3): closed error-code set
  (`first60.errors`, `LEAD_NOT_FOUND` / `LEAD_ALREADY_EXISTS` /
  `STAGE_TRANSITION_INVALID` / `SLOT_UNAVAILABLE` /
  `APPOINTMENT_NOT_FOUND`); stored records (`first60.models`: lead,
  message, appointment, follow-up, audit row) as frozen dataclasses
  with JSON-friendly fields; one store protocol
  (`first60.store.base`) with a durable SQLite implementation (v1
  schema, dict fields as JSON) and an in-memory implementation, both
  passing the same 11 contract tests; a local calendar
  (`first60.calendar.local`) with business-hours availability from
  the pack, busy blocks from the store, an injected clock, booking
  re-checked at booking time (`SLOT_UNAVAILABLE` when a slot is taken
  between offer and confirm) and idempotent re-booking under one key.
- Responders and handoff (build step 4): handoff rules
  (`first60.pipeline.handoff`, emergency terms from the pack with a
  fixed safety template carrying the pack's own emergency instruction,
  complaint/anger/refund/legal signals, human requests, two-failure
  stuck detection, pack `handoff_only` items, owner summary, automation
  pause flag); a responder interface (`first60.respond.base`,
  `Decision` kinds greet / ask / offer_slots / confirm_booking /
  handoff / follow_up / acknowledge / opt_out plus a `FactSheet` of the
  only facts a responder may state); a deterministic template responder
  (`first60.respond.rules`, slots verbatim, safety text passed through
  untouched); an optional LLM responder (`first60.respond.llm`,
  OpenAI-compatible endpoint via stdlib `urllib`, off unless
  `FIRST60_LLM_BASE_URL` is set, validated before sending: empty,
  overlong, offered slots not verbatim, any price, or a service not on
  the fact sheet all fall back to the template with the reason
  reported for audit). A test-local driver proves the pieces compose:
  a full conversation (qualify, offer real free slots, book, confirm)
  runs with the LLM path disabled and with it stubbed. 35 new tests
  (227 total), ruff and mypy clean. One driver-order fix found by the
  tests: opt-out is checked before handoff, so STOP never reads as a
  stuck conversation.
- Channels and follow-up engine (build step 5): a conversation
  engine (`first60.engine`, the step-4 test driver promoted to the
  real module: dedupe by channel handle then extracted contact,
  opt-out before handoff, qualify, offer real free slots, book with
  reminder consent, every side effect audited, write-mode gate on
  every send); a channel protocol (`first60.channels.base`) with a
  scripted simulated channel, an interactive console channel and a
  generic JSON webhook channel (malformed payloads answered 400
  with `MALFORMED_PAYLOAD`, never reaching the engine); a follow-up
  scheduler (`first60.followups`, chained touches at +4h/+24h/+72h
  from the last outbound, max 3, waking-window deferral to the next
  08:00, stop conditions checked at fire time: opt-out, stage LOST,
  automation paused, already booked, replied; appointment reminders
  at 24h and 2h, consent-gated, tracked by audit rows); a stdlib
  HTTP server (`first60.server`: `POST /message`, `GET /status`,
  `GET /` demo chat page) wired to `first60 serve` with `--pack`,
  `--host`, `--port`, `--mode` and `--db`. The SQLite store is now
  thread-safe (one re-entrant lock, `check_same_thread=False`) for
  the threaded server; the local calendar accepts an aware UTC
  clock and converts it to business-local time. 45 new tests (272
  total), ruff and mypy clean. Two fixes found by testing: the
  smoke test caught the SQLite thread error above, and the
  follow-up clock resets on every outbound reply (a new reply
  cancels the scheduled touch and re-schedules touch 1).
  36 new tests (192 total), ruff and mypy clean.
