---
phase: "01"
slug: "foundation-contract-read-only-graph-client"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-17"
---

# Phase 01 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| PyPI / GitHub release to developer machine | Third-party code and the uv binary enter the environment | Packages, toolchain (integrity) |
| Working tree to git history / sdist | Anything not ignored can be committed or shipped | Client drafts, config, certificates (confidential) |
| Tool to Microsoft Graph | Bearer token leaves the process; untrusted responses return | Token (secret), tenant metadata |
| Caller- and server-supplied URLs to the policy | Untrusted strings decide where a token goes (nextLink, Location, $batch) | Token (secret) |
| Process to run.jsonl and exception text | Persisted and displayed data | Must carry no secret or identifying content |
| Operator YAML / environment to Settings | Untrusted configuration input; effective config is printed | Config values, secret references |
| Collector output to fact_sheet.json and schema | The contract every later stage trusts | Evidence (integrity) |
| Third-party GitHub Actions to CI runner | Action code runs with repository read access | Source (integrity) |
| Tool to shared tenant capacity | Retries and concurrency consume shared Graph limits | Availability |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-01-01 | Tampering | pyproject.toml / uv.lock resolution | high | mitigate | Exact-minor pins; human-approved lock; `uv lock --check` gate step 1; forbidden-package test | closed |
| T-01-02 | Information disclosure | .gitignore | high | mitigate | Anchored ignores for drafts, external config, out/, *.pem, *.pfx, token caches, docs/private/ | closed |
| T-01-03 | Information disclosure | GraphError messages | medium | mitigate | errors.py rejects non-identifier reasons and URL-shaped templates; tested | closed |
| T-01-04 | Tampering | GraphClient._send / guard_request | high | mitigate | Policy check before token fetch; request hook allows GET and only POST /v1.0/$batch; write-verb tests record zero transport calls | closed |
| T-01-05 | Information disclosure | RunLog / events | high | mitigate | Closed typed events, extra=forbid, no body field, scrub_text per line, canary tests | closed |
| T-01-06 | Information disclosure | make_http_client | medium | mitigate | Transport only injected by tests; no verify override; HTTP/2 off | closed |
| T-01-07 | Information disclosure | Transport/HTTP error text | medium | mitigate | Class-name reasons raised from None; no URL in str() | closed |
| T-01-08 | Tampering | ci.yml actions | medium | mitigate | Actions pinned to 40-hex SHAs; permissions contents: read; tested | closed |
| T-01-09 | Elevation of privilege | Import contracts / network-library bypass | high | mitigate | 5 import-linter contracts with violation fixtures; ruff TID251; AST ban test. Confirmed red on real CI (UAT test 2) | closed |
| T-01-10 | Repudiation | Local vs CI gate drift | low | mitigate | CI runs scripts/check.py; step order pinned by test | closed |
| T-01-11 | Tampering | YAML parsing | high | mitigate | YamlConfigSettingsSource (safe_load); extra=forbid; StrictStr | closed |
| T-01-12 | Tampering | Mistyped env vars | medium | mitigate | unknown_env_vars scan on every load; tests | closed |
| T-01-13 | Information disclosure | Client secrets in config | high | mitigate | Before-validator and env scan reject client_secret; include_input=False; config show never reads the password variable | closed |
| T-01-14 | Tampering | Partially written outputs | medium | mitigate | temp + fsync + replace, bounded PermissionError retry, finally-unlink, sweep_orphans (residual WR-09) | closed |
| T-01-15 | Information disclosure | Client data in repo or sdist | high | mitigate | Repo scan over tracked and untracked files; external private-terms file; blocked-terms gate; sdist content test | closed |
| T-01-16 | Tampering | Unknown evidence recorded as zero | high | mitigate | Per-section state plus validators rejecting values under unknown statuses | closed |
| T-01-17 | Tampering | Model/schema drift | medium | mitigate | Generated-only schema, parsed-JSON drift test and --check, pydantic minor pinned | closed |
| T-01-18 | Elevation of privilege | Policy canonicaliser bypass | high | mitigate | Canonicalise then exact host/prefix and anchored templates; 55 hostile cases; hypothesis properties | closed |
| T-01-19 | Information disclosure | /content, $value, downloadUrl | high | mitigate | DENIED_SEGMENTS; downloadUrl rejected in query values; no content template | closed |
| T-01-20 | Tampering | $batch write smuggling | high | mitigate | check_batch_body whitelist, GET-only, relative allow-listed urls, 1-20 unique ids; enforced in _send and in the hook | closed |
| T-01-21 | Information disclosure | nextLink token leak | high | mitigate | Policy check on receipt and again before the token is attached; hostile nextLink tests | closed |
| T-01-22 | Information disclosure | 3xx redirect follow | high | mitigate | follow_redirects=False; validated manual hops, max 3, none on POST | closed |
| T-01-23 | Information disclosure | downloadUrl annotations in bodies | high | mitigate | strip_annotations on every body and sub-response (residual IN-01) | closed |
| T-01-24 | Denial of service | Retry storms against the shared tenant | high | mitigate | Retry only 429/503, honour Retry-After, one client-wide gate, per-site breaker (20 in 60 s). Retry cap enforced at 6: HttpSettings.max_retries le=6 (fixed in e1d6972, tests test_max_retries_cannot_exceed_six / test_max_retries_accepts_six) | closed |
| T-01-25 | Denial of service | Hostile or huge Retry-After | medium | mitigate | 300 s budget checked before sleeping; unparseable/non-finite treated as absent; negative clamped | closed |
| T-01-26 | Tampering | $batch sub-response correlation | medium | mitigate | Correlate by case-insensitive unique id; one result per item; shuffled-response tests | closed |
| T-01-27 | Denial of service | Concurrency beyond limits | medium | mitigate | Site semaphore (2) and per-session in-flight semaphore (4) around transport calls (residual IN-04) | closed |
| T-01-28 | Information disclosure | run.jsonl across all client paths | high | mitigate | Typed events, GUID-gated request ids, scrub_text, 13 canary tests, audit_run_log | closed |
| T-01-29 | Information disclosure | Exception text and tracebacks | medium | mitigate | Identifier-shaped reasons and from-None chaining on GraphError/transport paths; non-TransportError exceptions from the HTTP layer escape unwrapped (see AR-01) | open — below high threshold (non-blocking) |
| T-01-30 | Tampering | uv toolchain bootstrap | high | mitigate | Versioned archive + .sha256 checked by scripts/verify_sha256.py; no piped installer; developer re-check recorded | closed |
| T-01-31 | Tampering | Schema generation | medium | mitigate | Generator-only writes via atomic_write_text; byte-identical rendering; LF via .gitattributes | closed |
| T-01-32 | Tampering | run.jsonl after interrupted append | medium | mitigate | One write + flush per line; repair on open; tail ignored, corrupt terminated line raises | closed |
| T-01-33 | Tampering | guard_request $batch body | high | mitigate | Hook parses serialised body, requires application/json, rejects duplicate keys, fails closed, always uses packaged_policy() | closed |
| T-01-SC | Tampering | Package installs (all plans) | high | mitigate | Legitimacy checkpoint in 01-01; no dependency changes in 01-02..01-12; `uv sync --locked` in CI; post-phase quick tasks checked (lock and requirements unchanged by 261117-i8j) | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01 | T-01-29 | Exceptions raised inside the HTTP request call that are not TransportError (for example a decoding error, or a non-ASCII user_agent_company failing on first send) reach the caller unwrapped and without a run-log line. Probes found no URL or token in str() or the traceback. Fix deferred to the open review items IN-03 (catch RequestError/InvalidURL) and WR-01 (validate the user agent as ASCII at config load). | developer | 2026-11-17 |
| AR-02 | T-01-SC (quick 261117-i8j) | `[build-system] requires` widened to uv_build>=0.11,<0.14 so uv 0.11+ builds offline with its built-in backend. A frontend that fetches the backend itself does so unhashed, as before with the narrower range; the documented routes (offline uv build, or pip --require-hashes build.txt with --no-build-isolation) avoid it. Registered by the quick task as T-261117-i8j-04 (low, accept). | developer | 2026-11-17 |

*Accepted risks do not resurface in future audit runs.*

Informational residuals (from 01-REVIEW.md, still open in 01-REVIEW-DISPOSITION.md, not registered threats): WR-02 (no paging page limit or loop detection), IN-01 (`@content.downloadUrl` and permission `link.webUrl` not stripped), IN-02 (`WarningEvent.detail` free text, unused today), IN-04 (session usable after context exit bypasses the site slot), WR-09 (`sweep_orphans` does not check temp-file pid liveness), hook GET branch ignores `X-HTTP-Method-Override` (unreachable through GraphClient).

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-17 | 34 | 32 | 2 (1 blocking: T-01-24; 1 non-blocking: T-01-29) | gsd-security-auditor |
| 2026-11-17 | 34 | 33 | 1 non-blocking (T-01-29, accepted as AR-01) | orchestrator after fix e1d6972 (gate 8/8 green) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-17
