# First60: Design

Status: the design document for this project, kept in the repo root.
Prepared 2026-11-07 from RESEARCH.md (held in the TechAura design
workspace, not in this repo). Build step 1 of 7 is complete: the
package skeleton, the strict pack loader and the five bundled packs
exist and are tested. The remaining build steps are listed in
section 14. Owner: TechAura (@techaurah).
Relationship to the portfolio: this is the running-agent companion to
leadpipe-mcp. LeadPipe is the record layer (an MCP server exposing
pipeline operations with guardrails); this project is the actor layer
(the receptionist that talks to leads and drives that pipeline). It
reuses LeadPipe's proven vocabulary and safety patterns, and none of its
code or scope: LeadPipe sends nothing and talks to no lead; this project
exists precisely to do the talking, under stricter rules.

## 1. Name

**Recommendation: First60** (repo `techaurah/first60`, package `first60`).

The whole product is one measurable promise: every new enquiry gets a
real first reply, with a next step, inside the first 60 seconds, at any
hour. The name states the claim the demo then proves, in the coined
house style of qualbench and WorkLang. "AI receptionist" is what it is;
"First60" is why it wins.

Alternatives:
1. **`ai-receptionist`**: maximum search discoverability and an exact
   match for the offer's language, but it is the generic category name in
   a namespace of ~4,200 repos; nothing about it is ownable, and it
   invites comparison with voice products we deliberately are not.
2. **`nightdesk`**: strong emotional hook on the after-hours leak (the
   10 PM enquiry nobody answers), but it undersells the daytime
   speed-to-lead case, which is half the value.

Build step 0 verifies GitHub and PyPI availability of `first60` before
anything is scaffolded; if it is taken in a conflicting niche, fall back
to alternative 1 rather than inventing a fourth name under time pressure.

## 2. Positioning

One line: **First60 is an open-source AI receptionist for service
businesses that answers every text enquiry in under a minute, qualifies
it against your rules, books the appointment, and follows up until the
lead replies or opts out.**

For: plumbers, med spas, clinics, real estate practices and similar
appointment businesses whose leads arrive as DMs, WhatsApp-style messages
and web-form enquiries, and who have no CRM and no one watching the inbox
after hours. This is the reference implementation behind TechAura's AI
Lead Automation offer: the same loop we deploy for clients, readable and
forkable.

Explicitly not: a voice/phone product (that ground is occupied, see
RESEARCH.md), a CRM, a marketing platform, or a general agent framework.

## 3. Scope

### v0.1.0 in scope
- Text channels behind one channel protocol: a generic JSON webhook
  channel (the integration surface for forms and future platform
  adapters), a console channel, and a simulated channel for demo/tests.
- Instant first reply and multi-turn qualification conversation driven by
  a per-business rule pack (services, questions, hours, escalation terms).
- Deterministic qualification scoring and pipeline stages (Section 5).
- Appointment booking against a calendar protocol: availability from
  business hours + busy blocks, re-check at booking time, idempotent
  booking (the LeadPipe pattern).
- Follow-up engine: scheduled touches with caps, business-hours
  awareness, stop-on-reply, opt-out handling, appointment reminders.
- Human handoff rules with an owner summary; automation pauses per lead.
- Write modes for real sends: direct, dry-run, approval (LeadPipe
  pattern). Demo mode sends only to a fake outbox.
- Storage: SQLite file (stdlib) plus an in-memory store with the same
  protocol for tests and demo.
- Demo mode: zero credentials, seeded business and leads, simulated
  clock, scripted end-to-end scenario plus an interactive console mode.
- Optional LLM responder behind an interface, off by default (Section 6).

### Out of scope for v0.1.0 (explicitly not built)
- Voice calls, telephony, STT/TTS of any kind.
- Platform-native senders for Instagram, WhatsApp or email (v0.2
  candidates, each behind the channel protocol and its platform's
  official API and policy review; unofficial-client sending is out of
  scope permanently, per the ban-risk evidence in RESEARCH.md).
- Google Calendar and Google Sheets adapters (v0.2 candidates; the
  protocols are shaped so the LeadPipe-proven patterns drop in).
- Multi-business tenancy, hosted deployment, web dashboard UI (a status
  endpoint and the daily summary are the v0 read surfaces).
- Payments, invoicing, review requests, outbound campaigns or cold
  outreach of any kind. First60 only ever replies to people who contacted
  the business first, plus follow-ups to those same conversations.
- Replacing leadpipe-mcp or slotfill: pipeline record-keeping exposed to
  assistants stays LeadPipe's job; First60 keeps its own operational
  store and shares vocabulary, not storage.

