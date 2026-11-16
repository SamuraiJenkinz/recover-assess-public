---
phase: "1"
slug: "foundation-contract-read-only-graph-client"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-11-15"
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest ~=9.2 + pytest-asyncio ~=1.5 (asyncio_mode=auto) + hypothesis ~=6.170 |
| **Config file** | pyproject.toml [tool.pytest.ini_options] (Wave 0 installs) |
| **Quick run command** | `uv run pytest tests/<area> -x -q` |
| **Full suite command** | `uv run python scripts/check.py` |
| **Estimated runtime** | per-task scoped runs under 30 s; full gate about 60-120 s on Windows (subprocess violation fixtures and the sdist build are marked `slow`; `scripts/check.py --fast` skips them), so the full gate never appears in a per-task verify |

---

## Sampling Rate

- **After every task commit:** Run the task's scoped verify: its own test modules plus ruff/mypy on the files it touched (in parallel waves never a whole-tree command, and tests that read the whole working tree are named `whole_tree` and deselected with `-k "not whole_tree"`)
- **After every plan wave (wave join):** Run `uv run python scripts/check.py` on the merged tree. For parallel waves (2, 3, 4) this is enforced as a `<precondition>` on the first task of every next-wave plan (01-06, 01-12 after Wave 2; 01-05, 01-07 after Wave 3; 01-08 after Wave 4); single-plan waves (1, 5, 6, 7) run it once at plan end
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds for a per-task scoped run (FakeClock: no real sleeping anywhere in tests)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | FND-01 | T-01-01, T-01-02, T-01-30 | uv binary installed only from the checksum-verified versioned archive; lock resolved (no install) before review; drafts, external config, certs and token caches git-ignored | smoke | `uv lock --check` (after `python scripts/verify_sha256.py <archive> <sidecar>` printed OK) | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | FND-01 | T-01-SC, T-01-30 | Developer approves resolved packages, the uv archive hash and uv_build before any install (gate="blocking-human") | manual checkpoint | n/a (checkpoint) | n/a | ⬜ pending |
| 1-01-03 | 01 | 1 | FND-01 | T-01-03 | Error text cannot carry a URL; UrlNotAllowedError is a WriteAttemptError; README has no TLS-disabling advice; verify_sha256 matches and mismatches correctly | unit | `uv run pytest tests/unit/test_foundation.py -x -q` | ❌ W0 | ⬜ pending |
| 1-02-01 | 02 | 2 | GRPH-01, GRPH-07 | T-01-04, T-01-05, T-01-06, T-01-07 | Tracer: one GET end to end; non-GET and non-allow-listed paths never reach the transport; token absent from run.jsonl | integration (tracer) | `uv run pytest tests/graph/test_walking_skeleton.py -x -q` | ❌ W0 | ⬜ pending |
| 1-02-02 | 02 | 2 | GRPH-01, GRPH-07, FND-06 | T-01-04, T-01-07, T-01-32 | Hook refuses writes through the raw client; failure paths log one URL-free line; interrupted run.jsonl repaired on open and never read half-written | unit + integration | `uv run pytest tests/graph/test_walking_skeleton.py tests/unit/test_run_log.py -x -q` | ❌ W0 | ⬜ pending |
| 1-11-01 | 11 | 2 | FND-04 | T-01-31 | Envelope models: no defaults, extra forbidden, frozen, UTC Z datetimes, constrained warning codes | unit | `uv run pytest tests/unit/test_fact_sheet_schema.py -x -q` | ❌ W0 | ⬜ pending |
| 1-11-02 | 11 | 2 | FND-04 | T-01-31 | Schema generated from models, never hand-written; drift detected on parsed JSON; deterministic rendering | unit | `uv run python scripts/gen_schemas.py --check` and `uv run pytest tests/unit/test_fact_sheet_schema.py -x -q` | ❌ W0 | ⬜ pending |
| 1-03-01 | 03 | 2 | FND-02 | T-01-08, T-01-10 | Actions SHA-pinned, permissions contents: read; one gate script for local and CI | unit | `uv run pytest tests/unit/test_check_script.py -x -q` and `uv run python scripts/check.py --help` | ❌ W0 | ⬜ pending |
| 1-03-02 | 03 | 2 | FND-02 | T-01-09 | Each deliberate violation turns the real contracts BROKEN (committed-tree copies); AST bans on dynamic imports and write-verb calls | integration (slow) | `uv run pytest tests/unit/test_import_contracts.py tests/unit/test_source_bans.py -x -q -k "not whole_tree"` (whole_tree tests run at the wave-2 join) | ❌ W0 | ⬜ pending |
| 1-04-01 | 04 | 2 | FND-03 | T-01-11, T-01-12, T-01-13 | Unknown keys, env typos and client secrets are ConfigErrors; no allow-list key | unit | `uv run pytest tests/unit/test_config.py tests/unit/test_env_typo_scan.py -x -q` | ❌ W0 | ⬜ pending |
| 1-04-02 | 04 | 2 | FND-03 | T-01-13 | `config show` prints effective settings; secret env values never printed; example config loads | unit (CliRunner) | `uv run pytest tests/unit/test_config_show.py -x -q` | ❌ W0 | ⬜ pending |
| 1-12-01 | 12 | 3 | FND-06 | T-01-14 | No half-written or orphaned files after lock contention or interruption | unit (+win32) | `uv run pytest tests/unit/test_atomic_write.py -x -q` | ❌ W0 | ⬜ pending |
| 1-12-02 | 12 | 3 | FND-07 | T-01-15 | No client data in the shippable tree or the sdist | unit + slow | `uv run pytest tests/unit/test_repo_scan.py -x -q -k "not whole_tree"` and `uv run pytest tests/unit/test_sdist_contents.py -q -m "slow and needs_uv"` (real-tree scan at the wave-3 join) | ❌ W0 | ⬜ pending |
| 1-06-01 | 06 | 3 | GRPH-01 | T-01-18 | Exactly 13 pinned templates with Learn URLs; not configurable | unit | `uv run pytest tests/graph/test_allowlist_pinned.py tests/graph/test_walking_skeleton.py -x -q` | ❌ W0 | ⬜ pending |
| 1-06-02 | 06 | 3 | GRPH-02 | T-01-18, T-01-19 | Hostile corpus and hypothesis mutations rejected (each also a WriteAttemptError); content and downloadUrl denied | unit + property | `uv run pytest tests/graph/test_policy_urls.py -x -q` | ❌ W0 | ⬜ pending |
| 1-06-03 | 06 | 3 | GRPH-01 | T-01-20, T-01-33 | $batch with a non-GET, body, dependsOn or bad url rejected before send, by the policy and independently by the request hook on the serialised body (raw client and permissive injected policy: transport never called) | unit | `uv run pytest tests/graph/test_walking_skeleton.py tests/graph/test_allowlist_pinned.py tests/graph/test_policy_urls.py tests/graph/test_policy_verbs.py tests/graph/test_batch_hook.py -x -q` | ❌ W0 | ⬜ pending |
| 1-05-01 | 05 | 4 | FND-05 | T-01-16 | Unknown evidence (including exposure "unknown", COL-09) can never be recorded as a measured zero | unit | `uv run pytest tests/unit/test_fact_sheet_model.py -x -q` | ❌ W0 | ⬜ pending |
| 1-05-02 | 05 | 4 | FND-04 | T-01-17 | Full v1.0 schema regenerated atomically, structure-linted, fixtures validate; envelope-only tests rebuilt on the not-run fixture | unit | `uv run python scripts/gen_schemas.py --check` and `uv run pytest tests/unit/test_fact_sheet_schema.py tests/unit/test_fact_sheet_model.py -x -q` | ❌ W0 | ⬜ pending |
| 1-07-01 | 07 | 4 | GRPH-03, GRPH-02 | T-01-21, T-01-23 | Every nextLink validated before the token travels; downloadUrl annotations stripped; cap marks truncated | unit | `uv run pytest tests/graph -x -q` | ❌ W0 | ⬜ pending |
| 1-07-02 | 07 | 4 | GRPH-02 | T-01-22 | Redirects validated, at most 3 hops, never automatic; production keeps env proxies | unit | `uv run pytest tests/graph -x -q` | ❌ W0 | ⬜ pending |
| 1-08-01 | 08 | 5 | GRPH-05 | T-01-25 | Retry-After parsing, jitter bounds, gate and breaker boundaries exact | unit | `uv run pytest tests/graph/test_throttle_unit.py -x -q` | ❌ W0 | ⬜ pending |
| 1-08-02 | 08 | 5 | GRPH-05 | T-01-24 | 6 retries, 300 s budget, shared gate across sites, breaker poisons the session | unit | `uv run pytest tests/graph -x -q` | ❌ W0 | ⬜ pending |
| 1-09-01 | 09 | 6 | GRPH-04 | T-01-26 | Sub-responses correlated by id; only throttled ids re-queued; nextLink completed | unit | `uv run pytest tests/graph/test_batch.py -x -q` | ❌ W0 | ⬜ pending |
| 1-09-02 | 09 | 6 | GRPH-06, GRPH-08 | T-01-27 | At most 2 sites and 4 in flight per site; graph_stats semantics pinned and schema-valid; one client per run documented | unit (async) | `uv run pytest tests/graph/test_concurrency.py tests/graph/test_stats.py tests/graph/test_batch.py -x -q` | ❌ W0 | ⬜ pending |
| 1-10-01 | 10 | 7 | GRPH-07 | T-01-28, T-01-29 | No token, body, downloadUrl, raw ID or URL in run.jsonl or exception text on any path | unit | `uv run pytest tests/graph/test_logging_capture.py -x -q` | ❌ W0 | ⬜ pending |
| 1-10-02 | 10 | 7 | GRPH-07 (SC 1-5 jointly) | T-01-28 | Multi-site throttled scenario end to end (breaker distinguished from retries_exhausted); log audit clean | integration | `uv run pytest tests/integration/test_phase1_acceptance.py -x -q` (full `scripts/check.py` once at plan end) | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `scripts/verify_sha256.py` (uv bootstrap integrity; also makes the mypy `scripts` path exist) — Plan 01-01 Task 1
- [ ] `pyproject.toml`, `uv.lock`, `.python-version` (uv, pytest, mypy, ruff, import-linter configuration) — Plan 01-01 Task 1
- [ ] Framework install: uv 0.13.8 (checksum-verified archive) and CPython 3.12 at user level, then `uv sync --locked` after the legitimacy checkpoint — Plan 01-01 Tasks 1-3
- [ ] `tests/__init__.py` and package markers for `tests/{unit,graph,integration,fakes,support}` — Plan 01-01 Task 3
- [ ] `tests/conftest.py` (fake_clock, fake_graph, run_log_path, run_log, canary_token, make_graph_client; hypothesis profiles ci/dev) — Plan 01-02 Task 1
- [ ] `tests/fakes/clock.py`, `tests/fakes/fake_graph.py` — Plan 01-02 Task 1 (extended by Plans 01-07, 01-08, 01-09)
- [ ] `tests/support/import_violations.py` — Plan 01-03 Task 2
- [ ] `tests/support/repo_scan.py` — Plan 01-12 Task 2
- [ ] `tests/support/log_audit.py` — Plan 01-10 Task 1
- [ ] `scripts/check.py`, `.github/workflows/ci.yml` — Plan 01-03 Task 1

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Clean Windows 11 non-admin install behind a TLS-inspecting proxy | FND-01 | Needs a clean machine or profile and the corporate proxy; CI cannot reproduce either (RESEARCH A9) | Follow README "Install" and "Behind a TLS-inspecting proxy" verbatim, then `uv run recover-assess --version` prints 0.1.0 with no elevation and no TLS-disabling step (Plan 01-01 Task 3 human-check) |
| Package legitimacy review of the resolved lock and the uv bootstrap | FND-01 (T-01-SC, T-01-30) | Trust decision on third-party code must be a human's (gate="blocking-human", never auto-approved) | Plan 01-01 Task 2: confirm the uv archive SHA-256 against the 0.13.8 release page, compare the printed package list with RESEARCH Package Legitimacy Audit and pypi.org project pages, confirm uv_build; reply "approved" |
| CI run on GitHub-hosted windows-latest and ubuntu-latest | FND-02 | No git remote exists yet (CONTEXT Deferred Ideas) | After a remote is added, confirm the `ci` workflow passes on both runners; locally the same `scripts/check.py` is green on Windows |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s per task (aligned with the header and Sampling Rate; the 60-120 s full gate runs only at wave joins and plan ends)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** {pending / approved YYYY-MM-DD}
