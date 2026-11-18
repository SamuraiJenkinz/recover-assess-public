---
phase: 01-foundation-contract-read-only-graph-client
verified: 2026-11-18T01:20:00Z
status: passed
score: 5/5 must-haves verified
covered_files:
  - ".github/workflows/ci.yml"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-01-PLAN.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-01-SUMMARY.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-02-PLAN.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-02-SUMMARY.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-03-PLAN.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-03-SUMMARY.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-04-PLAN.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-04-SUMMARY.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-05-PLAN.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-05-SUMMARY.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-06-PLAN.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-06-SUMMARY.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-07-PLAN.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-07-SUMMARY.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-08-PLAN.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-08-SUMMARY.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-09-PLAN.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-09-SUMMARY.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-10-PLAN.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-10-SUMMARY.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-11-PLAN.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-11-SUMMARY.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-12-PLAN.md"
  - ".planning/phases/01-foundation-contract-read-only-graph-client/01-12-SUMMARY.md"
  - "README.md"
  - "pyproject.toml"
  - "requirements/build.txt"
  - "requirements/locked.txt"
  - "schemas/fact_sheet.schema.json"
  - "scripts/blocked_terms.py"
  - "scripts/check.py"
  - "scripts/export_requirements.py"
  - "scripts/gen_schemas.py"
  - "src/recover_assess/core/config.py"
  - "src/recover_assess/core/graph.py"
  - "src/recover_assess/core/graph_policy.py"
  - "src/recover_assess/core/log.py"
  - "src/recover_assess/core/models/common.py"
  - "src/recover_assess/core/models/fact_sheet.py"
  - "src/recover_assess/core/output.py"
  - "src/recover_assess/core/throttle.py"
covered_digest: "v4:sha256:c43aca2297016439936c64015535b3401756dea2b0d3ccf561a21ccef4cfb19c"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 4/5
  gaps_closed:
    - "SC1 clean-machine install and hosted CI enforcement (both human items passed in 01-UAT.md)"
  gaps_remaining: []
  regressions: []
---

# Phase 1: Foundation, Contract & Read-Only Graph Client Verification Report

**Phase Goal:** A developer has a CI-enforced scaffold in which the only path to Microsoft 365 is a tested read-only Graph client, and the fact-sheet v1.0 contract is generated from code
**Verified:** 2026-11-18
**Status:** passed
**Re-verification:** Yes. The previous report (2026-11-16, `human_needed`) was stale: README, pyproject, `scripts/check.py`, `config.py` and new files (`scripts/blocked_terms.py`, `scripts/export_requirements.py`, `requirements/*.txt`) changed after it ran. Every truth was re-checked against the current tree.

## Goal Achievement

