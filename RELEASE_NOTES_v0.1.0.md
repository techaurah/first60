# First60 v0.1.0

First60 is an open-source, text-first AI receptionist for service
businesses: every text enquiry answered with a next step inside 60
seconds, qualified against the business's own rules, with booking
and follow-ups handled by deterministic code. Zero required
dependencies, stdlib only, Python 3.11 or newer.

**This is the first release, and the build is complete: all seven
build steps are done.** The skeleton, the pure core, the store and
calendar, the responders and handoff, the channels and follow-up
engine, the demo, and the docs and release prep are all in. What
follows is what v0.1.0 actually does, and what it does not do.

## What works

- The full loop: instant reply, qualification against the pack's
  questions, deterministic scoring (six components, HOT/WARM/
  NURTURE/LOW bands), idempotent booking against business hours
  and busy blocks with a re-check at booking time, capped
  follow-ups (+4h/+24h/+72h, max 3, waking window 08:00-21:00,
  stop-on-reply and opt-out), human handoff with a fixed safety
  template, and a daily summary.
- Decisions by rules, not prompts: qualification, scoring, stage
  moves, booking safety and follow-up policy are deterministic
  code with tests. A responder only phrases the decision. The
  optional LLM responder is off unless `FIRST60_LLM_BASE_URL` is
  set, and its output is validated against the fact sheet with
  template fallback.
- Five business packs, all validated and all completing a scripted
  qualification conversation in tests: dental (BrightSmile Dental,
  fictional), plumber, med spa, clinic, real estate.
- `first60 init`: scaffold a starter pack from any builtin pack,
  edit it, run it with `first60 serve --pack-file`.
- `first60 serve`: the webhook channel over HTTP
  (`POST /message`, `GET /status`, `GET /` demo chat page), with
  write modes demo/direct/dry_run/approval and an audit row for
  every send or withheld send.
- The demo: `python -m first60 demo` runs the fictional
  BrightSmile Dental through a scripted Tuesday (after-hours
  enquiry booked, follow-up booking, opt-out, daily summary) with
  no keys, no Docker, no accounts. The same script is the
  release-gate integration test. Measured quick-start: about 11
  seconds from a fresh copy to the booked demo appointment
  (Python 3.12, two runs 11.2s and 10.9s, measured 2026-11-14).
- Tests: 310 passing, all offline. CI runs on Python 3.11 and
  3.12 with pytest, ruff and mypy. Docs: README plus
  `docs/configuration.md`, `docs/safety.md`, `docs/packs.md` and
  `docs/channels.md`.

## What v0.1.0 is not

- Not a voice product. No calls, no telephony, no speech-to-text
  or text-to-speech, in this release or planned for the next one.
- Not a platform sender. There are no native Instagram, WhatsApp
  or email senders yet; the live surface is the generic JSON
  webhook, and platform senders are v0.2 candidates behind each
  platform's official API and policy review. Unofficial-client
  sending is out of scope permanently.
- Not multi-business. One business per install, one pack per
  server. No hosted deployment, no web dashboard; the read
  surfaces are `GET /status` and `first60 summary`.
- Not a CRM and not a marketing platform. No cold outreach of any
  kind: First60 only replies to people who contacted the business
  first, plus follow-ups to those same conversations.
- Not a claim about the market. First60 is a reference
  implementation of the text-first receptionist loop; it is not
  the first AI receptionist and not the first open-source
  receptionist. The comparison table in the README (voice
  receptionists and n8n assemblies, from the 2026-11-06/07 scan)
  states what it does differently, and each point is verifiable
  from this repo.

## Install and run

```bash
git clone https://github.com/techaurah/first60.git
cd first60
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m first60 demo
```

For development (adds pytest, ruff and mypy):

```bash
pip install -e ".[dev]"
pytest
```

To make it yours:

```bash
first60 init --pack dental --name "Acme Dental"
first60 serve --pack-file my-business.toml
```

## Notes

- The demo business (BrightSmile Dental) and its leads are
  fictional, and their numbers are illustrative, not results.
- The wheel ships the builtin packs, so an installed-from-PyPI
  copy loads them; verified by a real wheel build and a fresh-venv
  install in the release prep.
- License: MIT.
