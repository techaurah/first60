# First60

**First60: every lead answered in the first 60 seconds.**

First60 is an open-source AI receptionist for service businesses that
answers every text enquiry in under a minute, qualifies it against your
rules, books the appointment, and follows up until the lead replies or
opts out.

> **Status: build step 1 of 7 (skeleton).** The package imports, the
> business pack loader works, and all five packs validate. The
> conversation engine, booking, follow-up engine, channels and demo are
> not built yet. See [Build progress](#build-progress) below.

## The 10 PM problem

A customer messages at 10 PM about an aching tooth. Nobody is watching
the inbox. By morning they have booked with the competitor who replied
first. First60 exists for that enquiry: an instant first reply with a
next step, qualification against the business's own rules, a booked
appointment, and follow-ups if the lead goes quiet, at any hour.

## Run it now

> **In progress.** The demo command lands in build step 6. When it is
> ready, this section will show the exact command and the measured
> quick-start time. No time is claimed here until it is measured.

The goal: clone, run one command, and watch a demo enquiry get booked,
with no keys, no Docker and no accounts.

## What it does

The loop, once built:

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

## Decisions by rules, not prompts

Qualification, scoring, stage moves, booking safety and follow-up
policy are deterministic code with tests. A responder (template by
default, or an optional LLM) only phrases the decision into text. An
LLM never decides, and its output is validated against the allowed
facts before sending, falling back to the template rendering if it
fails. That separation is what makes the system testable without a
model.

First60 is a reference implementation of the text-first receptionist
loop. It is not the first AI receptionist and not the first open-source
receptionist: voice receptionists already exist, and this project
deliberately does not do voice. What it does differently is the full
text loop (reply, qualify, score, book, follow up) as tested,
deterministic code that runs with zero credentials.

## Make it yours

Business behaviour lives in a pack: one TOML file in `packs/` per
vertical. Copy a pack, edit its services, qualifying questions, hours,
follow-up policy and emergency terms. Five packs ship with the repo:
dental, plumber, med spa, clinic and real estate. The dental pack uses
the fictional BrightSmile Dental business from the demo.

```bash
python -m first60 --help
```

Pack validation is strict: a pack with a missing service, a bad time or
an empty emergency list fails to load with a named field error, so a
broken pack can never silently run.

## Safety

- **Write modes.** Every outbound message passes a write-mode gate
  (direct, dry-run or approval) and writes an audit row. Demo mode
  sends only to a fake outbox. No silent sends, ever.
- **Opt-out handling.** STOP and unsubscribe wording stops all further
  touches for that conversation.
- **Handoff rules.** Emergency terms from the pack trigger a fixed
  safety template and a human handoff, never advice.
- **What it can never do in v0.1.0.** Call anyone, cold-message anyone,
  or give medical or trade advice.

## Going live

> **In progress.** The webhook channel lands in build step 5.
> Platform-native senders (Instagram, WhatsApp, email) are v0.2
> candidates, each behind that platform's official API and policy
> review. Unofficial-client sending is out of scope permanently.

## Architecture

Text channels (webhook, console, simulated) feed a conversation engine
that extracts, qualifies, scores and moves stages, driving a responder,
a calendar and a follow-up engine over one store. A clock is injected
everywhere so follow-ups due tomorrow are testable in milliseconds.
See the design doc for the full diagram and module layout.

## Roadmap

- **v0.2 candidates** (not promises): Google Calendar adapter, first
  platform sender behind official APIs, LeadPipe sync adapter.
- **Build progress** (see the design doc, section 14):
  - [x] Step 1: skeleton, pack loader, five packs, CI
  - [ ] Step 2: pure core (stages, scoring, extraction, qualification)
  - [ ] Step 3: store and calendar
  - [ ] Step 4: responders and handoff
  - [ ] Step 5: channels and follow-up engine
  - [ ] Step 6: demo and measured quick-start time
  - [ ] Step 7: docs and release prep

## Limitations, stated plainly

- Text only. No voice calls, no telephony, no speech-to-text or
  text-to-speech of any kind.
- Single business per install. Multi-business tenancy is out of scope
  for v0.1.0.
- No cold outreach. First60 only replies to people who contacted the
  business first, plus follow-ups to those same conversations.
- The demo business (BrightSmile Dental) is fictional and its numbers
  are illustrative, not results.
- The quick-start time is not claimed anywhere until it is measured in
  build step 6.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: see
[SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).
