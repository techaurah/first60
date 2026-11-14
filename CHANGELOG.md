# Changelog

All notable changes to First60 will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to
Semantic Versioning.

## [0.1.0] - Unreleased

The first release: the full text-first receptionist loop, built in
seven steps between 2026-11-08 and 2026-11-14, each step published
to `main` on its day. Test counts below are the suite totals at the
end of each step, all tests offline, stdlib only, zero required
dependencies throughout.

### Added

- Repository skeleton (build step 1, 2026-11-08): `pyproject.toml`
  with zero required dependencies, `src` layout, MIT license,
  contributing and security docs, code of conduct, issue and PR
  templates, and a GitHub Actions CI workflow (Python 3.11 and
  3.12, pytest, ruff, mypy non-strict).
- Business pack loader (`first60.config`): loads and validates a
  pack from TOML using stdlib `tomllib`, raising `PackError`
  naming the broken field on any invalid pack.
- Five validated business packs in `packs/`: dental (fictional
  BrightSmile Dental), plumber (SwiftFlow Plumbing), med spa
  (GlowHaven Med Spa), clinic (Harborview Family Clinic) and real
  estate (Keystone Homes Realty). Each pack carries services,
  qualifying questions, business hours, follow-up policy defaults
  (touches at +4h, +24h, +72h, max 3, waking window 08:00-21:00)
  and emergency handoff terms.
- CLI entry points: `first60` console script and `python -m
  first60` with `--help` and `--version`. 29 tests at the end of
  step 1.
- README visuals (2026-11-09): architecture, workflow and repo
  structure diagrams plus a demo-output visual, all drawn from the
  real code and the real demo transcript. A generic hero image
  added the same day was removed the same day.
- Dependabot config (2026-11-10): grouped weekly updates with a
  7-day cooldown.
- Pure core (build step 2, 2026-11-09): stages and transition map
  (`first60.pipeline.stages`, including
  `STAGE_TRANSITION_INVALID` and email-then-phone lead dedupe),
  deterministic qualification scoring
  (`first60.pipeline.scoring`, six components, LeadPipe bands HOT
  80+, WARM 65+, NURTURE 50+, LOW below 50), slot extraction from
  messages (`first60.pipeline.extract`, service matching,
  timeline and urgency, name/phone/email capture, opt-out and
  human-request detection), and the qualification question flow
  (`first60.pipeline.qualify`, opportunistic answers, two-failure
  stuck detection). No I/O anywhere in the pure core; 127 new
  tests (156 total), all five packs complete a scripted
  qualification conversation in tests.
- Store and calendar (build step 3, 2026-11-10): closed error-code
  set (`first60.errors`, `LEAD_NOT_FOUND` /
  `LEAD_ALREADY_EXISTS` / `STAGE_TRANSITION_INVALID` /
  `SLOT_UNAVAILABLE` / `APPOINTMENT_NOT_FOUND`); stored records
  (`first60.models`: lead, message, appointment, follow-up, audit
  row) as frozen dataclasses with JSON-friendly fields; one store
  protocol (`first60.store.base`) with a durable SQLite
  implementation (v1 schema, dict fields as JSON) and an
  in-memory implementation, both passing the same 11 contract
  tests; a local calendar (`first60.calendar.local`) with
  business-hours availability from the pack, busy blocks from the
  store, an injected clock, booking re-checked at booking time
  (`SLOT_UNAVAILABLE` when a slot is taken between offer and
  confirm) and idempotent re-booking under one key. 36 new tests
  (192 total), ruff and mypy clean.
- Responders and handoff (build step 4, 2026-11-11): handoff rules
  (`first60.pipeline.handoff`, emergency terms from the pack with
  a fixed safety template carrying the pack's own emergency
  instruction, complaint/anger/refund/legal signals, human
  requests, two-failure stuck detection, pack `handoff_only`
  items, owner summary, automation pause flag); a responder
  interface (`first60.respond.base`, `Decision` kinds greet / ask
  / offer_slots / confirm_booking / handoff / follow_up /
  acknowledge / opt_out plus a `FactSheet` of the only facts a
  responder may state); a deterministic template responder
  (`first60.respond.rules`, slots verbatim, safety text passed
  through untouched); an optional LLM responder
  (`first60.respond.llm`, OpenAI-compatible endpoint via stdlib
  `urllib`, off unless `FIRST60_LLM_BASE_URL` is set, validated
  before sending: empty, overlong, offered slots not verbatim,
  any price, or a service not on the fact sheet all fall back to
  the template with the reason reported for audit). A test-local
  driver proves the pieces compose: a full conversation (qualify,
  offer real free slots, book, confirm) runs with the LLM path
  disabled and with it stubbed. 35 new tests (227 total), ruff and
  mypy clean. One driver-order fix found by the tests: opt-out is
  checked before handoff, so STOP never reads as a stuck
  conversation.
