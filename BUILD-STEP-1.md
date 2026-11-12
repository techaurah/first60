# First60 build step 1: skeleton

Date: 2026-11-08. Local build only. No GitHub repo created, nothing pushed,
no browser used.

## Files created

- `pyproject.toml`: package `first60`, version 0.1.0, Python >= 3.11, zero
  required dependencies (stdlib only), console script `first60`, dev extras
  (pytest, ruff, mypy), MIT, TechAura URLs.
- `src/first60/__init__.py`: version 0.1.0, importable.
- `src/first60/__main__.py`: `python -m first60` entry point.
- `src/first60/cli.py`: argparse CLI with `--help` and `--version`; `demo`,
  `serve`, `summary` and `init` are stubs that report "not built yet" until
  their build steps land.
- `src/first60/config.py`: the only implemented module in this step.
  Business pack loading and validation with stdlib `tomllib`. A broken pack
  raises `PackError` (a named `ValueError` subclass) with a `field`
  attribute naming the broken field.
- `src/first60/pipeline/__init__.py`, `respond/__init__.py`,
  `channels/__init__.py`, `calendar/__init__.py`, `store/__init__.py`:
  importable stubs only, no implementation (steps 2-5).
- `packs/dental.toml` (BrightSmile Dental, fictional), `packs/plumber.toml`
  (SwiftFlow Plumbing), `packs/med-spa.toml` (GlowHaven Med Spa),
  `packs/clinic.toml` (Harborview Family Clinic),
  `packs/real-estate.toml` (Keystone Homes Realty). Each pack is complete:
  services with duration and value tier, qualifying questions, business
  hours, follow-up defaults (touches at +4h, +24h, +72h, max 3, waking
  window 08:00-21:00), emergency terms with a safety instruction, and
  booking terms. All business names are fictional; no real business data
  and no credentials anywhere.
- `LICENSE` (MIT, TechAura), `README.md` (skeleton per DESIGN.md section
  13, unbuilt parts marked in progress, no invented numbers, no "first"
  claims, limitations stated), `CONTRIBUTING.md`, `SECURITY.md`,
  `.gitignore` (Python standard), `CHANGELOG.md` (0.1.0 Unreleased entry).
- `.github/workflows/ci.yml`: push to main plus PRs, Python 3.11 and 3.12,
  pip install, ruff check, ruff format check, mypy, pytest.
- `tests/test_config.py`: all five packs load and validate, shared
  follow-up defaults, Sunday closed, builtin loader, plus broken-pack
  tests (missing file, malformed TOML, missing services, bad value tier,
  bad opening time, empty emergency terms, non-increasing follow-up
  delays), each asserting the named field on `PackError`.
- `tests/test_imports.py`: package imports, `__version__ == "0.1.0"`,
  subpackages import, CLI `--version` and no-command help,
  `python -m first60 --help` in a fresh process.
- `docs/` directory created, empty: docs pages land in build step 7.
- `.venv/` local virtualenv (Python 3.12.3, gitignored) used for the
  checks below. No global installs.

## Verification (local, 2026-11-08)

All run from `~/workspace/github-profile/first60/` with `.venv/bin/`:

- pytest: `29 passed in 0.16s` (24 config tests, 5 import/CLI tests).
- ruff check: `All checks passed!`
- ruff format check: `15 files already formatted` (after one
  `ruff format .` pass that reformatted 7 files).
- mypy: `Success: no issues found in 9 source files`
- `python -m first60 --help` exits 0 and prints usage; `first60 --version`
  prints `first60 0.1.0`.
- Fresh-process pack load: all five packs load via `load_builtin_pack`:
  clinic 5 services, dental 5, med-spa 5, plumber 6, real-estate 5, each
  5 questions, follow-up delays (4, 24, 72), max 3 touches.
- Em dash scan over all written files: no em dashes found (grep exit 1).
- No invented statistics and no quick-start time claimed anywhere; the
  README states the demo time will be measured in build step 6.

## Done-condition status

DESIGN.md section 14 step 1 done condition: "CI runs green on an
empty-but-importable package; all five packs load."

- All five packs load: verified locally, yes.
- Package is empty-but-importable: verified locally, yes.
- CI runs green: PENDING GitHub publish. There is no repo yet and nothing
  was pushed, so the GitHub Actions workflow has never run. The workflow
  mirrors the leadpipe-mcp CI (same commands, same Python versions) and
  every command it runs passes locally, but "CI runs green" cannot be
  claimed until the repo exists and the workflow runs there. Local checks
  green is what was verified.

## Next step

Build step 2 (pure core): stages, scoring, extraction, qualification
flow, no I/O, with the design's ~42 pure-core tests.
