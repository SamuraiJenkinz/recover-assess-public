---
phase: 01-foundation-contract-read-only-graph-client
plan: 02
subsystem: api
tags: [graph, httpx2, read-only, allow-list, jsonl, run-log, tracer, walking-skeleton, pydantic]

requires:
  - phase: 01-foundation-contract-read-only-graph-client
    provides: "core.errors exception tree and error codes, core.clock injectable Clock, package skeleton and import-linter contracts (Plan 01-01)"
provides:
  - "ReadOnlyPolicy: pure first guard (verb rule, absolute-URL canonicalisation, anchored per-segment template match) with no HTTP import"
  - "Packaged allow-list core/graph_allowlist.yaml (one entry, site_by_id) loaded with importlib.resources and yaml.safe_load"
  - "GraphClient/GraphSession over httpx2 with guard_request as an independent request-hook second guard and make_http_client(transport=...) factory"
  - "RunLog: typed JSONL run log with six event types, scrub filter, single-writer lock, repair-on-open and tolerant reader (FND-06 as amended by D-14)"
  - "Test doubles FakeClock and FakeGraph (httpx2.MockTransport), conftest fixtures and hypothesis profiles"
affects: [01-03, 01-04, 01-06, 01-07, 01-08, 01-09, 01-11, 01-12, phase-02-collectors]

actuals:
  tokens: 12700
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Policy before network: GraphClient._send calls ReadOnlyPolicy.check before the token is fetched or anything is sent"
    - "Two independent guards: the policy plus an httpx2 request hook that also stops raw-client calls before any transport"
    - "transport= is passed to httpx2 only when a test supplies it, so production keeps HTTPS_PROXY and NO_PROXY"
    - "Errors re-raised from None with a class-name reason and a path template, never a URL"
    - "Typed closed set of log events with no free-text body field; ts stamped by RunLog from the injected clock under the writer lock"
    - "Append-only stream safety: one write plus flush per line, repair tail on open, tolerant reader"

key-files:
  created:
    - src/recover_assess/core/log.py
    - src/recover_assess/core/graph_policy.py
    - src/recover_assess/core/graph_allowlist.yaml
    - tests/conftest.py
    - tests/fakes/clock.py
    - tests/fakes/fake_graph.py
    - tests/graph/test_walking_skeleton.py
    - tests/unit/test_run_log.py
  modified:
    - src/recover_assess/core/graph.py

key-decisions:
  - "RunLog.emit stamps ts from the injected clock under the writer lock, so event models carry ts as an optional field that callers leave unset and timestamps always follow emission order"
  - "The downloadUrl scrub has an escaped-form pattern so redaction inside an already-serialised JSON string keeps the log line valid JSON"
  - "WarningEvent validates its code with is_error_code in a field_validator, because pydantic's Rust regex engine rejects the Python-flavoured \\A \\Z anchors in ERROR_CODE_PATTERN"
  - "Query values containing downloadurl are refused by the policy (fail closed), following the research prototype"
  - "GraphSession.get re-runs policy.check on a non-2xx response to obtain the template for GraphHttpError, so _send keeps its stable signature and returns the raw response"

patterns-established:
  - "Test fixtures build token-shaped strings at runtime by concatenation; GUIDs use the repeated-digit synthetic form (FND-07 convention)"
  - "Tests use sync helpers for Path reads inside async tests to satisfy ruff ASYNC240"
  - "make_graph_client is an async factory fixture that closes every client at teardown (filterwarnings=error)"

requirements-completed: [GRPH-01, GRPH-07, FND-06]

