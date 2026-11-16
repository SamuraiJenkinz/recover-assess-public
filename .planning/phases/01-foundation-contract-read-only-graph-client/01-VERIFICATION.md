---
phase: 01-foundation-contract-read-only-graph-client
verified: 2026-11-16T02:00:00Z
status: human_needed
score: 4/5 must-haves verified
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
  - "schemas/fact_sheet.schema.json"
  - "scripts/check.py"
  - "src/recover_assess/core/config.py"
  - "src/recover_assess/core/graph.py"
  - "src/recover_assess/core/graph_policy.py"
  - "src/recover_assess/core/log.py"
  - "src/recover_assess/core/models/common.py"
  - "src/recover_assess/core/models/fact_sheet.py"
  - "src/recover_assess/core/output.py"
  - "src/recover_assess/core/throttle.py"
covered_digest: "v4:sha256:2eb25670c5b41c951f9feb2eaf69dc31f69ee7b0874c3f60c9359550f2a6062b"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "FND-01 clean-machine install. On a clean Windows 11 machine or fresh user profile without admin rights, and behind the corporate TLS-inspecting proxy if available, follow README 'Install' and 'Behind a TLS-inspecting proxy' verbatim, then run `uv run recover-assess --version`."
    expected: "uv installs to the user profile; `uv python install 3.12` and `uv sync --locked` succeed (with UV_SYSTEM_CERTS=true behind the proxy, or the UV_PYTHON_DOWNLOADS=never fallback); the command prints 0.1.0; no step asks for elevation or disables TLS verification."
    why_human: "A clean non-admin machine and a TLS-inspecting proxy cannot be reproduced here (01-01 Task 3 human-check, assumption A9). Never executed by any plan."
  - test: "CI enforcement on a real runner. Push the repo to GitHub (it has no git remote), let `.github/workflows/ci.yml` run on windows-latest and ubuntu-latest, then push a throwaway branch with a deliberate violation (for example `core/zz.py` importing `recover_assess.cli`)."
    expected: "The clean branch is green on both OS runners; the violating branch turns the `check` job red at the import-contracts step."
    why_human: "The workflow has never run (no remote). Only its shape (steps, pinned action SHAs, single gate call) is tested locally, so 'CI-enforced' is verified as 'gate script + workflow present', not as 'a hosted run went red/green'."
---

# Phase 1: Foundation, Contract & Read-Only Graph Client Verification Report

**Phase Goal:** A developer has a CI-enforced scaffold in which the only path to Microsoft 365 is a tested read-only Graph client, and the fact-sheet v1.0 contract is generated from code
**Verified:** 2026-11-16
**Status:** human_needed
**Re-verification:** No, initial verification

## Goal Achievement

