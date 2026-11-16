---
phase: 01-foundation-contract-read-only-graph-client
plan: 09
subsystem: graph-client
tags: [graph, batch, concurrency, graph-stats, user-agent]
status: complete

requires:
  - phase: 01-foundation-contract-read-only-graph-client
    provides: "Plan 01-08 throttling: shared ThrottleGate, SiteBreaker, session counters, retry budget"
  - phase: 01-foundation-contract-read-only-graph-client
    provides: "Plan 01-06 ReadOnlyPolicy.check with batch_body, check_relative_url, packaged-policy request hook"
  - phase: 01-foundation-contract-read-only-graph-client
    provides: "Plan 01-04 Settings.http and Plan 01-11 GraphStats model"
provides:
  - "GraphSession.batch(items, chunk_size, max_items_per_result) -> list[BatchResult], BatchItem, BatchResult, MAX_BATCH_SIZE"
  - "GraphClient(max_sites=2, max_in_flight_per_site=4): client-wide site semaphore and per-session in-flight semaphore"
  - "GraphSession.graph_stats() -> models.fact_sheet.GraphStats"
  - "GraphClient.from_settings(settings, token, run_log, clock, transport, rng) and build_user_agent"
  - "FakeGraph $batch route (shuffled, per-sub throttling), sub_throttle, per-site in-flight counters"
affects: [01-10, 01-12, phase-02-collectors, phase-03-orchestrator]

actuals:
  tokens: 14700
  tasks: 2
  commits: 2

plan_head_before: 52c7131c2a8865a6ff973dee2997acf443893a3e
plan_head_after: 83ddc5c45ce8473cbb4d99e0d21bb74973ce095e

tech-stack:
  added: []
  patterns:
    - "One $batch POST goes through the same _send retry loop and ReadOnlyPolicy.check as any request; sub-requests are judged per sub-response"
    - "The in-flight slot is taken inside _hop around the transport call only, so gate waits and backoff sleeps never hold a slot"
    - "Counters live in _hop (requests, batches), so every attempt and redirect hop is counted once at the point it is sent"

key-files:
  created:
    - tests/graph/test_batch.py
    - tests/graph/test_concurrency.py
    - tests/graph/test_stats.py
  modified:
    - src/recover_assess/core/graph.py
    - tests/fakes/fake_graph.py

key-decisions:
  - "batches is incremented in _hop for every POST attempt, so a whole-batch 429 that is retried counts two batches and two requests"
  - "A $batch re-queue round is capped at max_retries rounds (initial POST plus 6 re-sends), mirroring single requests; leftovers end as BatchResult error_code throttled_out with the last throttled status"
  - "An id the server does not answer yields BatchResult(status 0, error_code batch_response_missing) so the one-result-per-item guarantee always holds"
  - "A blank user_agent_company counts as absent (bare recover-assess/version); a pipe, non-printable character or more than 64 characters raises ValueError"
  - "A sub-body next link is validated against the policy as soon as it arrives, so a hostile link raises UrlNotAllowedError before any further request and the whole batch call fails"

requirements-completed: [GRPH-04, GRPH-06, GRPH-08]

coverage:
  - id: D1
    description: "batch() chunks at 20 (19/20/21/45 give 1/1/2/3 POSTs of 19; 20; 20+1; 20+20+5), empty sends nothing, chunk_size 0 or 21 raises, sub-requests carry only id, method, relative url, ids 1..n per POST"
    requirement: GRPH-04
    verification:
      - kind: unit
        ref: "tests/graph/test_batch.py#test_items_are_sent_in_groups_of_at_most_twenty"
        status: pass
      - kind: unit
        ref: "tests/graph/test_batch.py#test_each_sub_request_carries_only_id_method_and_a_relative_url"
        status: pass
      - kind: unit
        ref: "tests/graph/test_batch.py#test_an_invalid_chunk_size_is_refused_before_any_request"
        status: pass
    human_judgment: false
  - id: D2
    description: "Results return in input order despite shuffled sub-responses; sub 403/404/500 are results with graph_error_NNN and never raise"
    requirement: GRPH-04
    verification:
      - kind: unit
        ref: "tests/graph/test_batch.py#test_results_come_back_in_input_order_although_the_server_shuffles"
        status: pass
      - kind: unit
        ref: "tests/graph/test_batch.py#test_a_sub_403_and_a_sub_404_are_results_not_exceptions"
        status: pass
    human_judgment: false
  - id: D3
    description: "Only throttled subs are re-queued after the longest sub Retry-After; throttled_out at the limit; budget and breaker apply; nextLink completion and item cap"
    requirement: GRPH-04
    verification:
      - kind: unit
        ref: "tests/graph/test_batch.py#test_only_the_throttled_sub_requests_are_re_sent_after_the_longest_retry_after"
        status: pass
      - kind: unit
        ref: "tests/graph/test_batch.py#test_a_sub_request_throttled_every_round_ends_as_throttled_out"
        status: pass
      - kind: unit
        ref: "tests/graph/test_batch.py#test_a_sub_response_with_a_next_link_is_completed_by_paged_gets"
        status: pass
    human_judgment: false
  - id: D4
    description: "Peak of 2 sessions and 4 in flight per site across 5 sessions of 10 GETs; slot not held during backoff; released on exception"
    requirement: GRPH-06
    verification:
      - kind: unit
        ref: "tests/graph/test_concurrency.py#test_five_sessions_of_ten_gets_peak_at_two_sites_and_four_in_flight"
        status: pass
      - kind: unit
        ref: "tests/graph/test_concurrency.py#test_a_request_sleeping_on_a_429_backoff_does_not_hold_its_slot"
        status: pass
    human_judgment: false
  - id: D5
    description: "graph_stats counting rules pinned, key order, schema validation, per-session sums equal transport total; decorated User-Agent and from_settings"
    requirement: GRPH-08
    verification:
      - kind: unit
        ref: "tests/graph/test_stats.py"
        status: pass
    human_judgment: false

