---
phase: 01-foundation-contract-read-only-graph-client
reviewed: 2026-11-15T00:00:00Z
depth: standard
files_reviewed: 76
files_reviewed_list:
  - .gitattributes
  - .github/workflows/ci.yml
  - .gitignore
  - .python-version
  - README.md
  - config/README.md
  - pyproject.toml
  - recover-assess.example.yaml
  - schemas/fact_sheet.schema.json
  - scripts/check.py
  - scripts/gen_schemas.py
  - scripts/verify_sha256.py
  - src/recover_assess/__init__.py
  - src/recover_assess/cli.py
  - src/recover_assess/core/__init__.py
  - src/recover_assess/core/agent/__init__.py
  - src/recover_assess/core/clock.py
  - src/recover_assess/core/collect/__init__.py
  - src/recover_assess/core/config.py
  - src/recover_assess/core/errors.py
  - src/recover_assess/core/graph.py
  - src/recover_assess/core/graph_allowlist.yaml
  - src/recover_assess/core/graph_policy.py
  - src/recover_assess/core/log.py
  - src/recover_assess/core/models/__init__.py
  - src/recover_assess/core/models/common.py
  - src/recover_assess/core/models/fact_sheet.py
  - src/recover_assess/core/models/registry.py
  - src/recover_assess/core/output.py
  - src/recover_assess/core/providers/__init__.py
  - src/recover_assess/core/report/__init__.py
  - src/recover_assess/core/run/__init__.py
  - src/recover_assess/core/score/__init__.py
  - src/recover_assess/core/throttle.py
  - tests/__init__.py
  - tests/conftest.py
  - tests/fakes/__init__.py
  - tests/fakes/clock.py
  - tests/fakes/fake_graph.py
  - tests/fixtures/fact_sheet/example_complete.json
  - tests/fixtures/fact_sheet/example_not_run.json
  - tests/graph/__init__.py
  - tests/graph/test_allowlist_pinned.py
  - tests/graph/test_batch.py
  - tests/graph/test_batch_hook.py
  - tests/graph/test_concurrency.py
  - tests/graph/test_logging_capture.py
  - tests/graph/test_paging.py
  - tests/graph/test_policy_urls.py
  - tests/graph/test_policy_verbs.py
  - tests/graph/test_redirects.py
  - tests/graph/test_stats.py
  - tests/graph/test_throttle_retry.py
  - tests/graph/test_throttle_unit.py
  - tests/graph/test_transport_guard.py
  - tests/graph/test_walking_skeleton.py
  - tests/integration/__init__.py
  - tests/integration/test_phase1_acceptance.py
  - tests/support/__init__.py
  - tests/support/import_violations.py
  - tests/support/log_audit.py
  - tests/support/repo_scan.py
  - tests/unit/__init__.py
  - tests/unit/test_atomic_write.py
  - tests/unit/test_check_script.py
  - tests/unit/test_config.py
  - tests/unit/test_config_show.py
  - tests/unit/test_env_typo_scan.py
  - tests/unit/test_fact_sheet_model.py
  - tests/unit/test_fact_sheet_schema.py
  - tests/unit/test_foundation.py
  - tests/unit/test_import_contracts.py
  - tests/unit/test_repo_scan.py
  - tests/unit/test_run_log.py
  - tests/unit/test_sdist_contents.py
  - tests/unit/test_source_bans.py
findings:
  critical: 0
  warning: 9
  info: 5
  total: 14
  necessity: 0
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-11-15
**Depth:** standard
**Files Reviewed:** 76
**Status:** issues_found

## Summary

Production code was read in full (`core/graph.py`, `graph_policy.py`, `throttle.py`, `log.py`, `config.py`, `errors.py`, `output.py`, `models/*`, `cli.py`, `scripts/*`, the allow-list, `pyproject.toml`, CI). The central trust promise (read-only against M365) holds up. I could not find a path to the transport for a non-GET request. No finding is Critical. The defects below are robustness and contract-portability problems.

Tests were read for correctness of what they assert. The files read in full were `fake_graph.py`, the fake clock, `conftest.py`, `test_transport_guard.py`, `test_batch_hook.py`, `test_redirects.py`, `test_logging_capture.py`, `test_concurrency.py` and `tests/support/*`. The rest were sampled by test name. The tests that matter for the trust promise assert on the transport handler (`fake_graph.requests == []`), not on the policy, so they can fail.

