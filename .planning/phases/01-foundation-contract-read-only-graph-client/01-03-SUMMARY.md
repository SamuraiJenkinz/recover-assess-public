---
phase: 01-foundation-contract-read-only-graph-client
plan: 03
subsystem: testing
tags: [ci, quality-gate, import-linter, architecture, ast, github-actions, uv]

requires:
  - phase: 01-foundation-contract-read-only-graph-client
    provides: "five import-linter contracts in pyproject.toml, ruff TID251 bans, pytest markers (Plan 01-01); GraphClient/allow-list tree the AST bans scan (Plan 01-02)"
provides:
  - "scripts/check.py: stdlib-only single gate (uv lock --check, ruff check, ruff format --check, mypy, lint-imports, pytest) with PASS/FAIL/SKIP table, --fix and --fast"
  - ".github/workflows/ci.yml: windows-latest + ubuntu-latest matrix running the same check.py, uv 0.13.8, actions pinned to commit SHAs, permissions contents: read"
  - "tests/support/import_violations.py: seven deliberate-violation cases run against the real, unmodified contracts on a tmp copy of the committed tree"
  - "tests/unit/test_source_bans.py: AST bans for network imports, write-verb attribute calls and dynamic imports"
affects: [01-04, 01-06, 01-11, phase-02-collectors, every later plan that runs scripts/check.py]

actuals:
  tokens: 6300
  tasks: 2
  commits: 3
plan_head_before: 503be26e0ce391dc251d469ef95b6b093321f8f8
plan_head_after: 9e8dc7e974441e529436793848d1fb11cc442f7a

tech-stack:
  added: []
  patterns:
    - "One gate script for local and CI so the two cannot drift; every step runs after a failure and the exit code is exact"
    - "Violation fixtures run lint-imports --config <real pyproject.toml> --no-cache on a git-archive-HEAD tmp copy, never editing contracts"
    - "Test naming rule: whole_tree in a test name marks a working-tree-reading test, deselected by in-wave verifies with -k 'not whole_tree'"
    - "AST checker exposed as find_offenders(relative_path, source_text) so negative cases run on in-memory strings"

key-files:
  created:
    - scripts/check.py
    - .github/workflows/ci.yml
    - tests/unit/test_check_script.py
    - tests/support/import_violations.py
    - tests/unit/test_import_contracts.py
    - tests/unit/test_source_bans.py
  modified: []

key-decisions:
  - "check.py main() takes optional keyword-only runner, environ and uv_available so tests inject a fake runner; main(argv) alone behaves as specified"
  - "Provider modules may import httpx2 only; any other network library (requests, aiohttp, urllib3, socket) is an AST offender everywhere, including core/graph.py"
  - "The AST ban also flags a bare import_module(...) call, a superset of the specified importlib.import_module and __import__"
  - "Actions SHAs resolved with git ls-remote: checkout v7.0.1 = 3d3c42e5..., setup-uv v10.3.3 = 68559e99... (both lightweight tags, so the plain entry is the commit)"

patterns-established:
  - "Gate step order is pinned by a test; reordering or dropping a step fails test_check_script.py"
  - "Contracts proven by fixtures: each architecture rule has a violation case that must turn its named contract BROKEN"

requirements-completed: [FND-02]

coverage:
  - id: D1
    description: "scripts/check.py runs the six gate steps in order, reports every step, exits 1 on any single failure, supports --fix and --fast"
    requirement: FND-02
    verification:
      - kind: unit
        ref: "tests/unit/test_check_script.py (20 tests incl. test_every_single_failure_position_gives_exit_one)"
        status: pass
      - kind: other
        ref: "uv run python scripts/check.py -> all six steps PASS, exit 0"
        status: pass
    human_judgment: false
  - id: D2
    description: "CI workflow runs the same check.py on windows-latest and ubuntu-latest with SHA-pinned actions and read-only permissions"
    requirement: FND-02
    verification:
      - kind: unit
        ref: "tests/unit/test_check_script.py#test_workflow_* (shape only, parsed with yaml.safe_load)"
        status: pass
    human_judgment: true
    rationale: "No git remote exists, so the workflow has never run on a GitHub runner; Windows runner timing (RESEARCH A1) and action behaviour are unverified until a remote is added"
  - id: D3
    description: "Seven deliberate violations each turn their named import-linter contract BROKEN; the unmodified copy exits 0"
    requirement: FND-02
    verification:
      - kind: unit
        ref: "tests/unit/test_import_contracts.py (7 parametrised cases, test_control_copy_kept, test_whole_tree_untouched_by_violation_run)"
        status: pass
    human_judgment: false
  - id: D4
    description: "AST bans: httpx2 only in core/graph.py or core/providers/**, no post/put/patch/delete calls, no dynamic imports"
    requirement: FND-02
    verification:
      - kind: unit
        ref: "tests/unit/test_source_bans.py (12 negative, 4 positive in-memory cases, test_whole_tree_has_no_offenders)"
        status: pass
    human_judgment: false

duration: 14min
completed: 2026-11-16
status: complete
---

# Phase 1 Plan 03: Single quality gate, CI workflow and architecture-contract proof Summary

**One stdlib script (scripts/check.py) is the local and CI gate for lock, lint, format, types, import contracts and tests; seven deliberate violations are proven to turn the real import-linter contracts red, backed by AST bans for what import-linter cannot see.**

