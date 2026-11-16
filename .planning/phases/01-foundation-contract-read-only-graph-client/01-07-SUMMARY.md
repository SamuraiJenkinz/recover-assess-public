---
phase: 01-foundation-contract-read-only-graph-client
plan: 07
subsystem: graph-client
tags: [graph, paging, nextlink, redirects, proxy, annotations]
status: complete

requires:
  - phase: 01-foundation-contract-read-only-graph-client
    provides: "Plan 01-02 GraphClient._send, GraphSession, make_http_client, FakeGraph"
  - phase: 01-foundation-contract-read-only-graph-client
    provides: "Plan 01-06 ReadOnlyPolicy.check / check_absolute_url, canonical_segments, packaged_policy"
provides:
  - "GraphSession.iter_pages and get_all(cap): paging to the end, item cap, truncated flag, pages count"
  - "Every server-supplied next link and redirect Location validated by ReadOnlyPolicy before the token travels"
  - "Manual redirects: at most MAX_REDIRECT_HOPS = 3, none on POST /$batch, one run-log line per hop"
  - "strip_annotations: every @microsoft.graph.* key removed at every depth at the response boundary"
  - "FakeGraph.paged and FakeGraph.redirect test doubles; proxy-mount regression guard"
affects: [01-08, 01-09, 01-12, phase-02-collectors]

actuals:
  tokens: 8300
  tasks: 2
  commits: 2

plan_head_before: 644209ade5d8f339561b1c60d852bab52405939a
plan_head_after: 1f39f54e92f0cbaa5afc70063a5df61ffbd0b967

tech-stack:
  added: []
  patterns:
    - "Server-supplied URLs (next link, Location) are checked by the policy on receipt and again in _send before any request"
    - "iter_pages is an async generator wrapped in contextlib.aclosing inside get_all, so breaking at the cap closes it deterministically"
    - "Hostile userinfo-form URLs are built at runtime by explicit + concatenation (FND-07 scan convention)"

key-files:
  created:
    - tests/graph/test_paging.py
    - tests/graph/test_redirects.py
    - tests/graph/test_transport_guard.py
  modified:
    - src/recover_assess/core/graph.py
    - tests/fakes/fake_graph.py

key-decisions:
  - "A next link is validated when its page arrives, before the page is yielded, as well as in _send before it is requested: a tampered response yields nothing and nothing is sent"
  - "iter_pages is typed AsyncGenerator[Page, None] (a subtype of the planned AsyncIterator[Page]) so get_all can close it with aclosing when the cap is reached"
  - "A non-JSON or non-object 2xx body raises GraphError (response_not_json, response_not_object) instead of leaking a json error"
  - "Only 301, 302, 303, 307 and 308 are redirects; a 304 is a plain non-2xx GraphHttpError"

requirements-completed: [GRPH-02, GRPH-03]

coverage:
  - id: D1
    description: "Paging follows next links to the end; get_all cap boundary (N-1, N, N with link, N+5) marks truncated correctly; cap under 1 is a ValueError; no request after the cap"
    requirement: GRPH-03
    verification:
      - kind: unit
        ref: "tests/graph/test_paging.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Hostile, empty and non-string next links are refused with UrlNotAllowedError and nothing (no token fetch, no transport request, no run-log line) is sent to them"
    requirement: GRPH-02
    verification:
      - kind: unit
        ref: "tests/graph/test_paging.py#test_a_hostile_next_link_is_refused_and_never_requested"
        status: pass
    human_judgment: false
  - id: D3
    description: "Redirects are validated and followed by hand, capped at 3 hops, refused on POST, without Location, or to a hostile target"
    requirement: GRPH-02
    verification:
      - kind: unit
        ref: "tests/graph/test_redirects.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "Annotation stripping removes @microsoft.graph.* at every depth and keeps @odata.nextLink, @odata.deltaLink and @odata.count"
    requirement: GRPH-02
    verification:
      - kind: unit
        ref: "tests/graph/test_paging.py#test_download_annotations_never_reach_the_caller"
        status: pass
    human_judgment: false
  - id: D5
    description: "Production client keeps environment proxy mounts and honours NO_PROXY; a test transport has none; follow_redirects is False; the request hook refuses foreign hosts, ports and POST before any transport"
    requirement: GRPH-02
    verification:
      - kind: unit
        ref: "tests/graph/test_transport_guard.py"
        status: pass
    human_judgment: false

duration: 25 min
completed: 2026-11-16
---

# Phase 1 Plan 07: Paging, validated redirects and annotation stripping Summary

**`GraphSession.iter_pages`/`get_all(cap)` page to the end under an item cap that marks truncation, every server-supplied next link and redirect Location is policy-checked before the bearer token travels, and `@microsoft.graph.*` download annotations are stripped at the response boundary.**

## Accomplishments

