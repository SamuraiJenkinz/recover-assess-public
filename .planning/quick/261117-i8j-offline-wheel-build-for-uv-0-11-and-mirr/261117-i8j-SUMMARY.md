---
phase: 261117-i8j-offline-wheel-build-for-uv-0-11-and-mirr
plan: 01
subsystem: packaging
tags: [uv, build-system, wheel, pip-fallback, readme]
status: complete
requires: []
provides:
  - "[build-system] floor uv_build>=0.11,<0.14 so uv 0.11+ builds the wheel offline"
  - "mirror-first pip fallback in README with an offline uv wheel build"
affects: [README.md, pyproject.toml]
key-files:
  modified: [pyproject.toml, tests/unit/test_export_requirements.py, README.md]
  created: [tests/unit/test_wheel_build.py]
decisions:
  - "build dependency group stays uv_build>=0.13.8,<0.14; uv.lock and requirements/ unchanged"
  - "build-system equality test replaced by range tests (group range inside build-system range, locked backend inside both)"
commits: 3
plan_head_before: 54acb94
plan_head_after: da6c7a2
actuals:
  tokens: 40000
  tasks: 3
  commits: 3
---

# Phase 261117-i8j Plan 01: Offline wheel build for uv 0.11 and later Summary

`[build-system] requires` now admits uv 0.11, so uv uses its built-in backend and builds the project wheel offline; the README pip fallback leads with that mirror-first route and its commands were run as written in a fresh copy.

## Tasks

| Task | Name | Commit |
| ---- | ---- | ------ |
| 1 | Tracer: relax build-system floor, range tests, offline wheel test | d2b092f |
| 2 | README mirror-first pip fallback | 9eb9de9 |
| 3 | README TLS proxy framing, full gate | da6c7a2 |

## Task 1 evidence

- RED: before the pyproject change, `test_build_system_requires_admits_uv_0_11` failed with `assert (0, 13, 8) <= (0, 11, 0)`; the other 14 tests in the file passed.
- GREEN: `[build-system] requires = ["uv_build>=0.11,<0.14"]`; 16 tests pass across `test_export_requirements.py` and `test_wheel_build.py`. `uv lock --check` and `scripts/export_requirements.py --check` exit 0; `uv.lock` and `requirements/` are byte-identical to 54acb94. ruff check, ruff format --check and mypy clean.
- End-to-end from a clean `git archive` copy of the committed tree, uv 0.11.24 (`uvx --from uv==0.11.24 uv build --wheel --offline --no-cache`):
  `Building wheel (uv build backend)...` then `Successfully built ...recover_assess-0.1.0-py3-none-any.whl`. Hash-locked runtime install into a throwaway 3.12 venv, wheel installed with `--no-index --no-deps`, `recover-assess --version` printed `0.1.0`.

## Task 2 probe results (README primary PowerShell lines, extracted verbatim from the README)

Fresh `git archive` copy with no `.venv`; test credentials were a first.last at example.com user name and a token containing `/ : + =`; the stand-in for the mirror was the public index.

- `uv python find 3.12` pointed at the uv-managed interpreter, outside the copy (`OK py outside copy`).
- Escaped URL assertion passed (`OK escaped url`): `@` became `%40`, and `/ : + =` became `%2F %3A %2B %3D`.
- Locked hash-checked install succeeded; `uv build --wheel --offline --out-dir dist` built the wheel; wheel install succeeded; `recover-assess --version` printed `0.1.0`; `PIP_INDEX_URL` was empty after `Remove-Item`.
- Second wheel install with `--force-reinstall` uninstalled and reinstalled `recover-assess 0.1.0`. `python -m pip check`: `No broken requirements found.`
- Redaction check: `pip download` against an unreachable index with credentials in the URL printed `Looking in indexes: https://u%40example.com:****@127.0.0.1:9/simple`, so the README states that pip masks the token with `****`.
- bash `quote` lines with the same test values produced the same escaped URL as PowerShell.
- Secondary (no uv) PowerShell block, run in a second fresh copy with the interpreter path in place of the placeholder: locked and build.txt installs, `--no-build-isolation .` build and install, `recover-assess --version` printed `0.1.0`, `pip check` clean.

## Task 3 gate (`uv run --frozen python scripts/check.py`, exit 0)

| Step | Status |
| ---- | ------ |
| uv-lock-check | PASS |
| requirements-export | PASS |
| ruff-check | PASS |
| ruff-format | PASS |
| mypy | PASS |
| import-contracts | PASS |
| blocked-terms | PASS |
| pytest | PASS (945 passed, slow wheel test included) |

Commit messages for 54acb94..HEAD scanned with `blocked_terms.scan_text`: 0 hits. `git log --name-only 54acb94..HEAD` lists only `pyproject.toml`, `tests/unit/test_export_requirements.py`, `tests/unit/test_wheel_build.py` and `README.md`; neither `.planning/config.json` nor `.planning/state.json` is in any commit.

## Deviations from Plan

None - plan executed as written. (Minor wording: the README block-page subsection is headed "If every package fails the hash check" and the secondary route "Python 3.12 without uv", both as `###` subsections under the fallback heading, which is unchanged.)

## Known Stubs

None.

## Threat Flags

None.

## Self-Check: PASSED

- Commits d2b092f, 9eb9de9, da6c7a2 are ancestors of HEAD.
- `tests/unit/test_wheel_build.py` exists; README fallback heading unchanged.
