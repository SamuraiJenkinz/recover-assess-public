# Walking Skeleton — recover-assess

**Phase:** 1
**Generated:** 2026-11-15

## Capability Proven End-to-End

A developer runs `uv run python scripts/check.py` on Windows 11 and sees one allow-listed Microsoft Graph GET travel through the read-only policy, the Graph client and its request guard to a mock transport, come back, and write one typed, scrubbed `run.jsonl` line, while the fact-sheet v1.0 schema is regenerated from the pydantic models with no drift, and the same gate (with deliberate-violation fixtures proving the architecture contracts bite) is what CI runs.

This is a local CLI and library, not a web app, so the template's layers map as follows:

| Template layer | recover-assess equivalent | Delivered by |
|---|---|---|
| Project scaffold | uv project (Python 3.12, uv_build, src layout), ruff, mypy strict, pytest, import-linter, approved uv.lock | Plan 01-01 |
| Routing (one real route) | One allow-listed Graph template (`GET /sites/{site-id}`) through `ReadOnlyPolicy` and `GraphClient` | Plan 01-02 Task 1 (tracer) |
| Database read and write | Read: Graph response via `httpx2.MockTransport`. Write: append-only `logs/run.jsonl` line (Plan 01-02) and the generated `schemas/fact_sheet.schema.json` (Plan 01-11, same wave, split out of 01-02 for scope) | Plan 01-02 Task 1, Plan 01-11 |
| UI interaction | CLI entry `recover-assess --version` (Typer); `recover-assess config show` added in Plan 01-04 | Plans 01-01, 01-04 |
| Deployment / run command | `uv sync --locked` then `uv run python scripts/check.py` locally; `.github/workflows/ci.yml` runs the same script on windows-latest and ubuntu-latest | Plans 01-01, 01-03 |

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Runtime and packaging | Python 3.12 via uv 0.13.8 (installed from the checksum-verified versioned release archive, `scripts/verify_sha256.py`), uv_build backend, `src/recover_assess` layout, console script `recover-assess` | Spec-pinned; no admin rights needed; reproducible lockfile; explicit sdist include list keeps planning docs and drafts out (D-10); bootstrap integrity (T-01-30) |
| HTTP stack | httpx2 ~=2.16 for all outbound HTTP; tests inject `httpx2.MockTransport` through `make_http_client(transport=...)` | D-01 (costly to reverse). Passing `transport=` disables env proxies, so production never passes one (RESEARCH Pitfall 2) |
| Microsoft 365 access | Hand-written `core/graph.py` is the only module importing httpx2; pure `core/graph_policy.py` holds the policy; the allow-list is packaged YAML (`core/graph_allowlist.yaml`, 13 templates with Learn URLs), not operator-editable | Read-only is the product's trust promise (GRPH-01, D-08, D-09) |
| Write prevention | Two independent guards: `ReadOnlyPolicy.check` before the token is fetched, and an httpx2 `event_hooks["request"]` guard before any transport that also re-validates every serialised `$batch` body against the packaged allow-list (Plan 01-06); no public write methods; AST ban on `.post/.put/.patch/.delete` calls. Every refusal is catchable as `WriteAttemptError` (the GRPH-01 type); `UrlNotAllowedError` is its subclass for URL/host/path refusals | Defence in depth without breaking proxy support |
| Server-supplied URLs | Every `@odata.nextLink` and redirect `Location` is validated by the policy before it is followed; `follow_redirects=False`, at most 3 manual hops | Token must never reach a foreign host (GRPH-02) |
| Throttling | tenacity loop with custom wait/stop on an injected `Clock` and seeded rng; one `ThrottleGate` per client shared by all sites; per-site `SiteBreaker` (20 in 60 s); 6 retries; 300 s budget; one `ThrottledOut` type whose `.reason` (retries_exhausted, budget, breaker) stays distinguishable under the shared code `throttled_out` | GRPH-05; tenacity's built-in timing helpers are not injectable (RESEARCH Pitfall 1) |
| Concurrency | Client-wide semaphore of 2 sites; per-session semaphore of 4 in-flight requests held only around transport calls | GRPH-06 |
| One client per run (invariant, handoff to Phase 3) | The run orchestrator builds exactly one `GraphClient` (via `from_settings`) and opens every site's session from it | The throttle gate and site semaphore are client-wide; a second client would bypass tenant-wide coordination and double the site limit (Plans 01-08, 01-09) |
| Time | `core/clock.py` `Clock` protocol injected everywhere; the only module allowed to sleep (ruff TID251) | Deterministic millisecond tests of backoff and breakers |
| Data contract | pydantic v2 models in `core/models/` generate `schemas/fact_sheet.schema.json` (serialization mode, every key required, `additionalProperties: false`); parsed-JSON drift test; provisional v1.0 until Phase 6 | D-05, D-06 (one-way after the Phase 6 freeze), D-07 |
| Unknown vs zero | Per-section `SectionState(status, reason)`; `ExposureStatus` includes `unknown` (COL-09); model validators reject numbers under any status in `UNKNOWN_STATUSES` | Research's top risk; FND-05 |
| Configuration | pydantic-settings: defaults < external `recover-assess.yaml` < `RECOVER_ASSESS__*` env < CLI flags; `extra="forbid"`; env typo scan; client secrets rejected; no allow-list key | FND-03, D-08, D-12 |
| Logging | Closed set of typed pydantic events written as JSONL by a single-writer `RunLog`, with a scrub pass; no body field exists on any event; one write call plus flush per line, repair of an unterminated tail on open, and a tolerant `read_run_log` (Plan 01-02) | GRPH-07; FND-06 for the append-only log, as amended by D-14 |
| Output files | `core/output.py` atomic writers (same-directory temp, fsync, replace with bounded Windows lock retry) (Plan 01-12) | FND-06 |
| Auth | None in Phase 1: `GraphClient` takes an injected async token callable; Phase 2 plugs in the `TokenProvider` | CONTEXT phase boundary |
| Quality gate | stdlib `scripts/check.py` (uv lock --check, ruff, ruff format --check, mypy, lint-imports, pytest) is the only gate locally and in CI; no Makefile. During execution it runs once per wave join (asserted as a precondition by the next wave's plans) and at the end of single-plan waves; per-task verifies stay scoped to each plan's own files and under 30 s, and tests that read the whole working tree carry "whole_tree" in their names so in-wave verifies can deselect them | D-02, D-03 |
| Architecture enforcement | Five import-linter contracts (core never imports cli; httpx2 only in graph/providers; LLM SDKs only in providers; score/agent/report import no network libs; typer/rich only in cli) proven by deliberate-violation fixtures against the real contracts | FND-02, D-04 |
| Client-data guard | Generic repo scan over `git ls-files` of the shippable tree plus an optional external term list (`RECOVER_ASSESS_PRIVATE_TERMS_FILE`); sdist content test (Plan 01-12) | FND-07, D-10, D-11 |
| Directory layout | `src/recover_assess/{cli.py, core/{errors,clock,log,config,output,throttle,graph,graph_policy}.py, core/graph_allowlist.yaml, core/models/{common,fact_sheet,registry}.py, core/{collect,score,agent,report,providers,run}/}`; `tests/{unit,graph,integration,fakes,support,fixtures}/`; `scripts/` (verify_sha256.py, check.py, gen_schemas.py; no package marker); `schemas/`; `config/` (operator data files from Phase 3, never the allow-list) | Layering per research ARCHITECTURE.md; empty stage packages exist so import-linter can name them |

## Stack Touched in Phase 1

- [ ] Project scaffold (uv, uv_build, ruff, mypy strict, pytest, import-linter, approved lock) — Plan 01-01
- [ ] Routing: one real allow-listed Graph template end to end — Plan 01-02 Task 1
- [ ] Data: one real read (Graph response on MockTransport) and real writes (run.jsonl line — Plan 01-02; generated schema file — Plan 01-11)
- [ ] Interface: CLI `--version` and `config show` wired to real code — Plans 01-01, 01-04
- [ ] Run command: `uv run python scripts/check.py` locally and the same script in `.github/workflows/ci.yml` — Plan 01-03

## Out of Scope (Deferred to Later Slices)

- Sign-in of any kind (delegated device code/browser, certificate, managed identity), the `TokenProvider`, DPAPI token cache, `doctor` — Phase 2 and Phase 11
- One TLS context shared by MSAL, Graph and the LLM client (truststore wiring) — Phase 2 (AUTH-05)
- Site resolution, CSV intake, any collector (C1-C9), run folders and per-site state machine — Phases 2-6
- Resource-unit token buckets and x-ms-resource-unit tracking — not required by GRPH-05; revisit if pilot throttling demands it
- Retrying transient 5xx and transport errors (RESEARCH A10) — only 429/503 retry per spec
- Pushing to a GitHub remote, branch protection, the private CI job with the external term list — user actions once a remote exists
- Scoring, reports, LLM providers, agent, skill — Phases 7-12

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering its architectural decisions:

- Phase 2: sign in, `doctor`, resolve one site by URL, collect C1 into a schema-valid partial fact sheet in a run folder
- Phase 3: CSV batches, `--validate-only`, `grants plan`, C2/C3 site structure, per-site run states
- Phase 4: streaming drive-delta inventory and folder patterns (C4) with honest truncation
- Phase 5: fill rates, exposure, ownership, SAM join (C5-C7, C9): the complete fact sheet
- Phase 6: durable runs, redaction, progress, prune and Step 1 pilot acceptance (contract freeze)
- Phase 7: deterministic scoring and calibration harness
- Phase 8: `assess --no-llm` reports and portfolio (the Core Value)
- Phase 9: LLM providers and capability probe
- Phase 10: agent (schema proposal, plan, verifier)
- Phase 11: batch hardening and unattended server runs
- Phase 12: Claude Code skill and pilot calibration
