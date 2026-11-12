# First60 build step 5: channels and follow-up engine

Date: 2026-11-12. Author: TechAura (@techaurah).

## What was built

DESIGN.md section 14 step 5: "Channel protocol with simulated,
console and webhook implementations; scheduler with caps, waking
window, stop conditions and reminder consent, all on the injected
clock."

- `src/first60/engine.py`: the conversation engine, promoting the
  step-4 test-local driver into the real module (the driver's
  behaviour is unchanged, and its tests now drive this engine).
  Dedupe by channel handle, then extracted contact (email, then
  phone); opt-out checked before handoff (STOP is never a stuck
  conversation); qualify, offer real free slots from the calendar,
  book with reminder consent; every side effect audited with its
  write mode. Write modes: `demo` and `direct` send through the
  channel; `dry_run` audits `reply_would_send` and `approval`
  audits `reply_pending_approval`, and both return `None` so the
  caller cannot deliver a reply the engine withheld. A withheld
  reply is never recorded as an outbound message, so it cannot
  reset the follow-up clock. After every outbound reply that
  leaves the conversation open, the follow-up clock resets: the
  scheduled touch is cancelled and touch 1 is re-scheduled from
  the new last outbound. A paused lead's messages are audited as
  `message_held_for_human` and answered with nothing.
- `src/first60/channels/base.py`: the channel protocol
  (`send` / `receive`) plus the `InboundMessage` shape. A channel
  carries text and never decides anything.
- `src/first60/channels/simulated.py`: scripted channel for demo
  and tests; `receive` pops the next scripted message, `send`
  records in the outbox.
- `src/first60/channels/console.py`: interactive terminal channel
  (stdin in, stdout out, streams injected for tests); `run`
  drives a handler until end of input.
- `src/first60/channels/webhook.py`: generic JSON webhook channel.
  `parse_webhook_payload` validates `{"sender", "text"}` and raises
  `MALFORMED_PAYLOAD` (new closed error code) on anything else;
  a malformed payload never reaches the engine. Push-driven, so
  `receive` returns `None` and `send` records in an outbox the
  server reads as the HTTP response.
- `src/first60/followups.py`: the scheduler. Chained touches
  (+4h, +24h, +72h from the last outbound, max 3): each touch is
  due that many hours after the most recent outbound, so touch 2
  is due 24h after touch 1 fired. Stop conditions checked at fire
  time, in reason priority order: opted_out, stage_lost,
  automation_paused, already_booked, replied. A touch due outside
  the waking window (08:00-21:00 business-local) is deferred to
  the next window start, never suppressed and never sent while
  closed. Appointment reminders at 24h and 2h before a confirmed
  appointment, only with consent (`reminders_consented`, set at
  booking), tracked by `reminder_sent` audit rows so a restart
  never double-sends. Every fired, suppressed or deferred touch
  writes an audit row with its reason.
- `src/first60/server.py`: stdlib HTTP server. `POST /message`
  (webhook round trip; malformed body 400, withheld reply 202),
  `GET /status` (business, leads by stage and band, today's
  bookings, overdue and handed-off leads), `GET /` (minimal demo
  chat page). Binds `127.0.0.1` by default.
- `src/first60/cli.py`: `first60 serve` is wired (`--pack`,
  `--host`, `--port`, `--mode`, `--db`; SQLite store, rule
  responder, webhook channel).
- `src/first60/store/sqlite.py`: thread-safe for the threaded
  server (connection opened with `check_same_thread=False`, one
  re-entrant lock around every public method; `move_stage`
  re-enters through `get_lead`/`update_lead`).
- `src/first60/calendar/local.py`: the clock may now return an
  aware UTC datetime (the engine's clock); it is converted to
  business-local naive time before comparison, so one clock serves
  both the engine and the calendar.
- `src/first60/errors.py`: two new closed codes,
  `MALFORMED_PAYLOAD` and `INVALID_WRITE_MODE`.

## Verification (local, before publish)

- 272 pytest passed (227 existing + 45 new: 5 conversation incl.
  dry-run, 9 channels, 21 follow-ups, 5 server, 1 SQLite thread
  test, plus 4 more across the step), ruff check + format clean,
  mypy clean.
- Live smoke test of `first60 serve` on a real SQLite store: four
  HTTP round trips booked Crown fitting Thursday 09:00, and
  `GET /status` reported `BOOKED: 1` with 1 booking. The smoke
  test caught the SQLite thread error fixed above
  (`sqlite3.ProgrammingError`, connection created in another
  thread); the threaded server now shares one locked connection.
- Step 5 done condition ("follow-up and server tests pass") met:
  follow-up tests 21/21, server tests 5/5, conversation tests 5/5.

## Design decisions recorded

- Follow-up delays are chained from the last outbound, not from
  the first reply. The design text ("touch 2 at +24h after last
  outbound") supports both readings; chained is the standard drip
  cadence and the one the tests pin.
- A dry-run/approval reply is not recorded as an outbound
  message. Recording it would reset the follow-up clock and count
  as a reply for the "replied" stop check, both wrong for a send
  that never happened.
- Reminder consent is set by booking through the engine. A lead
  booked by any other route has no consent and gets no reminders;
  consent is a positive opt-in, not a default.
- The engine's dedupe handle map is single-process. A restart
  re-dedupes by extracted contact; a sender with neither email nor
  phone gets a fresh lead. Documented in the engine docstring as
  a known v0 limitation.

## Open items for step 6

- The demo scenario (seed data, scripted transcript, interactive
  mode, the scenario as the release-gate integration test) and the
  measured clean-machine quick-start time.
- `first60 serve` defaults to `--mode demo` and binds loopback;
  a production deployment note belongs in step 7 docs, not here.
