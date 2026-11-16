---
phase: 01-foundation-contract-read-only-graph-client
plan: 08
subsystem: graph-client
tags: [graph, throttling, retry, tenacity, breaker]
status: complete

requires:
  - phase: 01-foundation-contract-read-only-graph-client
    provides: "Plan 01-07 GraphClient._send with manual redirects, iter_pages, get_all"
  - phase: 01-foundation-contract-read-only-graph-client
    provides: "Plan 01-01 injectable Clock, ThrottledOut, RetryEvent"
provides:
  - "core/throttle.py: parse_retry_after, full_jitter_delay, ThrottleGate, SiteBreaker and the fixed spec constants"
  - "GraphClient retries 429 and 503 through a tenacity AsyncRetrying loop on the injected clock and rng"
  - "One ThrottleGate per GraphClient shared by every session; one SiteBreaker and one counters dataclass per GraphSession"
  - "FakeGraph.throttle, per-request clock timestamps, ManualClock and settle test helpers"
affects: [01-09, 01-12, phase-02-collectors]

actuals:
  tokens: 8750
  tasks: 2
  commits: 2

plan_head_before: 3b8f129b7ad57e2c3f39aa25ab1763a408158d4a
plan_head_after: de12b46192bb6f54f9573e0ba86111c840ac9de0

tech-stack:
  added: []
  patterns:
    - "tenacity custom stop and wait callables over injected Clock and random.Random; its wall-clock stop and global-random jitter helpers are never used"
    - "Throttling primitives are pure (no HTTP import); the client owns the wiring"
    - "A ManualClock whose sleepers really block lets a test observe two concurrent tasks, which advance-on-sleep cannot show"

key-files:
  created:
    - src/recover_assess/core/throttle.py
    - tests/graph/test_throttle_unit.py
    - tests/graph/test_throttle_retry.py
  modified:
    - src/recover_assess/core/graph.py
    - tests/fakes/fake_graph.py
    - tests/fakes/clock.py
    - tests/conftest.py

key-decisions:
  - "tenacity evaluates wait before stop, so _wait_for returns 0 without side effects once retries are spent; otherwise the 7th throttle would trip the gate, count a retry and write a retry line for a retry that never happens"
  - "Non-retryable statuses are returned once by _send and raised as GraphHttpError by the caller (existing _fetch_object), so no status other than 429 or 503 is ever sent twice"
  - "Policy check, breaker check, gate wait and token fetch all run per attempt, so a token that expired during a long wait is refreshed"
  - "Retry-After seconds are matched by a strict decimal pattern; exponent forms such as 1e3 are treated as absent rather than parsed"
  - "The breaker raises from inside the attempt with the request template, and a poisoned session raises before any send"

requirements-completed: [GRPH-05]

coverage:
  - id: D1
    description: "Retry-After (seconds, decimals, HTTP-date, clamped, non-finite as absent) and seeded full jitter within [0, min(60, 2^(n-1))]"
    requirement: GRPH-05
    verification:
      - kind: unit
        ref: "tests/graph/test_throttle_unit.py"
        status: pass
      - kind: unit
        ref: "tests/graph/test_throttle_retry.py#test_retry_after_seconds_is_honoured_then_the_body_is_returned"
        status: pass
    human_judgment: false
  - id: D2
    description: "At most 6 retries (7th throttle exhausts after 7 sends and 6 sleeps); 300 s budget fails at once, exactly 300 s is allowed"
    requirement: GRPH-05
    verification:
      - kind: unit
        ref: "tests/graph/test_throttle_retry.py#test_the_seventh_consecutive_throttle_exhausts_the_retries"
        status: pass
      - kind: unit
        ref: "tests/graph/test_throttle_retry.py#test_a_wait_that_would_pass_the_budget_fails_at_once_without_sleeping"
        status: pass
    human_judgment: false
  - id: D3
    description: "Only 429 and 503 are retried; 400, 403, 404, 500, 502, 504 are sent once with no sleep and no retry line"
    requirement: GRPH-05
    verification:
      - kind: unit
        ref: "tests/graph/test_throttle_retry.py#test_other_statuses_are_sent_once_and_never_retried"
        status: pass
    human_judgment: false
  - id: D4
    description: "One shared gate holds a send on another site until resume_at; resume_at never moves backwards"
    requirement: GRPH-05
    verification:
      - kind: unit
        ref: "tests/graph/test_throttle_retry.py#test_a_throttle_on_one_site_holds_the_next_send_on_another_site"
        status: pass
      - kind: unit
        ref: "tests/graph/test_throttle_unit.py#test_gate_never_moves_backwards_and_waits_the_remaining_time"
        status: pass
    human_judgment: false
  - id: D5
    description: "Per-site breaker: 19 in 60 s do not trip, the 20th does, exactly 60 s apart does not; a tripped session fails without sending while other sessions work"
    requirement: GRPH-05
    verification:
      - kind: unit
        ref: "tests/graph/test_throttle_unit.py"
        status: pass
      - kind: unit
        ref: "tests/graph/test_throttle_retry.py#test_the_breaker_fails_a_site_without_touching_other_sites"
        status: pass
    human_judgment: false

duration: 35 min
completed: 2026-11-16
---

# Phase 1 Plan 08: Throttling, retries, shared gate and breaker Summary

