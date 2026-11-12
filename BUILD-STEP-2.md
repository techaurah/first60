# First60 build step 2: pure core

Date: 2026-11-09. Local build only. No GitHub repo created, nothing pushed,
no browser used.

## Files created

- `src/first60/pipeline/stages.py`: the `Stage` enum (NEW, CONTACTED,
  QUALIFIED, BOOKED, NURTURE, LOST), the transition map, and lead dedupe.
  `transition(current, target)` returns the new stage; a same-stage move
  is a no-op success; any other illegal move raises
  `StageTransitionError` with code `STAGE_TRANSITION_INVALID` (DESIGN.md
  section 5). The map is the sequential flow NEW -> CONTACTED ->
  QUALIFIED -> BOOKED, with NURTURE and LOST reachable from any live
  stage and reactivation LOST -> NURTURE only. Dedupe is on normalised
  email first, then phone, exactly as LeadPipe specifies
  (`dedupe_key`, `normalize_email`, `normalize_phone`).
- `src/first60/pipeline/scoring.py`: deterministic qualification scoring
  (`ScoringInput`, `Score`, `score_lead`, `band_for`). Six components
  totalling 0-100: service_fit (full 25, related 15, none 5), urgency
  (emergency 20, today 15, this week 10, flexible 5, unknown 0),
  contact (name 5, reachable contact 10), completeness (15 scaled by
  the share of required questions answered), value (matched service
  tier: high 15, standard 10, low 5; a stated job-size signal is 10
  with no service matched), engagement (2 per lead reply, capped at
  5 replies). Bands use LeadPipe's thresholds: HOT 80-100, WARM 65-79,
  NURTURE 50-64, LOW below 50. There is deliberately no `total` input:
  a total is computed, never accepted.
- `src/first60/pipeline/extract.py`: slot extraction from message text
  (`match_service`, `extract_timeline`, `extract_contact`,
  `extract_name`, `extract_phone`, `extract_email`, `detect_opt_out`,
  `detect_human_request`). Service matching is keyword-based on the
  service name with generic words dropped: full when every distinctive
  word appears, related when at least one does, most matched words
  wins, ties break by pack order. Timeline urgency ranks pack
  emergency terms first, then today phrases, then this week (tomorrow,
  weekday names, this weekend), then flexible phrases. Name capture
  uses "my name is / I'm / I am / call me" and rejects words that
  cannot be a name, so "I'm in pain" yields no name. Opt-out detection
  is whole-word, so "stopcock" never counts as STOP.
- `src/first60/pipeline/qualify.py`: the qualification question flow
  (`ConversationState`, `initial_state`, `next_question`,
  `is_qualified`, `completeness`, `answered_required`,
  `apply_message`). State is an immutable dataclass: answers, matched
  service, strongest urgency seen, consecutive extraction failures,
  stuck flag, reply count. `apply_message` mines each message
  opportunistically (a volunteered service, timeline, name or contact
  fills its question even when it was not the one just asked), then
  judges the question the lead was asked before the message arrived:
  structured questions need a successful extraction, free-text
  questions take any non-empty reply. Two consecutive extraction
  failures on the same question mark the conversation stuck (the
  handoff trigger in DESIGN.md section 8).
- `src/first60/pipeline/__init__.py`: exports the pure-core public API
  (was a stub in step 1).
- `tests/test_stages.py` (10 test functions, 43 cases): every allowed
  transition, every illegal transition with the named error code,
  same-stage no-op for all six stages, LOST reactivates only to
  NURTURE, NURTURE re-enters at CONTACTED, BOOKED never moves
  backwards, dedupe precedence and normalisation.
- `tests/test_scoring.py` (14 test functions, 37 cases): band
  boundaries 49/50, 64/65, 79/80; every component at min/max; a perfect
  lead scores 100 and HOT; a total can never be passed in.
- `tests/test_extract.py` (12 test functions, 33 cases): service
  matching (full, related, most-words-wins, no match), timeline
  phrases and pack emergency terms, phone/email/name extraction with
  rejections ("I'm in pain" yields no name), opt-out and human-request
  detection including the "stopcock" and "estate agent" negatives.
- `tests/test_qualify.py` (9 test functions): pack-order questioning,
  one message answering two questions, free-text questions, two
  failures mark stuck, failure reset on success, optional questions
  never block qualification, urgency only escalates, related-to-full
  service upgrade, empty messages ignored.