No fallow structural findings were supplied. The necessity reference was read, and no necessity finding survived its evidence rule (the `_wait_for` TypeError guard and the `_send` RuntimeError exist for mypy narrowing, so they are not removable on provable grounds).

### Answers to the five areas the orchestrator asked about

1. **Non-GET reaching the transport: no path found.**
   - `_send` -> `_attempt` runs `policy.check(method, url, batch_body=...)` before the token is fetched. The request hook `guard_request` runs again before any transport. The hook uses `packaged_policy()`, never the injected policy, and re-parses the serialised body bytes with a duplicate-key-rejecting hook.
   - `follow_redirects=False`. The manual redirect loop (graph.py:599-611) re-checks every `Location` with `policy.check("GET", ...)` before the follow-up. A 3xx on a POST raises `redirect_on_batch`.
   - nextLinks are checked on arrival and again in `_attempt`.
   - The `$batch` re-queue (graph.py:956-963) rebuilds the body from the already-validated `urls[]`. Only throttled indices are re-sent, and the body passes the hook again.
   - Minor defence-in-depth gap: the hook's GET branch checks only host and prefix, so a raw-client GET can reach any path under `/v1.0/` (still a read). It does not inspect a `X-HTTP-Method-Override` header on a POST to `$batch`. Neither is reachable through `GraphClient`.
2. **Token, body, downloadUrl or header value reaching run.jsonl, exceptions or tracebacks: no leak found on the normal paths.**
   - `RequestEvent` and `RetryEvent` carry only closed-set fields.
   - `request-id` is regex-gated (graph.py:101-114).
   - Transport errors are re-raised `from None` with a class name only.
   - `GraphError` validates `reason` and `template`.
   - Residual risks are WR-01 (an exception that embeds the user-agent text), IN-02 (the free-text `WarningEvent.detail`, protected only by the scrub filter) and IN-03 (non-`TransportError` httpx2 exceptions escape unwrapped). The token source's own exceptions are also not wrapped.
3. **Regex anchors: both mechanisms behave correctly.** I ran `WarningEntry` and `WarningEvent` against `"timeout\n"`, `"xtimeout"` and `"graph_error_999"`, and both reject them. The fragility is real but different from what was suspected; see WR-04.
4. **`_load_env_vars` override: see WR-07.**
5. **Concurrency:**
   - The site slot is released on exception (`async with` inside the `@asynccontextmanager`).
   - The per-site in-flight semaphore wraps only the transport call, so it is not held across a backoff sleep. Cancellation releases it.
   - Gate and breaker state are mutated without an await between read and write, so they are safe under asyncio.
   - **tenacity ordering confirmed.** In the installed tenacity 9.2.1 (`__init__.py:468-470`), `_run_wait` runs before `_run_stop`. The early `return 0.0` in `_wait_for` (graph.py:625-628) is therefore necessary: without it the final failed attempt would trip the gate, bump `retries` and log a retry that never happens. The stop predicate `attempt_number > max_retries` gives exactly `max_retries` retries.
   - Remaining concurrency concerns are WR-05 and IN-04.

## Warnings

### WR-01: A non-ASCII `user_agent_company` passes validation, then crashes every request

**File:** `src/recover_assess/core/graph.py:213`
**Issue:** `build_user_agent` accepts any `str.isprintable()` text up to 64 characters, so `"Café"` is accepted. `httpx2` encodes header values as ASCII (`_models.py:85`, `value.encode(encoding or "ascii")`). I reproduced it: `build_request(..., headers={"User-Agent": "NONISV|Café|x"})` raises `UnicodeEncodeError`. The error surfaces on the first Graph request, not at configuration time. It is not a `TransportError`, so it escapes `_hop`'s handlers as a raw exception whose text includes the offending value. `HttpSettings.user_agent_company` (config.py:136) has no validator either.
**Fix:**
```python
if not company.isascii() or not company.isprintable() or "|" in company or len(company) > _MAX_COMPANY_LENGTH:
    raise ValueError(...)
```
Also add a `field_validator` on `HttpSettings.user_agent_company` that calls `build_user_agent`, so `load_settings` fails at start-up with a `ConfigError`. Add a test with a non-ASCII name.

