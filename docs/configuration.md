# Configuration

First60 is configured by one file: a business pack. A pack is a
TOML file describing a single service business: its services,
qualifying questions, hours, follow-up policy, handoff rules and
booking terms. There is no other configuration file in v0.1.0. The
optional LLM responder is configured by environment variables (see
below); everything else lives in the pack.

## Starting from a pack

```bash
first60 init --pack dental --name "Acme Dental"
```

This copies the dental pack to `my-business.toml` in the current
directory and prints the next steps. `--pack` picks the vertical to
copy from: `dental`, `plumber`, `med-spa`, `clinic` or
`real-estate`. `--name` renames the business. `--output` picks the
file to write (default `my-business.toml`); an existing file is
left alone unless `--force` is passed. The written file is
validated with the same strict loader the server uses, so a bad
scaffold is reported at init time, never at first enquiry.

Run a scaffolded pack with:

```bash
first60 serve --pack-file my-business.toml
first60 summary --pack-file my-business.toml --db first60.db
```

`--pack-file` takes a path to a pack file. `--pack` takes a builtin
pack name instead; the two are mutually exclusive, and passing both
is an error. The five builtin packs ship in `packs/` and are loaded
by name: `first60 serve --pack plumber`.

## Pack format

Every field is validated on load. A pack with a missing field, a
bad time or an empty list fails with a `PackError` naming the broken
field, and a broken pack can never silently run. The dental pack
(`packs/dental.toml`, fictional BrightSmile Dental) is the worked
example; every rule below is visible in it.

### `[business]`

| Field | Rule |
| --- | --- |
| `name` | Non-empty string. The name the receptionist uses when it introduces itself. |
| `vertical` | One of `dental`, `plumber`, `med-spa`, `clinic`, `real-estate`. |
| `timezone` | Non-empty string, for example `Europe/London`. Business hours and the waking window are read in this timezone. |
| `currency` | A 3-letter code, for example `GBP`. Stored upper-cased. |

### `[[services]]`

A non-empty list. Each service has:

| Field | Rule |
| --- | --- |
| `name` | Non-empty string, unique within the pack (case-insensitive). |
| `duration_minutes` | Whole number of minutes, 5 to 480. Drives slot length and booking. |
| `value_tier` | One of `low`, `standard`, `high`. Drives the value component of the qualification score (low 5, standard 10, high 15). |
| `description` | Optional string. Free text about the service. |

Service matching is keyword-based on the service name: generic
words (appointment, consultation, visit, treatment and the like)
carry no signal, and a service is a full match when every
remaining word appears in the message, related when at least one
does. There is no synonym list: "toothache" does not match a crown
service. If a service needs to be found by another word, name it
so the word appears, or add the wording to the pack's questions.

### `[[questions]]`

A non-empty list, asked in pack order. Each question has:

| Field | Rule |
| --- | --- |
| `id` | Non-empty string, unique within the pack. |
| `text` | Non-empty string, the question as asked to the lead. |
| `required` | Optional boolean, default `true`. Required questions count toward the completeness component of the score. |

The engine asks the first unanswered required question, and takes
opportunistic answers: a message that answers a later question out
of order is recorded, not ignored. Two consecutive extraction
failures on the same question hand the lead to a human (see
[safety](safety.md)).

### `[hours]`

Every weekday (`monday` through `sunday`) must be present. Each day
is either `{ closed = true }` or `{ open = "09:00", close = "17:30" }`
with 24-hour times and open before close. Hours drive both slot
availability and the demo clock; a day with no hours entry is a
pack error, not a closed day.

### `[followups]`

| Field | Rule |
| --- | --- |
| `touch_delays_hours` | Non-empty list of increasing positive whole hours. Defaults in the shipped packs: `[4, 24, 72]`. |
| `max_touches` | Whole number from 1 up to the number of touch delays. Defaults in the shipped packs: `3`. |
| `waking_window_start` | 24-hour time, for example `08:00`. |
| `waking_window_end` | 24-hour time, after the start, for example `21:00`. |

Touches fire only inside the waking window; a touch due outside it
is deferred to the next 08:00. The follow-up clock resets on every
outbound reply: a new reply cancels the scheduled touch and
re-schedules touch 1 from the new last outbound.

### `[handoff]`

| Field | Rule |
| --- | --- |
| `emergency_terms` | Non-empty list of non-empty strings, for example `["severe pain", "swelling", "bleeding"]`. A message containing one hands the lead to a human with the fixed safety template. |
| `emergency_instruction` | Non-empty string, quoted verbatim in the safety reply. This is the pack's own instruction, so write it as the business would say it. |
| `handoff_only` | Optional list of strings, for example `["insurance claim"]`. Messages about these topics go straight to a human. |

### `[booking]`

| Field | Rule |
| --- | --- |
| `slot_minutes` | Optional whole number of minutes, 5 to 480, default `30`. The grid slots are offered on. |
| `confirmation_required` | Optional boolean, default `true`. |

## The optional LLM responder

Off unless set. The template responder is the default in every mode
and the only responder the demo and the test suite use.

| Variable | Meaning |
| --- | --- |
| `FIRST60_LLM_BASE_URL` | OpenAI-compatible endpoint. Setting it switches the LLM path on; without it the LLM responder is inert. |
| `FIRST60_LLM_API_KEY` | Key sent to that endpoint. Empty when unset. |
| `FIRST60_LLM_MODEL` | Model name, default `gpt-4o-mini`. |

The LLM only phrases decisions: it receives the decision object
and the allowed-facts sheet, never the raw conversation, and it
never decides. Its output is validated before sending: an empty
reply, an overlong reply (over 600 characters by default), offered
slots that do not appear verbatim, any price, or a service not on
the fact sheet all fall back to the template rendering of the same
decision, and the fallback is audit-logged. Extraction, scoring and
decisions never come from the LLM in either mode.

## What is not configurable in v0.1.0

One business per install (one pack per server). There is no
multi-business tenancy, no hosted deployment and no web dashboard;
the read surfaces are `GET /status` and `first60 summary`. The
scoring weights, stage map and band thresholds (HOT 80+, WARM 65+,
NURTURE 50+, LOW below 50) are fixed in code, not in the pack: the
pack is the tuning surface for what the business offers and asks,
not for how leads are judged.