- `tests/test_pack_paths.py` (1 test function, 5 cases): every pack
  completes a scripted qualification conversation end to end (messages
  in, qualification out, a score with components, stage walk NEW ->
  CONTACTED -> QUALIFIED). Scores measured from the real code: dental
  76 WARM (Crown fitting, related), plumber 95 HOT (Boiler repair,
  full), med-spa 73 WARM (Signature facial, related), clinic 78 WARM
  (Blood test, full), real-estate 76 WARM (Property viewing, related).

## Files changed

- `CHANGELOG.md`: step 2 entry under 0.1.0 Unreleased.
- `README.md`: status line now reads build step 2 of 7; the
  conversation-engine pure core is marked built, booking, follow-up
  engine, channels and demo still in progress; step 2 checked off in
  the build progress list.

## Verification (local, 2026-11-09)

All run from `~/workspace/github-profile/first60/` with `.venv/bin/`:

- pytest: `156 passed in 0.29s` (29 existing still passing, 127 new
  cases from 46 new test functions: 43 stages, 37 scoring, 33
  extraction, 9 qualification, 5 pack paths).
- ruff check: `All checks passed!`
- ruff format check: `25 files already formatted` (after one
  `ruff format .` pass that reformatted 4 files).
- mypy: `Success: no issues found in 13 source files`
- Fresh-process pack load: all five packs still load via
  `load_builtin_pack` (unchanged from step 1).
- Em dash scan over all written files: no em dashes found (grep exit 1).

## Design choices made

Where DESIGN.md leaves a detail open, the simplest deterministic rule
was chosen and documented in a code comment in the module concerned:

- Stages: a move never skips a step (CONTACTED -> BOOKED is illegal),
  a booked lead can go NURTURE or LOST but never backwards, a nurtured
  lead re-enters at CONTACTED and re-earns qualification.
- Dedupe: formatting variants of the same dial string dedupe together
  (spaces, dashes, leading `+` or `00`); international/trunk
  equivalents (`+44...` vs `020...`) do not, because that needs
  country knowledge the pack does not carry.
- Scoring: unclassifiable service scores 5 (the lead did contact the
  business); "tomorrow" and weekday names count as this week;
  completeness counts required questions only, so a lead that answered
  everything required is fully complete; engagement caps at 5 replies
  so chatter alone never reaches HOT.
- Extraction: service matching is keyword-based on service-name words
  only, no synonyms ("toothache" does not match a crown); a bare
  "emergency" word with no pack term counts as today, not emergency;
  "this is ..." is not a name pattern (it misfires on "this is an
  emergency").
- Qualification: success or failure is judged against the question the
  lead was asked before the message arrived; opportunistic fill only
  ever fills questions the pack actually asks.

## Bug found and fixed during verification

The first test run failed 4 of 156: `apply_message` judged failure
against the current question *after* opportunistic fill, so a message
that answered two questions at once was counted as failing the next
one, and a message answering a structured question had its text
swallowed as the next free-text question's answer. It also filled a
"timeline" answer for the plumber pack, which has an "urgency"
question and no "timeline" question. Fixed in
`src/first60/pipeline/qualify.py`: the current question is captured
before the fill, and fill only applies to question ids the pack asks.
All 156 tests pass after the fix. The rule is recorded in the module
docstring so step 5's engine does not reintroduce it.

## Done-condition status

DESIGN.md section 14 step 2 done condition: "the ~42 pure-core tests
pass."

- Pure-core tests: 45 test functions in the three planned groups
  (stages 10, scoring 14, extraction + qualification 21), 122 cases,
  all passing, plus 5 pack-path cases.
- No I/O anywhere in `first60/pipeline`: stages, scoring, extraction
  and qualification take plain values and return plain values; the
  store, calendar, channels and demo remain for later steps.

## Next step

Build step 3 (store and calendar): the store protocol with sqlite and
memory implementations under one contract test set, and
LocalCalendar availability with idempotent booking. It builds on
this step's `ConversationState` (the store will persist it),
`Stage.transition` (the store's stage moves go through the same map),
and the scoring components (stored per lead and shown in the
summary). Open items for step 3: none from this step; the pure core
is complete and tested.
