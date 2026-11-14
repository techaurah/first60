# First60 build step 7: docs and release prep

Date: 2026-11-14. Author: TechAura (@techaurah).

## What was built

DESIGN.md section 14 step 7: "README completed per Section 13
with the measured time; docs/ pages (configuration, safety, packs,
channels); CHANGELOG from actual commits; dogfood run against
fictional data only, friction logged as issues." Plus the three
open items from BUILD-STEP-6.md: the `init` CLI command, the wheel
packaging gap, and the name-extraction quirk.

- `first60 init` (`src/first60/init_pack.py`, new): scaffolds a
  starter business pack from any builtin pack. `first60 init
  --pack dental --name "Acme Dental"` copies the dental pack to
  `my-business.toml`, replacing only the `name` line inside the
  `[business]` section, and prints next steps (edit the file, run
  `first60 serve --pack-file my-business.toml`, read
  `docs/configuration.md`). `--output` picks the file (parents
  created), `--force` overwrites, an existing file is otherwise
  left alone with exit code 2. The written file is validated with
  the same strict loader the server uses, so a bad scaffold is
  reported at init time. Deterministic and offline: no network, no
  prompts. 16 new tests in `tests/test_init.py`.
- `--pack-file` on `serve` and `summary` (`src/first60/cli.py`):
  loads a pack file (for example one made by `init`); mutually
  exclusive with `--pack`, and passing both is an error rather
  than a silent win. `--pack` now defaults to dental only when no
  `--pack-file` is given.
- Wheel packaging fix (`pyproject.toml`, `src/first60/config.py`):
  the wheel now ships `packs/` inside the installed package
  (`force-include`, wheel and sdist), and `config.py` looks for
  packs inside the package first, then at the repo root, so an
  installed-from-PyPI copy can load a builtin pack. Verified by a
  real wheel build (`first60-0.1.0-py3-none-any.whl`, all five
  packs under `first60/packs/`), a fresh-venv install, and a
  `first60 demo` run from the installed copy with no repo on the
  path. The installed copy also ran `init`, `summary --pack-file`
  and a `serve` smoke test end to end.
