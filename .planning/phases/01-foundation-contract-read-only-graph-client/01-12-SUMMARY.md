---
phase: 01-foundation-contract-read-only-graph-client
plan: 12
subsystem: output-and-repo-guard
tags: [atomic-write, repo-guard, portability, sdist, windows]

requires:
  - phase: 01-foundation-contract-read-only-graph-client
    provides: "core.errors.OutputError and core.clock.SYSTEM_CLOCK (01-01), packaged graph_allowlist.yaml (01-02), schemas/fact_sheet.schema.json (01-11), uv_build source-include/source-exclude and slow/needs_uv markers (01-01)"
provides:
  - "core/output.py: atomic_write_bytes/text/json with bounded Windows lock retry, and sweep_orphans"
  - "tests/support/repo_scan.py: generic client-data scanner (Finding, RULES, scan_text, load_private_terms, shippable_files, scan_tree)"
  - "test_whole_tree_scan_clean running inside the single gate"
  - "sdist content test proving the schema and allow-list ship and planning docs, drafts and secrets do not"
affects: [01-05, 01-10]

actuals:
  tokens: 7200
  tasks: 2
  commits: 4

plan_head_before: b654e4e35e11c7ec8e2a6f5d9fb59d11147e759e
plan_head_after: 870f49e86f3bede9e2b093c9ebfb2bb3fe742ba9

tech-stack:
  added: []
  patterns:
    - "Temp file .{name}.tmp-{pid}-{counter} in the target directory, fsync, replace; PermissionError retried with injected sleep/rng; temp always unlinked in finally"
    - "Generic in-repo scan rules with an external private-terms file; findings carry no excerpt"
    - "Sensitive-shaped test strings built by runtime concatenation so the test files stay clean under their own scan"

key-files:
  created:
    - src/recover_assess/core/output.py
    - tests/unit/test_atomic_write.py
    - tests/support/repo_scan.py
    - tests/unit/test_repo_scan.py
    - tests/unit/test_sdist_contents.py
  modified: []

key-decisions:
  - "Non-PermissionError OSError during write, fsync or replace is wrapped in OutputError immediately (no retry); only PermissionError is retried"
  - "shippable_files returns sorted repository-relative POSIX strings and drops index entries whose file no longer exists"
  - "An env var set to the empty string is treated as unset for the private-terms file; a non-empty missing path raises FileNotFoundError"
  - "The retry options are a TypedDict (Unpack) on the text/json wrappers so they stay type-checked under mypy strict"

patterns-established:
  - "Atomic writer is the only way any output file except run.jsonl is written (D-14)"
  - "Scan rule allow-lists are code predicates (synthetic tenant label, example domains, single-repeated-hex-digit GUID groups), not data files"

requirements-completed: [FND-06, FND-07]

duration: 25min
completed: 2026-11-16
status: complete
---

# Phase 1 Plan 12: Atomic Writer and Client-Data Guard Summary

**Atomic temp-fsync-replace writer with bounded jittered Windows lock retry, plus a generic git-enumerated repo scanner and sdist content test that keep client data out of the shippable tree**

## Performance

- **Duration:** about 25 min
- **Completed:** 2026-11-16T00:38Z
- **Tasks:** 2
- **Files created:** 5 (no existing file modified)

## Accomplishments

- `atomic_write_bytes/text/json` write `.{name}.tmp-{pid}-{counter}` beside the target, flush and fsync it, then replace. `PermissionError` on replace is retried with 50-250 ms jittered waits from an injected sleep (default `SYSTEM_CLOCK.sleep_sync`) up to `attempts`; persistent failure raises `OutputError`; the temp file is always removed and the previous target is never disturbed. `sweep_orphans` removes stale temp files from a killed process.
- The Windows held-handle tests ran on this machine (not skipped): a held target exhausts the retries with `OutputError`, and releasing the handle from a thread mid-retry lets the write succeed.
- `tests/support/repo_scan.py` enforces six generic rules (other SharePoint tenants, non-example email domains, non-synthetic GUIDs, JWT shape, Bearer token shape, `apis.*` gateway hosts) plus the optional external private-terms file (`RECOVER_ASSESS_PRIVATE_TERMS_FILE`); binary shippable files are themselves findings.
- `test_whole_tree_scan_clean` scans the real shippable tree (58 files, including untracked ones) and is clean; it runs inside `scripts/check.py`.
- `test_sdist_contents` builds the sdist with `uv build --sdist` and proves the schema and the packaged allow-list ship while `.planning`, `.claude`, `docs/private`, the root drafts, `*.pem`, `*.pfx` and `recover-assess.yaml` do not.

