# Contributing to First60

Thank you for considering a contribution. First60 is an open-source
text-first AI receptionist for service businesses, built by TechAura.

## Ground rules

- **Rules decide, responders phrase.** Qualification, scoring, stage
  moves, booking and follow-up timing are deterministic code. A
  responder only renders text from a decision object. Never let a model
  make a decision.
- **No credentials, no real business data.** Demo data is fictional
  (BrightSmile Dental). Never commit tokens, keys, real lead data, real
  phone numbers or real business details, in code, tests or examples.
- **Zero required dependencies.** The runtime is stdlib only. A new
  dependency needs a design discussion first.
- **Tests for every behaviour change.** All tests run offline. Run the
  full check suite before opening a pull request (see below).
- **Honest claims only.** Do not claim First60 is the first AI
  receptionist or the first open-source receptionist; the research in
  `RESEARCH.md` (design folder) contradicts that. Claims in the README
  must be verifiable from the repo.

## How to contribute

1. Fork the repo and create a branch from `main`.
2. Pick an open issue, or open one describing the change first for
   anything larger than a typo fix.
3. Follow the style of the module you are changing. Type hints on all
   public functions.
4. Add or update tests. Keep the suite offline and fast.
5. Run the checks, then open a pull request scoped to one issue.

## Checks

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
ruff format --check .
mypy src/first60
```

CI runs the same checks on Python 3.11 and 3.12. Red CI blocks a merge.

## Reporting bugs

Open an issue with the pack or command involved, what you expected, what
happened, and the smallest steps to reproduce it. For security issues,
see SECURITY.md instead of opening a public issue.