- Name-extraction fix (`src/first60/pipeline/extract.py`): the
  step-6 quirk ("I'm in severe pain" captured the name "Severe
  Pain"). Distress and symptom words (severe, agony, aching,
  hurting, sore, swollen, swelling, bleeding, throbbing, burning,
  unbearable, terrible, awful, dizzy, nauseous, vomiting, fever,
  infection, bruised, fractured, sprained, leaking, flooding,
  burst, cracked, damaged, broken, numb, stuck) and the verbs
  that introduce them (having, feeling, getting, experiencing,
  suffering, dealing) joined the non-name list, and any captured
  word from that list now rejects the whole capture instead of
  only the first word being checked. Scoped to extraction only:
  no other module changed for this fix. 8 new parametrised cases
  in `tests/test_extract.py`, including the surname guard ("I'm
  John Sharp" still captures "John Sharp").
- Med-spa pack fix (`packs/med-spa.toml`): the dogfood run showed
  the med-spa pack missing "severe pain" and plain "swelling" from
  its emergency terms, so a distressed lead was asked which
  treatment they wanted instead of being handed off. Both terms
  added ("severe swelling" kept, ordered before "swelling" so the
  more specific term matches first). One new handoff test proves
  both messages trigger the safety reply.
- Em-dash sweep: the standing TechAura rule (no em dashes
  anywhere) is now true of the whole working copy. User-facing
  product text changed with it: the demo transcript, the
  booked-lead acknowledgement replies, and the README quote of
  the transcript now use hyphens. Tests asserting those strings
  were updated with them. No behaviour changed.
- README completed per DESIGN.md section 13 (all 12 sections):
  claim, the 10 PM hook, run-it-now with the re-measured
  quick-start, the loop with the scoring components table,
  decisions-by-rules with the honest comparison table against
  voice receptionists and n8n assemblies (from RESEARCH.md, repo
  pages read 2026-11-06/07), make-it-yours with the worked dental
  vertical and the `init` command, safety, going live, architecture
  with the module layout and docs links, roadmap as labelled v0.2
  candidates, limitations stated plainly, sources and thanks
  (LeadPipe as the pattern source, the scan as the comparison
  source). No "first" claim anywhere.
- Docs pages, all written from the real code: `docs/configuration.md`
  (pack format field by field with validation rules, `init`,
  `--pack-file`, LLM env vars), `docs/safety.md` (write modes,
  opt-out, handoff order, follow-up limits, data handling),
  `docs/packs.md` (the five shipped packs with their real
  services, questions, emergency terms and slot grids; writing
  your own pack), `docs/channels.md` (webhook contract with the
  400 and 202 responses, console, simulated, the inbound flow).
  `docs/assets/directory-tree.txt` updated from its step-1-era
  text to the finished tree.
- CHANGELOG.md rewritten from actual commits: 107 commits on
  main, steps 1-7 with their real dates and real test counts
  (29, 156, 192, 227, 272, 285, 310). The previous version had
  the step-3 count line misplaced after the step-5 paragraph;
  that is fixed. `## [0.1.0]` stays "Unreleased": the tag is not
  created in this step (Tech's approval step).
- `RELEASE_NOTES_v0.1.0.md` drafted from the changelog: what
  v0.1.0 does, and what it is not (no voice, no platform senders,
  no multi-business, no CRM, no cold outreach, no "first"
  claims). No tag created, nothing published.

## Working-copy verification (before editing)

The working copy was verified against published main at 0582c86
before any edit. All 12 files spot-checked by git blob hash
matched the remote exactly. A full-tree diff against a fresh clone
of main then found 10 files present on main but missing from the
working copy: DESIGN.md, CODE_OF_CONDUCT.md, the issue and PR
templates, dependabot.yml, and the five docs/assets files. They
were published to the repo in steps 1-2 but never copied back into
the local tree. All 10 were restored verbatim from the clone (head
verified as 0582c86) and byte-compared after copying. The restored
DESIGN.md is identical to the design-workspace copy this step was
built from. After restoration the only remaining diffs against main
are exactly this step's edits. One local-only file remains
unpublished and untouched: `.gitignore` exists in the working copy
but not on main; the parent publish run decides whether to add it.

## Verification (local, before publish)

- 310 pytest passed (285 existing + 25 new: 16 init, 8
  extraction, 1 handoff), ruff check + format clean, mypy clean.
- Wheel: built `first60-0.1.0-py3-none-any.whl`, all five packs
  under `first60/packs/`; installed into a fresh venv; `first60
  demo` ran from the installed copy (both bookings, opt-out,
  summary); `init`, `summary --pack-file` and a `serve` smoke test
  ran from the installed copy.
- Quick-start re-measured (README-only steps, fresh copy, fresh
  venv, `pip install -e .`, `python -m first60 demo`): 11.2s and
  10.9s (Python 3.12.3), phase split on run 2: copy 0.4s, venv
  5.0s, pip install 5.2s, demo 0.3s. Slightly above the step-6
  runs (9.8s/10.1s); the install phase varies with the network
  fetch of the build backend. Still far under the 5-minute target.
  The README now carries the new numbers with the 2026-11-14 date.
- Secrets grep: no credential, token or real business data in the
  tree. The only matches are the word "token" inside the
  `_tokens` function name, the `api_key` parameter of the LLM
  responder (read from `FIRST60_LLM_API_KEY`, no value anywhere),
  and the fictional demo phone 07123 456789 in the README
  transcript. All business names are the five fictional packs; all
  emails in code and tests are example.com. No `.db` store file in
  the tree (only mypy caches).

## Measured quick-start time

About 11 seconds from a fresh copy to the booked demo appointment
(Python 3.12, two runs: 11.2s and 10.9s, measured 2026-11-14 with
`/tmp/quickstart-measure-7.py`). Phase split on the second run:
copy 0.4s, fresh venv 5.0s, `pip install -e .` 5.2s, demo 0.3s;
both demo bookings present in the output, exit code 0. Same honest
caveat as step 6, recorded here and in one line in the README: the
"clone" step was a fresh local copy of the working tree, not a
`git clone` over the network, because the local tree is not a git
checkout (publishing happens in the parent run via the browser).
A real `git clone` of this small repo adds a few seconds on a
normal connection; the total stays far under the 5-minute target
either way.

## Dogfood run (fictional data only)

`python -m first60 demo` (full transcript, both bookings, dedupe,
opt-out, summary), `first60 serve` smoke on the working copy and
on the installed wheel copy, `first60 summary` on fresh and
populated stores, `first60 init` for plumber and med-spa packs,
all against fictional businesses only (BrightSmile Dental, Acme
Plumbing, GlowHaven Test Spa).

Friction found and fixed in this step:

1. Med-spa pack missed "severe pain" and "swelling" as emergency
   terms: a distressed med-spa lead ("I am in severe pain and my
   face is swelling") was asked which treatment they wanted
   instead of being handed off. Fixed: both terms added to
   `packs/med-spa.toml`, with a handoff regression test, and
   verified live on the builtin pack (safety template fires, lead
   handed off, no name captured). Note: a pack scaffolded by
   `init` before the fix keeps the old terms, because `init`
   copies the pack as a snapshot; re-run `init` to pick up pack
   fixes.
2. Name extraction captured "Severe Pain" as a name (step-6 open
   item). Fixed as above; verified live on the dental pack: the
   distress message gets the safety template, the lead is handed
   off, and the summary shows the lead as an unnamed id
   ("Handed off: lead 0c991e77"), never as "Severe Pain".

Friction logged, not fixed (open items):

1. An unnamed lead shows in the summary as a bare id prefix
   ("Overdue: lead 91213b47", "Handed off: lead 0c991e77"). That
   is the designed fallback for a lead with no captured name, and
   it is honest, but it reads as a leak of an internal id to the
   business owner. Candidate for a later pass: show "unnamed lead"
   with the channel handle instead, or nothing at all.
2. `first60 summary` prints a zeroed summary for a fresh store,
   which is correct, but the date it prints is today, not the
   store's last activity date. A store untouched for a week still
   reports "today" with zeroes. Cosmetic; candidate for a later
   pass.
3. The demo's Sam act: Sam says "Hi, I'm Sam. Do you do
   whitening?" and the engine asks "When would you like to come
   in?" before Sam says STOP. The whitening question is correct
   (the timeline question follows the service match), but the
   transcript reads as if the receptionist ignored the greeting.
   Cosmetic; the flow is the designed question order.

## Design decisions recorded

- `init` copies the builtin pack as plain text rather than
  generating one: the owner edits a real pack, and the copy is
  validated by the same loader the server uses. The business name
  replacement touches only the `name` line inside `[business]`,
  so a service or question that happens to carry a name is never
  rewritten.
- `--pack-file` wins over `--pack`, but passing both is an error:
  a silent precedence would hide a typo in the pack name. The
  same rule holds on `serve` and `summary`.
- The wheel ships packs inside the package (`first60/packs`)
  rather than as package data beside it, because `config.py`
  resolves the pack directory from its own file location: the
  installed layout and the repo layout differ by exactly one
  directory, and the lookup tries the installed one first.
- The em-dash sweep touched user-facing output strings in
  `demo.py` and `engine.py` as well as prose, because the README
  quotes the demo transcript verbatim: leaving the dash in the
  output would have forced either a dash in the README or a
  misquote. Historical build logs (BUILD-STEP-1..6) were left
  alone except BUILD-STEP-3.md, which carried two em dashes in
  its prose and was swept with the rest of the tree.
- The changelog keeps `## [0.1.0] - Unreleased`: the tag and the
  release publication are Tech's approval step, and the release
  notes draft says so. Nothing in this step creates a tag or
  publishes anything.

## v0.1.0 checklist (DESIGN.md section 15)

- [x] CI green on main on Python 3.11 and 3.12 (pytest, ruff,
  mypy): local run green (310 tests, ruff check + format, mypy).
  GitHub CI itself cannot be run from here; the parent run
  verifies the CI run on the published head before calling it
  green.
- [x] Test count at or above the section 11 target (~109), all
  offline: 310 tests, zero network calls in code or tests.
- [x] Demo scenario integration test passes; it is the same script
  a visitor runs (`tests/test_demo.py`, and the live `first60
  demo` run above).
- [x] Clean-environment quick start verified: fresh venv, README
  only, fresh copy to booked demo appointment in 11.2s and 10.9s,
  inside the time the README claims; the claim is the
  measurement, not the target.
- [x] All five packs load, validate and each completes a scripted
  qualification conversation in tests (`tests/test_pack_paths.py`).
- [x] No credential, token or real business data anywhere in the
  tree; demo business is fictional (BrightSmile Dental). See the
  secrets grep above.
- [x] README carries the limitations section and the no-voice,
  no-cold-outreach statements; no claim in the README contradicts
  RESEARCH.md's claims discipline (no "first" claims; the
  comparison table is sourced from the 2026-11-06/07 scan).
- [x] LICENSE, SECURITY.md, CONTRIBUTING.md present; version
  0.1.0 in pyproject; CHANGELOG written from actual commits.
- [ ] Tag `v0.1.0` and release notes drafted from the changelog:
  release notes drafted (`RELEASE_NOTES_v0.1.0.md`); the tag is
  NOT created here. Publication follows the standing approval
  flow (Tech's step).

## Open items for the release (not for this step)

- Tag `v0.1.0` and publish the release: Tech's approval step.
  The parent run records it as pending.
- The three dogfood frictions above (unnamed-lead id in the
  summary, summary date on a fresh store, Sam's greeting beat)
  are candidates for v0.1.1 or v0.2, not blockers: none of them
  changes a decision, a booking or a safety outcome.
- The med-spa pack fix only reaches businesses that re-run
  `init` or pull the new pack; scaffolded copies are snapshots.
  Worth one line in the release notes if a pack fix ever ships
  after v0.1.0.
