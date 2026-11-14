# First60

**First60: every lead answered in the first 60 seconds.**

First60 is an open-source AI receptionist for service businesses that
answers every text enquiry in under a minute, qualifies it against your
rules, books the appointment, and follows up until the lead replies or
opts out.

> **Status: build step 7 of 7 (docs and release prep).** The full loop
> is built and tested: the pure core (stages, scoring, extraction,
> qualification), the store (one protocol, SQLite and in-memory under
> the same contract tests) with a local calendar and idempotent
> booking, responders (a deterministic template responder for every
> decision type, an optional LLM responder validated against the fact
> sheet with template fallback, handoff rules with fixed safety
> templates), the channels and follow-up engine (webhook, console and
> simulated channels, capped touches inside the waking window with
> stop-on-reply and appointment reminders, `first60 serve` over HTTP),
> and the demo (the scripted BrightSmile Dental scenario runs the real
> engine end to end, and the same script is the release-gate
> integration test). Docs and release prep are complete: the README
> below, `docs/` pages, a changelog from actual commits, `first60
> init` for starter packs, and the wheel ships the builtin packs so
> an installed copy can load them. See [Build
> progress](#build-progress) below.

## The 10 PM problem

A customer messages at 10 PM about an aching tooth. Nobody is watching
the inbox. By morning they have booked with the competitor who replied
first. First60 exists for that enquiry: an instant first reply with a
next step, qualification against the business's own rules, a booked
appointment, and follow-ups if the lead goes quiet, at any hour.

## Run it now

```bash
git clone https://github.com/techaurah/first60.git
cd first60
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m first60 demo
```

Measured quick-start: about 11 seconds from a fresh copy to the
booked demo appointment (Python 3.12, two runs: 11.2s and 10.9s,
measured 2026-11-14). The clone step was a fresh local copy of the
tree; a real `git clone` of this small repo adds a few seconds on a
normal connection. No keys, no Docker, no accounts.

The demo runs the fictional BrightSmile Dental through a scripted
Tuesday: a noon enquiry books from its +4h follow-up, an after-hours
enquiry books Thursday morning, an opt-out stops all further touches,
and Wednesday 08:00 prints the daily summary. The headline moment:

```text
[Tuesday 21:47] sarah: do you have anything Thursday morning, my crown is aching
[Tuesday 21:47] BrightSmile Dental: Hi, thanks for messaging BrightSmile Dental. What is your name?
[Tuesday 21:47] sarah: I'm Sarah
[Tuesday 21:47] BrightSmile Dental: What is the best phone number or email to reach you on?
[Tuesday 21:47] sarah: 07123 456789
[Tuesday 21:47] BrightSmile Dental: Thanks Sarah. For Crown fitting, these times are free:
  Thursday 09:00, Thursday 09:30, Thursday 11:00. Which works best for you?
[Tuesday 21:47] sarah: Thursday 09:00 works for me
[Tuesday 21:47] BrightSmile Dental: You're booked in for Crown fitting on Thursday 09:00.
Sarah: stage NEW -> BOOKED, score 70 (WARM) - service_fit 15, urgency 10,
  contact 15, completeness 15, value 15, engagement 0.
```

The 10:00 slot never appears in the offer: the calendar already
holds an existing patient's Thursday 10:30 booking, so a 60-minute
crown cannot start at 10:00. Availability is real, not staged.

Play the customer yourself instead:

```bash
python -m first60 demo --interactive
```

The same script is the release-gate integration test
(`tests/test_demo.py`), so the demo a visitor runs and the demo the
test suite runs are one script, not two.

## What it does

The loop:

1. **Reply** instantly to a text enquiry (DM, WhatsApp-style message or
   web-form enquiry) with a next step.
2. **Qualify** the lead by asking the pack's questions in order.
3. **Score** the lead deterministically (service fit, urgency, contact,
   completeness, value, engagement) into HOT, WARM, NURTURE or LOW.
4. **Book** the appointment against business hours and busy blocks,
   re-checking availability at booking time.
5. **Follow up** on a schedule from the pack (touches at +4h, +24h,
   +72h, maximum 3), only inside the waking window (08:00-21:00),
   stopping on any reply, booking or opt-out.
6. **Hand off** to the human owner on emergency terms, complaints, or
   when the lead asks for a human, with automation paused for that lead.
7. **Summarise** the pipeline daily: leads by stage and band, bookings,
   overdue and handed-off leads.

### Pipeline stages and bands

| Stages | NEW, CONTACTED, QUALIFIED, BOOKED, NURTURE, LOST |
| ------ | ------------------------------------------------- |
| Bands  | HOT 80-100, WARM 65-79, NURTURE 50-64, LOW below 50 |
| Follow-up defaults | Touches at +4h, +24h, +72h; max 3; waking window 08:00-21:00 |

### Scoring components (0-100, computed, never accepted as input)

| Component | Points | What it measures |
| --------- | ------ | ---------------- |
| service_fit | 0-25 | Requested service matches a bookable service (full 25, related 15, unclassifiable 5) |
| urgency | 0-20 | Emergency terms, "today", this week, flexible |
| contact | 0-15 | Name known (5) plus a reachable contact (10) |
| completeness | 0-15 | Share of the pack's required questions answered |
| value | 0-15 | Matched service's value tier (high 15, standard 10, low 5) |
| engagement | 0-10 | Replies within the conversation (2 per reply, capped) |

Component scores are stored per lead and shown in the summary, so a
human can always see why a lead is HOT. A hand-editable rule pack, not
a model, is the tuning surface.

## Decisions by rules, not prompts

Qualification, scoring, stage moves, booking safety and follow-up
policy are deterministic code with tests. A responder (template by
default, or an optional LLM) only phrases the decision into text. An
LLM never decides, and its output is validated against the allowed
facts before sending, falling back to the template rendering if it
fails. That separation is what makes the system testable without a
model.

### How First60 compares

From the competitor scan in RESEARCH.md (repo pages read directly,
2026-11-06/07). First60 is a reference implementation of the
text-first receptionist loop. It is not the first AI receptionist
and not the first open-source receptionist: voice receptionists
already exist, and this project deliberately does not do voice.

|  | First60 v0.1.0 | Voice receptionist (Tel-Agent, LobbyStack) | n8n workflow assembly |
| --- | --- | --- | --- |
| Channel | Text: DM, web form, webhook | Phone calls (SIP/Twilio, STT/TTS) | Text via WhatsApp template |
| First run needs | Python only, zero credentials | PBX/SIP endpoint or Twilio, plus STT, LLM and TTS keys | n8n plus Evolution API and keys |
| Qualification scoring | Deterministic, six components, tested | None: Tel-Agent refuses the workflow layer by design | Suggested as an extension, untested |
| Booking | Idempotent, re-checked at booking time | Google Calendar via tools (LobbyStack) | Per-workflow extension |
| Follow-ups | Capped touches (+4h/+24h/+72h), stop-on-reply, opt-out | One appointment reminder at most (LobbyStack) | None in the stock workflow |
| Full loop demo | One command, no keys, simulated clock | No zero-credential run of the full loop | Workflow JSON for one vertical, not a codebase |

## Make it yours

Business behaviour lives in a pack: one TOML file per vertical.
Start from the closest shipped pack:

```bash
first60 init --pack dental --name "Acme Dental"
first60 serve --pack-file my-business.toml
```

`first60 init` copies a builtin pack to `my-business.toml` (or
`--output` wherever you want it) and prints the next steps. Edit
the copy: services, qualifying questions, hours, follow-up policy
and emergency terms. Five packs ship with the repo: dental,
plumber, med spa, clinic and real estate. See
[docs/packs.md](docs/packs.md) for what each one carries, and
[docs/configuration.md](docs/configuration.md) for every field and
its validation rules.

### Worked vertical: dental

The dental pack is the fictional BrightSmile Dental from the demo:
five services (Check-up and clean, Emergency appointment, Crown
fitting, Teeth whitening, New patient consultation), five questions
(service, timeline, name, contact, plus an optional pain question),
hours Monday to Friday 09:00-17:30 (Friday to 17:00), Saturday
09:00-13:00, Sunday closed, and emergency terms (severe pain,
swelling, bleeding, knocked out tooth, face swelling) with the
practice's own emergency instruction. The same shape holds for the
other verticals: the plumber's emergency terms are gas smell and
burst pipe, the clinic's are chest pain and heavy bleeding, the
med spa's are allergic reaction and severe swelling, and the real
estate pack's are time-based (urgent viewing today, offer deadline
today).