- Channels and follow-up engine (build step 5, 2026-11-12): a
  conversation engine (`first60.engine`, the step-4 test driver
  promoted to the real module: dedupe by channel handle then
  extracted contact, opt-out before handoff, qualify, offer real
  free slots, book with reminder consent, every side effect
  audited, write-mode gate on every send); a channel protocol
  (`first60.channels.base`) with a scripted simulated channel, an
  interactive console channel and a generic JSON webhook channel
  (malformed payloads answered 400 with `MALFORMED_PAYLOAD`,
  never reaching the engine); a follow-up scheduler
  (`first60.followups`, chained touches at +4h/+24h/+72h from the
  last outbound, max 3, waking-window deferral to the next 08:00,
  stop conditions checked at fire time: opt-out, stage LOST,
  automation paused, already booked, replied; appointment
  reminders at 24h and 2h, consent-gated, tracked by audit rows);
  a stdlib HTTP server (`first60.server`: `POST /message`, `GET
  /status`, `GET /` demo chat page) wired to `first60 serve` with
  `--pack`, `--host`, `--port`, `--mode` and `--db`. The SQLite
  store is now thread-safe (one re-entrant lock,
  `check_same_thread=False`) for the threaded server; the local
  calendar accepts an aware UTC clock and converts it to
  business-local time. 45 new tests (272 total), ruff and mypy
  clean. Two fixes found by testing: the smoke test caught the
  SQLite thread error above, and the follow-up clock resets on
  every outbound reply (a new reply cancels the scheduled touch
  and re-schedules touch 1).
- Demo and measured quick-start (build step 6, 2026-11-13): a
  scripted demo scenario (`first60.demo`, run by `python -m
  first60 demo`) loads the dental pack as fictional BrightSmile
  Dental, seeds the local calendar with one busy block (an
  existing patient, Thursday 10:30), and runs the real engine
  against the simulated channel and a hand-set clock through a
  fixed Tuesday: a noon enquiry books Wednesday 09:00 from its
  +4h follow-up touch, an after-hours enquiry books Crown fitting
  Thursday 09:00 with its score and components printed (70,
  WARM), the same lead's re-message is deduped to one lead and
  one appointment, a STOP opt-out is audited with no further
  touches scheduled, and Wednesday 08:00 prints the daily summary
  (leads by stage and band, the booking list, overdue and
  handed-off leads). The identical script is the release-gate
  integration test (`tests/test_demo.py`). `python -m first60
  demo --interactive` opens the console channel on a fresh seeded
  world so a visitor can play the customer; `first60 summary`
  prints the same daily summary for a SQLite store. One engine bug
  found by the demo and fixed here: a booked lead who wrote again
  crashed with `STAGE_TRANSITION_INVALID` (the engine re-offered
  slots and attempted BOOKED -> QUALIFIED); the engine now
  acknowledges the booking by service and time and schedules no
  follow-up. Measured clean-machine quick-start: about 10 seconds
  from a fresh copy to the booked demo appointment (Python 3.12,
  two runs 9.8s and 10.1s). 13 new tests (285 total), ruff and
  mypy clean.
- Docs and release prep (build step 7, 2026-11-14): README
  completed per the design's section 13 (12 sections: claim, the
  10 PM hook, run-it-now with the measured quick-start, the loop
  with the scoring table, decisions-by-rules with the honest
  comparison table against voice receptionists and n8n assemblies
  from the 2026-11-06/07 competitor scan, make-it-yours with the
  worked dental vertical, safety, going live, architecture with
  the module layout and docs links, roadmap as labelled v0.2
  candidates, limitations stated plainly, sources and thanks);
  docs pages (`docs/configuration.md`, `docs/safety.md`,
  `docs/packs.md`, `docs/channels.md`) written from the real code;
  `first60 init` (`first60.init_pack`) scaffolds a starter
  business pack from any builtin pack, with `--name`, `--output`
  and `--force`, and the written file is validated before success
  is printed; `first60 serve` and `first60 summary` accept
  `--pack-file` for scaffolded packs; the wheel now ships
  `packs/` inside the installed package, verified by a real wheel
  build, a fresh-venv install, and a `first60 demo` run from the
  installed copy; the med-spa pack gained the "severe pain" and
  "swelling" emergency terms the dogfood run showed it missing;
  the directory tree in `docs/assets/directory-tree.txt` updated
  to the finished layout. 25 new tests (310 total), ruff and mypy
  clean. Measured quick-start re-run on 2026-11-14: about 11
  seconds (Python 3.12, two runs 11.2s and 10.9s).

### Fixed

- Name extraction no longer captures distress phrasing as a name
  (build step 7): "I'm in severe pain" used to capture the name
  "Severe Pain", so a handoff lead appeared under that name in the
  summary. Distress and symptom words (severe, bleeding, swelling
  and the like) and the verbs that introduce them (having,
  feeling, getting) are now in the non-name list, and any captured
  word from that list rejects the whole capture. Regression tests
  cover the reported phrase and its variants; real names are
  unaffected ("I'm John Sharp" still captures "John Sharp").
- Em dashes removed from all user-facing product text (build step
  7): the demo transcript, the booked-lead acknowledgement replies
  and the README quote of the transcript now use hyphens, per the
  standing TechAura writing rule. No behaviour changed; the tests
  asserting those strings were updated with them.
