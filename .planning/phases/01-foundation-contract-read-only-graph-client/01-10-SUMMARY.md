---
phase: 01-foundation-contract-read-only-graph-client
plan: 10
subsystem: graph-client
tags: [logging, privacy, acceptance, phase-gate]
status: complete

requires:
  - phase: 01-foundation-contract-read-only-graph-client
    provides: "Plan 01-09 $batch, concurrency limits, graph_stats and from_settings"
  - phase: 01-foundation-contract-read-only-graph-client
    provides: "Plan 01-03 fact-sheet models and generated schema (GraphStats definition)"
provides:
  - "tests/support/log_audit.py: AuditFinding, SECRET_PATTERNS, audit_run_log (reusable run.jsonl audit)"
  - "tests/graph/test_logging_capture.py: canary log capture across ten client paths plus adjacency tests"
  - "tests/integration/test_phase1_acceptance.py: five-site throttled acceptance scenario (ROADMAP SC3 and SC4 jointly)"
  - "README Developer quick check section"
  - "graph.py: server-supplied request-id logged only when GUID-shaped"
affects: [phase-02-collectors, phase-03-orchestrator, phase-06-pilot-log-audit]

actuals:
  tokens: 8600
  tasks: 2
  commits: 2

plan_head_before: 001c4493afbffda078a021aa2d7c753f205b1a6c
plan_head_after: c1c52f26ca308b584ec29c1bb37aff9ef33f0b61

tech-stack:
  added: []
  patterns:
    - "Canaries are concatenated at runtime so the FND-07 repo scan never sees a token-shaped literal"
    - "Audit findings carry only a line number and a rule name, never the matched text"

key-files:
  created:
    - tests/support/log_audit.py
    - tests/graph/test_logging_capture.py
    - tests/integration/test_phase1_acceptance.py
  modified:
    - src/recover_assess/core/graph.py
    - README.md

key-decisions:
  - "A request-id header value is logged only when it fullmatches [A-Za-z0-9-]{1,64}; otherwise request_id is null (it does not fall through to client-request-id)"
  - "The acceptance scenario gets its 20 throttles inside one 60 s window with Retry-After 1; no timing input needed changing"

requirements-completed: [GRPH-07]

coverage:
  - id: D1
    description: "Ten client paths write no token, body sentinel, downloadUrl, raw ID, site title, URL or query string to run.jsonl; request lines carry exactly the twelve keys, an allow-list template and the opaque site key"
    requirement: GRPH-07
    verification:
      - kind: unit
        ref: "tests/graph/test_logging_capture.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Exceptions on the failure paths (hostile redirect, hostile nextLink, 403, transport errors, DELETE) have str() and traceback free of URLs, queries and canaries"
    requirement: GRPH-07
    verification:
      - kind: unit
        ref: "tests/graph/test_logging_capture.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "Adjacency: retry 0/1/2 plus two retry lines; $batch of 3 gives 1 outer plus 3 via_batch lines; a followed redirect gives one line per hop"
    requirement: GRPH-07
    verification:
      - kind: unit
        ref: "tests/graph/test_logging_capture.py#test_a_request_retried_twice_logs_retry_0_1_2_and_two_retry_lines"
        status: pass
    human_judgment: false
  - id: D4
    description: "audit_run_log flags a DELETE line, a POST outside /$batch, a JWT and an unparseable line, and returns no findings for every log produced here"
    requirement: GRPH-07
    verification:
      - kind: unit
        ref: "tests/graph/test_logging_capture.py#test_the_audit_flags_a_delete_a_post_outside_batch_and_a_secret"
        status: pass
    human_judgment: false
  - id: D5
    description: "Five sites through two slots: site-3 ends with reasons [retries_exhausted, retries_exhausted, breaker] after exactly 20 sends, a further get raises breaker with no new send, the other four complete, peaks 2 sessions and 4 in flight hold, graph_stats validate against the schema, audit is clean"
    requirement: GRPH-07
    verification:
      - kind: integration
        ref: "tests/integration/test_phase1_acceptance.py"
        status: pass
    human_judgment: false

duration: 35 min
completed: 2026-11-15
---

# Phase 1 Plan 10: Canary log capture, run.jsonl audit and phase acceptance Summary

**No client path can now put a token, response body, download URL, raw ID, URL or query string into run.jsonl or exception text (proven with runtime-built canaries over ten paths), a reusable audit checks real run logs, and a five-site throttled scenario proves the breaker, the concurrency limits and the fact-sheet counters together. The full gate is green on Windows.**

## Accomplishments