The code half of the goal is achieved and independently confirmed. The two things that cannot be confirmed here (a clean non-admin proxied install, and a hosted CI run) are human-only and are reported as such, not as passes. No must-have truth FAILED. Nine code-review warnings were weighed; none defeats a must-have, but WR-02, WR-03 and WR-05 should be fixed or consciously accepted before Phase 3/4 depend on the client.

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Clean-machine `uv sync --locked` installs pinned Python 3.12 (with `UV_SYSTEM_CERTS` guidance); CI runs ruff, mypy strict, import-linter; a deliberate violation (core->cli, non-graph httpx2, non-provider LLM SDK, score/agent/report network import) turns CI red | UNCERTAIN (human) for install and hosted CI. Gate half VERIFIED | `.python-version`=3.12, `requires-python>=3.12`, README lines 35-47 carry `UV_SYSTEM_CERTS` and `UV_PYTHON_DOWNLOADS=never` guidance, `uv run recover-assess --version` prints 0.1.0. `scripts/check.py` runs uv-lock-check, ruff-check, ruff-format, mypy, import-contracts, pytest (I ran it: all PASS, exit 0, 907 passed). `pyproject.toml` has 5 import-linter contracts matching the four required rules plus typer/rich-only-in-cli. `tests/unit/test_import_contracts.py` copies the tree, injects each violation, and asserts the expected contract is BROKEN (I ran it: 9 passed, including a control copy that stays kept and a proof the source tree is untouched). `.github/workflows/ci.yml` calls `scripts/check.py` on windows-latest and ubuntu-latest with SHA-pinned actions. Workflow has never executed (no remote); clean-machine install never performed. |
| 2 | Every non-GET verb, non-allow-listed path, `/content`, beta URL, `POST /$batch` with a non-GET sub-request, and hostile nextLink/redirect are rejected before any network call | VERIFIED | My own probe (scratchpad `probe.py`) with a recording MockTransport: raw client POST/PUT/PATCH/DELETE/OPTIONS/HEAD/"Post" all raise `WriteAttemptError` and never reach the transport; beta path -> `WriteAttemptError`; evil host and http scheme -> `UrlNotAllowedError`; via `GraphSession.get`: `/content` (two shapes), `/beta/...`, `/me`, `/users`, `..` traversal, `//evil.com`, `%2e%2e`, unlisted query key all refused; `$batch` with DELETE sub-request and with a `body` key refused at the hook. Transport saw only the two intended GETs. Two independent guards: `ReadOnlyPolicy.check` (graph_policy.py:323-351) and the `guard_request` event hook (graph.py:259) that re-parses serialised bytes using the packaged policy; `follow_redirects=False`. 13-template allow-list is pinned by `tests/graph/test_allowlist_pinned.py`. Hostile nextLink/redirect tests exist (`test_paging.py:154,188,208`, `test_redirects.py:122,205`, `test_batch.py:462`). |
| 3 | Under simulated throttling: pages to end (cap marks `truncated`), `$batch` <=20 with re-queue, Retry-After then jittered backoff (<=6 retries, 5 min give-up), shared throttle gate, per-site breaker -> `throttled_out`, <=4 in-flight/site and 2 sites, `graph_stats` recorded | VERIFIED (with WR-02/WR-05 caveats below) | `throttle.py` constants: base 1 s, cap 60 s, `MAX_RETRIES_DEFAULT=6`, `REQUEST_BUDGET_S=300`, breaker 20 throttles / 60 s window, retryable {429,503}. `GraphClient.__init__` builds one `ThrottleGate` and `Semaphore(max_sites=2)`; session semaphore default 4. Named behavioural tests all pass in the 907-test run: `test_five_sessions_of_ten_gets_peak_at_two_sites_and_four_in_flight`, `test_the_seventh_consecutive_throttle_exhausts_the_retries`, `test_six_throttles_then_success_is_still_within_the_retry_limit`, `test_a_wait_that_would_pass_the_budget_fails_at_once_without_sleeping`, `test_a_throttle_on_one_site_holds_the_next_send_on_another_site`, `test_the_breaker_fails_a_site_without_touching_other_sites`, `test_items_are_sent_in_groups_of_at_most_twenty`, `test_only_the_throttled_sub_requests_are_re_sent_after_the_longest_retry_after`, `test_get_all_marks_truncation_at_the_cap`, `test_a_sub_response_with_a_next_link_is_completed_by_paged_gets`, plus `test_stats.py` for `graph_stats`. Multi-site acceptance in `tests/integration/test_phase1_acceptance.py`. Behaviour-dependent invariants are exercised by tests, not presence alone. |
| 4 | Log-capture test proves `run.jsonl` has path template, status, duration, retries, request-id for every request and never bodies, tokens or `downloadUrl` | VERIFIED | My probe's run.jsonl line carries `template` `/sites/{site-id}`, `status`, `duration_ms`, `retry`, `request_id` (null when server sent none), with no URL query or token. `tests/graph/test_logging_capture.py` uses a canary JWT and sentinel body and audits across single GET, paged, redirect, hostile redirect/nextLink, throttle retry, 403 with sentinel body, transport error with URL in message, batch, hostile request-id header; `tests/support/log_audit.py` audit is itself tested to flag DELETE, non-batch POST and secrets. Residual: WR-01, IN-02, IN-03 (see warnings). |
| 5 | Config precedence + unknown keys/mistyped env errors; schema generated from pydantic with the FND-05 fields and a drift test; interrupted write leaves no half-written file; repo scan finds no client data | VERIFIED (FND-07 scope caveat below) | `tests/unit/test_config.py` (defaults<YAML<env<CLI incl. deep-merge, unknown keys, client_secret rejection, allow-list not configurable), `test_env_typo_scan.py`. `schemas/fact_sheet.schema.json` carries `schema_version` const "1.0" and, as required keys on objects whose `required` equals all properties: `privacy`, `collect_limits`, `sections`, per-section `status`/`reason`, `coverage`, `truncated_reason`, `path_unresolved`, `hash_coverage`, `owners_source`, `last_activity`, `graph_stats`. `gen_schemas.py --check` prints `OK fact_sheet`; `test_fact_sheet_schema.py` has parsed-JSON drift tests including mutated value, removed key, missing file. `output.py` atomic write (temp, fsync, replace with Windows lock retry) tested incl. failed fsync/replace leaving prior bytes and no temp; `run.jsonl` repair-on-open per D-14 amendment tested in `test_run_log.py`. `tests/unit/test_repo_scan.py::test_whole_tree_scan_clean` runs over tracked and untracked shippable files; `test_sdist_contents.py` builds a real sdist and asserts `.planning`, `.claude`, drafts and secrets are absent. |

