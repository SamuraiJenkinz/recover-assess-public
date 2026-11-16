---
gsd_state_version: "1.0"
milestone: v1.0
current_phase: 01
current_phase_name: Foundation, Contract & Read-Only Graph Client
status: verifying
stopped_at: Completed 01-10-PLAN.md
last_updated: "2026-11-16T20:21:12.066Z"
last_activity: 2026-11-16
last_activity_desc: Phase 01 execution started
state_head: f241972cc9cc415c355bf972e47c94798a1b950e
progress:
  total_phases: 12
  completed_phases: 0
  total_plans: 12
  completed_plans: 12
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-11-15)

**Core value:** Every site's effort rating, action and strategy is deterministic, traceable to evidence in the fact sheet, and produced without ever writing to Microsoft 365. If the LLM layer fails, Collector + scoring must still give a credible, defensible triage.
**Current focus:** Phase 01 — Foundation, Contract & Read-Only Graph Client

## Current Position

Phase: 01 (Foundation, Contract & Read-Only Graph Client) — EXECUTING
Plan: 12 of 12
Status: Phase complete — ready for verification
Last activity: 2026-11-16 - Completed quick task 261116-kqf: Corporate-network install guide with a hash-locked pip fallback

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: - min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01 P01 | 25 min | 3 tasks | 28 files |
| Phase 01 P02 | 5 min | 2 tasks | 9 files |
| Phase 01 P03 | 14 min | 2 tasks | 6 files |
| Phase 01 P04 | 15 min | 2 tasks | 6 files |
| Phase 01 P11 | 15 min | 2 tasks | 6 files |
| Phase 01 P06 | 15 min | 3 tasks | 8 files |
| Phase 01 P12 | 25 min | 2 tasks | 5 files |
| Phase 01 P05 | 35 min | 2 tasks | 8 files |
| Phase 01 P07 | 25 min | 2 tasks | 5 files |
| Phase 01 P08 | 35 min | 2 tasks | 7 files |
| Phase 01 P09 | 40 min | 2 tasks | 5 files |
| Phase 01 P10 | 35 min | 2 tasks | 5 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Vertical MVP, fine granularity, 12 phases. Walking skeleton (sign in, doctor, resolve, C1) lands in Phase 2 right after the read-only Graph client and fact-sheet contract (Phase 1).
- [Roadmap]: Scoring + reports (`--no-llm`, the Core Value) are Phases 7-8, before providers (9) and agent (10). Providers are technically independent and can be pulled forward.
- [Roadmap]: `app_certificate` / `managed_identity` (AUTH-02/03) are deferred to Phase 11 with the Task Scheduler README; delegated auth ships first behind the same `TokenProvider`.
- [Roadmap]: PIL-01 (Collector acceptance) is Phase 6; PIL-02 (calibration) and PIL-03 (workstation + server) are Phase 12.
- [Sign-off 2, resolved]: Display-name resolution is out of v1 (INP-02 returns `name_requires_url`); V2-03 is the opt-in.
- [Sign-off 3, resolved]: A1 sample-tier classification is v2 (SMP-02) and advisory only; scorecard is metadata-only.
- [Phase 01]: uv bootstrapped from the versioned 0.13.8 release archive with a SHA-256 check (no piped installer); uv.lock approved by the developer before any install
- [Phase 01]: UrlNotAllowedError subclasses WriteAttemptError so one except clause catches every refused request; ThrottledOut is one type with three reasons and one code
- [Phase 01]: ruff extend-exclude covers .planning, .claude and out because ruff 0.17 formats markdown
- [Phase 01]: RunLog.emit stamps ts from the injected clock under the writer lock; event models carry ts as optional
- [Phase 01]: downloadUrl scrub covers the escaped form so a scrubbed run.jsonl line stays valid JSON
- [Phase 01]: WarningEvent.code validated with is_error_code (pydantic Rust regex rejects the anchors in ERROR_CODE_PATTERN)
- [Phase 01]: GraphSession.get re-runs policy.check on non-2xx to get the template, keeping _send's signature stable
- [Phase 01]: 01-03: check.py is the single local and CI gate; violation fixtures run the real contracts on a git-archive-HEAD tmp copy; provider modules may import httpx2 only (AST ban)
- [Phase 01]: 01-04: load_settings honours its environ argument for the build via an EnvSettingsSource subclass; client-secret keys matched by casefold minus underscores/hyphens; no allow-list field exists in any Settings model (D-08)
- [Phase 01]: Contract sets regex_engine=python-re so the anchored ERROR_CODE_PATTERN compiles in pydantic
- [Phase 01]: 01-06: the request hook rejects duplicate JSON keys and any query on POST /v1.0/$batch (fail closed, beyond plan)
- [Phase 01]: 01-06: list_drive Learn citation is the list resource page, because drive-get does not document the list-scoped path
- [Phase 01]: 01-06: GraphClient._send forwards json_body to ReadOnlyPolicy.check as batch_body so POST is validated against the body sent
- [Phase 01]: Atomic writer wraps non-PermissionError OSError in OutputError without retry; only PermissionError is retried
- [Phase 01]: Repo scan rule allow-lists are code predicates (synthetic tenant label, example domains, repeated-digit GUID groups); client terms only via external private-terms file
- [Phase 01]: Empty RECOVER_ASSESS_PRIVATE_TERMS_FILE value is treated as unset; non-empty missing path raises FileNotFoundError
- [Phase 01]: Contract sets hide_input_in_errors so validation errors never echo submitted evidence values — Plan 01-05 requires error messages to name the section but never include values
- [Phase 01]: A could-not-look sections.exposure status forces exposure_total and every library exposure to null/unknown — Closes the per-library gap so no number sits under an unknown section (01-05, FND-05)
- [Phase 01]: FactSheet vocabulary names stay provisional until the Phase 6 freeze (FA-3 open) — Research proposal A12 not yet reviewed by the developer; D-06 allows in-place renames
- [Phase 01]: 01-07: next links are policy-validated on receipt and again in _send; iter_pages is typed AsyncGenerator so get_all can aclose it at the cap; only 301/302/303/307/308 are redirects (max 3 hops, none on POST)
- [Phase 01]: 01-08: tenacity wait runs before stop, so _wait_for is a no-op once retries are spent; only 429/503 retry, per-attempt breaker/gate/policy/token, one ThrottleGate per GraphClient
- [Phase 01]: 01-09: batches counted per POST attempt in _hop; a whole-batch 429 retry counts two batches
- [Phase 01]: 01-09: $batch re-queue capped at max_retries rounds; leftovers end as throttled_out; unanswered ids become batch_response_missing
- [Phase 01]: 01-09: blank user_agent_company counts as absent; pipe, non-printable or >64 chars raises ValueError
- [Phase 01]: 01-10: request-id header logged only when GUID-shaped (fullmatch [A-Za-z0-9-]{1,64}), else null

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 1, resolved 2026-11-15] Sign-off 1 approved: httpx2 + built-in `MockTransport` replace httpx + respx (01-CONTEXT D-01).
- [Phase 8] `jinja2` is outside the approved dependency list and needs approval before Phase 8 planning. `msal[broker]` only if the Phase 2 auth spike shows Conditional Access blocks both device code and loopback browser. Sample-tier extractors and `defusedxml` are no longer needed (sample tier is v2).
- [Phase 2] Long-lead external items, start on day one: auth matrix on the pilot workstation (Conditional Access, WAM, Sites.Selected consent), three-stack TLS/proxy check, resolve 403-vs-404 spike.
- [Phase 9] Gateway key/deployment and gateway capability spike (strict `json_schema` pass-through, empty-200, `upstream_auth_403`, WAF limits) depend on external provisioning.
- [Phase 3/5/6] Pilot sites need read grants from Security; sandbox Sites.Selected grant spike (client ID vs object ID; managed-identity visibility delay up to about 24 h gates Phase 11).
- [Phase 4] Live delta spike on a >50k library before planning; decide first-wins vs last-wins from real data.
- [Phase 5] Sites.Selected plus `/permissions` read may force Sites.Read.All or caller-scoped results; `owners` via `GroupMember.Read.All` and SAM export format are open.
- [Phase 7] Calibration on ~10 sites cannot discriminate alone: record hand labels before viewing tool output, keep a holdout, report the trivial baseline.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 261116-915 | Scrub client-specific nomenclature from tracked files and add a blocked-term CI check | 2026-11-16 | af6f009 | [261116-915-scrub-client-specific-nomenclature-from-](./quick/261116-915-scrub-client-specific-nomenclature-from-/) |
| 261116-kqf | Corporate-network install guide with a hash-locked pip fallback | 2026-11-16 | f241972 | [261116-kqf-corporate-network-install-guide-with-has](./quick/261116-kqf-corporate-network-install-guide-with-has/) |

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-11-16T01:13:27.965Z
Stopped at: Completed 01-10-PLAN.md
Resume file: None