Pack validation is strict: a pack with a missing service, a bad time or
an empty emergency list fails to load with a named field error, so a
broken pack can never silently run.

## Safety

- **Write modes.** Every outbound message passes a write-mode gate
  (demo, direct, dry-run or approval) and writes an audit row. Demo
  mode sends only to a fake outbox. No silent sends, ever.
- **Opt-out handling.** STOP and unsubscribe wording stops all further
  touches for that conversation.
- **Handoff rules.** Emergency terms from the pack trigger a fixed
  safety template and a human handoff, never advice. Complaints,
  human requests, and two stuck questions hand off too.
- **What it can never do in v0.1.0.** Call anyone, cold-message anyone,
  or give medical or trade advice.

See [docs/safety.md](docs/safety.md) for the full guardrails: write
modes, opt-out, handoff order, follow-up limits, and data handling.

## Going live

The webhook channel is live: `first60 serve` runs the receptionist
over HTTP on `127.0.0.1:8765` by default, with a SQLite store. Send
`POST /message` with `{"sender": ..., "text": ...}` and the reply
comes back as `{"reply": ...}`. `GET /status` reports leads by stage
and band, today's bookings, overdue leads and handed-off leads, and
`GET /` serves a minimal demo chat page. The write mode defaults to
`demo`; pass `--mode direct` to send for real, or `--mode dry_run`
/ `--mode approval` to withhold sends (the reply is audited, not
delivered). See [docs/channels.md](docs/channels.md) for the full
contract, including the 400 for malformed payloads and the 202
"held" response. Platform-native senders (Instagram, WhatsApp,
email) are v0.2 candidates, each behind that platform's official API
and policy review. Unofficial-client sending is out of scope
permanently.

