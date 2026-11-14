# Business packs

A business pack is one TOML file describing one service business.
Five packs ship with First60, one per vertical, all fictional
businesses with no real business data. Each pack is a complete,
working configuration: services, qualifying questions, hours,
follow-up policy, handoff rules and booking terms. Copy one with
`first60 init` and edit it, or run it as-is to see the vertical.

## The five shipped packs

| Pack | Business (fictional) | Services | Questions | Slot grid |
| --- | --- | --- | --- | --- |
| `dental` | BrightSmile Dental | 5 | 5 | 30 min |
| `plumber` | SwiftFlow Plumbing | 6 | 5 | 60 min |
| `med-spa` | GlowHaven Med Spa | 5 | 5 | 30 min |
| `clinic` | Harborview Family Clinic | 5 | 5 | 15 min |
| `real-estate` | Keystone Homes Realty | 5 | 5 | 30 min |

Every pack follows the same shape (see
[configuration](configuration.md) for every field and its
validation rules). The differences are the vertical's own: its
services, its questions, its emergency terms, and its slot size.

### dental: BrightSmile Dental

Services: Check-up and clean, Emergency appointment, Crown
fitting, Teeth whitening, New patient consultation. Questions:
service, timeline, name, contact, and an optional pain question
("Are you in pain at the moment, or is anything swollen?").
Emergency terms: severe pain, swelling, bleeding, knocked out
tooth, face swelling. Hours: Monday to Friday 09:00-17:30 (Friday
to 17:00), Saturday 09:00-13:00, Sunday closed. This is the demo
pack: `python -m first60 demo` runs BrightSmile Dental through a
scripted Tuesday.

### plumber: SwiftFlow Plumbing

Services: Emergency call-out, Leak repair, Boiler service, Boiler
repair, Bathroom installation, Tap replacement. Emergency terms:
gas smell, burst pipe, flooding, water pouring, no water. The
emergency instruction tells the lead to turn off the water at the
stopcock if safe, and to leave the property and call the gas
emergency service if they smell gas. Slot grid is 60 minutes:
plumbing visits are longer bookings.

### med-spa: GlowHaven Med Spa

Services: Signature facial, Laser hair removal, Botox
consultation, Chemical peel, Massage therapy. Emergency terms:
severe pain, severe swelling, swelling, burn, allergic reaction,
blistering, difficulty breathing. `handoff_only` includes refund requests and medical
advice: a med spa lead asking for medical advice goes to a human,
never to the receptionist.

### clinic: Harborview Family Clinic

Services: Same-day sick visit, Annual physical, Vaccination, Blood
test, Follow-up consultation. Emergency terms: chest pain,
difficulty breathing, severe pain, heavy bleeding, unconscious.
`handoff_only` includes prescription refills and test results.
Slot grid is 15 minutes: short clinical appointments.

### real-estate: Keystone Homes Realty

Services: Property viewing, Valuation appointment, Buyer
consultation, Rental viewing, Virtual tour. Emergency terms are
time-based rather than medical: urgent viewing today, offer
deadline today. `handoff_only` includes legal questions, offer
negotiation and contract questions: the receptionist books the
viewing, it never negotiates.

## Every pack completes a qualification in tests

Each pack has a scripted conversation in `tests/test_pack_paths.py`
that runs through the pure core end to end: messages in,
qualification out, a score with components, and the stage walk
NEW to CONTACTED to QUALIFIED. Every scripted path reaches at
least NURTURE (score 50 or above). If you add a pack, add a
scripted path for it the same way.

## Writing your own pack

Start from the closest shipped pack, not from blank:

```bash
first60 init --pack dental --name "Acme Dental"
```

Then edit the copy: rename the business, replace the services with
the ones the business actually books, rewrite the questions in the
business's own words, set the real hours, and write the emergency
terms and instruction for the vertical. Keep the emergency terms
short and specific to the business: they are matched as phrases in
the lead's message, so "severe pain" catches more real emergencies
than a long sentence does. Keep `handoff_only` for the topics the
business never wants automated: insurance, refunds, legal,
prescriptions, test results.

Validation is strict and immediate: run `first60 summary
--pack-file my-business.toml` and a broken pack fails with the
field named, before any lead is ever served. A pack that loads is
a pack that runs.

## What packs are not

A pack is data, not a fork: five verticals run from one codebase,
and a new vertical is a new TOML file. Packs do not carry prices
(no pack publishes any), credentials, or channel adapters. A pack
cannot change the scoring weights, the stage map, the band
thresholds, or the follow-up engine's rules: those are fixed in
code, so two businesses running the same version judge leads the
same way and differ only in what they offer and ask.
