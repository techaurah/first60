# Safety

First60 answers people who contacted the business first. It never
calls anyone, never cold-messages anyone, and never gives medical
or trade advice. This page states the guardrails that enforce that,
and what to do when they fire.

## Write modes: no silent sends

Every outbound message passes a write-mode gate, and every send or
withheld send writes an audit row. The mode is chosen per run with
`first60 serve --mode <mode>`:

| Mode | What happens to a reply |
| --- | --- |
| `demo` | The reply goes to the fake outbox (the simulated channel). Nothing leaves the process. This is the default. |
| `direct` | The reply is sent through the channel. Use only when a real channel adapter is wired up. |
| `dry_run` | The reply is audited as `reply_would_send` and not delivered. The caller gets no reply text. |
| `approval` | The reply is audited as `reply_pending_approval` and not delivered. The caller gets no reply text. |

A withheld reply is never recorded as an outbound message, so it
cannot reset the follow-up clock. In demo mode the engine sends
only to the fake outbox; the demo scenario and the test suite run
entirely in this mode.

## Opt-out: stop means stop

STOP, unsubscribe, "opt out", "do not message me", "remove me" and
similar wording opts the lead out. Whole-word matching is used, so
"stopcock" (plumbing) never counts as STOP. When a lead opts out:

- The opt-out is written to the audit log.
- No further follow-up touches are scheduled for that conversation.
- The lead is listed separately in the daily summary (`Opted out`),
  not lumped in with handed-off leads.

Opt-out is checked before handoff, so STOP is never read as a
stuck conversation or an emergency.

## Handoff: a human takes over

A lead is handed to the human owner, automation is paused for that
lead, and a summary (who, contact, service, urgency, last message)
is written to the outbox/summary surface, when any of these fire,
in this order:

1. **Emergency terms from the pack.** The reply is a fixed safety
   template carrying the pack's own emergency instruction verbatim.
   It never contains advice: no diagnosis, no treatment suggestion,
   no trade instruction. The dental pack's instruction, for example,
   tells the lead to contact their dentist or urgent dental service
   right away, or seek urgent care if swelling affects breathing.
2. **Pack `handoff_only` items.** Topics the pack marks for humans
   only, for example insurance claims or test results.
3. **Complaint, anger, refund or legal signals.**
4. **The lead asks for a human**, in any wording the extractor
   recognises ("speak to a human", "real person", "talk to
   someone" and the like).
5. **Two consecutive extraction failures** on the same question:
   the conversation is stuck, and a human does better.

A paused lead's further messages are audited as
`message_held_for_human` and answered with nothing. The pause is
per lead, not per business: other conversations keep running.

## What First60 can never do in v0.1.0

- Call anyone, or send voice messages. There is no telephony, no
  speech-to-text and no text-to-speech anywhere in the codebase.
- Cold-message anyone. First60 only replies to people who contacted
  the business first, plus follow-ups to those same conversations.
  There is no outbound campaign, list import or cold outreach
  feature, and none is planned.
- Give medical or trade advice. Emergency wording triggers the
  fixed safety template and a handoff, never a suggestion.
- Invent prices or services. The template responder states only
  pack facts; the optional LLM responder is validated against the
  allowed-facts sheet and falls back to the template when its
  output invents a price, a service, or drops an offered slot.
  No pack publishes prices, so no reply can quote one.

## Follow-up limits

Follow-ups are capped by the pack (3 touches by default, at +4h,
+24h, +72h) and sent only inside the waking window (08:00-21:00 by
default). Stop conditions are checked at fire time, not schedule
time: any inbound reply, a confirmed booking, an opt-out, stage
LOST, or an open handoff all suppress the touch, and the
suppression is audit-logged with its reason. Appointment reminders
(24h and 2h before a confirmed appointment) fire only where the
lead consented to reminders during booking.

## Data and privacy

The store is a local SQLite file (`first60.db` by default) or an
in-memory store for the demo and tests. There is no hosted
database, no analytics call and no network call in the code or the
tests. Lead data lives in the file the operator chose, and nowhere
else. The demo business (BrightSmile Dental) and its leads are
fictional; the demo writes nothing real.

## Reporting a safety problem

Security issues follow [SECURITY.md](../SECURITY.md): report
privately, never in a public issue. A safety failure in the
receptionist itself (a reply that gave advice, a message sent
after opt-out, a follow-up that fired after a booking) is a bug:
open an issue with the transcript, the pack, and the audit rows if
you have them. The audit log is the first place to look for "why
did this lead get (or not get) a message": every fired or
suppressed touch writes a row with its reason.