## Architecture

Text channels (webhook, console, simulated) feed a conversation engine
that extracts, qualifies, scores and moves stages, driving a responder,
a calendar and a follow-up engine over one store. A clock is injected
everywhere so follow-ups due tomorrow are testable in milliseconds.
Every side effect is audited. The module layout:

```text
src/first60/
  cli.py            entry points: demo, serve, summary, init
  config.py         business pack loading + validation (stdlib tomllib)
  init_pack.py      first60 init: scaffold a starter pack
  engine.py         the conversation engine (dedupe, qualify, book, follow up)
  demo.py           scripted scenario on the simulated clock
  server.py         stdlib HTTP server: webhook, demo chat, /status
  pipeline/         stages, scoring, extraction, qualification, handoff
  respond/          template responder (default), optional LLM responder
  channels/         webhook, console, simulated
  calendar/         business hours + busy blocks, idempotent booking
  followups.py      scheduler: caps, waking window, stop conditions, reminders
  store/            SQLite + in-memory under one protocol
packs/              dental, plumber, med-spa, clinic, real-estate
docs/               configuration, safety, packs, channels
```

Docs: [configuration](docs/configuration.md),
[safety](docs/safety.md), [packs](docs/packs.md),
[channels](docs/channels.md). The design doc is DESIGN.md in the
repo root; the competitor scan (RESEARCH.md) lives in the TechAura
design workspace, not in this repo; the build logs are
BUILD-STEP-1.md through BUILD-STEP-7.md.

## Roadmap

- **v0.2 candidates** (not promises): Google Calendar adapter, first
  platform sender behind official APIs, LeadPipe sync adapter.
- **Build progress** (see the design doc, section 14):
  - [x] Step 1: skeleton, pack loader, five packs, CI
  - [x] Step 2: pure core (stages, scoring, extraction, qualification)
  - [x] Step 3: store and calendar
  - [x] Step 4: responders and handoff
  - [x] Step 5: channels and follow-up engine
  - [x] Step 6: demo and measured quick-start time
  - [x] Step 7: docs and release prep

## Limitations, stated plainly

- Text only. No voice calls, no telephony, no speech-to-text or
  text-to-speech of any kind.
- Single business per install. Multi-business tenancy is out of scope
  for v0.1.0.
- No cold outreach. First60 only replies to people who contacted the
  business first, plus follow-ups to those same conversations.
- The demo business (BrightSmile Dental) is fictional and its numbers
  are illustrative, not results.
- The quick-start time is measured, not targeted: about 11 seconds
  from a fresh copy to the booked demo appointment (Python 3.12, two
  runs: 11.2s and 10.9s, measured 2026-11-14).
- The LLM responder is optional and caged: it phrases decisions only,
  validated against the fact sheet, with template fallback. It is off
  unless `FIRST60_LLM_BASE_URL` is set.

## Sources and thanks

The pipeline model (stages, bands, dedupe on normalised email then
phone, idempotent booking, audit log, write modes) is inherited from
[leadpipe-mcp](https://github.com/techaurah/leadpipe-mcp), TechAura's
MCP server for pipeline record-keeping; First60 is the actor layer
to LeadPipe's record layer, sharing vocabulary, not storage. The
comparison table above comes from the competitor scan in RESEARCH.md
(repo pages read directly, 2026-11-06/07), covering Tel-Agent,
LobbyStack, Siphon, Frontdesk.ai, the WhatsApp n8n templates and
the n8n template library. If Tel-Agent or LobbyStack later ships
deterministic qualification plus follow-up sequences on text
channels, the table will be corrected the same week.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: see
[SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).