### WR-02: Paging has no page limit or loop detection; a repeating or empty-page `nextLink` loops forever

**File:** `src/recover_assess/core/graph.py:826-844` (also `1065-1081`)
**Issue:** `iter_pages` follows `@odata.nextLink` until it is absent. `get_all`'s cap counts items, not pages, so a server (or proxy bug) that keeps returning `{"value": [], "@odata.nextLink": <same or new link>}` never reaches the cap and never terminates. `_complete_sub_pages` has the same exposure. The link is policy-valid each time, so nothing stops it. Each iteration also counts as a request and advances a clock that the per-request budget does not cover (the budget is per request, not per paging run).
**Fix:** Track the links already seen and raise `GraphError("paging_loop")` on a repeat. Add a hard `max_pages` bound, for example `ceil(cap / 1) + slack` or a constant like 10_000, raising `GraphError("too_many_pages")`. Cover both with a test using a self-referencing link.

### WR-03: nextLink validation uses the narrow, case-sensitive query-key allow-list, so legitimate Graph paging links may be refused

**File:** `src/recover_assess/core/graph_policy.py:48-50,226-228` (and `graph.py:836-837,1058,1080`)
**Issue:** `ALLOWED_QUERY_KEYS` is `{$select, $expand, $top, $filter, $skiptoken, token}`, matched exactly and case-sensitively. Server-supplied nextLinks are validated against the same set, with `Page.next_link` used verbatim. Graph nextLinks vary by resource: some carry `$skip=`, some `$skipToken` (camel case), and `$count`/`$orderby`/`$search`/`$format` can be echoed back. Any such link fails with `query_not_allowed`, so an otherwise healthy site fails closed mid-pagination. The test fake (`FakeGraph.paged`, fake_graph.py:126-138) only ever emits `$skiptoken`, so the suite cannot see this. The comment on `ID_SEGMENT` says confirmed by the Phase 2 smoke, but there is no equivalent confirmation for query keys.
**Fix:** Keep the strict key set for client-built queries. For links the server returns, validate host, prefix, path template and absence of `downloadUrl`, but do not apply the client-query key allow-list; or extend the set after a live smoke (`$skip`, `$skiptoken` compared case-insensitively). Add a fake that emits each real variant.

### WR-04: The published JSON Schema carries Python-only `\A`/`\Z` anchors, which breaks the "contract with later stages" outside Python

**File:** `src/recover_assess/core/errors.py:54-55`, `src/recover_assess/core/models/common.py:88`, `schemas/fact_sheet.schema.json:1478,1646`
**Issue:** `ERROR_CODE_PATTERN` is emitted verbatim into the schema as `"\\A(?:...)\\Z"`. JSON Schema 2020-12 patterns are ECMA-262 regexes, where `\A` and `\Z` are not anchors. In non-Unicode mode they are identity escapes matching the letters "A" and "Z"; in Unicode mode they are a syntax error. A JS, Java or .NET consumer of the schema either rejects every valid code or fails to compile. Python `jsonschema` happens to work. The root cause is that `Contract` needs `regex_engine="python-re"` (common.py:60) only because of the `\Z`; `log.py` avoids the pydantic pattern entirely and calls `is_error_code` (log.py:110-116). That gives two mechanisms for the same rule. A future published model that does not inherit `Contract` and uses `ErrorCodeStr` will fail at class definition (loud, not silent).
**Fix:** Use `^(?:...)$` for the pattern. Rust's `$` and ECMA's `$` both match only at end of input, so the default engine can be restored and `regex_engine="python-re"` dropped. Keep `is_error_code` with `fullmatch` for the Python-side belt-and-braces check. Regenerate the schema and goldens in the same commit (D-06 allows it before the Phase 6 freeze).

### WR-05: A single throttled or over-budget sub-request discards the whole `batch()` result, and 20 throttled sub-responses in one batch open the breaker immediately

