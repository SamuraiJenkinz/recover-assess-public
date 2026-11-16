---
phase: 01-foundation-contract-read-only-graph-client
plan: 01
subsystem: infra
tags: [uv, python-3.12, supply-chain, pydantic, typer, import-linter, ruff, mypy, scaffold]

requires:
  - phase: none
    provides: first plan of the project
provides:
  - "uv 0.13.8 and CPython 3.12 installed at user level from a checksum-verified archive, no admin"
  - "pyproject.toml with every pin, tool config and the five import-linter contracts; uv.lock approved by the developer before any install"
  - "recover_assess.core.errors: exception tree, 11 spec error codes plus graph_error_NNN, URL-free messages"
  - "recover_assess.core.clock: injectable Clock protocol and SystemClock"
  - "recover-assess --version CLI (Typer) with locals hidden in tracebacks"
  - "Package markers and core/graph.py placeholder so import-linter contracts resolve"
affects: [01-02, 01-03, 01-04, 01-11, graph-client, contract, ci-gate]

actuals:
  tokens: 7425
  tasks: 3
  commits: 3

tech-stack:
  added: [httpx2, tenacity, pydantic, pydantic-settings, pyyaml, typer, pytest, pytest-asyncio, hypothesis, ruff, mypy, import-linter, jsonschema, types-pyyaml, types-jsonschema]
  patterns:
    - "Leaf modules (errors, clock) import only the standard library so every later module can depend on them"
    - "Exception messages are built only from an identifier-shaped reason and a path template, never a URL"
    - "pytest.raises on broad exceptions always passes match= (ruff PT011)"
    - "Imports inside test functions during TDD RED so each test fails on its own, not at collection"

key-files:
  created:
    - pyproject.toml
    - uv.lock
    - .python-version
    - .gitignore
    - .gitattributes
    - README.md
    - config/README.md
    - scripts/verify_sha256.py
    - src/recover_assess/__init__.py
    - src/recover_assess/cli.py
    - src/recover_assess/core/errors.py
    - src/recover_assess/core/clock.py
    - src/recover_assess/core/graph.py
    - tests/unit/test_foundation.py
  modified: []

key-decisions:
  - "uv is bootstrapped from the versioned 0.13.8 release archive with a SHA-256 check, never a piped installer"
  - "UrlNotAllowedError subclasses WriteAttemptError so one except clause catches every refused request"
  - "ThrottledOut is one type with three reasons (retries_exhausted, budget, breaker) and one code, throttled_out"
  - "ruff is told to skip .planning, .claude and out, because ruff 0.17 reformats markdown"

patterns-established:
  - "Error vocabulary: ERROR_CODES plus ERROR_CODE_PATTERN anchored with \\A and \\Z; is_error_code uses fullmatch"
  - "Typer options use Annotated defaults, which keeps ruff B008 quiet"

requirements-completed: [FND-01]

coverage:
  - id: D1
    description: "uv 0.13.8 and CPython 3.12 installed at user level from a checksum-verified archive; uv.lock approved by the developer before any install"
    requirement: FND-01
    verification:
      - kind: other
        ref: "uv --version; uv lock --check; uv sync --locked"
        status: pass
    human_judgment: true
    rationale: "A clean non-admin Windows machine behind a TLS-inspecting proxy cannot be reproduced here (Task 3 human-check, assumption A9)"
  - id: D2
    description: "Pinned manifest with ruff, mypy, pytest and import-linter configuration; lock contains none of httpx, respx, requests, vcrpy, pytest-httpx"
    requirement: FND-01
    verification:
      - kind: unit
        ref: "tests/unit/test_foundation.py#test_lock_names_none_of_the_forbidden_packages"
        status: pass
      - kind: unit
        ref: "tests/unit/test_foundation.py#test_ruff_select_is_the_explicit_fifteen_rule_list"
        status: pass
      - kind: other
        ref: "uv run lint-imports (5 contracts kept, 0 broken)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Error vocabulary: 11 spec codes plus graph_error_NNN, URL-free messages, WriteAttemptError hierarchy"
    requirement: FND-01
    verification:
      - kind: unit
        ref: "tests/unit/test_foundation.py#test_is_error_code_accepts_spec_codes"
        status: pass
      - kind: unit
        ref: "tests/unit/test_foundation.py#test_url_not_allowed_message_carries_no_url_or_token"
        status: pass
      - kind: unit
        ref: "tests/unit/test_foundation.py#test_url_not_allowed_is_a_write_attempt_error"
        status: pass
    human_judgment: false
  - id: D4
    description: "Injectable clock and Typer entry point printing exactly 0.1.0"
    requirement: FND-01
    verification:
      - kind: unit
        ref: "tests/unit/test_foundation.py#test_version_option_prints_exactly_the_version"
        status: pass
      - kind: unit
        ref: "tests/unit/test_foundation.py#test_system_clock_utcnow_is_timezone_aware_utc"
        status: pass
    human_judgment: false
  - id: D5
    description: "README documents the no-admin install and the UV_SYSTEM_CERTS proxy fix and never suggests weakening TLS"
    requirement: FND-01
    verification:
      - kind: unit
        ref: "tests/unit/test_foundation.py#test_readme_never_suggests_weakening_tls"
        status: pass
    human_judgment: true
    rationale: "Whether the install steps work verbatim on a clean proxied machine needs a human run"