- **`audit_run_log`.** Stdlib-only. Flags a request line whose method is not GET or POST, a POST whose template is not `/$batch`, any line matching a secret pattern (bearer, JWT shape, `sig=`, tempauth, downloadurl, api-key, access_token) and any unparseable line. Findings hold only a line number and a rule name.
- **Canary capture.** One test per path, each with its own run.jsonl: single GET, capped paged GET over three pages, followed redirect, hostile redirect, hostile next link, 429 then 200, 403 with a sentinel body, `ReadTimeout` and `ConnectError` carrying a URL and token in their message, `$batch` of three with a sub-429 and a sub-404, and a DELETE on the raw client. Every canary is in every fake response body (token, sentinel, downloadUrl annotation at two levels, site title, raw site, drive and item IDs) and none reaches a log line or an exception's text or rendered traceback.
- **Adjacency.** A request retried twice gives retry 0, 1, 2 and two retry lines; a `$batch` of three gives one outer line and three `via_batch` lines; a redirect gives one line per hop.
- **Acceptance scenario.** Five sessions on one client (2 site slots, 4 in flight). Healthy sites each do eight concurrent gets, a capped `get_all` (25 of 40 items, truncated) and a batch of five with one sub-429 re-queued (requests 13, batches 2, throttled 1, retries 1). Site-3 answers 429 with Retry-After 1 forever: its gets end `retries_exhausted`, `retries_exhausted`, `breaker` (20 sends, 20 throttles, 17 retries); one more get raises `breaker` with no new send. Peaks: 2 sessions, 4 in flight. Wall time 0.2 s. Mutation checks: raising the client limits to 3 sites and 6 in flight fails the peak assertion; Retry-After 40 breaks the reason sequence.
- **README.** "Developer quick check" section after the Quality gate section.

## Task Commits

1. Task 1: canary log capture, audit and request-id scrub fix - `523e7a7`
2. Task 2: acceptance scenario and developer quick check - `c1c52f2`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Server-supplied request-id reached run.jsonl unchecked**
- **Found during:** Task 1 (a hostile `request-id` header test written beyond the plan's canary list)
- **Issue:** `RequestEvent.request_id` took the raw `request-id` / `client-request-id` header (single GET and `$batch` sub-responses). Text such as a URL or a token-shaped string would be logged; `scrub_text` redacts only bearer, JWT and signed-parameter shapes, so a URL with a path or free text passed through. The test failed before the fix (a `?` and a URL fragment in the log).
- **Fix:** `_safe_request_id` in `core/graph.py` keeps a value only if it fullmatches `[A-Za-z0-9-]{1,64}` (GUID-shaped), else `None`. Applied at both log sites. All 501 existing graph tests still pass, including the request-id fallback tests.
- **Files modified:** `src/recover_assess/core/graph.py`
- **Commit:** 523e7a7

**2. [Rule 3 - Blocking] TDD cycle collapsed into one commit per task**
- **Issue:** The canary tests are characterization tests for behaviour that already held, except the request-id case. Committing a failing test alone would break the gate on the branch.
- **Fix:** The one real RED (hostile request-id test failing on `"?" not in text`) was observed, then fixed, then committed together with its tests.
- **Commit:** 523e7a7

**Total deviations:** 2 (1 Rule 2, 1 Rule 3). **Impact:** one small hardening in `graph.py`; no scenario timing input or assertion had to change.

## Issues Encountered

None. No canary other than the request-id one leaked: `scrub_text` and the closed set of typed events were already sufficient for the plan's listed canaries.

## Known Stubs

None.

## Threat Flags

None. T-01-28 and T-01-29 are mitigated by the canary tests; the request-id hardening closes a gap beside them. No new packages.

## Flagged Assumptions

- CI on GitHub still starts only when a remote exists; the gate is proven locally on Windows.
- `audit_run_log` is ready for Phase 6's pilot-run log audit; fact sheets and reports have no writer yet, so their no-secrets guarantee is carried by the typed models.
- The gate-trip assertion "a send on another site happens at least one throttle delay after the first site-3 send" is weak on `FakeClock` (concurrent sleepers advance time additively); it is kept as the plan wrote it.

## Verification

- `uv run --frozen python scripts/check.py` exits 0 (907 tests).

| Step | Status |
|------|--------|
| uv-lock-check | PASS |
| ruff-check | PASS |
| ruff-format | PASS |
| mypy | PASS |
| import-contracts | PASS (5 kept, 0 broken) |
| pytest | PASS (907 passed in 11.4 s) |

- `uv run pytest tests/integration/test_phase1_acceptance.py tests/graph/test_logging_capture.py -q`: passed.
- `uv run python scripts/gen_schemas.py --check`: `OK fact_sheet`.
- `grep -c "Developer quick check" README.md` is 1.
- Demo command: `uv run pytest tests/integration/test_phase1_acceptance.py -q`

## Pending Human Verification

- FND-01 manual clean-machine install (Plan 01-01 human check) remains batched for end-of-phase UAT.

## Next Phase Readiness

Phase 1 plans are complete; ready for `/gsd-verify-work`.

## Self-Check: PASSED

- Created files exist: `tests/support/log_audit.py`, `tests/graph/test_logging_capture.py`, `tests/integration/test_phase1_acceptance.py`; modified: `src/recover_assess/core/graph.py`, `README.md`.
- Commits `523e7a7` and `c1c52f2` are ancestors of HEAD.