The goal is achieved. The two items that blocked the previous report are resolved by observed evidence in `01-UAT.md` (a non-admin proxied install on a corporate workstation, and hosted CI green on both OS runners and red on a deliberate import-contract violation, with the failing contract named). I did not re-raise them. No new item needs a human. No must-have is FAILED. The advisory review findings are carried as warnings below; none defeats a must-have.

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Clean-machine `uv sync --locked` installs pinned Python 3.12 (with `UV_SYSTEM_CERTS` guidance); CI runs ruff, mypy strict and import-linter; a deliberate violation turns CI red | VERIFIED | `.python-version` = 3.12; README carries `UV_SYSTEM_CERTS` (lines 34, 53, 59) and `UV_PYTHON_DOWNLOADS=never` (line 136) guidance; `uv run recover-assess --version` prints 0.1.0 (run today). Gate re-run today: `uv run --frozen python scripts/check.py` exit 0, 8/8 steps PASS (uv-lock-check, requirements-export, ruff-check, ruff-format, mypy, import-contracts, blocked-terms, pytest), 948 passed. Import-linter output: 5 contracts kept, 0 broken (core-not-cli; httpx2 only in graph/providers; LLM SDKs only in providers; score/agent/report no network libs; typer/rich only in cli). `tests/unit/test_import_contracts.py` injects each violation into a tree copy and asserts the contract breaks. UAT: install passed on a non-admin proxied workstation; hosted CI green on windows-latest and ubuntu-latest, red on a throwaway branch with `core` importing `cli`. |
| 2 | Every non-GET verb, non-allow-listed path, `/content`, beta URL, `POST /$batch` with a non-GET sub-request, and hostile nextLink/redirect URLs are rejected before any network call | VERIFIED | Fresh run of my recording-MockTransport probe today: raw client POST/PUT/PATCH/DELETE/OPTIONS/HEAD/"Post" all raise `WriteAttemptError` and never reach the transport; beta path `WriteAttemptError`; foreign host and http scheme `UrlNotAllowedError`. Via `GraphSession.get`: `/content` (two shapes), `/beta`, `/me`, `/users`, `..` traversal, `//evil.com`, `%2e%2e`, unlisted query key all refused with reasons; `$batch` with a DELETE sub-request and with a `body` key refused at the hook. Transport only saw the intended GETs. Two independent guards (`ReadOnlyPolicy.check`, and the `guard_request` event hook re-parsing serialised bytes); `follow_redirects=False`. Hostile nextLink/redirect tests: `test_paging.py`, `test_redirects.py`, `test_batch.py`. 13-template allow-list pinned by `test_allowlist_pinned.py`. |
| 3 | Under simulated throttling: pages to end (cap marks `truncated`), `$batch` <=20 with re-queue, Retry-After then jittered backoff (<=6 retries, 5-minute give-up), shared gate, per-site breaker to `throttled_out`, <=4 in-flight per site and 2 sites, `graph_stats` | VERIFIED | `throttle.py` constants match GRPH-05 (1 s base, 60 s cap, 6 retries, 300 s budget, breaker 20 per 60 s, retryable 429/503). Behaviour-dependent invariants are exercised by named tests that pass in the 948-test run: concurrency peak (2 sites / 4 in flight), 7th consecutive throttle exhausts, 6 throttles then success, budget give-up without sleeping, cross-site gate hold, per-site breaker isolation, batch groups of at most 20, only throttled sub-requests re-sent, truncation at cap, sub-response nextLink completed by paged GETs, `test_stats.py`. Retry cap is now also enforced at the config layer (`HttpSettings.max_retries` has `le=6`, commit e1d6972; I confirmed `max_retries=7` raises `ValidationError` and a test covers it). |
| 4 | Log-capture test proves `run.jsonl` carries path template, status, duration, retries and request-id for every request and never bodies, tokens or `downloadUrl` | VERIFIED | Probe log line today: `template` `/sites/{site-id}`, `status`, `duration_ms`, `retry`, `request_id`, `via_batch`, `batch_size`; no query string or token. `test_logging_capture.py` uses a canary JWT and sentinel body across single, paged, redirect, hostile redirect/nextLink, throttled retry, 403, transport error, batch and hostile request-id paths; the audit helper is itself tested. |
| 5 | Config precedence + unknown keys/mistyped env errors; schema generated from pydantic with the FND-05 fields and a drift test; interrupted write leaves no half-written file; repo scan finds no client-specific data | VERIFIED | `test_config.py` and `test_env_typo_scan.py` (defaults < YAML < env < CLI, unknown keys, client secret rejected, allow-list not configurable). `gen_schemas.py --check` prints `OK fact_sheet` today; drift tests in `test_fact_sheet_schema.py`; schema carries `schema_version` 1.0 and the FND-05 fields. `output.py` atomic write (temp, fsync, replace with Windows lock retry) tested incl. failed fsync/replace; `run.jsonl` repair-on-open per the D-14 amendment. Repo scan: the gate's `blocked-terms` step reports 136 tracked files scanned, 0 skipped, clean (this whole-repo scan supersedes the earlier shippable-only scope); `test_repo_scan.py` and `test_sdist_contents.py` also pass. |

