---
phase: 01-foundation-contract-read-only-graph-client
reviewed: 2026-11-17T00:00:00Z
depth: standard
files_reviewed: 16
files_reviewed_list:
  - .claude/CLAUDE.md
  - .gitattributes
  - README.md
  - pyproject.toml
  - requirements/build.txt
  - requirements/locked.txt
  - scripts/blocked_terms.py
  - scripts/check.py
  - scripts/export_requirements.py
  - src/recover_assess/core/config.py
  - tests/unit/test_blocked_terms.py
  - tests/unit/test_check_script.py
  - tests/unit/test_config.py
  - tests/unit/test_export_requirements.py
  - tests/unit/test_wheel_build.py
  - uv.lock
findings:
  critical: 0
  warning: 5
  info: 6
  total: 11
  necessity: 1
carried_forward: 14
incremental_since: 74b4892
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-11-17
**Depth:** standard (incremental re-review since 74b4892)
**Files Reviewed:** 16
**Status:** issues_found

## Summary

This is an incremental re-review of the changes since the 2026-11-15 report. The new surface is a hash-based blocked-term gate (`scripts/blocked_terms.py`), a hash-locked pip requirements export with a drift check (`scripts/export_requirements.py`, `requirements/*.txt`), a widened `uv_build>=0.11,<0.14` build requirement, the README install, TLS and pip-fallback documentation, and the `http.max_retries` cap at 6.

I read every changed script and test in full and the README diff. I also ran the checks that decide the findings:
- `export_requirements.py --check` reports both files in sync, and `uv lock --check --offline` passes, so `uv.lock`, `pyproject.toml` and `requirements/*.txt` are mutually consistent.
- `blocked_terms.py` reports clean over 136 tracked files.
- I built the sdist with uv 0.13.8 and listed its members (WR-13).
- I fed the scanner synthetic encodings and word shapes, using a harmless word and not any real term (WR-10, IN-08).

No new finding is Critical. The retry cap (`le=6`) and its tests are correct, and the lockfile addition is consistent. The defects are in the new gate's coverage and threat model, and in packaging consistency.

No fallow structural findings were supplied. The necessity reference was read.

None of the 14 prior findings is resolved by the changed files. `config.py` changed only on `max_retries`, which is unrelated to WR-07. `ci.yml` and `verify_sha256.py` are unchanged, so WR-08 and IN-05 stand. All 14 are carried forward below.

## Critical Issues

None.

## Warnings

### WR-10: The blocked-term scan silently skips any file that contains a NUL byte or is not valid UTF-8

