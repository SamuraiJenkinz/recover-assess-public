---
phase: 01-foundation-contract-read-only-graph-client
plan: 11
subsystem: contract
tags: [contract, schema, pydantic, json-schema, walking-skeleton]

requires:
  - phase: 01-foundation-contract-read-only-graph-client
    provides: "core.errors ERROR_CODE_PATTERN (plan 01-01), .gitattributes LF rules, ruff scripts/* ignores"
provides:
  - "Contract base model and shared scalar types (Share, UtcDatetime, NonNegInt, round3, round4)"
  - "Provisional v1.0 fact-sheet envelope models (FactSheet, GraphStats, WarningEntry)"
  - "PUBLISHED registry with deterministic schema rendering"
  - "scripts/gen_schemas.py with --check and --root"
  - "schemas/fact_sheet.schema.json generated from the models"
affects: [01-05, 01-09, 01-12]

actuals:
  tokens: 5700
  tasks: 2
  commits: 2

plan_head_before: 3c6fd70c99642450a0c68c510d693abf69e4a7c3
plan_head_after: ad6c36418ba35492ffc72d889f002d827abbf9a1

tech-stack:
  added: []
  patterns:
    - "Published models: no field defaults, extra forbid, frozen, every key required in the serialization-mode schema"
    - "Schema drift compared on parsed JSON, never on text"
    - "regex_engine python-re on Contract so the anchored error-code pattern compiles"

key-files:
  created:
    - src/recover_assess/core/models/common.py
    - src/recover_assess/core/models/fact_sheet.py
    - src/recover_assess/core/models/registry.py
    - scripts/gen_schemas.py
    - schemas/fact_sheet.schema.json
    - tests/unit/test_fact_sheet_schema.py
  modified: []

key-decisions:
  - "Contract sets regex_engine=python-re because pydantic's default Rust engine rejects the \\A...\\Z anchors in ERROR_CODE_PATTERN"
  - "Envelope status is a closed set complete, partial, failed; schema_version is pinned to the literal 1.0"
  - "gen_schemas.py treats unparseable JSON on disk as drift as well as a missing file"

patterns-established:
  - "_envelope_fact_sheet(**overrides) is the single place envelope FactSheets are built in tests"
  - "Structure-lint test: every object in the generated schema lists all properties in required and sets additionalProperties false"

requirements-completed: [FND-04]

coverage:
  - id: D1
    description: "Envelope contract models with no defaults, strict extras, frozen, UTC Z datetimes and constrained warning codes"
    requirement: FND-04
    verification:
      - kind: unit
        ref: "tests/unit/test_fact_sheet_schema.py#TestEnvelopeModel"
        status: pass
      - kind: unit
        ref: "tests/unit/test_fact_sheet_schema.py#TestCollectedAt"
        status: pass
      - kind: unit
        ref: "tests/unit/test_fact_sheet_schema.py#TestWarningEntry"
        status: pass
    human_judgment: false
  - id: D2
    description: "Schema generated from the models, deterministic, checked in, guarded by parsed-JSON drift test and --check"
    requirement: FND-04
    verification:
      - kind: unit
        ref: "tests/unit/test_fact_sheet_schema.py#TestDrift"
        status: pass
      - kind: integration
        ref: "uv run python scripts/gen_schemas.py --check"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-11-16
status: complete
---

# Phase 1 Plan 11: Fact-sheet contract pipeline Summary

**Fact-sheet envelope pydantic models generate `schemas/fact_sheet.schema.json` through a deterministic registry and a `gen_schemas.py` script with a parsed-JSON `--check` drift guard.**

## Performance

- **Duration:** about 15 min
- **Completed:** 2026-11-16
- **Tasks:** 2
- **Files created:** 6

## Accomplishments

- `Contract` base (extra forbid, frozen, serialization defaults required) with `Share`, `UtcDatetime`, `NonNegInt`, `round3`, `round4`; published models carry no defaults, so a collector that omits a key fails loudly (D-05).
- `FactSheet` / `GraphStats` / `WarningEntry` envelope: `collected_at` serialises in UTC with trailing Z, warning codes are constrained by `ERROR_CODE_PATTERN` in both the model and the generated schema, `GraphStats` keys are in spec order with `seconds` rounded to 3 dp.
- `registry.py` renders the schema byte-stably (indent 2, ensure_ascii False, LF, one trailing newline, field order); `gen_schemas.py --check` compares parsed JSON, so CRLF checkouts are not drift while any changed key or value is.
- 56 tests cover model behaviour, determinism, drift (CRLF, mutated value, removed key), `--check` exit codes via subprocess, and jsonschema validation of dumped documents.