## 4. Architecture

```
            +------------------- channels -------------------+
            |  webhook (JSON in/out)   console   simulated   |
            +------------------------+-----------------------+
                                     v
   inbound message -> [reception] -> dedupe conversation, load lead
                                     |
            +------------------------+-----------------------+
            |  conversation engine (per-lead state machine)  |
            |   extract -> qualify -> score -> stage move    |
            |   decide next action: reply / offer slots /    |
            |   book / hand off / schedule follow-up         |
            +-----+------------------+------------------+----+
                  v                  v                  v
           [responder]        [calendar]        [follow-up engine]
           rules / LLM        availability      scheduler, caps,
           (phrasing)         + idempotent      opt-out, reminders
                              booking
                  \                  |                  /
                   +-------- [store: leads, messages, --------+
                            appointments, followups, audit]
                                     |
                            [daily summary + status]
```

Design rules that hold across every module:
1. **Rules decide, responders phrase.** Intent, extraction, scoring,
   stage moves, slot offers, booking and follow-up timing are computed by
   deterministic code. A responder (template or LLM) receives a decision
   object and renders text. This is the project's core claim and its test
   strategy: the decisions are unit-testable without a model.
2. **A clock is injected everywhere.** Production uses the system clock;
   demo and tests use a simulated clock, so a follow-up due in 24 hours
   is testable in milliseconds and demoable in one run.
3. **Every side effect is audited.** Each reply sent, stage move, booking
   and follow-up is an append-only audit row with mode
   (direct / dry_run / approval / demo), in the LeadPipe pattern.
4. **No silent sends, ever.** In demo mode sends land in a fake outbox.
   In real mode the write-mode gate applies to every outbound message,
   including follow-ups and reminders.

### Modules (package `first60`)
```
src/first60/
  cli.py            entry points: demo, serve, summary, init
  config.py         business.toml loading + validation (stdlib tomllib)
  models.py         Lead, Message, Appointment, FollowUp, enums
  errors.py         closed error-code set, LeadPipe style
  pipeline/
    stages.py       stage enum + transition map (pure)
    scoring.py      qualification scoring + bands (pure)
    extract.py      slot extraction from messages (pure)
    qualify.py      question flow: what is known, what to ask next (pure)
    handoff.py      escalation rules (pure)
  respond/
    base.py         Responder protocol: render(decision, facts) -> text
    rules.py        deterministic template responder (default)
    llm.py          optional OpenAI-compatible responder (urllib, no SDK)
  channels/
    base.py         Channel protocol: receive() / send()
    webhook.py      generic JSON webhook channel (stdlib http.server)
    console.py      interactive terminal channel
    simulated.py    scripted channel for demo and tests
  calendar/
    base.py         Calendar protocol: free_slots() / book()
    local.py        business hours + SQLite busy blocks
  followups.py      scheduler: due touches, caps, stop conditions
  store/
    base.py         Store protocol
    sqlite.py       durable store
    memory.py       in-memory store (demo/tests, same contract)
    schema.py       DDL + migrations-by-version
  demo_data.py      seeded business + leads (fictional BrightSmile Dental)
  demo.py           scripted scenario runner on the simulated clock
  server.py         stdlib HTTP server: webhook, demo chat, /status
packs/
  dental.toml  plumber.toml  med-spa.toml  clinic.toml  real-estate.toml
tests/              mirrors the layout
docs/               configuration.md, safety.md, packs.md, channels.md
```

## 5. The pipeline model (inherited from LeadPipe, adapted)

**Stages** (front-desk subset of the LeadPipe stage vocabulary; the
sales stages PROPOSAL / NEGOTIATION / WON stay in LeadPipe's domain):
`NEW -> CONTACTED -> QUALIFIED -> BOOKED`, with `NURTURE` and `LOST`
reachable as in LeadPipe's transition map, and reactivation
`LOST -> NURTURE` only. Illegal transitions raise
`STAGE_TRANSITION_INVALID`; same-stage is a no-op success. Dedup before
create, on normalised email then phone, exactly as LeadPipe specifies.

**Scoring** (computed by the server from extracted signals, never
accepted as input, never produced by an LLM). Components, 0-100 total:
- `service_fit` 0-25: requested service matches a bookable service in the
  pack (full), a related service (partial), or is unclassifiable (low).
- `urgency` 0-20: emergency or "today" signals, requested timeline.
- `contact` 0-15: name known, plus a reachable contact (phone, email or
  channel handle) captured.
- `completeness` 0-15: share of the pack's qualifying questions answered.
- `value` 0-15: the matched service's configured value tier, or a stated
  job-size signal.
- `engagement` 0-10: replies within the conversation, follow-up responses.

Bands use LeadPipe's thresholds so the two projects read identically:
HOT 80-100, WARM 65-79, NURTURE 50-64, LOW below 50. Component scores are
stored per lead and shown in the summary, so a human can always see why
a lead is HOT; a hand-editable rule pack, not a model, is the tuning
surface.

## 6. Responders: templates by default, LLM optional and caged

- Default `RuleResponder`: renders the decision from the pack's templates
  with the business's own facts (services, prices where the pack chooses
  to publish them, hours, address). Zero keys, fully deterministic, and
  the mode the demo and the entire test suite run in.