**File:** `src/recover_assess/core/graph.py:681,935-942,1008-1013`
**Issue:** Two behaviours interact badly.
- `_requeue_wait` raises `ThrottledOut("budget")` (graph.py:680-681) when the longest sub `Retry-After` exceeds the remaining 300 s. The exception propagates out of `batch()`, so results already stored in the local `results` list (up to 19 successful sub-responses in that chunk, plus every earlier chunk) are lost. The docstring promises that items still throttled at the limit end as `throttled_out` results, which is inconsistent with the budget path.
- `_post_batch` calls `self._breaker.record()` once per throttled sub-response. A single 429-everything `$batch` of 20 therefore trips the breaker (threshold 20) in one response, before any retry is attempted, poisoning the session. `test_twenty_throttled_sub_responses_open_the_breaker` locks this in as intended, but it counts 1 server decision as 20 events.
**Fix:** On `ThrottledOut` ("budget" or "breaker") inside `_run_chunk`, mark the remaining throttled indices as `throttled_out` results and return the partial list instead of raising (or attach `partial_results` to the exception). Record the breaker once per throttled `$batch` response (or once per distinct `Retry-After` round) rather than once per sub-response, and document the choice.

### WR-06: Transport errors and 502/504 are never retried; one connection reset fails the whole site

**File:** `src/recover_assess/core/graph.py:510-537,590`
**Issue:** `RETRYABLE_STATUSES = {429, 503}`, and `httpx2.TransportError` (connect reset, read error) and timeouts raise `GraphTransportError` immediately. Microsoft's throttling and transient-error guidance also retries 502 and 504, and long collection runs over a corporate proxy see occasional resets. The project's own text says "429/503", so this may be a deliberate spec choice. Even so, a single transient failure aborts a site that may have hours of work behind it, and the circuit-breaker design suggests resilience was a goal.
**Fix:** Confirm against the spec. If resilience is wanted, retry `GraphTransportError` (non-timeout, plus read timeouts for idempotent GETs) and 502/504 through the same `AsyncRetrying` loop with the same budget and a separate counter. If the spec is intentionally strict, record the decision in a code comment and README.

### WR-07: `config.py` overrides the private `EnvSettingsSource._load_env_vars` and silently drops base-class behaviour

**File:** `src/recover_assess/core/config.py:157-164`
**Issue:** The subclass replaces `_load_env_vars` (an underscore method; `pydantic_settings/sources/providers/env.py:91-99` in 2.16.3) and returns `{name.casefold(): value}`. The base implementation also honours `env_ignore_empty`, `env_parse_none_str` and the Windows case-sensitivity fix-up, and the override loses all three. They are unused today, but a future `SettingsConfigDict(env_ignore_empty=True)` would be silently ignored. The method is also called from `EnvSettingsSource.__init__`, so it depends on the ContextVar being set at construction time. Other pydantic-settings providers (aws, azure, dotenv) override it too, which makes it a semi-stable seam, but a rename or signature change in a minor release (`~=2.16.3` allows only patch bumps) would break env loading, and the failure mode could be silent: an empty mapping instead of an error.
**Fix:** Pin an explicit test that fails if the hook is not called (for example: set a canary env var in a mapping and assert it reaches `Settings`, and assert `EnvSettingsSource._load_env_vars` still exists with the same signature). Prefer a public route: build the source from `parse_env_vars(context.environ, case_sensitive=False, ...)` and assign it to `source.env_vars` after construction instead of overriding the private hook. Document the dropped options.

### WR-08: CI has no job timeout or concurrency control, and runs twice for pushed pull-request branches

**File:** `.github/workflows/ci.yml:3-16`
**Issue:** The `check` job has no `timeout-minutes` (a hung subprocess test, such as `lint-imports` or the sdist build, burns the 6-hour default on two OS runners). There is no `concurrency` group with `cancel-in-progress`. `on: push:` and `on: pull_request:` with no branch filter run the whole matrix twice for every PR-branch push. Actions are correctly pinned by SHA and `permissions: contents: read` is set; those are good.
**Fix:**
```yaml
on:
  push:
    branches: [main]
  pull_request:
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
jobs:
  check:
    timeout-minutes: 20
```

### WR-09: `sweep_orphans` can delete another live run's in-flight temp file

