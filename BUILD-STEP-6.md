# First60 build step 6: demo and measured quick-start time

Date: 2026-11-13. Author: TechAura (@techaurah).

## What was built

DESIGN.md section 14 step 6: "Seed data, scripted scenario,
interactive mode; the scenario wired in as the integration test;
clean-machine quick-start timed honestly."

- `src/first60/demo.py`: the demo module.
  - `SimulatedClock`: a hand-set clock (`set` / `now`); the demo
    moves it explicitly through the day, so every act runs at its
    real time and the +4h follow-up genuinely fires at 16:00.
  - `build_demo_world`: dental pack, in-memory store, rule
    responder, simulated channel, engine in `demo` write mode,
    clock starting Tuesday 21:40, calendar seeded with one busy
    block (an existing patient, Thursday 10:30 check-up, a real
    lead in stage BOOKED with a real appointment).
  - `run_demo`: the scripted scenario, printing the transcript as
    it goes. Tuesday 12:00 Priya enquires about whitening
    Wednesday morning and goes quiet; 16:00 touch 1 fires and she
    books Wednesday 09:00 from it; 21:47 Sarah's after-hours
    enquiry ("do you have anything Thursday morning, my crown is
    aching") is qualified in three questions and books Crown
    fitting Thursday 09:00, score 70 (WARM) printed with its
    components; Sarah re-messages and dedupe holds (2 demo leads
    before, 2 after, one appointment); 22:05 Sam enquires then
    replies STOP, audit shows the opt-out, 0 further touches
    scheduled; Wednesday 08:00 the daily summary prints. The
    seeded Thursday 10:30 block is visible in Sarah's offer: the
    60-minute crown cannot start at 10:00, so the offer reads
    09:00, 09:30, 11:00.
  - `render_daily_summary`: the daily summary as plain text. Stage
    and band counts come from the server's `/status` surface
    (`first60.server.status_payload`), so the printed summary and
    the HTTP surface cannot disagree; the booking list covers
    every booked appointment (not just today's), and paused leads
    are split into handed-off and opted-out, which the status
    payload lumps together.
  - `run_interactive`: opens the console channel on a fresh seeded
    world (simulated Tuesday 21:40 clock) so a visitor can play
    the customer. The engine's channel stays the simulated outbox
    in this mode, so the console loop prints each reply exactly
    once; the engine never sends anywhere real.
- `src/first60/cli.py`: `demo` and `summary` are wired (both were
  labelled build step 6 in the CLI already). `first60 summary`
  (`--pack`, `--db`) prints the same daily summary for a SQLite
  store; it is read-only, and a missing store file prints a zeroed
  summary rather than an error. Only `init` remains a stub
  (step 7).
- `src/first60/engine.py`: one bug found by the demo, fixed here.
  A booked lead who wrote again crashed with
  `STAGE_TRANSITION_INVALID`: the engine re-offered slots and
  attempted the illegal BOOKED -> QUALIFIED move. The engine
  docstring already promised an acknowledgement; the code did not
  do it. `handle_inbound` now answers a booked lead with
  `_acknowledge_booking` (names the booked service and time) and
  schedules no follow-up. The fix is scoped to this path: opt-out
  and handoff checks still run first, so a booked lead saying STOP
  still opts out.

## Verification (local, before publish)

- 285 pytest passed (272 existing + 13 new: the release-gate
  scenario test, a determinism test, 2 booked-lead tests, 2
  interactive tests, 2 summary tests, 1 clock test, 3 CLI tests),
  ruff check + format clean, mypy clean.
- Live runs: `python -m first60 demo` prints the full transcript
  (both bookings, the dedupe note, the opt-out note, the Wednesday
  summary); `python -m first60 demo --interactive` books Crown
  fitting Thursday 09:00 from piped console input; `first60
  summary` prints a zeroed summary for a fresh store.

## Measured quick-start time

About 10 seconds from a fresh copy to the booked demo
appointment, target under 5 minutes: two runs, 9.8s and 10.1s
(Python 3.12.3, measured 2026-11-13 with
`/tmp/quickstart-measure.py`). Phase split on the second run:
copy 0.0s, fresh venv 4.7s, `pip install -e .` 5.1s, demo 0.3s;
both demo bookings present in the output, exit code 0.

Honest caveat, recorded here and in one line in the README: the
"clone" step was a fresh local copy of the working tree, not a
`git clone` over the network, because the local tree is not a git
checkout (publishing happens in the parent run via the browser).
A real `git clone` of this small repo adds a few seconds on a
normal connection; the total stays far under the 5-minute target
either way. The number in the README is the measurement, not the
target.

## Design decisions recorded

- The scenario runs in clock order (12:00, 16:00, 21:47, 22:05,
  Wednesday 08:00), not the design's listing order: the clock
  never moves backwards, so the +4h touch genuinely fires at
  16:00 and the summary genuinely follows the day. The design's
  "simulated clock set to Tuesday 21:40" is the starting clock
  for the after-hours act; the acts before it set the clock
  explicitly.
- One seeded busy block, not several: a single Thursday 10:30
  booking is enough to make the crown offer visibly skip 10:00
  and 10:30, and it keeps the summary's booking list readable
  (three bookings: the two demo bookings plus the pre-existing
  one, narrated up front).
- The summary splits paused leads into handed-off and opted-out.
  The `/status` surface reports both as handed-off (both set
  `automation_paused`); the printed summary is the human-facing
  surface, so it says which is which.
- Priya's 2h appointment reminder (due Wednesday 07:00 for her
  09:00 appointment) is not fired in the scripted run: the demo
  prints the summary at 08:00 but does not run the scheduler
  there, and the design's scenario does not ask for a reminder
  beat. The reminder engine itself is covered by step-5 tests.
- The `first60 summary` command defaults to the dental pack and
  `first60.db`, matching `serve`'s defaults.

## Observed, not fixed (out of scope for step 6)

- Name extraction misfires on distress phrasing: "I'm in severe
  pain and my face is swelling" captures the name "Severe Pain"
  (the "I'm" pattern takes the following words; "severe" is not
  in the non-name list). A handoff lead then appears under that
  name in the summary. Pre-existing step-2 behaviour; the demo
  test works around it by having the lead introduce himself
  first. Candidate for step 7 or a later extraction pass, not
  fixed here, because changing extraction semantics is outside
  the step-6 scope.

## Open items for step 7

- Docs and release prep (DESIGN.md section 14 step 7): README
  completion per section 13, `docs/` pages, CHANGELOG from actual
  commits, dogfood run, v0.1.0 checklist in section 15.
- The `init` CLI command is still a stub.
- The wheel build (`pyproject.toml` packages only `src/first60`)
  does not ship `packs/`, so an installed-from-PyPI copy cannot
  load a builtin pack; the editable install used by the
  quick-start keeps the layout and works. Packaging fix belongs
  with step 7's release prep.
- The extraction quirk above ("Severe Pain" as a captured name).