- Optional `LLMResponder`: any OpenAI-compatible endpoint via stdlib
  urllib (no SDK dependency), configured by env vars, off unless set. It
  receives only the decision object and the allowed-facts sheet. Its
  output is validated before sending: if a booking decision's offered
  slots do not appear verbatim, if a price or service not on the fact
  sheet appears, or if the output is empty or over length, the send
  falls back to the template rendering of the same decision and the
  fallback is audit-logged. Extraction, scoring and decisions never come
  from the LLM in either mode (contrast: the single-file demos in
  RESEARCH.md keep extraction rule-based for the same reason; we extend
  that discipline to every decision).

## 7. Follow-up engine

Policy lives in the business pack; defaults: touch 1 at +4h, touch 2 at
+24h, touch 3 at +72h after last outbound with no reply, maximum 3 touches
per conversation in v0, sent only inside the business's waking window
(default 08:00-21:00 local) unless the lead is mid-conversation.
Stop conditions, checked at fire time, not schedule time: any inbound
reply, a confirmed booking, an opt-out (STOP / unsubscribe / "stop
messaging me" patterns), stage LOST, or an open handoff. Appointment
reminders are separate from the follow-up sequence: 24h and 2h before a
confirmed appointment, only where the lead consented to reminders during
booking. Every fired or suppressed touch writes an audit row with its
reason, so "why did this lead get / not get a message" is always
answerable from the log. This engine is the piece no scanned incumbent
ships; it gets the deepest tests.

## 8. Handoff rules

A lead is handed to the human owner, with automation paused for that
lead and a summary (who, what they asked, score, stage, last messages)
written to the outbox/summary surface, when any of these fire:
- Emergency terms from the pack (plumber: gas smell, burst pipe flooding;
  clinic/med spa: pain, swelling, adverse reaction), the reply is a
  fixed safety template with the business's emergency instruction, never
  advice.
- Complaint or anger signals, refund or legal terms.
- The lead asks for a human, in any wording the extractor recognises.
- Two consecutive extraction failures on the same question (the
  conversation is stuck; a human does better).
- Anything the pack marks `handoff_only` (for example insurance claims).

## 9. Demo mode (the launch asset)

`python -m first60 demo`: no credentials, no network, no Docker:
1. Loads the dental pack as fictional BrightSmile Dental, seeds the
   local calendar with busy blocks, simulated clock set to Tuesday
   21:40.
2. Runs the scripted scenario, printing the transcript as it goes:
   - 21:47, an after-hours enquiry ("do you have anything Thursday
     morning, my crown is aching") gets an instant reply, is qualified
     in three questions, offered real free slots, and booked. Stage
     NEW -> BOOKED, score shown with its components.
   - The same lead re-messages; dedupe holds, no duplicate lead.
   - A second lead who enquired at noon and went quiet receives
     follow-up touch 1 when the clock reaches 16:00 (+4h) and books
     from it.
   - A third lead replies STOP; the audit shows the opt-out and no
     further touches are scheduled.
   - Wednesday 08:00: the daily summary prints: leads by stage and
     band, the booking list, the overdue and handed-off leads.
3. `python -m first60 demo --interactive` opens the console channel so a
   visitor can play the customer themselves.

The scenario is not a recording: it runs the real engine against the
simulated channel and clock, and the identical script is the release-
gate integration test. Quick-start target: clone to booked demo
appointment in under 5 minutes on a clean machine, measured during the
build (step 6) and printed in the README only as measured, per the LeadPipe
honesty rule.

## 10. Tech choices

- Python 3.11+, **zero required dependencies**. Stdlib only: sqlite3,
  tomllib, http.server, urllib, dataclasses. This is a deliberate
  competitive choice, not a limitation: every scanned rival needs a
  stack of accounts and services before first run; First60 needs Python.
- Optional extras in pyproject: none required for v0.1.0. The LLM
  responder uses urllib against an OpenAI-compatible endpoint, so even
  the AI path adds no dependency. (FastAPI, a real database server, and
  platform SDKs are v0.2+ decisions, each behind the existing protocols.)
- Packaging mirrors leadpipe-mcp: pyproject, `src/` layout, console
  script `first60`, MIT license, type hints on public functions, mypy
  non-strict in CI.

## 11. Test plan (target: 100+ tests, all offline)

Mirroring the portfolio's standards (leadpipe-mcp 94, WorkLang 117):
- scoring (14): band boundaries 49/50, 64/65, 79/80; each component at
  min/max; unclassifiable service; total never accepted as input.
- stages (10): every allowed transition; illegal set (BOOKED -> NEW,
  LOST -> QUALIFIED, WON-stage absence); same-stage no-op; dedupe
  precedence email over phone, formatting variants.
- extraction + qualification flow (18): service matching, timeline and
  urgency phrases, contact capture, question ordering, completeness
  accounting, two-failure stuck detection.
- calendar + booking (12): business-hours intersection, busy-block
  exclusion, slot sizes, re-check at booking time (slot taken between
  offer and confirm -> `SLOT_UNAVAILABLE`), idempotent re-book returns
  the same appointment.
- follow-up engine (14): schedule times, waking-window deferral, cap
  enforcement, each stop condition, reminder consent gate, suppression
  audit reasons, all on the simulated clock.
- handoff (7): each trigger class, safety template content, automation
  pause, summary contents.
- responders (12): template rendering of every decision type; LLM
  responder against a stub HTTP server (no network): slot-verbatim
  validation, fact-sheet violation fallback, empty/overlong fallback,
  fallback audit row.
- store parity (8): the same contract tests run against sqlite and
  memory stores.
- server + webhook channel (6): message in -> reply out round trip,
  malformed payload rejection, /status shape.
- config + packs (6): all five shipped packs load and validate; a broken
  pack fails with a named field.
- integration (2): the full demo scenario end to end (the release gate),
  and the daily summary against the scenario's end state.
Total target ≈ 109. No test touches the network or a real credential.

## 12. CI plan

GitHub Actions on push and PR, Python 3.11 and 3.12: install from
pyproject, `pytest`, `ruff` (lint + format check), `mypy` non-strict.
Red CI blocks the v0.1.0 tag, no bypass: the standing house rule from
the LeadPipe spec.

## 13. README outline (HOOK / VALUE, in the portfolio's best style)

1. **Name + one-breath claim.** "First60: every lead answered in the
   first 60 seconds." Badge row: license, CI, Python, stars.
2. **HOOK: the 10 PM problem.** The after-hours enquiry, the morning
   reply, the booked competitor, in three sentences, then the demo
   transcript screenshot/text showing the same enquiry booked at 21:47.
3. **Run it now.** The demo command and the measured quick-start time;
   interactive mode; "no keys, no Docker, no accounts."
4. **VALUE: what it does.** The loop as a numbered flow (reply, qualify,
   score, book, follow up, hand off, summarise) with the pipeline table:
   stages, bands, follow-up policy defaults.
5. **Decisions by rules, not prompts.** The Section 6 separation, the
   scoring components table, and why it is testable. The honest
   comparison table vs a voice receptionist and vs an n8n assembly (from
   RESEARCH.md, kept factual).
6. **Make it yours.** Business packs: copy a pack, edit services,
   questions, hours. One fully worked vertical (dental) in the main text.
7. **Safety.** Write modes, no silent sends, opt-out handling, handoff
   rules, what it can never do in v0.1.0 (call anyone, cold-message
   anyone, give medical or trade advice).
8. **Going live.** The webhook channel contract, write-mode choice, and
   the honest statement that platform-native senders are v0.2 and why.
9. **Architecture + docs links.** Diagram from Section 4; docs/ pages.
10. **Roadmap as news beats.** v0.2 candidates (Google Calendar adapter,
    first platform sender behind official APIs, LeadPipe sync adapter),
    each labelled candidate, not promise.
11. **Limitations, stated plainly.** Text only; single business per
    install; the demo business is fictional and its numbers are
    illustrative, not results.
12. Citation of the pattern sources, Contributing, License (MIT).

## 14. Build steps (each independently verifiable)

0. **Name and freeze.** Verify `first60` availability on GitHub and
   PyPI; freeze this design; anything not in Section 3 goes to the
   backlog list. Done when: availability recorded, scope list signed off.
1. **Skeleton.** Repo scaffolding in the portfolio pattern: pyproject,
   src layout, LICENSE (MIT), README skeleton, CONTRIBUTING, SECURITY,
   .gitignore, CI workflow, config loader with pack validation.
   Done when: CI runs green on an empty-but-importable package; all five
   packs load.
2. **Pure core.** Stages + transition map, scoring + bands, extraction,
   qualification flow, no I/O. Done when: the ~42 pure-core tests pass.
3. **Store and calendar.** Store protocol with sqlite and memory
   implementations under one contract test set; LocalCalendar
   availability and idempotent booking. Done when: parity tests and
   booking tests pass, including slot-taken-between-offer-and-confirm.
4. **Responders and handoff.** RuleResponder for every decision type;
   LLMResponder with validation and template fallback against a stub
   server; handoff rules with safety templates. Done when: responder and
   handoff tests pass; the engine completes a full conversation with the
   LLM path disabled and with it stubbed.
5. **Channels and follow-up engine.** Channel protocol with simulated,
   console and webhook implementations; scheduler with caps, waking
   window, stop conditions and reminder consent, all on the injected
   clock. Done when: follow-up and server tests pass.
6. **Demo.** Seed data, scripted scenario, interactive mode; the
   scenario wired in as the integration test; clean-machine quick-start
   timed honestly. Done when: the release-gate test passes and the
   measured quick-start time is recorded for the README.
7. **Docs and release prep.** README completed per Section 13 with the
   measured time; docs/ pages (configuration, safety, packs, channels);
   CHANGELOG from actual commits; dogfood run against fictional data
   only, friction logged as issues. Done when: the v0.1.0 checklist in
   Section 15 passes end to end.

## 15. v0.1.0 release definition of done

- [ ] CI green on main on Python 3.11 and 3.12 (pytest, ruff, mypy).
- [ ] Test count at or above the Section 11 target (~109), all offline.
- [ ] Demo scenario integration test passes; it is the same script a
      visitor runs.
- [ ] Clean-environment quick start verified: fresh venv, README only,
      clone to booked demo appointment inside the time the README
      claims; the claim is the measurement, not the target.
- [ ] All five packs load, validate and each completes a scripted
      qualification conversation in tests.
- [ ] No credential, token or real business data anywhere in the repo or
      its history; demo business is fictional (BrightSmile Dental).
- [ ] README carries the limitations section and the no-voice,
      no-cold-outreach statements; no claim in the README contradicts
      RESEARCH.md's claims discipline.
- [ ] LICENSE, SECURITY.md, CONTRIBUTING.md present; version 0.1.0 in
      pyproject; CHANGELOG written from actual commits.
- [ ] Tag `v0.1.0` and release notes drafted from the changelog
      (publication follows the standing approval flow).

## 16. Risks, and what would make us stop or pivot

1. **The incumbents move down into our layer.** Watch item: Tel-Agent
   adding qualification/follow-up workflow, or LobbyStack making the AI
   answer texts with a follow-up cadence. If either ships our full loop,
   differentiation narrows to packaging (zero-dependency, MIT,
   rules-not-prompts). Pivot then: reposition First60 as the reference
   implementation and teaching artifact, and lean on the LeadPipe sync
   adapter as the distinctive bridge. Review the watch item monthly.
2. **Voice gravity.** The field's demand signal is phone calls, and
   every partner conversation will pull toward voice. Voice is a
   different product on someone else's stack (LiveKit/Siphon). Rule: any
   voice work is a separate, explicit decision with its own research
   pass, never scope drift inside this repo. If the market verdict is
   that text-first has no audience after two release beats, stop and
   write the post-mortem rather than bolting on telephony.
3. **Platform policy on real channels.** Instagram and WhatsApp sending
   is policy-gated; unofficial clients carry ban risk (documented in
   RESEARCH.md). v0's webhook-only surface keeps the core clean. If, at
   v0.2 planning, the demanded channels cannot be served through
   official APIs, stop at the contract and let deployers integrate,
   rather than shipping a ban-risk adapter under our name.
4. **Demo friction.** If the clean-machine quick start cannot reach a
   booked demo appointment in under 5 minutes after two fix rounds in
   step 6, the packaging has failed at the exact point Frontdesk.ai
   failed. Stop adding features; fix onboarding or shrink scope until
   it passes.
5. **LLM responder trust.** If validation fallbacks fire often in
   dogfooding (the model keeps inventing prices or dropping slots), ship
   v0.1.0 rules-only and mark the LLM path experimental in docs, instead
   of loosening the validator.
6. **Duplication drift.** If a feature request would rebuild LeadPipe
   (assistant-facing pipeline tools) or slotfill (standalone slot
   management) inside First60, it belongs in those repos; First60 links
   to them. The boundary in the Status note is the guardrail.