**Score:** 4/5 truths verified; 1 UNCERTAIN routed to human verification (SC1 install + hosted CI). 0 FAILED. 0 behavior-unverified.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/recover_assess/core/graph.py` (1086 lines) | The only Graph/httpx2 module: client, hook, paging, batch, retry, session | VERIFIED | Substantive; wired into config via `from_settings`; exercised end to end by probe and tests |
| `src/recover_assess/core/graph_policy.py` + `graph_allowlist.yaml` | Canonicaliser, 13-template allow-list, `$batch` body validator | VERIFIED | Packaged in sdist, locked, no config key can alter it (test_config) |
| `src/recover_assess/core/throttle.py` | Retry-After parse, full jitter, gate, breaker | VERIFIED | Constants match GRPH-05 exactly |
| `src/recover_assess/core/log.py` | Typed run.jsonl events, scrub, repair-on-open | VERIFIED | Closed-field events; one-write-per-line |
| `src/recover_assess/core/config.py` | Layered typo-proof settings | VERIFIED | See WR-07 note |
| `src/recover_assess/core/output.py` | Atomic writer with Windows retry | VERIFIED | `sweep_orphans` latent defect WR-09 (unused in src) |
| `src/recover_assess/core/models/*` + `schemas/fact_sheet.schema.json` | Contract generated from code | VERIFIED | Drift test + `--check` OK |
| `scripts/check.py`, `.github/workflows/ci.yml`, `pyproject.toml` | Single gate, CI, contracts | VERIFIED locally; CI never run | See human item 2 |
| `README.md`, `.python-version`, `uv.lock` | Install guidance, pins | VERIFIED (content); install unrun | See human item 1 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `GraphSession.get/iter_pages/batch` | `ReadOnlyPolicy.check` | `_send` -> `_attempt` before token fetch | WIRED | Probe: refused paths never reached transport |
| `make_http_client` | `guard_request` hook | `event_hooks={"request": [...]}` | WIRED | Raw `http.request("POST"...)` refused |
| `_hop` | redirect re-check | manual loop, `follow_redirects=False` | WIRED | `test_redirects.py` |
| `GraphClient` | `RunLog` | `_log_request` per hop/sub-response | WIRED | Probe log line |
| `GraphClient.from_settings` | `Settings.http` | limits and UA | WIRED | `test_from_settings_*` |
| `gen_schemas.py` | `models/registry.py` | model_json_schema | WIRED | `--check` OK |
| `check.py` | `lint-imports`, ruff, mypy, pytest | subprocess steps | WIRED | Ran green |
| `ci.yml` | `check.py` | `uv run python scripts/check.py` | WIRED (not executed) | Shape tested in `test_check_script.py` |

### Data-Flow Trace (Level 4)

Not applicable: no rendered dynamic data in Phase 1 (library, CLI scaffold and schema only). `graph_stats` flows from per-session counters to a validated `GraphStats` model (`test_stats.py`).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Single gate | `uv run --frozen python scripts/check.py` | all 6 steps PASS, 907 passed | PASS |
| Schema drift | `uv run --frozen python scripts/gen_schemas.py --check` | `OK fact_sheet` | PASS |
| Import contracts catch violations | `pytest tests/unit/test_import_contracts.py` | 9 passed | PASS |
| Write verbs / hostile URLs | scratchpad `probe.py` against recording MockTransport | all refused pre-transport; legit GET logged | PASS |
| CLI entry | `uv run --frozen recover-assess --version` | `0.1.0` | PASS |
| Paging loop guard | scratchpad `probe2.py`, server returns empty page + nextLink forever | 51 requests until the fake server itself failed; no loop detection | FAIL (WR-02 confirmed, see warnings) |

### Probe Execution

SKIPPED: no `scripts/*/tests/probe-*.sh` declared or present.

### Requirements Coverage

All 15 phase IDs appear in plan frontmatter (01-01 FND-01; 01-02 GRPH-01, GRPH-07, FND-06; 01-03 FND-02; 01-04 FND-03; 01-05 FND-04, FND-05; 01-06 GRPH-01, GRPH-02; 01-07 GRPH-02, GRPH-03; 01-08 GRPH-05; 01-09 GRPH-04, GRPH-06, GRPH-08; 01-10 GRPH-07; 01-11 FND-04; 01-12 FND-06, FND-07). REQUIREMENTS.md maps no additional Phase 1 IDs: no orphans. Checkboxes and the traceability table already show all 15 complete; status below is from code evidence, not checkbox state.

| Requirement | Source Plan | Status | Evidence |
|-------------|-------------|--------|----------|
| FND-01 | 01-01 | NEEDS HUMAN | Pins, README guidance, `--version` verified; clean non-admin proxied install never performed |
| FND-02 | 01-03 | SATISFIED (hosted CI unrun) | check.py + 5 contracts + violation-copy tests; ci.yml shape tested |
| FND-03 | 01-04 | SATISFIED | test_config.py, test_env_typo_scan.py, test_config_show.py |
| FND-04 | 01-05, 01-11 | SATISFIED | Generated schema, drift tests, `--check` OK |
| FND-05 | 01-05 | SATISFIED | All listed fields present and required in schema |
| FND-06 | 01-02, 01-12 | SATISFIED | atomic writer tests; run.jsonl repair-on-open and tolerant read (D-14 amendment) |
| FND-07 | 01-12 | SATISFIED within shippable scope; see warning W-A | Whole-tree scan + sdist test |
| GRPH-01 | 01-02, 01-06 | SATISFIED | Probe + test_policy_verbs, test_transport_guard, test_batch_hook |
| GRPH-02 | 01-06, 01-07 | SATISFIED | nextLink/redirect validation tests; `/content` refused at policy. Note the second-guard hook alone does not refuse `/content` (probe: raw client GET to `.../items/x/content` reached transport); unreachable via the public API, still a read |
| GRPH-03 | 01-07 | SATISFIED | test_paging.py (cap, truncated). Item cap only; see WR-02 |
| GRPH-04 | 01-09 | SATISFIED | test_batch.py |
| GRPH-05 | 01-08 | SATISFIED | throttle constants + test_throttle_retry/unit |
| GRPH-06 | 01-09 | SATISFIED | test_concurrency.py |
| GRPH-07 | 01-02, 01-10 | SATISFIED | test_logging_capture.py, log_audit |
| GRPH-08 | 01-09 | SATISFIED | test_stats.py, GraphStats model in schema |

### Anti-Patterns Found

No `TODO|FIXME|XXX|TBD` markers in `src`, `scripts`, `tests` or `.github`. No stubs or hollow props. Debt-marker gate clear.

### Code Review Weighing (01-REVIEW.md: 0 critical, 9 warnings)

Disposition file shows all 9 `open`. None turns a must-have truth FAILED; classified as WARNING:

| ID | Weight against must-haves |
|----|---------------------------|
| WR-02 paging has no page limit / loop detection | Confirmed by my probe. Item cap never trips on empty pages, so a buggy or hostile server loops until the 300 s per-request budget does nothing (budget is per request). Does not falsify "pages to the end, cap marks truncated" in normal operation, but weakens GRPH-03's intent. Fix before Phase 4 bulk collection. |
| WR-03 nextLink query keys use the narrow client-built allow-list | Real Graph links (`$skip`, `$skipToken`, `$count`) would fail closed mid-pagination. Safe direction (fail closed), but likely to hit in Phase 2/4 live smoke. |
| WR-05 budget `ThrottledOut` discards the whole `batch()` result; breaker counts 20 per all-throttled batch | Behaviour is tested and consistent with GRPH-05 as written ("gives up after 5 minutes", breaker at 20); a robustness and docstring-consistency concern for Phase 3. |
| WR-06 transport errors and 502/504 never retried | Matches the literal requirement (429/503); resilience decision for the owner. |
| WR-01 non-ASCII `user_agent_company` crashes first request with the value in the message | Config-time validation gap; minor leak risk (company name, not a secret). |
| WR-04 `\A`/`\Z` anchors in published schema | Python-only regex in a contract meant for later stages; fix before the Phase 6 freeze (D-06 allows regeneration). |
| WR-07 private `_load_env_vars` override | Works today; pinned-version fragility. |
| WR-08 CI lacks timeout/concurrency | Hygiene. |
| WR-09 `sweep_orphans` may delete a live run's temp file | Latent: unused in `src`. |

**W-A (FND-07 scope, decision requested):** `.claude/CLAUDE.md` and `.planning/` are tracked in git and name the pilot organisation and its gateway (no endpoints, hostnames or data). It is outside the scanner's shippable scope and excluded from the sdist by test, so the shipped asset is clean and the design (D-10/D-11) is met. If FND-07 is meant to cover every tracked file, that file and `.planning/` would violate it. I judge this acceptable as designed; flagging for an explicit owner decision. Resolved by quick task 261116-915: every tracked file was scrubbed and the gate's blocked-terms step now enforces this across the whole repository.

### Human Verification Required

1. **FND-01 clean-machine install** (01-01 Task 3 human-check, harvested)
   - **Test:** On a clean Windows 11 machine or fresh profile without admin rights, behind the corporate TLS-inspecting proxy if available, follow README "Install" and "Behind a TLS-inspecting proxy" verbatim, then `uv run recover-assess --version`.
   - **Expected:** User-profile install, `uv python install 3.12` and `uv sync --locked` succeed (with `UV_SYSTEM_CERTS=true` or the `UV_PYTHON_DOWNLOADS=never` fallback), prints `0.1.0`, no elevation, TLS verification never disabled.
   - **Why human:** Cannot be reproduced here (assumption A9); never performed.

2. **Hosted CI actually enforces the gate**
   - **Test:** Add a remote, push, let `ci.yml` run on both runners, then push a branch with a deliberate import-contract violation.
   - **Expected:** Clean branch green on windows-latest and ubuntu-latest; violating branch red.
   - **Why human:** The repo has no git remote; the workflow has never run. "CI-enforced" is verified only as local gate plus workflow shape.

### Gaps Summary

No blocking gaps. Phase 1 delivers a working, heavily tested read-only Graph client (two independent guards, pinned allow-list, validated nextLinks/redirects, throttling, batching, concurrency limits, scrubbed logging) and a code-generated, drift-tested fact-sheet v1.0 contract; the local quality gate is green (907 tests). Status is `human_needed` solely because the clean non-admin proxied install and a real hosted CI run cannot be verified in this environment. Recommended before Phase 3/4: resolve WR-02, WR-03, WR-05 and WR-04 (all currently `open` in 01-REVIEW-DISPOSITION.md).

---

_Verified: 2026-11-16_
_Verifier: Claude (gsd-verifier)_