## Performance

- **Duration:** about 14 min (start time not captured at launch; approximate)
- **Completed:** 2026-11-16T00:12Z
- **Tasks:** 2
- **Files created:** 6, none modified

## Accomplishments

- `scripts/check.py` runs uv-lock-check, ruff-check, ruff-format, mypy, import-contracts, pytest in order, never stops early, prints an aligned STEP / STATUS / SECONDS / DETAIL table, and exits 1 on any failure. uv missing is SKIP locally and FAIL when `CI` is set. `--fix` prepends the two ruff writers; `--fast` adds `-m "not slow"`.
- `.github/workflows/ci.yml` runs that script on a windows-latest and ubuntu-latest matrix after `uv python install` and `uv sync --locked`, with uv 0.13.8, both actions pinned to 40-hex commit SHAs with tag comments, and top-level `permissions: contents: read`.
- `tests/support/import_violations.py` snapshots the committed `src/recover_assess` tree with `git archive HEAD`, adds one forbidden module, and runs `lint-imports --config <real pyproject.toml> --no-cache` in the tmp copy. All seven cases break the expected contract; the control copy keeps all five.
- `tests/unit/test_source_bans.py` bans network-library imports outside the allowed modules, write-verb attribute calls and dynamic imports, and the real tree has zero offenders.

## Join gate evidence

This plan ran on a quiet tree (sequential execution, no sibling plans in flight), so the wave-2 join gate was run here:

`uv run python scripts/check.py` exited 0:

| Step | Status |
|------|--------|
| uv-lock-check | PASS |
| ruff-check | PASS |
| ruff-format | PASS |
| mypy | PASS |
| import-contracts | PASS (5 contracts kept, 0 broken) |
| pytest | PASS (140 passed) |

Siblings 01-04 and 01-11 were not yet merged at that point, so the gate must be re-run after they land.

## Task Commits

1. **Task 1 RED: check.py and CI shape tests** - `27c5a62` (test)
2. **Task 1 GREEN: check.py and ci.yml** - `c2fa252` (feat)
3. **Task 2: violation fixtures, contract tests, AST bans** - `9e8dc7e` (test)

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

## Files Created/Modified

- `scripts/check.py` - the single gate (STEP_NAMES, Step, StepResult, build_steps, run_steps, render_table, main)
- `.github/workflows/ci.yml` - CI matrix calling check.py
- `tests/unit/test_check_script.py` - gate behaviour and workflow shape tests
- `tests/support/import_violations.py` - ViolationCase, CASES, snapshot_committed_src, run_lint_imports_on_copy
- `tests/unit/test_import_contracts.py` - violation, control and real-tree-untouched tests (slow)
- `tests/unit/test_source_bans.py` - AST checker and its tests

## Decisions Made

- check.py `main()` accepts optional keyword-only `runner`, `environ`, `uv_available` for injection; the specified `main(argv)` call is unchanged.
- Provider modules may import httpx2 only. `requests`, `aiohttp`, `urllib3`, `socket` are offenders in every module, including `core/graph.py`.
- The dynamic-import ban also catches a bare `import_module(...)` call.
- `pyproject.toml` is untouched: contracts and ruff config were used unmodified (D-04, prohibition on weakening the gate).

## Deviations from Plan

None - plan executed exactly as written. Two lint/type fixes during Task 1 GREEN (a redundant `noqa: S603` that RUF100 flagged because scripts already ignore S603 per file, and a tuple annotation for mypy) were corrections to my own new code, not gate weakening.

## TDD Gate Compliance

- Task 1: RED `27c5a62` (tests errored at fixture load because `scripts/check.py` did not exist, which is the expected RED for a brand-new script; no `gsd_run check tdd-red-evidence` record was produced), GREEN `c2fa252`. No refactor commit.
- Task 2: tests-only task. It verifies contracts that Plan 01-01 already wrote, so there is no production code to turn green and no separate `feat` commit; the tests passed on first run and were separately confirmed to detect violations by printing the BROKEN lines for cases 3 and 5 and the control.

## Issues Encountered

None.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None. The CI workflow is the only new trust surface and is covered by T-01-08 (SHA pins, read-only permissions, asserted by tests).

## Not exercised here

- **CI workflow has never run.** There is no git remote, so `.github/workflows/ci.yml` is committed and shape-tested only. RESEARCH assumption A1 (Windows runner time with subprocess fixtures) is unverified; `--fast` and the `slow` marker are the mitigation.

## User Setup Required

None - no external service configuration required. A GitHub remote and branch protection remain a user action (CONTEXT Deferred Ideas).

## Next Phase Readiness

- Later plans can rely on `uv run python scripts/check.py` as the gate. Wave 3 plans should re-run it after 01-04 and 01-11 merge.
- Any new module that needs a network library must live in `core/graph.py` or `core/providers/**` or the contracts and `test_whole_tree_has_no_offenders` will fail.

## Self-Check: PASSED

- All six files exist on disk.
- Commits `27c5a62`, `c2fa252`, `9e8dc7e` are ancestors of HEAD.
- Scoped verifies pass; full `scripts/check.py` exits 0.

---
*Phase: 01-foundation-contract-read-only-graph-client*
*Completed: 2026-11-16*
