# Channels

First60 talks to leads over text channels behind one channel
protocol. A channel has two jobs: `receive()` inbound messages and
`send()` outbound replies. The conversation engine does not know
which channel a message came from: it dedupes, qualifies, scores,
books and follows up the same way for all three. v0.1.0 ships
three channels; platform-native senders (Instagram, WhatsApp,
email) are v0.2 candidates, each behind that platform's official
API and policy review. Unofficial-client sending is out of scope
permanently.

## Webhook channel (the live channel)

`first60 serve` runs the receptionist over HTTP, on
`127.0.0.1:8765` by default, with a SQLite store. This is the
integration surface for web forms and future platform adapters:
anything that can POST JSON can feed the receptionist.

```bash
first60 serve --pack dental --mode demo --db first60.db
first60 serve --pack-file my-business.toml --host 127.0.0.1 --port 8765
```

### `POST /message`

Request body, a JSON object with string `sender` and `text`, both
non-empty after stripping:

```json
{"sender": "sarah", "text": "do you have anything Thursday morning?"}
```

Response, the reply as JSON:

```json
{"reply": "Hi, thanks for messaging BrightSmile Dental. What is your name?"}
```

A malformed body (not JSON, not an object, missing or blank
`sender` or `text`) is answered 400 with `{"error":
"MALFORMED_PAYLOAD", "detail": ...}` naming the broken field, and
never reaches the engine: a bad form post can never create a lead
or a reply. An unknown path is 404 with `{"error": "NOT_FOUND"}`.

When the engine has no reply to give (the lead is paused for a
human, has opted out, or the write mode withheld the send), the
answer is 202 with `{"status": "held", "reason": ...}` instead of
a 200 with an empty reply, so the caller can tell "held" apart
from "answered".

### `GET /status`

The pipeline read surface, as JSON: business name, date, leads by
stage and by band, today's bookings, overdue leads (in CONTACTED
or QUALIFIED with no booking and no reply since the last outbound)
and handed-off leads (automation paused). The daily summary printed
by `first60 summary` is built from this same payload, so the
printed summary and the HTTP surface cannot disagree.

### `GET /`

A minimal demo chat page in the browser, posting to `/message`
behind the scenes. It is a demo surface, not a dashboard: there is
no lead list, no settings page, and no multi-business view in
v0.1.0.

### Write modes on serve

`--mode` defaults to `demo`: replies go to the fake outbox and
nothing leaves the process. Pass `--mode direct` to send for real
through the wired channel, or `--mode dry_run` / `--mode approval`
to withhold sends (the reply is audited, not delivered). See
[safety](safety.md) for what each mode guarantees. The server binds
loopback by default; put a reverse proxy in front of it before
exposing it beyond the machine it runs on.

## Console channel (interactive demo)

```bash
python -m first60 demo --interactive
```

Opens a terminal session where the visitor plays the customer
against the fictional BrightSmile Dental on the simulated Tuesday
21:40 clock. Type messages, answer the questions, pick a slot like
"Thursday 09:00" to book it, end with Ctrl-D. The engine's channel
stays the simulated outbox in this mode, so the console loop prints
each reply exactly once and the engine never sends anywhere real.

## Simulated channel (demo and tests)

The scripted channel behind `python -m first60 demo` and the test
suite. The demo drives it with a fixed script and a hand-set clock
through a Tuesday: a noon enquiry books from its +4h follow-up, an
after-hours enquiry books Thursday morning, an opt-out stops all
further touches, and Wednesday 08:00 prints the daily summary.
The identical script is the release-gate integration test
(`tests/test_demo.py`), so the demo a visitor runs and the demo the
test suite runs are one script, not two. The channel is also what
`first60 summary` uses to render the daily summary without sending
anything.

## How inbound messages flow

1. A channel delivers `(sender, text)` to the engine.
2. The engine dedupes by channel handle, then by extracted
   contact (normalised email first, then phone). A returning lead
   resumes their conversation; no duplicate lead is created.
3. Opt-out is checked first, then handoff, then qualification:
   the engine extracts service, timeline and contact, asks the
   next unanswered question, offers real free slots from the
   calendar, books with a re-check at booking time, and schedules
   follow-ups.
4. Every side effect (reply sent, stage move, booking, follow-up,
   opt-out, handoff) is written to the audit log with its write
   mode.

A booked lead who writes again is acknowledged by service and time
("You're already booked in for Crown fitting on Thursday 09:00")
and hears no new offer: the engine never re-offers slots to a
booked lead, and never attempts the illegal BOOKED to QUALIFIED
move.