**File:** `scripts/blocked_terms.py:107-115`
**Issue:** `_scan` skips a file when `b"\x00" in data` or `data.decode("utf-8")` fails, and only counts it in the "skipped" tally of a clean message. A UTF-16 text file (Windows PowerShell 5.1 `>` redirection and `Out-File` write UTF-16 by default, which this project's Windows-first users will use), or a Latin-1 or cp1252 text file, therefore passes the gate with a blocked word in it. I confirmed both: a UTF-16 line and a Latin-1 line containing the test word are skipped and produce no hit. The gate is documented as "fail closed" for git errors, but it fails open for file content. The tokeniser only needs ASCII `[A-Za-z0-9]+` runs, so skipping is unnecessary.
**Fix:** Decode every file leniently and scan it, so no text file can evade by encoding. For UTF-16, check for a BOM and decode accordingly.
```python
data = target.read_bytes()
if data.startswith((b"\xff\xfe", b"\xfe\xff")):
    text = data.decode("utf-16", errors="replace")
else:
    text = data.decode("utf-8", errors="replace")  # NULs and bad bytes become separators
hits.extend(scan_text(text, path=name, blocked=blocked))
```
If binary files must stay skipped, make the skip list explicit by extension or by a git attribute, and fail on an unexpected skip. Update `test_binary_invalid_utf8_and_deleted_files_are_skipped` to assert the new behaviour.

### WR-11: Unsalted SHA-256 digests of single words are reversible by dictionary attack, so the committed list effectively discloses the terms

**File:** `scripts/blocked_terms.py:36-44`
**Issue:** The stated goal (module docstring, lines 5-6) is that the repository "must never spell those words". The mechanism is unsalted SHA-256 of one lowercase word per digest. Organisation and product names are low-entropy, and every digest is a single dictionary word or name. Anyone with read access to the repo, including any other company the playbook is packaged for, can recover the words from the five digests in seconds with a wordlist and `hashlib`. The hashing hides the words from casual grep and from CI logs, but not from a determined reader, and the constraint it implements is a Portability / IP constraint. The `--hash-term` helper also makes the recipe public.
**Fix:** Use a keyed digest whose key is not in the repo: `HMAC-SHA256(key, token)`, with the key supplied from a CI secret or an untracked local file, and the digest list stored with that external config (the project already treats the organisation's config as external). If the list must stay in the repo, state plainly in the docstring and README that it is obfuscation, not secrecy, and do not describe it as a guarantee. A slow KDF is not a fix here: it only raises the cost per guess, and the gate has to hash every token of every file.

### WR-12: File paths are never scanned, and a path hit would echo the term

**File:** `scripts/blocked_terms.py:102-117,159-161`
**Issue:** `_scan` tokenises file content only. A tracked file or directory whose name contains a blocked word (for example `docs/<name>-notes.md` or `fixtures/<name>/`) passes. The spec's file-name examples are exactly where such words appear. If a path check were added naively, `main` prints `hit.path` (line 161), which would then print the blocked word into CI logs, defeating the no-excerpt design.
**Fix:** Run `scan_text(name, ...)` on each path as well as its content, report such hits as `<redacted path #N>: blocked term in file name` (an index, not the path), and cover it with a test using the harmless word in a file name.

### WR-13: The sdist ships `tests/**` and `scripts/**` but not `requirements/`, so the new committed-file tests fail when run from the sdist

**File:** `pyproject.toml:41-49`, `tests/unit/test_export_requirements.py:216-240`
**Issue:** `[tool.uv.build-backend] source-include` lists `scripts/**`, `tests/**` and `uv.lock` but not `requirements/**`. I built the sdist and confirmed it contains `scripts/export_requirements.py`, `tests/unit/test_export_requirements.py` and `uv.lock` and no `requirements/*.txt`. The three tests that read `ROOT / "requirements/..."` (`test_committed_locked_txt_pins_are_hashed_and_match_uv_lock`, `test_committed_locked_txt_covers_runtime_dependencies_only`, `test_committed_build_txt_is_only_the_build_backend`) then raise `FileNotFoundError` in any tree unpacked from the sdist. The sibling `test_blocked_terms.py` already handles an exported tree (`pytest.skip` when `.git` is absent), which shows that running the suite from the sdist is an intended use. `test_sdist_contents.py` does not check for this gap.
**Fix:** Add `"requirements/**"` to `source-include` (the files carry hashes only and no secrets), and add an assertion in `test_sdist_contents.py` that `requirements/locked.txt` ships. Alternatively skip those three tests when `requirements/` is absent.

### WR-14: The `<0.14` upper bound makes the README's "uv 0.11 or later" offline build break on newer uv, and the widened lower bound is untested

**File:** `pyproject.toml:35`, `README.md:220,311`, `tests/unit/test_wheel_build.py:25-41`
**Issue:** uv uses its built-in backend, and so builds offline, only when its own version satisfies `build-system.requires`. With `uv_build>=0.11,<0.14`, a user on uv 0.14 or later falls back to downloading the backend, and `uv build --wheel --offline` (the README's primary route) fails. The README says "uv 0.11 or later" with no upper limit. CI pins 0.13.8 (`ci.yml` `version: "0.13.8"`), so nothing catches the break until a user upgrades. Separately, the lower bound now admits uv_build 0.11 and 0.12, but the only build the suite runs (`test_wheel_build.py`) uses the pinned 0.13.8. That compatibility is claimed, not verified.
**Fix:** State "uv 0.11 to 0.13" in the README (lines 220 and 311) and keep `<0.14` in sync with it, with a note that the range moves with the pin. Add a CI matrix leg that runs the wheel-build test with uv 0.11.x, or narrow the lower bound to what is verified.

## Info

### IN-06: README claims pip "uses the Windows trust store by default", which depends on the pip version in the new venv

**File:** `README.md:127-130`
**Issue:** pip uses `truststore` by default only from pip 24.2. A venv created from an older 3.12 patch release bundles an older pip, which uses its own CA bundle and fails behind a TLS-inspecting proxy, which is the scenario this section covers.
**Fix:** Say "pip 24.2 or later" and add `python -m pip install --upgrade pip` (through the mirror) or `--use-feature=truststore` to the proxy notes.

### IN-07: The retry cap is enforced only in the settings layer, not in `GraphClient`

**File:** `src/recover_assess/core/config.py:133-134`, `src/recover_assess/core/graph.py:328,334`
**Issue:** The new comment and tests state that config "may lower the retry count, never raise it" (GRPH-05, T-01-24). `GraphClient.__init__` only rejects negative values, so `GraphClient(max_retries=50)` still works. Today the only production caller is `from_settings`, so the limit holds, but the cap lives in one layer and the constant it mirrors (`MAX_RETRIES_DEFAULT = 6` in `throttle.py`) is not referenced by the config field, so the two numbers can drift. `test_out_of_range_values_are_rejected` still passes with `"11"` but no longer tests a boundary.
**Fix:** In `config.py` write `le=MAX_RETRIES_DEFAULT` (import it from `throttle`, if the import contracts allow it), and add `if max_retries > MAX_RETRIES_DEFAULT: raise ValueError(...)` in the client constructor.

### IN-08: Lower-case concatenated forms of a multi-word name are not matched, and the real-digest test pins an exact count

**File:** `scripts/blocked_terms.py:9-15,61-67`, `tests/unit/test_blocked_terms.py:93-96`
**Issue:** By design, each word is blocked separately. A name written as one lower-case run, such as `wordone` + `wordtwo` joined in a host name, a package name or a path segment (`x.wordonewordtwo.com`), yields one token that matches neither digest. I confirmed that a joined lower-case run produces no hit while the camelCase and digit-suffixed forms do. Hostnames are exactly the form the project constraints name. Separately, `test_the_real_digest_set_is_five_lowercase_sha256_values` fails on any legitimate addition of a term, which turns the documented "add a digest" procedure into a two-file change.
**Fix:** Document the joined-run limitation in the docstring, or add an optional digest list for joined forms. Replace the count assertion with the shape check only (`all(HEX64.match(d) ...)`, non-empty).

### IN-09: A tracked file name that is not valid UTF-8 crashes the scanner with a traceback and exit code 1

**File:** `scripts/blocked_terms.py:93,155`
**Issue:** `proc.stdout.decode("utf-8")` raises `UnicodeDecodeError`, a `ValueError`, which `main` does not catch (it catches `CalledProcessError`, `FileNotFoundError` and `OSError`). The run ends with a traceback and exit code 1, the code the docstring reserves for "hits found", not 2.
**Fix:** Decode with `os.fsdecode` on the split bytes, or add `UnicodeDecodeError` to the caught exceptions in `main` so it returns 2.

### IN-10: `generate()` can leave the two requirements files out of step, and a stale `.tmp` on failure

**File:** `scripts/export_requirements.py:117-127`
**Issue:** The loop computes and writes each file in turn. If the second `uv export` fails, `requirements/locked.txt` is already replaced and `build.txt` is not, so the pair is inconsistent until the next successful run. A failed `write_text` leaves `requirements/<name>.txt.tmp` behind.
**Fix:** Compute every `expected_text` first, then write and replace in a second loop, with a `try/finally` that unlinks the temp file.

### IN-11: `build_steps(environ=...)` is a parameter that is deliberately ignored

**Category:** necessity
**File:** `scripts/check.py:65-67`
**Issue:** The function begins `del environ  # reserved: the argv does not currently vary with the environment`. Every caller (`main`, and the tests, which pass `environ={}` or a CI mapping) supplies a value that is discarded, and the new steps added in this change did not use it either. This is generality without instantiation: a parameter reserved for a future need, with a `del` to keep the linter quiet. The evidence is the function body and the lack of any read of `environ` in it. This is a judgment call, so Info.
**Fix:** Drop the parameter and update the call sites and tests, or keep it and use it (for example to select the `in_ci` behaviour there instead of in `run_steps`).

## Carried forward from the 2026-11-15 review

None resolved by the changed files. Bodies are unchanged from the prior report.

### WR-01 (warning, `src/recover_assess/core/graph.py:213`): A non-ASCII `user_agent_company` passes validation, then crashes every request

**File:** `src/recover_assess/core/graph.py:213`
**Issue:** `build_user_agent` accepts any `str.isprintable()` text up to 64 characters, so `"Café"` is accepted. `httpx2` encodes header values as ASCII (`_models.py:85`, `value.encode(encoding or "ascii")`). I reproduced it: `build_request(..., headers={"User-Agent": "NONISV|Café|x"})` raises `UnicodeEncodeError`. The error surfaces on the first Graph request, not at configuration time. It is not a `TransportError`, so it escapes `_hop`'s handlers as a raw exception whose text includes the offending value. `HttpSettings.user_agent_company` (config.py:136) has no validator either.
**Fix:**
```python
if not company.isascii() or not company.isprintable() or "|" in company or len(company) > _MAX_COMPANY_LENGTH:
    raise ValueError(...)
```
Also add a `field_validator` on `HttpSettings.user_agent_company` that calls `build_user_agent`, so `load_settings` fails at start-up with a `ConfigError`. Add a test with a non-ASCII name.

### WR-02 (warning, `src/recover_assess/core/graph.py:826-844`): Paging has no page limit or loop detection; a repeating or empty-page `nextLink` loops forever

**File:** `src/recover_assess/core/graph.py:826-844` (also `1065-1081`)
**Issue:** `iter_pages` follows `@odata.nextLink` until it is absent. `get_all`'s cap counts items, not pages, so a server (or proxy bug) that keeps returning `{"value": [], "@odata.nextLink": <same or new link>}` never reaches the cap and never terminates. `_complete_sub_pages` has the same exposure. The link is policy-valid each time, so nothing stops it. Each iteration also counts as a request and advances a clock that the per-request budget does not cover (the budget is per request, not per paging run).
**Fix:** Track the links already seen and raise `GraphError("paging_loop")` on a repeat. Add a hard `max_pages` bound, for example `ceil(cap / 1) + slack` or a constant like 10_000, raising `GraphError("too_many_pages")`. Cover both with a test using a self-referencing link.

### WR-03 (warning, `src/recover_assess/core/graph_policy.py:48-50,226-228`): nextLink validation uses the narrow, case-sensitive query-key allow-list, so legitimate Graph paging links may be refused

**File:** `src/recover_assess/core/graph_policy.py:48-50,226-228` (and `graph.py:836-837,1058,1080`)
**Issue:** `ALLOWED_QUERY_KEYS` is `{$select, $expand, $top, $filter, $skiptoken, token}`, matched exactly and case-sensitively. Server-supplied nextLinks are validated against the same set, with `Page.next_link` used verbatim. Graph nextLinks vary by resource: some carry `$skip=`, some `$skipToken` (camel case), and `$count`/`$orderby`/`$search`/`$format` can be echoed back. Any such link fails with `query_not_allowed`, so an otherwise healthy site fails closed mid-pagination. The test fake (`FakeGraph.paged`, fake_graph.py:126-138) only ever emits `$skiptoken`, so the suite cannot see this. The comment on `ID_SEGMENT` says confirmed by the Phase 2 smoke, but there is no equivalent confirmation for query keys.
**Fix:** Keep the strict key set for client-built queries. For links the server returns, validate host, prefix, path template and absence of `downloadUrl`, but do not apply the client-query key allow-list; or extend the set after a live smoke (`$skip`, `$skiptoken` compared case-insensitively). Add a fake that emits each real variant.

### WR-04 (warning, `src/recover_assess/core/errors.py:54-55`, `models/common.py:88`, `schemas/fact_sheet.schema.json:1478,1646`): The published JSON Schema carries Python-only `\A`/`\Z` anchors, which breaks the "contract with later stages" outside Python

**File:** `src/recover_assess/core/errors.py:54-55`, `src/recover_assess/core/models/common.py:88`, `schemas/fact_sheet.schema.json:1478,1646`
**Issue:** `ERROR_CODE_PATTERN` is emitted verbatim into the schema as `"\\A(?:...)\\Z"`. JSON Schema 2020-12 patterns are ECMA-262 regexes, where `\A` and `\Z` are not anchors. In non-Unicode mode they are identity escapes matching the letters "A" and "Z"; in Unicode mode they are a syntax error. A JS, Java or .NET consumer of the schema either rejects every valid code or fails to compile. Python `jsonschema` happens to work. The root cause is that `Contract` needs `regex_engine="python-re"` (common.py:60) only because of the `\Z`; `log.py` avoids the pydantic pattern entirely and calls `is_error_code` (log.py:110-116). That gives two mechanisms for the same rule. A future published model that does not inherit `Contract` and uses `ErrorCodeStr` will fail at class definition (loud, not silent).
**Fix:** Use `^(?:...)$` for the pattern. Rust's `$` and ECMA's `$` both match only at end of input, so the default engine can be restored and `regex_engine="python-re"` dropped. Keep `is_error_code` with `fullmatch` for the Python-side belt-and-braces check. Regenerate the schema and goldens in the same commit (D-06 allows it before the Phase 6 freeze).

### WR-05 (warning, `src/recover_assess/core/graph.py:681,935-942,1008-1013`): A single throttled or over-budget sub-request discards the whole `batch()` result, and 20 throttled sub-responses in one batch open the breaker immediately

**File:** `src/recover_assess/core/graph.py:681,935-942,1008-1013`
**Issue:** Two behaviours interact badly.
- `_requeue_wait` raises `ThrottledOut("budget")` (graph.py:680-681) when the longest sub `Retry-After` exceeds the remaining 300 s. The exception propagates out of `batch()`, so results already stored in the local `results` list (up to 19 successful sub-responses in that chunk, plus every earlier chunk) are lost. The docstring promises that items still throttled at the limit end as `throttled_out` results, which is inconsistent with the budget path.
- `_post_batch` calls `self._breaker.record()` once per throttled sub-response. A single 429-everything `$batch` of 20 therefore trips the breaker (threshold 20) in one response, before any retry is attempted, poisoning the session. `test_twenty_throttled_sub_responses_open_the_breaker` locks this in as intended, but it counts 1 server decision as 20 events.
**Fix:** On `ThrottledOut` ("budget" or "breaker") inside `_run_chunk`, mark the remaining throttled indices as `throttled_out` results and return the partial list instead of raising (or attach `partial_results` to the exception). Record the breaker once per throttled `$batch` response (or once per distinct `Retry-After` round) rather than once per sub-response, and document the choice.

### WR-06 (warning, `src/recover_assess/core/graph.py:510-537,590`): Transport errors and 502/504 are never retried; one connection reset fails the whole site

**File:** `src/recover_assess/core/graph.py:510-537,590`
**Issue:** `RETRYABLE_STATUSES = {429, 503}`, and `httpx2.TransportError` (connect reset, read error) and timeouts raise `GraphTransportError` immediately. Microsoft's throttling and transient-error guidance also retries 502 and 504, and long collection runs over a corporate proxy see occasional resets. The project's own text says "429/503", so this may be a deliberate spec choice. Even so, a single transient failure aborts a site that may have hours of work behind it, and the circuit-breaker design suggests resilience was a goal.
**Fix:** Confirm against the spec. If resilience is wanted, retry `GraphTransportError` (non-timeout, plus read timeouts for idempotent GETs) and 502/504 through the same `AsyncRetrying` loop with the same budget and a separate counter. If the spec is intentionally strict, record the decision in a code comment and README.

### WR-07 (warning, `src/recover_assess/core/config.py:157-164`): `config.py` overrides the private `EnvSettingsSource._load_env_vars` and silently drops base-class behaviour

**File:** `src/recover_assess/core/config.py:157-164`
**Issue:** The subclass replaces `_load_env_vars` (an underscore method; `pydantic_settings/sources/providers/env.py:91-99` in 2.16.3) and returns `{name.casefold(): value}`. The base implementation also honours `env_ignore_empty`, `env_parse_none_str` and the Windows case-sensitivity fix-up, and the override loses all three. They are unused today, but a future `SettingsConfigDict(env_ignore_empty=True)` would be silently ignored. The method is also called from `EnvSettingsSource.__init__`, so it depends on the ContextVar being set at construction time. Other pydantic-settings providers (aws, azure, dotenv) override it too, which makes it a semi-stable seam, but a rename or signature change in a minor release (`~=2.16.3` allows only patch bumps) would break env loading, and the failure mode could be silent: an empty mapping instead of an error.
**Fix:** Pin an explicit test that fails if the hook is not called (for example: set a canary env var in a mapping and assert it reaches `Settings`, and assert `EnvSettingsSource._load_env_vars` still exists with the same signature). Prefer a public route: build the source from `parse_env_vars(context.environ, case_sensitive=False, ...)` and assign it to `source.env_vars` after construction instead of overriding the private hook. Document the dropped options.

### WR-08 (warning, `.github/workflows/ci.yml:3-16`): CI has no job timeout or concurrency control, and runs twice for pushed pull-request branches

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

### WR-09 (warning, `src/recover_assess/core/output.py:137-147`): `sweep_orphans` can delete another live run's in-flight temp file

**File:** `src/recover_assess/core/output.py:137-147`
**Issue:** The temp name is `.{name}.tmp-{pid}-{n}` but `sweep_orphans` removes every match regardless of whether `pid` is alive. Two concurrent `recover-assess` processes writing into the same run folder (or a resumed run racing an old one) would have one process delete the other's temp file between `fsync` and `replace`, producing `replace_failed` for the victim. `entry.unlink(missing_ok=True)` also raises `PermissionError` on Windows if the file is held open, aborting the sweep part-way. The function is unused in `src` today, so the defect is latent.
**Fix:** Parse the pid and skip files whose pid is the current process or is alive (`os.kill(pid, 0)` on POSIX, `OpenProcess` on Windows), or only sweep files older than a threshold. Catch `OSError` per entry and continue.

### IN-01 (info, `src/recover_assess/core/graph.py:117-131`): `strip_annotations` removes only `@microsoft.graph.*`; other bearer-like URLs pass through to callers

**File:** `src/recover_assess/core/graph.py:117-131`, `src/recover_assess/core/graph_allowlist.yaml:48-51`
**Issue:** The `@content.downloadUrl` variant (returned by the OneDrive consumer API) is not stripped. The allow-listed `/drives/{drive-id}/items/{item-id}/permissions` endpoint returns `link.webUrl`, which for "anyone" links is an anonymous-access URL, and nothing strips it. Phase 1 never logs bodies, so nothing leaks today, but the stated invariant ("annotations never reach a caller, a log or a fixture") is narrower than the data. Later collectors must project into models rather than store raw bodies.
**Fix:** Also drop keys whose case-folded name contains `downloadurl`, and note in the Phase 4 plan that permission `link.webUrl` must be reduced to scope and type before storage.

### IN-02 (info, `src/recover_assess/core/log.py:103-116`): `WarningEvent.detail` is a free-text field, contradicting the "no free-text body field" guarantee

**File:** `src/recover_assess/core/log.py:103-116` (header comment at 3-9), `src/recover_assess/core/models/fact_sheet.py:353-357`
**Issue:** The module docstring says a response body cannot be logged by construction, but `WarningEvent.detail: str | None` and `WarningEntry.detail` accept arbitrary text. Protection then rests entirely on `scrub_text`, a deny-list regex that does not cover, for example, a bare signed URL without `sig=`, a site title or a user name.
**Fix:** Constrain `detail` to an identifier-shaped or length-limited pattern, or remove it until a collector needs it. Correct the docstring if it stays.

### IN-03 (info, `src/recover_assess/core/graph.py:507-537`): httpx2 exceptions that are not `TransportError` escape `_hop` unwrapped

**File:** `src/recover_assess/core/graph.py:507-537`
**Issue:** Only `TimeoutException` and `TransportError` are translated. `httpx2.DecodingError` (a malformed `Content-Encoding` body) is a `RequestError` but not a `TransportError`, and `httpx2.InvalidURL` / `StreamError` are not `RequestError` at all. They propagate with their original messages and `__context__`, bypassing the "no exception carries a URL" rule, and no run-log line is written for the failed attempt.
**Fix:** Catch `httpx2.RequestError` (after the two narrower clauses) and `httpx2.InvalidURL`, log a status-less request line and raise `GraphTransportError(type(exc).__name__, ...) from None`.

### IN-04 (info, `src/recover_assess/core/graph.py:425-433,875`): A session stays usable after its context exits, and `batch()` has a hard-coded item cap

**File:** `src/recover_assess/core/graph.py:425-433,875`
**Issue:** `open_session` releases the site slot on exit, but the returned `GraphSession` is a plain object. Retaining it and calling `get` after exit sends requests without a held slot, so the `max_sites` limit is only a convention. `max_items_per_result: int = 50_000` duplicates the `collect.max_items_per_library` default and is not wired to settings; `from_settings` does not pass it.
**Fix:** Mark the session closed in a `finally` and make `_send` refuse a closed session. Plumb the cap from settings or require it as an argument.

### IN-05 (info, `scripts/verify_sha256.py:22-33,55-56`): `verify_sha256.py` fails with a traceback on bad input and rejects BSD-style sidecars

**File:** `scripts/verify_sha256.py:22-33,55-56`
**Issue:** A missing archive or sidecar raises `FileNotFoundError`, and a sidecar in `SHA256 (file) = <hex>` form raises `ValueError`. Both produce a traceback with exit code 1 instead of a one-line failure. For a bootstrap integrity check that is still a failing exit, but the message is unhelpful and a wrapping script cannot tell mismatch from malformed input. Note too that the check only has value if the sidecar comes from a channel independent of the archive.
**Fix:** Catch `(OSError, ValueError)` in `main`, print a one-line `ERROR ...` and return 2. Accept both sidecar forms.

---

_Reviewed: 2026-11-17_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