**Score:** 5/5 truths verified (0 behavior-unverified, 0 failed, 0 overrides).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/recover_assess/core/graph.py` (1086 lines) | Sole Graph/httpx2 module: client, hook, paging, batch, retry, session | VERIFIED | Substantive, wired via `from_settings`, exercised by probe and tests |
| `core/graph_policy.py` + packaged allow-list | Canonicaliser, 13-template allow-list, `$batch` validator | VERIFIED | No config key alters it |
| `core/throttle.py` | Retry-After, full jitter, gate, breaker | VERIFIED | |
| `core/log.py`, `core/output.py`, `core/config.py` | Scrubbed run log, atomic writer, layered settings | VERIFIED | |
| `core/models/*` + `schemas/fact_sheet.schema.json` | Contract generated from code | VERIFIED | `--check` OK |
| `scripts/check.py`, `.github/workflows/ci.yml`, `pyproject.toml` | Single gate, CI, 5 contracts | VERIFIED | Gate green locally; CI green and red-on-violation per UAT |
| `scripts/blocked_terms.py`, `scripts/export_requirements.py`, `requirements/*.txt` | Whole-repo term gate; hash-locked export with drift check | VERIFIED | Both steps PASS in the gate |
| `README.md`, `.python-version`, `uv.lock` | Install guidance and pins | VERIFIED | Install confirmed by UAT |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `GraphSession.get/iter_pages/batch` | `ReadOnlyPolicy.check` | `_send` before token fetch | WIRED | Refused paths never reached transport |
| `make_http_client` | `guard_request` hook | `event_hooks` | WIRED | Raw POST refused |
| `_hop` | redirect re-check | manual loop, no auto-follow | WIRED | `test_redirects.py` |
| `GraphClient` | `RunLog` | `_log_request` per hop/sub-response | WIRED | Probe log line |
| `GraphClient.from_settings` | `Settings.http` | limits, UA, retries | WIRED | `test_from_settings_*` |
| `gen_schemas.py` | `models/registry.py` | `model_json_schema` | WIRED | `--check` OK |
| `check.py` | ruff, mypy, lint-imports, blocked-terms, pytest | subprocess steps | WIRED | Ran green |
| `ci.yml` | `check.py` | single gate call | WIRED | Executed on hosted runners per UAT |

### Data-Flow Trace (Level 4)

Not applicable: no rendered dynamic data in Phase 1. `graph_stats` flows from per-session counters to the validated `GraphStats` model (`test_stats.py`).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Single gate | `uv run --frozen python scripts/check.py` | 8/8 PASS, 948 passed | PASS |
| Schema drift | `uv run --frozen python scripts/gen_schemas.py --check` | `OK fact_sheet` | PASS |
| CLI entry | `uv run --frozen recover-assess --version` | `0.1.0` | PASS |
| Write verbs / hostile URLs | scratchpad probe against recording MockTransport | all refused pre-transport; legit GET logged scrubbed | PASS |
| Retry cap in config | `HttpSettings(max_retries=7)` | `ValidationError` | PASS |
| Paging loop guard | probe: server returns empty pages with nextLink forever | 51 requests until the fake server itself errored; client has no loop/page limit | WARNING (WR-02, unchanged) |

### Probe Execution

SKIPPED: no `scripts/*/tests/probe-*.sh` declared or present.

### Requirements Coverage

All 15 phase IDs appear in PLAN frontmatter (01-01 FND-01; 01-02 GRPH-01, GRPH-07, FND-06; 01-03 FND-02; 01-04 FND-03; 01-05 FND-04, FND-05; 01-06 GRPH-01, GRPH-02; 01-07 GRPH-02, GRPH-03; 01-08 GRPH-05; 01-09 GRPH-04, GRPH-06, GRPH-08; 01-10 GRPH-07; 01-11 FND-04; 01-12 FND-06, FND-07). REQUIREMENTS.md maps no other IDs to Phase 1: no orphans. Status below comes from code evidence, not checkbox state.

| Requirement | Source Plan | Status | Evidence |
|-------------|-------------|--------|----------|
| FND-01 | 01-01 | SATISFIED | Pins, README guidance, `--version`; non-admin proxied install passed in UAT |
| FND-02 | 01-03 | SATISFIED | 5 contracts kept; violation-copy tests; hosted CI red on violation (UAT) |
| FND-03 | 01-04 | SATISFIED | test_config, test_env_typo_scan, test_config_show |
| FND-04 | 01-05, 01-11 | SATISFIED | Generated schema, drift tests, `--check` OK |
| FND-05 | 01-05 | SATISFIED | All listed fields present and required in the schema |
| FND-06 | 01-02, 01-12 | SATISFIED | Atomic writer tests; run.jsonl repair-on-open and tolerant read (D-14) |
| FND-07 | 01-12 | SATISFIED | Whole-repo blocked-terms gate (136 files, clean) plus shippable scan and sdist test; org/gateway settings external |
| GRPH-01 | 01-02, 01-06 | SATISFIED | Probe plus policy/transport/batch-hook tests |
| GRPH-02 | 01-06, 01-07 | SATISFIED | nextLink/redirect tests; `/content` refused by policy (see WR-note below) |
| GRPH-03 | 01-07 | SATISFIED | `test_paging.py` (cap, truncated); item cap only (WR-02) |
| GRPH-04 | 01-09 | SATISFIED | `test_batch.py` |
| GRPH-05 | 01-08 | SATISFIED | throttle constants, `test_throttle_*`, config cap `le=6` |
| GRPH-06 | 01-09 | SATISFIED | `test_concurrency.py` |
| GRPH-07 | 01-02, 01-10 | SATISFIED | `test_logging_capture.py`, `log_audit` |
| GRPH-08 | 01-09 | SATISFIED | `test_stats.py`, `GraphStats` in schema |

### Anti-Patterns Found

No `TBD`, `FIXME` or `XXX` markers in `src`, `scripts`, `tests` or `.github`. No stubs or hollow props. Debt-marker gate clear.

### Advisory Findings (01-REVIEW.md, all `open` in 01-REVIEW-DISPOSITION.md; 0 critical)

None breaks a must-have; reported as warnings, not gaps.

| ID | Weight against must-haves |
|----|---------------------------|
| WR-02 | Re-confirmed today: no page limit or loop detection when pages are empty and nextLink repeats. Normal paging and the item cap work (GRPH-03 met as written). Fix before Phase 4 bulk inventory. |
| WR-03 | nextLink query keys use the narrow client-built allow-list; real `$skiptoken`-style links may fail closed. Safe direction; likely to surface in the first live smoke test. |
| WR-05, WR-06 | Whole-batch discard on one budget failure; transport errors and 502/504 not retried. Both match the literal GRPH-04/05 text; resilience decisions for Phase 3/4. |
| WR-01, WR-04, WR-07, WR-08, WR-09 | Config validation, Python-only schema anchors (fix before the Phase 6 freeze), private-API reliance, CI hygiene, unused `sweep_orphans`. |
| WR-10 to WR-14, IN-01 to IN-11 | Blocked-term scanner hardening (digests reversible, skip-on-binary, path scanning), sdist test scope, uv upper bound, minor info items. Today's gate scanned 136 files with 0 skipped. |
| Hook `/content` note | The raw-client hook alone does not refuse a `.../items/x/content` GET (probe: it reached the transport); the policy layer refuses it on every public path, and the raw `_http` handle is private. Defence-in-depth gap only. Recommend adding `/content` to the hook-level check when Phase 4 starts using the client. |

### Human Verification Required

None. Both prior items were resolved by 01-UAT.md (2 passed, 0 issues). No new item needs a human.

### Gaps Summary

No gaps. Phase 1 delivers a tested read-only Graph client (two independent guards, pinned allow-list, validated nextLinks and redirects, throttling, batching, concurrency limits, scrubbed logging) and a code-generated, drift-tested fact-sheet v1.0 contract, all behind a gate that is green locally (948 tests, 8 steps), green on hosted runners, and proven to go red on an import-contract violation. Security (01-SECURITY.md: 0 open threats) and validation (01-VALIDATION.md: nyquist compliant) are consistent with this result. Recommended before Phase 3/4 depend on the client: triage WR-02, WR-03, WR-05 and the hook-level `/content` note.

---

_Verified: 2026-11-18_
_Verifier: Claude (gsd-verifier)_
