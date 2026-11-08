# Changelog

All notable changes to First60 will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to
Semantic Versioning.

## [0.1.0] - Unreleased

### Added
- Repository skeleton (build step 1): `pyproject.toml` with zero required
  dependencies, `src` layout, MIT license, contributing and security docs,
  and a GitHub Actions CI workflow (Python 3.11 and 3.12, pytest, ruff,
  mypy non-strict).
- Business pack loader (`first60.config`): loads and validates a pack
  from TOML using stdlib `tomllib`, raising `PackError` naming the broken
  field on any invalid pack.
- Five validated business packs in `packs/`: dental (fictional
  BrightSmile Dental), plumber, med spa, clinic and real estate. Each
  pack carries services, qualifying questions, business hours,
  follow-up policy defaults (touches at +4h, +24h, +72h, max 3, waking
  window 08:00-21:00) and emergency handoff terms.
- CLI entry points: `first60` console script and `python -m first60`
  with `--help` and `--version`. The `demo`, `serve`, `summary` and
  `init` commands are stubs until their build steps land.