**File:** `src/recover_assess/core/output.py:137-147`
**Issue:** The temp name is `.{name}.tmp-{pid}-{n}` but `sweep_orphans` removes every match regardless of whether `pid` is alive. Two concurrent `recover-assess` processes writing into the same run folder (or a resumed run racing an old one) would have one process delete the other's temp file between `fsync` and `replace`, producing `replace_failed` for the victim. `entry.unlink(missing_ok=True)` also raises `PermissionError` on Windows if the file is held open, aborting the sweep part-way. The function is unused in `src` today, so the defect is latent.
**Fix:** Parse the pid and skip files whose pid is the current process or is alive (`os.kill(pid, 0)` on POSIX, `OpenProcess` on Windows), or only sweep files older than a threshold. Catch `OSError` per entry and continue.

## Info

### IN-01: `strip_annotations` removes only `@microsoft.graph.*`; other bearer-like URLs pass through to callers

**File:** `src/recover_assess/core/graph.py:117-131`, `src/recover_assess/core/graph_allowlist.yaml:48-51`
**Issue:** The `@content.downloadUrl` variant (returned by the OneDrive consumer API) is not stripped. The allow-listed `/drives/{drive-id}/items/{item-id}/permissions` endpoint returns `link.webUrl`, which for "anyone" links is an anonymous-access URL, and nothing strips it. Phase 1 never logs bodies, so nothing leaks today, but the stated invariant ("annotations never reach a caller, a log or a fixture") is narrower than the data. Later collectors must project into models rather than store raw bodies.
**Fix:** Also drop keys whose case-folded name contains `downloadurl`, and note in the Phase 4 plan that permission `link.webUrl` must be reduced to scope and type before storage.

### IN-02: `WarningEvent.detail` is a free-text field, contradicting the "no free-text body field" guarantee

**File:** `src/recover_assess/core/log.py:103-116` (header comment at 3-9), `src/recover_assess/core/models/fact_sheet.py:353-357`
**Issue:** The module docstring says a response body cannot be logged by construction, but `WarningEvent.detail: str | None` and `WarningEntry.detail` accept arbitrary text. Protection then rests entirely on `scrub_text`, a deny-list regex that does not cover, for example, a bare signed URL without `sig=`, a site title or a user name.
**Fix:** Constrain `detail` to an identifier-shaped or length-limited pattern, or remove it until a collector needs it. Correct the docstring if it stays.

### IN-03: httpx2 exceptions that are not `TransportError` escape `_hop` unwrapped

**File:** `src/recover_assess/core/graph.py:507-537`
**Issue:** Only `TimeoutException` and `TransportError` are translated. `httpx2.DecodingError` (a malformed `Content-Encoding` body) is a `RequestError` but not a `TransportError`, and `httpx2.InvalidURL` / `StreamError` are not `RequestError` at all. They propagate with their original messages and `__context__`, bypassing the "no exception carries a URL" rule, and no run-log line is written for the failed attempt.
**Fix:** Catch `httpx2.RequestError` (after the two narrower clauses) and `httpx2.InvalidURL`, log a status-less request line and raise `GraphTransportError(type(exc).__name__, ...) from None`.

### IN-04: A session stays usable after its context exits, and `batch()` has a hard-coded item cap

**File:** `src/recover_assess/core/graph.py:425-433,875`
**Issue:** `open_session` releases the site slot on exit, but the returned `GraphSession` is a plain object. Retaining it and calling `get` after exit sends requests without a held slot, so the `max_sites` limit is only a convention. `max_items_per_result: int = 50_000` duplicates the `collect.max_items_per_library` default and is not wired to settings; `from_settings` does not pass it.
**Fix:** Mark the session closed in a `finally` and make `_send` refuse a closed session. Plumb the cap from settings or require it as an argument.

### IN-05: `verify_sha256.py` fails with a traceback on bad input and rejects BSD-style sidecars

**File:** `scripts/verify_sha256.py:22-33,55-56`
**Issue:** A missing archive or sidecar raises `FileNotFoundError`, and a sidecar in `SHA256 (file) = <hex>` form raises `ValueError`. Both produce a traceback with exit code 1 instead of a one-line failure. For a bootstrap integrity check that is still a failing exit, but the message is unhelpful and a wrapping script cannot tell mismatch from malformed input. Note too that the check only has value if the sidecar comes from a channel independent of the archive.
**Fix:** Catch `(OSError, ValueError)` in `main`, print a one-line `ERROR ...` and return 2. Accept both sidecar forms.

---

_Reviewed: 2026-11-15_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