coverage:
  - id: D1
    description: "One allow-listed GET (/sites/{site-id}) travels policy, client, request hook and MockTransport and writes exactly one typed request line with every required field; bearer token never in run.jsonl"
    requirement: GRPH-07
    verification:
      - kind: unit
        ref: "tests/graph/test_walking_skeleton.py#test_one_get_writes_one_typed_line"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every non-GET verb (including lower-case spellings) and every off-allow-list path raises WriteAttemptError / UrlNotAllowedError before the transport runs and writes no line, both through GraphClient and through the raw httpx2 client (request hook); 10 GETs plus 1 DELETE concurrently reach the transport as 10 GETs"
    requirement: GRPH-01
    verification:
      - kind: unit
        ref: "tests/graph/test_walking_skeleton.py#test_non_get_verbs_never_reach_the_transport"
        status: pass
      - kind: unit
        ref: "tests/graph/test_walking_skeleton.py#test_raw_client_write_verbs_are_refused_by_the_request_hook"
        status: pass
      - kind: unit
        ref: "tests/graph/test_walking_skeleton.py#test_ten_gets_and_one_delete_reach_the_transport_as_ten_gets"
        status: pass
      - kind: unit
        ref: "tests/graph/test_walking_skeleton.py#test_path_off_the_allow_list_is_refused_and_not_logged"
        status: pass
    human_judgment: false
  - id: D3
    description: "Failure paths: non-2xx gives GraphHttpError graph_error_NNN, transport errors give URL-free GraphTransportError (from None), each with exactly one request line; request_id falls back to client-request-id then null"
    requirement: GRPH-07
    verification:
      - kind: unit
        ref: "tests/graph/test_walking_skeleton.py#test_connect_error_becomes_a_url_free_transport_error_with_one_line"
        status: pass
      - kind: unit
        ref: "tests/graph/test_walking_skeleton.py#test_read_timeout_is_flagged_as_a_timeout"
        status: pass
      - kind: unit
        ref: "tests/graph/test_walking_skeleton.py#test_request_id_falls_back_to_client_request_id_then_null"
        status: pass
    human_judgment: false
  - id: D4
    description: "make_http_client keeps env proxies unless a transport is supplied, follow_redirects False, HTTP/2 off, no verify argument"
    requirement: GRPH-01
    verification:
      - kind: unit
        ref: "tests/graph/test_walking_skeleton.py#test_make_http_client_keeps_env_proxies_unless_a_transport_is_given"
        status: pass
    human_judgment: false
  - id: D5
    description: "run.jsonl is append-only, ordered, flushed per line, never interleaved under 50 concurrent emits, and survives an interrupted append: repair-on-open, tolerant reader, corruption raises OutputError, 64 KiB block boundary"
    requirement: FND-06
    verification:
      - kind: unit
        ref: "tests/unit/test_run_log.py#test_opening_a_log_truncates_the_fragment_and_the_next_emit_is_clean"
        status: pass
      - kind: unit
        ref: "tests/unit/test_run_log.py#test_fifty_concurrent_emits_never_interleave"
        status: pass
      - kind: unit
        ref: "tests/unit/test_run_log.py#test_a_fragment_after_a_large_prefix_is_removed_exactly"
        status: pass
      - kind: unit
        ref: "tests/unit/test_run_log.py#test_a_corrupt_terminated_middle_line_is_an_error_not_an_interruption"
        status: pass
    human_judgment: false
  - id: D6
    description: "Scrub filter redacts bearer tokens, JWT-shaped strings, signed-URL parameters and downloadUrl members and keeps a serialised line valid JSON"
    requirement: GRPH-07
    verification:
      - kind: unit
        ref: "tests/unit/test_run_log.py#test_scrub_redacts_tokens_signed_urls_and_download_urls"
        status: pass
      - kind: unit
        ref: "tests/unit/test_run_log.py#test_scrub_keeps_a_serialised_line_valid_json"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-11-16
status: complete
commits: 3
plan_head_before: c5b3ea7d04fb5f103b8bbeecad6e94e50428a5e4
plan_head_after: 5a5e505d7307c0880301c99414dff38ab52965f3
---

# Phase 1 Plan 02: Walking Skeleton Summary

**Read-only Graph client slice on httpx2: a pure allow-list policy plus an independent request-hook guard in front of MockTransport, writing scrubbed typed run.jsonl lines that survive an interrupted append**

## Performance

- **Duration:** 5 min (measured from the recorded start to the last task commit)
- **Started:** 2026-11-15T23:58:00Z (approximate; start epoch recorded at executor start)
- **Completed:** 2026-11-16T00:07:35Z
- **Tasks:** 2 of 2 (Task 1 is the phase tracer, Task 2 is TDD)
- **Files modified:** 9 (8 created, 1 modified); about 12.7K tokens of diff (chars/4)

## Accomplishments