duration: 25min
completed: 2026-11-15
status: complete
commits: 3
plan_head_before: 48f2e6ad77239f1db910964e9373d44406b78171
plan_head_after: e506e62c4cd37dd3c5f5cd37adf2aeb2678b8be4
---

# Phase 1 Plan 01: Toolchain, Pinned Manifest and Package Skeleton Summary

**Checksum-verified uv 0.13.8 toolchain, a developer-approved pinned uv.lock, and a package skeleton with a URL-free error vocabulary, an injectable clock and a `recover-assess --version` Typer entry point**

## Performance

- **Duration:** about 25 min (from the plan commit to the last task commit, by commit timestamps; the run was split across two executors by the blocking-human checkpoint)
- **Completed:** 2026-11-15
- **Tasks:** 3 of 3 (Task 2 is a review-only checkpoint with no files)
- **Files modified:** 27 excluding uv.lock (28 with it); about 7.4K tokens of hand-written diff (chars/4, uv.lock excluded)

## Accomplishments

- uv 0.13.8 and CPython 3.12.16 are installed in the user profile with no admin rights. The uv archive was hashed by `scripts/verify_sha256.py` before extraction, and the developer re-checked the SHA-256 against the GitHub release page at the Task 2 checkpoint.
- `pyproject.toml` carries every runtime and dev pin, the uv_build backend config, and the strict ruff, mypy, pytest and import-linter configuration. All five import-linter contracts resolve and are kept (5 kept, 0 broken), because every module they name now exists.
- `core/errors.py` defines the exception tree and the error-code vocabulary. No message can carry a URL or token: constructors reject non-identifier reasons and URL-shaped templates.
- `core/clock.py` gives later plans an injectable `Clock` and the one module allowed to sleep.
- `uv run recover-assess --version` prints exactly `0.1.0`; running with no arguments prints help and exits 2.

## Task Commits

1. **Task 1: Pinned manifest, user-level toolchain and lockfile** - `eeb18cc` (chore)
2. **Task 2: Package legitimacy review of the resolved uv.lock** - no commit (review only); developer replied "approved"
3. **Task 3: Package skeleton, install from the approved lock, foundation tests (TDD)**
   - RED: `cd41beb` (test) - 36 of 50 tests failed on the missing `errors`, `clock` and `cli` modules
   - GREEN: `e506e62` (feat) - 50 of 50 pass

**Plan metadata:** recorded in the docs commit that follows this summary.

## Task 2 Checkpoint: Approval and Review Notes

The developer personally verified the uv archive SHA-256 (`529e78a9cec6cd7e3e014f7ecd8bda0c113969d4ed0f2efeedb85c30943325b8`, archive `uv-x86_64-pc-windows-msvc.zip` from the 0.13.8 GitHub release) against the release page and replied "approved" to the lock. `uv sync --locked` ran only after that reply.

Orchestrator review notes:
- All 6 runtime dependencies and the 6 transitive packages not on the audit list (`httpcore2`, `ast-serialize`, `librt`, `annotated-doc`, `python-dotenv`, `httpx2-jsfetch`) trace to expected parents and to expected upstream repositories and publishers on PyPI.
- `httpx2-jsfetch` has no repository link on PyPI, but uv.lock gates it on `sys_platform == 'emscripten'`, so it is never installed on Windows, macOS or Linux.
- `uv-build` 0.13.8 is Astral's.

## Files Created/Modified

- `pyproject.toml` - pinned deps, uv_build config, ruff/mypy/pytest/import-linter config
- `uv.lock` - resolved lock, approved at the Task 2 checkpoint (47 packages plus the project)
- `.python-version`, `.gitignore`, `.gitattributes` - Python pin, ignore rules for drafts, secrets and run output, LF line endings
- `README.md` - no-admin install, `UV_SYSTEM_CERTS` proxy guidance (PowerShell and bash), `UV_PYTHON_DOWNLOADS=never` fallback
- `scripts/verify_sha256.py` - stdlib-only SHA-256 checker used for the uv bootstrap
- `src/recover_assess/__init__.py`, `cli.py` - version constant and Typer entry point
- `src/recover_assess/core/errors.py`, `clock.py` - leaf modules every later plan imports
- `src/recover_assess/core/graph.py` and 13 package `__init__.py` markers - docstring-only placeholders
- `config/README.md` - what the config folder is for, and why the allow-list is not there
- `tests/unit/test_foundation.py` - 50 foundation tests