- **Paging (GRPH-03).** `iter_pages` follows the server's next link verbatim (a skip token is never built by hand), yields `Page(items, next_link, delta_link)` and never follows a delta link. `get_all(path, params, *, cap)` returns `PagedResult(items, truncated, cap, pages)`; the cap counts items; `truncated` is true exactly when items were dropped or a next link remained at the cap; no page is requested after that. Six parametrised boundary cases plus the "N with link remaining" and "N+5 available" cases pin this.
- **Validated next links (GRPH-02).** Seven hostile forms (foreign host, http, `/beta`, item `/content`, userinfo host, port 8443, empty string) plus a non-string value raise `UrlNotAllowedError` and the transport records only the legitimate requests. The test counts token fetches (2 for 2 legitimate requests) so it also proves the token is not even obtained for a rejected URL, and counts run-log lines.
- **Manual redirects (GRPH-02, D-09).** `_send` follows 301/302/303/307/308 on a GET by resolving `Location` with `urljoin`, calling `policy.check("GET", ...)` and only then sending, at most 3 follow-ups (`too_many_redirects` on the 4th). A 3xx on POST raises `redirect_on_batch`; missing or empty `Location` raises `redirect_without_location`. Each hop writes its own request line (302 then 200, same template). `follow_redirects` stays False.
- **Annotation stripping.** `strip_annotations` removes every `@microsoft.graph.*` key at every nesting level in `get` and every page, so `downloadUrl` never reaches a caller, log or fixture; `@odata.*` keys survive.
- **Proxy regression guard.** Tests assert production `make_http_client` keeps proxy mounts under `HTTPS_PROXY`, honours `NO_PROXY`, an injected transport has none, and the raw client does not follow a 302 on its own; the request hook refuses foreign host, port 8443 and a POST to a site path with the handler never called.

## Task Commits

1. Task 1: paging, cap, validated next links, annotation stripping, `FakeGraph.paged` - `1b44f42`
2. Task 2: validated manual redirects, `FakeGraph.redirect`, transport guard tests - `1f39f54`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `aclosing` needs an async generator type**
- **Found during:** Task 1 (mypy)
- **Issue:** `get_all` wraps `iter_pages` in `contextlib.aclosing` so breaking at the cap closes the generator deterministically; mypy rejected `AsyncIterator[Page]` (no `aclose`).
- **Fix:** `iter_pages` is annotated `AsyncGenerator[Page, None]`, a subtype of the planned `AsyncIterator[Page]`; callers are unaffected.
- **Files modified:** `src/recover_assess/core/graph.py`
- **Commit:** 1b44f42

**2. [Rule 2 - Missing critical] Malformed 2xx bodies leaked a raw JSON error**
- **Found during:** Task 1
- **Issue:** `json.loads` on a non-JSON body or a non-object body would raise or return a non-dict where callers expect a mapping.
- **Fix:** shared `_fetch_object` raises `GraphError("response_not_json")` or `("response_not_object")` with the path template; `get` and paging both use it. Empty body still returns `{}`.
- **Files modified:** `src/recover_assess/core/graph.py`
- **Commit:** 1b44f42

**3. [Rule 2 - Missing critical] Next link validated on receipt as well as before the request**
- **Found during:** Task 1
- **Issue:** The plan validates in `_send` when the link is followed. With a hostile link on a page that `get_all` stops at (cap reached), a tampered response would otherwise be accepted silently.
- **Fix:** `iter_pages` also runs `policy.check` on the link when the page arrives, before yielding it; a non-string link raises `UrlNotAllowedError("next_link_invalid")`. `_send` still checks again, so the guarantee does not depend on this ordering.
- **Commit:** 1b44f42

**4. [Rule 3 - Blocking] Ruff ASYNC240 in a redirect test**
- **Found during:** Task 2
- **Issue:** `Path.read_text` called inside an async test.
- **Fix:** moved the read into a sync helper `log_text`, as the walking-skeleton tests do.
- **Commit:** 1f39f54

**Total deviations:** 4 auto-fixed (2 blocking, 2 missing critical). **Impact:** all tighten the plan's guarantees; no scope creep, no new dependency.

### Process note

The plan is `type: execute` (tdd per task, one commit per task), so each task was one feat commit with its tests rather than separate RED/GREEN commits. To keep the commit boundary at the task line, the Task 1 commit holds `_send` without the redirect loop and Task 2 adds it.

## Issues Encountered

None.

## Known Stubs

None.

## Threat Flags

None. The surface added matches T-01-21 (next link), T-01-22 (redirects) and T-01-23 (download annotations) in the plan's threat model, each with a mitigating test.

## Verification

- `uv run --frozen python scripts/check.py` exits 0 on the final tree (761 tests, ruff, format, mypy strict, import contracts).
- Scoped commands from both tasks pass: `pytest tests/graph -x -q` (356 passed), `ruff check`, `mypy` and `ruff format --check` on this plan's five files.
- Acceptance greps: `def strip_annotations` count 1; `MAX_REDIRECT_HOPS` present; the email-shape grep over `tests/graph/*.py` and `tests/fakes/*.py` prints no file name (FND-07 hygiene for the wave-4 join).
- Demo: `uv run pytest tests/graph/test_paging.py tests/graph/test_redirects.py -q`.

## Next Phase Readiness

Ready for the wave-4 join and Plan 01-08. Flagged assumptions stand: nextLinks use host `graph.microsoft.com` (a different host fails closed), delta nextLinks use the `?token=` form (Phase 4 confirms), and the delta link is exposed but never followed. A next link whose query carries a key outside the allow-list (for example a bare `$skip`) is refused; Phase 2 collectors should confirm real nextLinks only use `$skiptoken` or `token`.

## Self-Check: PASSED

- Created files exist: `tests/graph/test_paging.py`, `tests/graph/test_redirects.py`, `tests/graph/test_transport_guard.py`; modified: `src/recover_assess/core/graph.py`, `tests/fakes/fake_graph.py`.
- Commits `1b44f42` and `1f39f54` are ancestors of HEAD.