duration: 40 min
completed: 2026-11-15
---

# Phase 1 Plan 09: $batch, concurrency limits, graph_stats and from_settings Summary

**The Graph client now batches small GETs safely (at most 20 per `$batch`, each sub-response judged on its own, only throttled subs re-queued, paged subs completed), enforces 2 sites and 4 in-flight requests per site, reports `graph_stats` that validate against the fact-sheet contract, and builds itself from operator settings with a decorated User-Agent.**

## Accomplishments

- **`GraphSession.batch`.** Validates every item against the allow-list up front, then sends chunks as `POST /$batch` through the existing `_send` retry loop, so `ReadOnlyPolicy.check` validates each whole body before anything is sent. Sub-responses are correlated by id (case-insensitive) and returned in input order. A sub 403 or 404 is a `BatchResult` with `error_code graph_error_NNN`, never an exception. Throttled subs (429 or 503) feed the shared gate and the site breaker and are re-sent alone after the longest sub `Retry-After` (else seeded full jitter), inside the same 6-retry and 300 s limits; the leftovers end as `throttled_out`. A sub-body with `@odata.nextLink` is completed by validated paged GETs, merged, and capped by `max_items_per_result` with `truncated`.
- **Concurrency (GRPH-06).** `GraphClient` owns an `asyncio.Semaphore(max_sites)` held for a whole session (released on exceptions) and each session owns an `asyncio.Semaphore(max_in_flight_per_site)` that `_hop` holds only around the transport call. The one-client-per-run invariant is in the `GraphClient` docstring for Phase 3.
- **`graph_stats` (GRPH-08).** Built from the session counters; `seconds` is the session wall time on the injected clock rounded to 3 places. `requests` and `batches` are counted in `_hop`, so retries, redirect hops and each `$batch` POST count once, and sub-responses add no requests.
- **`from_settings` and `build_user_agent`.** Maps `http.*` limits and timeouts, and sends `NONISV|{company}|recover-assess/{version}` when a company is set. `Settings` is imported under `TYPE_CHECKING` only.
- **Test doubles.** `FakeGraph` answers `POST /v1.0/$batch` with a seeded shuffle (unless a test registers its own route), supports `sub_throttle`, records `batch_posts` and `batch_response_ids`, and tracks per-site current and peak in-flight while yielding five times per request so tasks interleave.

## Task Commits

1. Task 1: `$batch` with per-sub results, re-queue and nextLink fallback - `442fe72`
2. Task 2: concurrency, graph_stats and from_settings tests - `83ddc5c`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 1 commit also carries Task 2's production code**
- **Found during:** Task 1 commit
- **Issue:** Both tasks edit only `graph.py`, and the interleaved hunks (the in-flight slot inside `_hop`, the `batches` counter, `graph_stats`, `from_settings`) could not be split without interactive staging, which this environment does not support.
- **Fix:** Commit `442fe72` contains all `graph.py` and `fake_graph.py` changes; commit `83ddc5c` adds the Task 2 test modules. Task 2's behaviours were verified against the code in a separate pass, including two mutation checks (removing the in-flight and site semaphores fails 3 and 4 concurrency tests).
- **Files modified:** `src/recover_assess/core/graph.py`, `tests/fakes/fake_graph.py`
- **Commit:** 442fe72

**2. [Rule 1 - Bug] Test float equality on gate-derived sleeps**
- **Found during:** Task 1 (`test_a_requeue_without_retry_after_uses_seeded_full_jitter`)
- **Issue:** The gate sleeps `resume_at - now`, so the recorded sleep differs from the jitter value by float rounding.
- **Fix:** The test compares with `pytest.approx`.
- **Files modified:** `tests/graph/test_batch.py`
- **Commit:** 442fe72

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug). **Impact:** no behaviour change; only the commit split differs from the plan.

## Issues Encountered

None.

## Known Stubs

None.

## Threat Flags

None. T-01-26 (correlation) is covered by id-only correlation, unique ids per POST, one result per input item and shuffled-response tests; T-01-27 (concurrency) by the two semaphores and peak-count tests. No new packages. `POST` remains confined to `/$batch`, and the AST ban test still finds no `.post(` call.

## Flagged Assumptions

- RESEARCH Open Question 4: `chunk_size` is exposed so Phase 5 can use smaller groups for permission calls.
- RESEARCH Open Question 5: `graph_stats.seconds` is a float rounded to 3 places.
- RESEARCH A4: the decorated User-Agent form is assumed correct; it affects throttling priority only.
- Handoff to Phase 3: build one `GraphClient` per run (`from_settings`) and open every site's session from it, or the shared gate and the 2-site limit do not hold.

## Verification

- `uv run --frozen python scripts/check.py` exits 0 (887 tests, ruff, format, mypy strict, import contracts, lock check).
- `uv run pytest tests/graph/test_batch.py tests/graph/test_concurrency.py tests/graph/test_stats.py -q`: 66 passed in about 1 s, no real sleeping.
- Acceptance greps: `MAX_BATCH_SIZE` count 5, `def graph_stats` count 1, `response.elapsed` count 0; `tests/unit/test_source_bans.py` passes.

## Next Phase Readiness

Ready for Plan 01-10.

## Self-Check: PASSED

- Created files exist: `tests/graph/test_batch.py`, `tests/graph/test_concurrency.py`, `tests/graph/test_stats.py`; modified: `src/recover_assess/core/graph.py`, `tests/fakes/fake_graph.py`.
- Commits `442fe72` and `83ddc5c` are ancestors of HEAD.