## TDD Gate Compliance

Both tasks followed RED, GREEN with no refactor commit (none needed).

- **Task 1 RED** (`e6f813a`): 15 tests against a do-nothing stub of `output.py`; all 15 failed on assertions (wrong bytes, DID NOT RAISE, missing files). Semantic assessment: each failure is the planned behaviour being absent, not an import, syntax or fixture fault.
- **Task 2 RED** (`2e6715f`): 14 of 19 scanner tests failed on assertions against a stub `repo_scan.py`; the 5 passing ones are the negative cases ("no findings") that a stub satisfies. The two sdist tests passed at RED because they characterise packaging configured by Plans 01-01, 01-02 and 01-11; they test existing behaviour, not new code. The real-tree test was deselected in-wave per the plan and passed at the join.

## Task Commits

1. **Task 1 RED: atomic writer tests** - `e6f813a` (test)
2. **Task 1 GREEN: atomic writer** - `3151d31` (feat)
3. **Task 2 RED: scanner and sdist tests** - `2e6715f` (test)
4. **Task 2 GREEN: scanner** - `870f49e` (feat)

## Files Created/Modified

- `src/recover_assess/core/output.py` - atomic writers and `sweep_orphans`
- `tests/unit/test_atomic_write.py` - 15 tests: retry, interruption, empty, ordering, idempotency, temp naming, 4x5 concurrent writers, sweep, Windows held handle
- `tests/support/repo_scan.py` - scanner rules and tree enumeration
- `tests/unit/test_repo_scan.py` - 20 tests including `test_whole_tree_scan_clean`
- `tests/unit/test_sdist_contents.py` - slow, needs_uv sdist membership tests

## Decisions Made

See `key-decisions` above. The scanner contains no client-specific term (FND-07 prohibition): every rule is generic and client terms can only arrive from the external file.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] RED needed stub modules**
- **Found during:** Task 1 and Task 2 RED
- **Issue:** The tests import modules that did not exist, which would give a collection error (INVALID_RED) rather than a failing assertion.
- **Fix:** Committed do-nothing stubs of `output.py` and `repo_scan.py` with the RED tests, replaced by the real implementation in the GREEN commits.
- **Verification:** RED runs showed assertion failures only.
- **Committed in:** `e6f813a`, `2e6715f`

**2. [Rule 1 - Bug] Test-side lint and typing fixes**
- **Found during:** Task 1 GREEN
- **Issue:** Tests patched `output.os.fsync` (mypy: module does not export `os`) and used `random.Random(7)` (ruff S311).
- **Fix:** Patch `os.fsync` directly; add a justified `noqa: S311` for the deterministic test jitter.
- **Files modified:** `tests/unit/test_atomic_write.py`
- **Committed in:** `3151d31`

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug). **Impact:** none on scope.

## Issues Encountered

None. The wave-2 precondition (`scripts/check.py` exits 0) held at the start, and the whole gate exits 0 at the end (566 passed).

## Authentication Gates

None.

## Known Stubs

None. (The RED-phase stubs were replaced in the GREEN commits.)

## Threat Flags

None. `core/output.py` writes only to a caller-supplied path whose parent must already exist and puts only the file name (never the full path) in error messages.

## User Setup Required

None - no external service configuration required. Optional: set `RECOVER_ASSESS_PRIVATE_TERMS_FILE` to an external file of client terms (one per line) on a developer machine or private CI job to enable the client-term check.

## Next Phase Readiness

- Plan 01-05 can call `atomic_write_text` from `scripts/gen_schemas.py` and scan its fixtures with `scan_text`.
- Plan 01-10 re-runs the repo scan over its new test files through `test_whole_tree_scan_clean`.

---
*Phase: 01-foundation-contract-read-only-graph-client*
*Completed: 2026-11-16*

## Self-Check: PASSED

All five created files exist; commits `e6f813a`, `3151d31`, `2e6715f`, `870f49e` are on the phase branch; `uv run --frozen python scripts/check.py` exits 0.