**The Graph client now survives throttling: it waits `Retry-After` (seconds or HTTP-date) else seeded full-jitter backoff, retries 429 and 503 at most 6 times inside a 300 s budget, holds every site behind one shared gate, and fails a site through a 20-in-60 s breaker, all driven by tenacity on an injected clock so the tests run in milliseconds.**

## Accomplishments

- **Pure primitives (`core/throttle.py`).** `parse_retry_after` takes integer or decimal seconds (negative clamped to 0) and HTTP-dates relative to the injected clock; blank, unparseable, NaN, infinite and exponent forms count as absent. `full_jitter_delay` is uniform in `[0, min(60, 2^(n-1))]` from an injected `random.Random`, so a seed reproduces the sleep sequence. `ThrottleGate` never moves `resume_at` backwards. `SiteBreaker` uses a half-open 60 s window and stays open once tripped.
- **Retry loop in `GraphClient._send`.** `AsyncRetrying(sleep=clock.sleep, stop, wait, retry_if_exception_type(_Throttled), reraise=True)` with custom callables. Each attempt checks the breaker, waits on the gate, re-runs the policy, fetches a token, sends (redirect hops stay inside the attempt) and logs a `RequestEvent` whose `retry` is the attempt index. Each scheduled retry writes a `RetryEvent`. Exhaustion raises `ThrottledOut("retries_exhausted")`, a wait past the budget raises `ThrottledOut("budget")` before sleeping, and the 20th throttle in 60 s raises `ThrottledOut("breaker")` and poisons the session.
- **Shared coordination.** One `ThrottleGate` per client; one `SiteBreaker` and `_SessionCounters` (requests, batches, throttled, retries) plus `opened_at` per session, exposed through read-only properties for Plan 01-09's `graph_stats`.
- **Test doubles.** `FakeGraph.throttle(path_regex, times, status, retry_after)`, `request_times` (clock value per handled request), `ManualClock` and `settle` in `tests/fakes/clock.py`.

## Task Commits

1. Task 1: pure throttling primitives and unit tests - `fb16553`
2. Task 2: retries, budget, shared gate and breaker wired into `GraphClient._send`, with `FakeGraph.throttle` - `de12b46`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] tenacity computes the wait before checking stop**
- **Found during:** Task 2 (first run of the exhaustion test: 7 retry lines instead of 6)
- **Issue:** On the 7th throttle tenacity calls `wait` before `stop`, so the wait callable tripped the gate, counted a retry and wrote a `RetryEvent` for a retry that never happens, and could raise `budget` instead of `retries_exhausted`.
- **Fix:** `_wait_for` returns 0.0 with no side effects when the stop condition already holds.
- **Files modified:** `src/recover_assess/core/graph.py`
- **Commit:** de12b46

**2. [Rule 3 - Blocking] A discriminating shared-gate test needs a clock whose sleepers block**
- **Found during:** Task 2
- **Issue:** The existing `FakeClock` advances time inside `sleep`, so a second site would pass the gate whether or not the gate exists (RESEARCH A11).
- **Fix:** added `ManualClock` and `settle` to `tests/fakes/clock.py`; `FakeGraph` takes an optional clock and the `fake_graph` fixture in `tests/conftest.py` passes `fake_clock`. A mutation check (removing `gate.wait()`) makes the shared-gate test fail.
- **Files modified:** `tests/fakes/clock.py`, `tests/fakes/fake_graph.py`, `tests/conftest.py`
- **Commit:** de12b46

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking). **Impact:** tighter than the plan; `tests/conftest.py` and `tests/fakes/clock.py` were not in the plan's `files_modified` list.

## Issues Encountered

None.

## Known Stubs

None. `_SessionCounters.batches` stays 0 until Plan 01-09 adds `$batch`; that is the planned hand-off, not a stub.

## Threat Flags

None. The surface matches T-01-24 (retry storms: only 429/503, one gate, 6 retries, breaker) and T-01-25 (hostile Retry-After: 300 s budget fails fast, `86400` raises `budget` with no sleep, non-finite counts as absent). No new packages (tenacity was already locked).

## Flagged Assumptions

- RESEARCH A10 stands: only 429 and 503 retry; transient 500, 502, 504 and transport errors fail at once. Adding them is one line in `RETRYABLE_STATUSES` plus tests.
- Handoff to Phase 3: tenant-wide coordination holds only if a run builds exactly one `GraphClient` and opens every site's session from it.

## Verification

- `uv run --frozen python scripts/check.py` exits 0 on the final tree (821 tests, ruff, format, mypy strict, 5 import contracts).
- `uv run pytest tests/graph -q`: 416 passed in about 3 s, no real sleeping.
- Acceptance greps: the tenacity time and jitter helper grep over `graph.py` counts 0; `AsyncRetrying` counts 2.
- Demo: `uv run pytest tests/graph/test_throttle_retry.py -q`.

## Next Phase Readiness

Ready for Plan 01-09 (`$batch`, user agent, `graph_stats` from the session counters).

## Self-Check: PASSED

- Created files exist: `src/recover_assess/core/throttle.py`, `tests/graph/test_throttle_unit.py`, `tests/graph/test_throttle_retry.py`; modified: `graph.py`, `tests/fakes/fake_graph.py`, `tests/fakes/clock.py`, `tests/conftest.py`.
- Commits `fb16553` and `de12b46` are ancestors of HEAD.
