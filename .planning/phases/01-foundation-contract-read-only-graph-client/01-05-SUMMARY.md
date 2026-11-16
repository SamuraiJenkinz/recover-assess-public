---
phase: 01-foundation-contract-read-only-graph-client
plan: 05
subsystem: contract
tags: [contract, schema, pydantic, unknown-vs-zero, fact-sheet]

requires:
  - phase: 01-foundation-contract-read-only-graph-client
    provides: "Contract base, Share/UtcDatetime/NonNegInt, registry and gen_schemas.py (01-11); atomic_write_text and repo_scan.scan_text (01-12); ERROR_CODE_PATTERN (01-01)"
provides:
  - "Status vocabulary: SectionStatus, ExposureStatus, UNKNOWN_STATUSES, SectionState and the FND-05 literals in models/common.py"
  - "Full provisional v1.0 FactSheet (privacy, collect_limits, sections, input, site, libraries, lists, exposure_total, ownership, sample_candidates, sam, graph_stats, warnings), no field defaults"
  - "Unknown-vs-zero model validators on FactSheet, Library, LibraryExposure and ExposureTotal"
  - "schemas/fact_sheet.schema.json regenerated from the full models via the atomic writer"
  - "Neutral fixtures example_complete.json and example_not_run.json"
affects: [01-07, 01-08, 02, 04, 05, 06]

actuals:
  tokens: 21000
  tasks: 2
  commits: 2

plan_head_before: 2619d1012a2e7c9e3d2b532c97fbfa4c9c799a29
plan_head_after: 7a4b8978ede03f6094ff80653ba363829efece5c

tech-stack:
  added: []
  patterns:
    - "Unknown is never zero: a could-not-look status forces null counts or empty lists, enforced by model_validator(mode=after)"
    - "Validation messages name the section and rule only; Contract sets hide_input_in_errors so submitted values never reach error text"
    - "Test FactSheets are built from the all-not-run fixture; no test constructs an envelope-only sheet"
    - "Shared _ExposureCounts base gives LibraryExposure and ExposureTotal the same eight counts and one null-under-unknown rule"

key-files:
  created:
    - tests/unit/test_fact_sheet_model.py
    - tests/fixtures/fact_sheet/example_complete.json
    - tests/fixtures/fact_sheet/example_not_run.json
  modified:
    - src/recover_assess/core/models/common.py
    - src/recover_assess/core/models/fact_sheet.py
    - scripts/gen_schemas.py
    - schemas/fact_sheet.schema.json
    - tests/unit/test_fact_sheet_schema.py

key-decisions:
  - "Contract gains hide_input_in_errors=True so validation errors never echo submitted evidence values (satisfies the no-values error requirement for every model, not just the new validators)"
  - "When sections.exposure is a could-not-look status, exposure_total must hold no numbers and every library.exposure must itself be a could-not-look status; the plan listed only the totals, this closes the per-library gap"
  - "ErrorCodeStr moved to models/common.py so SectionState.reason and WarningEntry.code share one definition"
  - "Fixture collect_limits use the Build Spec defaults (50000, 500, 200, 10, sample_size 15)"

patterns-established:
  - "Vocabulary names (SectionStatus, ExposureStatus, Coverage fields) remain provisional until Phase 6 per D-06 and flagged assumption FA-3"

requirements-completed: [FND-04, FND-05]

coverage:
  - id: D1
    description: "Full provisional v1.0 FactSheet and status/coverage vocabulary with every key required"
    requirement: FND-04
    verification:
      - kind: unit
        ref: "tests/unit/test_fact_sheet_model.py#TestBaselines"
        status: pass
      - kind: unit
        ref: "tests/unit/test_fact_sheet_schema.py#TestFnd05Vocabulary"
        status: pass
    human_judgment: false
  - id: D2
    description: "Unknown is never zero: numbers or non-empty lists under a could-not-look status are rejected for every section and for exposure counts"
    requirement: FND-05
    verification:
      - kind: unit
        ref: "tests/unit/test_fact_sheet_model.py#TestExposure"
        status: pass
      - kind: unit
        ref: "tests/unit/test_fact_sheet_model.py#TestOwnership"
        status: pass
      - kind: unit
        ref: "tests/unit/test_fact_sheet_model.py#TestLibrariesAndListsSections"
        status: pass
    human_judgment: false
  - id: D3
    description: "Regenerated schema is structurally strict (all properties required, no additional properties), written atomically and proven against complete and all-unknown fixtures"
    requirement: FND-04
    verification:
      - kind: unit
        ref: "tests/unit/test_fact_sheet_schema.py#TestSchemaStructure"
        status: pass
      - kind: unit
        ref: "tests/unit/test_fact_sheet_schema.py#TestFixtures"
        status: pass
      - kind: integration
        ref: "uv run python scripts/gen_schemas.py --check"
        status: pass
    human_judgment: false
  - id: D4
    description: "Vocabulary names are the research proposal and need developer review before Phase 4/5 collectors populate them (FA-3)"
    requirement: FND-05
    verification: []
    human_judgment: true
    rationale: "Naming of status and coverage fields is a design judgment no test asserts; D-06 allows in-place renames until the Phase 6 freeze"

duration: 35min
completed: 2026-11-16
status: complete
---

# Phase 1 Plan 05: Full v1.0 fact-sheet contract Summary