- The tracer slice works end to end: `GraphSession.get` goes through `ReadOnlyPolicy.check`, then the token source, then `httpx2` with the request hook, then `MockTransport`, and writes exactly one `request` line carrying ts, level, event, site, method, template, status, duration_ms, retry and request_id.
- Write attempts cannot reach a transport: every verb other than GET and every off-list path is refused by the policy, and the request hook independently refuses the same things on the raw client, including every POST (so `POST /v1.0/$batch` stays refused until Plan 01-06 adds the hook's own body check).
- `run.jsonl` is safe against interruption (FND-06 per D-14): one write plus flush per line, tail repair on open (64 KiB backward scan), a reader that ignores an unterminated tail and raises `OutputError("run_log_corrupt_line: line N")` for a terminated corrupt line.
- Failure paths log one line and raise URL-free errors: `GraphHttpError` (`graph_error_404`), and `GraphTransportError` re-raised `from None` for connect errors and timeouts.
- Full gate green on the whole tree: 94 tests, ruff check and format, mypy strict (28 files), 5 import-linter contracts kept.

## Task Commits

1. **Task 1: End-to-end one allow-listed GET to one typed run.jsonl line (tracer)** - `f10538b` (feat)
2. **Task 2: Harden the slice (TDD)**
   - RED: `57b0463` (test) - 10 tests failed, all in `tests/unit/test_run_log.py`
   - GREEN: `5a5e505` (feat) - 44 of 44 pass in the two plan test files

**Plan metadata:** recorded in the docs commit that follows this summary.

Tracer gate: `human_verify_mode` is `end-of-phase`, the tracer's `<verify>` is automated-only, so the verify was re-run (12 passed) and the run continued without a checkpoint.

## TDD Gate Compliance

- RED (`57b0463`): the failing tests were the run-log behaviours (`read_run_log`, `repair_run_log` and `RunLog.repaired_bytes` did not exist), each failing with `AttributeError` on the module or object, not at collection. The repair, reader and corruption code was held back from Task 1 on purpose so that these tests were red.
- Semantic assessment of RED: the target tests executed and failed because the planned behaviour was missing. The new raw-client, failure-path, request-id and concurrency tests were green at RED because Task 1's implementation already satisfied them; they are regression pins for the second guard and the failure paths, not RED targets. `workflow.tdd_mode` is not enabled, so `gsd_run check tdd-red-evidence` was not run.
- GREEN (`5a5e505`): all pass. No REFACTOR commit was needed.

## Files Created/Modified

- `src/recover_assess/core/log.py` - six typed events, `scrub_text`, `RunLog` (lock, flush, repair on open), `repair_run_log`, `read_run_log`, `RunLogContents`
- `src/recover_assess/core/graph_policy.py` - pure `ReadOnlyPolicy`, `Allowlist` models, `load_allowlist`, canonicaliser and template matcher
- `src/recover_assess/core/graph_allowlist.yaml` - packaged allow-list with the one `site_by_id` entry and its Learn URL
- `src/recover_assess/core/graph.py` - `GraphClient`, `GraphSession`, `guard_request`, `make_http_client` (replaces the 01-01 placeholder)
- `tests/conftest.py` - fixtures and hypothesis profiles `ci` and `dev`
- `tests/fakes/clock.py`, `tests/fakes/fake_graph.py` - `FakeClock`, `FakeGraph`, `RecordedRequest`, `SYNTHETIC_SITE_ID`
- `tests/graph/test_walking_skeleton.py` - tracer, verb and path refusal, raw-client hook, failure-path and concurrency tests
- `tests/unit/test_run_log.py` - interruption safety, concurrency, ordering, scrub tests

## Decisions Made

- `RunLog.emit` stamps `ts` itself from the injected clock under the writer lock, so callers build events without a timestamp and the file's timestamps follow emission order. Later plans only emit.
- The `downloadUrl` scrub handles both the plain member form and the escaped form inside an already-serialised string, so a scrubbed line is still valid JSON.
- `WarningEvent.code` is checked with `is_error_code` in a field validator, because pydantic's regex engine cannot parse `\A` and `\Z` (see Deviations).
- The policy also refuses a query value containing `downloadurl`, as in the research prototype. It is fail-closed and no later plan depends on it being allowed.
- `GraphSession.get` calls `policy.check` once more on a non-2xx response to get the template for `GraphHttpError`. This keeps `_send` returning the raw response, which Plans 01-07 to 01-09 extend.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `ERROR_CODE_PATTERN` is not usable as a pydantic `pattern=`**
- **Found during:** Task 1 (first import of `core.log`)
- **Issue:** `Field(pattern=ERROR_CODE_PATTERN)` raised a `SchemaError` ("unrecognized escape sequence") because pydantic's Rust regex engine rejects the `\A` and `\Z` anchors that Plan 01-01 deliberately used in the Python pattern.
- **Fix:** Replaced the pattern with a `field_validator("code")` that calls `is_error_code`, which uses the same pattern through Python's `re`. Behaviour is identical; `ERROR_CODE_PATTERN` is untouched.
- **Files modified:** `src/recover_assess/core/log.py`
- **Verification:** `tests/unit/test_run_log.py#test_scrub_keeps_a_serialised_line_valid_json` builds a `WarningEvent` with code `truncated`; the whole suite passes
- **Committed in:** `f10538b`

**2. [Rule 3 - Blocking] Lint rules shaped the tests and fakes**
- **Found during:** Task 1 (scoped ruff run)
- **Issue:** ruff `ASYNC240` rejects `Path.read_text` inside async tests, `SIM300` rejects a Yoda comparison, and `E501` rejected the long synthetic site id literal.
- **Fix:** Added a sync `log_text` helper, swapped the comparison, and split the id literal into adjacent strings (same value).
- **Files modified:** `tests/graph/test_walking_skeleton.py`, `tests/fakes/fake_graph.py`
- **Verification:** scoped and whole-tree ruff pass
- **Committed in:** `f10538b`

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Neither changes behaviour or any signature in the interfaces block.

## Issues Encountered

None beyond the deviations above.

## Known Stubs

None. The allow-list holds one entry by design; Plan 01-06 adds the other twelve. `ReadOnlyPolicy.check` accepts `batch_body` and ignores it until Plan 01-06, as the plan states.

## Threat Flags

None. The surface added is the one the plan's threat model covers (T-01-04 to T-01-07, T-01-32). No new packages were installed (T-01-SC): `uv sync --locked` only.

## Verification Results

Demo: `uv run pytest tests/graph/test_walking_skeleton.py -q` passes and the test reads back the produced line, which has the shape `{"ts":"2026-11-15T00:00:00Z","level":"INFO","event":"request","site":"site-1","method":"GET","template":"/sites/{site-id}","status":200,"duration_ms":0.0,"retry":0,"request_id":"11111111-2222-3333-4444-555555555555","via_batch":false,"batch_size":null}`.

| Check | Result |
|-------|--------|
| `uv run pytest tests/graph/test_walking_skeleton.py tests/unit/test_run_log.py -x -q` | 44 passed |
| `uv run pytest -q` (whole tree) | 94 passed |
| `uv run ruff check .` / `uv run ruff format --check .` | clean / 30 files formatted |
| `uv run mypy` | no issues in 28 source files |
| `uv run lint-imports` | 5 contracts kept, 0 broken |
| `grep -c "follow_redirects=False" graph.py` | 1 |
| `grep -c "import httpx2" graph_policy.py` | 0 |
| `grep -c "learn_url: https://learn.microsoft.com/" graph_allowlist.yaml` | 1 |
| `grep -c "def repair_run_log"` / `"def read_run_log"` in log.py | 1 / 1 |

`scripts/check.py` does not exist yet (Plan 01-03), so the wave-2 join gate was run as its component commands above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plans 01-06 to 01-09 can extend `_send` and `GraphSession` without signature changes and add allow-list entries; 01-06 must enable POST `/v1.0/$batch` in `guard_request` only together with the hook's own body check.
- Plan 01-03's AST ban (no `.post(`, `.put(`, `.patch(`, `.delete(` attribute calls in `src`) holds: all sends use `self._http.request`.
- Plan 01-12's real-tree scan reads the tests and fakes written here; they follow the synthetic GUID and runtime-concatenated token conventions.
- Flagged assumptions RESEARCH A2 (ID segment class) and A5 (case-sensitive literals) stand until the Phase 2 live smoke.

## Self-Check: PASSED

- Created files present: `log.py`, `graph_policy.py`, `graph_allowlist.yaml`, `graph.py`, `tests/conftest.py`, `tests/fakes/clock.py`, `tests/fakes/fake_graph.py`, `tests/graph/test_walking_skeleton.py`, `tests/unit/test_run_log.py`
- Commits `f10538b`, `57b0463`, `5a5e505` are ancestors of HEAD
- `git rev-list --count` from the plan-head ledger to HEAD measured 3, matching `commits: 3`

---
*Phase: 01-foundation-contract-read-only-graph-client*
*Completed: 2026-11-16*