## Decisions Made

- The uv bootstrap uses the versioned release archive plus its published `.sha256` rather than a piped installer (T-01-30).
- `UrlNotAllowedError` is a subclass of `WriteAttemptError`, so `except WriteAttemptError` catches every refused verb and URL while tests can still assert the exact class.
- `ThrottledOut` is a single class with three reasons and one stable code.
- `ruff format .` and `ruff check .` skip `.planning`, `.claude` and `out`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] ruff 0.17 reformatted tracked markdown planning files**
- **Found during:** Task 3 (running `uv run ruff format .`)
- **Issue:** ruff 0.17 formats markdown. The command rewrote `.planning/phases/01-.../01-RESEARCH.md`, `.planning/research/ARCHITECTURE.md` and `.planning/research/STACK.md`, which are not this plan's files. Every later plan that runs the plan's own `ruff format .` would have hit the same thing.
- **Fix:** Reverted the three files with `git checkout -- <path>` (file by file) and added `extend-exclude = [".planning", ".claude", "out"]` to `[tool.ruff]` in `pyproject.toml`. `ruff format --check .` now covers 23 Python files.
- **Files modified:** `pyproject.toml`
- **Verification:** `uv run ruff format --check .` and `uv run ruff check .` clean; `git status` shows no `.planning` research files modified
- **Committed in:** `e506e62` (Task 3 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Config-only and necessary so the format step does not touch planning documents. No scope creep.

## Issues Encountered

- The RED run needed the package installed first, so the package marker and version module were created and `uv sync --locked` was run before the tests were committed. The RED commit holds only the tests and test package markers; `src/` went in the GREEN commit.
- Task 3's human-check (follow the README verbatim on a clean non-admin machine, behind the corporate proxy if possible) has not been performed. It cannot be reproduced here. It is the confirmation of Flagged assumption FA-1 and RESEARCH A9, and remains open for the developer.

## Known Stubs

| File | Line | Reason |
|------|------|--------|
| `src/recover_assess/core/graph.py` | 1 | Docstring-only placeholder. It must exist so import-linter contracts resolve; Plan 01-02 implements the read-only Graph client. Intentional and documented in the plan. |

## Verification Results

Demo command: `uv run recover-assess --version` prints `0.1.0`.

| Check | Result |
|-------|--------|
| `uv --version` | `uv 0.13.8` |
| `uv lock --check` | exit 0 (Resolved 48 packages) |
| `uv sync --locked` | exit 0 |
| `uv run pytest tests/unit/test_foundation.py -x -q` | 50 passed |
| `uv run ruff check src tests` and `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 23 files already formatted |
| `uv run mypy` | Success: no issues found in 21 source files |
| `uv run lint-imports` | 5 contracts kept, 0 broken |
| `grep -c UV_SYSTEM_CERTS README.md` | 3 (at least 2 required) |
| `grep -c "httpx2~=2.16.0" pyproject.toml` | 1 |
| `grep -c "pretty_exceptions_show_locals=False" src/recover_assess/cli.py` | 1 |
| `git check-ignore` on both drafts, recover-assess.yaml, out/x.json, a.pem, a.pfx | all ignored |

Task 1 recorded the uv bootstrap route as the checksum-verified release archive (not the pip `--require-hashes` fallback).

## User Setup Required

None - no external service configuration required. One manual check remains open: the Task 3 clean-machine, proxied install check (see Issues Encountered).

## Next Phase Readiness

- Plans 01-02, 01-03, 01-04 and 01-11 (Wave 2) can import `recover_assess.core.errors` and `recover_assess.core.clock`, and no longer need to edit any package marker.
- The import-linter contracts are the fixed reference (D-04); later plans must not weaken them.
- Open item for the developer: the clean-machine install human-check above.

## Self-Check: PASSED

- Created files verified present: `pyproject.toml`, `uv.lock`, `README.md`, `scripts/verify_sha256.py`, `src/recover_assess/cli.py`, `src/recover_assess/core/errors.py`, `src/recover_assess/core/clock.py`, `src/recover_assess/core/graph.py`, `tests/unit/test_foundation.py`
- Commits verified: `eeb18cc`, `cd41beb`, `e506e62` all ancestors of HEAD
- `git rev-list --count` from the plan-head ledger to HEAD measured 3, matching `commits: 3`

---
*Phase: 01-foundation-contract-read-only-graph-client*
*Completed: 2026-11-15*