**The envelope-only FactSheet is now the full provisional v1.0 contract: per-section status plus model validators make unknown evidence (not_run, unavailable, forbidden, failed, unknown) impossible to record as a measured zero, and the checked-in schema is regenerated through the atomic writer and structure-linted.**

## Performance

- **Duration:** about 35 min
- **Completed:** 2026-11-16
- **Tasks:** 2
- **Files:** 3 created, 5 modified

## Accomplishments

- Vocabulary in `models/common.py`: `SectionStatus` (7 values), `ExposureStatus` (6, including `unknown` for COL-09), `UNKNOWN_STATUSES`, `SectionState(status, reason)` with the reason constrained to stable error codes, plus the truncation, path, contributor, column, pattern, activity, owner and site-kind literals.
- `models/fact_sheet.py` holds the complete tree in the behaviour-list field order. Library carries coverage, `truncated_reason`, `path_unresolved`, `hash_coverage` and `last_activity_sources`; Ownership carries `owners_source`; exposure carries eight counts under a status.
- Invariants: libraries, lists, sample candidates, site, sam, exposure totals and ownership numbers are null or empty under a could-not-look section status; `site` null requires such a status; library `truncated` is true exactly when `truncated_reason` is set; a library or total exposure status in the could-not-look set requires every count null. Error text names the section and rule, never the value.
- `gen_schemas.py` now writes through `atomic_write_text`; `schemas/fact_sheet.schema.json` regenerated (never hand-edited) and `--check` prints `OK fact_sheet`.
- Neutral fixtures: `example_complete.json` (one library, one list, canonical dump of the models) and `example_not_run.json` (every section not_run). Both validate against the model and schema, the complete one round-trips byte for byte, removing any top-level key from the not-run one fails the schema, and both pass the client-data scan.
- `test_fact_sheet_schema.py` is rebuilt on the not-run fixture (`_envelope_fact_sheet` loads it), and gains structure-lint, FND-05 presence, fixture, and atomic-writer tests. No `FactSheet(` construction remains in the tree.
- Gate: `uv run --frozen python scripts/check.py` exits 0 (707 tests); `gen_schemas.py --check` OK.

## Task Commits

1. **Task 1: Full provisional v1.0 FactSheet with status/coverage vocabulary and the unknown-vs-zero invariant** - `28b62a5` (feat)
2. **Task 2: Regenerate the schema atomically, lint its structure, prove neutral fixtures validate** - `7a4b897` (feat)

**Plan metadata:** recorded in the following docs commit.

_TDD note: tests were written first for both tasks. For Task 1 the observed RED was a collection `ImportError` (the new model names did not exist yet), not a failing assertion, so it is not strict RED evidence in the tdd.md sense; test and implementation were committed together per task as the plan's commit protocol states. `workflow.tdd_mode` gating was not requested by the dispatcher._

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Library-level exposure under an unknown exposure section**
- **Found during:** Task 1
- **Issue:** The plan only forced `exposure_total` to null under a could-not-look `sections.exposure`; a library could still report measured exposure counts, which would be a number under an unknown section.
- **Fix:** `FactSheet` also rejects any library whose `exposure.status` is not a could-not-look value while `sections.exposure` is one. Test added.
- **Files modified:** src/recover_assess/core/models/fact_sheet.py, tests/unit/test_fact_sheet_model.py
- **Commit:** 28b62a5

**2. [Rule 2 - Missing critical functionality] Submitted values in validation errors**
- **Found during:** Task 1
- **Issue:** Pydantic prints `input_value=` in error text by default, which would put evidence values into messages despite the "never include submitted values" behaviour.
- **Fix:** `hide_input_in_errors=True` on `Contract`. Tests assert a distinctive count and a wrong-type input never appear in `str(error)`.
- **Files modified:** src/recover_assess/core/models/common.py
- **Commit:** 28b62a5

**Total deviations:** 2 auto-fixed (both Rule 2). **Impact:** stricter than the plan, no scope or schema-shape change.

## Issues Encountered

None blocking. Two shell-escaping slips while scripting edits (backslash sequences halved on the Windows command line) were caught by ruff and tests and fixed with direct edits before commit.

## Known Stubs

None.

## Threat Flags

None. No new network surface; the model layer adds only validation.

## Next Phase Readiness

- Wave-4 join: `scripts/check.py` is green on this tree including the real-tree repo scan over the new fixtures; Plan 01-07 can proceed.
- FA-3 stays open: review the status and coverage vocabulary names before Phase 4/5 collectors populate them (D-06 allows in-place renames until the Phase 6 freeze).
- COL-09 handoff: Phase 5 decides which Graph outcomes map to `unknown`, `forbidden` and `partial_caller_scoped`; the model already forbids a number under any could-not-look value.

## Self-Check: PASSED

- Created files exist: tests/unit/test_fact_sheet_model.py, tests/fixtures/fact_sheet/example_complete.json, tests/fixtures/fact_sheet/example_not_run.json
- Commits 28b62a5 and 7a4b897 are on the branch; `git rev-list --count` from plan_head_before to HEAD is 2
- Acceptance greps: UNKNOWN_STATUSES in fact_sheet.py (8), "unknown" in common.py (2), atomic_write_text in gen_schemas.py (2), "truncated_reason" in the schema (2)
- `scripts/check.py` exit 0; `gen_schemas.py --check` prints `OK fact_sheet`