## Task Commits

1. **Task 1: Contract base types and the fact-sheet envelope models** - `6544003` (feat)
2. **Task 2: Registry, generator and the checked-in schema with a parsed-JSON drift test** - `ad6c364` (feat)

**Plan metadata:** recorded in the following docs commit.

_TDD note: tests were written first for both tasks. For Task 1 the observed RED was a collection error (`ModuleNotFoundError` for the not-yet-existing modules), not a failing assertion, so it is not strict RED evidence in the tdd.md sense, and the test and implementation were committed together per task as the plan's commit protocol states (one commit per task). `workflow.tdd_mode` gating was not requested by the dispatcher._

## Files Created/Modified

- `src/recover_assess/core/models/common.py` - Contract base and scalar types
- `src/recover_assess/core/models/fact_sheet.py` - provisional v1.0 envelope models
- `src/recover_assess/core/models/registry.py` - PUBLISHED, build_schema, render_schema, schema_path
- `scripts/gen_schemas.py` - generator CLI with `--check` and `--root`
- `schemas/fact_sheet.schema.json` - generated schema (never hand-edited)
- `tests/unit/test_fact_sheet_schema.py` - envelope, registry, drift, generator and validation tests

## Decisions Made

- `regex_engine="python-re"` on `Contract`: the default Rust regex engine rejects `\Z` in `ERROR_CODE_PATTERN` ("unrecognized escape sequence"). Python `re` handles the anchors, matches the plan's requirement that the model and the schema share one pattern, and `jsonschema` evaluates the same pattern with Python `re`.
- Unparseable or unreadable schema files count as drift in `--check`, same as missing files.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Rust regex engine cannot compile ERROR_CODE_PATTERN**
- **Found during:** Task 1 (WarningEntry model)
- **Issue:** pydantic's default regex engine raised a SchemaError on the `\Z` anchor, so `WarningEntry` could not be defined.
- **Fix:** set `regex_engine="python-re"` in the `Contract` config; the emitted schema `pattern` is unchanged.
- **Files modified:** `src/recover_assess/core/models/common.py`
- **Verification:** `TestWarningEntry` (including a trailing-newline rejection case) and `test_warning_code_pattern_is_enforced_by_the_schema` pass.
- **Commit:** `6544003`

**Total deviations:** 1 auto-fixed (1 blocking). **Impact:** none on the contract; one config key added.

## Issues Encountered

- A Python heredoc used to patch the test file was rejected by the shell; the test additions were made with the Edit tool instead. No effect on the result.

## Known Stubs

None.

## Threat Flags

None. T-01-31 mitigated: schema is only written by `scripts/gen_schemas.py`, drift is checked on parsed JSON, rendering is byte-identical across runs, LF is enforced by `.gitattributes` and the generator's `newline="\n"`. T-01-SC: no new packages (`uv sync --locked`, `jsonschema` already in the dev group).

## Verification

- `uv run python scripts/gen_schemas.py --check` prints `OK fact_sheet`, exit 0
- `uv run pytest tests/unit/test_fact_sheet_schema.py -x -q`: 56 passed
- scoped ruff check, ruff format --check and mypy: clean
- `grep -c "json_schema_serialization_defaults_required=True" common.py` = 1; `grep -c '"additionalProperties": false' schemas/fact_sheet.schema.json` = 3
- `uv run --frozen python scripts/check.py`: all six steps PASS (257 tests)

## Next Phase Readiness

Plan 01-05 can expand `FactSheet` in place, rebuild `_envelope_fact_sheet` on a full not-run fixture, regenerate the schema in the same commit, and switch the generator write to the FND-06 atomic writer.

## Self-Check: PASSED

- All six created files exist on disk.
- Commits `6544003` and `ad6c364` are ancestors of HEAD.
