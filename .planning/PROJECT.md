# recover-assess

## What This Is

`recover-assess` is a read-only Python CLI that takes one named SharePoint site (or a CSV of sites), collects evidence from Microsoft Graph, and returns a Recover-track assessment per site: an effort rating (Low / Medium / High) calculated in code, a recommended action (Enrich / Archive / Restrict / Delete), the best backfill strategy, a proposed starter schema, and a plain-English plan written by an LLM agent and checked by a verifier. It is the engine behind **Module 1 (AI-readiness assessment)** of the AI-Ready SharePoint Framework & Enablement Playbook: first piloted at the pilot organisation, then packaged as a portable asset for other companies.

## Core Value

Every site's effort rating, action and strategy is **deterministic, traceable to evidence in the fact sheet, and produced without ever writing to Microsoft 365**. If the LLM layer fails, the Collector + scoring must still give a credible, defensible triage.

## Business Context

- **Customer**: the pilot organisation first (internal pilot: content/site owners, Security, the assessment team); then other companies' M365 estates via the playbook
- **Revenue model**: Playbook Module 1 ("AI-readiness assessment, ~2 weeks"), the lead-in to later modules (reference architecture, content contracts, adoption kit)
- **Success metric**: Calibration on ~10 hand-assessed pilot sites in the pilot tenant: effort band matches on ≥8/10, action matches on ≥9/10
- **Strategy notes**: `AI-Ready SharePoint Framework & Enablement Playbook (Draft).md`; parent spec https://claude.ai/artifact/GHAZsGcEsoVtkTRMqdkaCN

## Requirements

### Validated

- ✓ Read-only Graph client: v1.0 only, GET + `$batch`-of-GETs allow-list, paging, Retry-After/backoff (≤6 retries, 300 s budget), circuit breaker, concurrency limits, truststore + proxy, structured logs with no bodies/tokens — Phase 1
- ✓ CI-enforced scaffold (ruff, mypy strict, import-linter contracts, blocked-terms gate, one `scripts/check.py` gate locally and on windows/ubuntu runners) and the generated provisional fact-sheet v1.0 schema — Phase 1
- ✓ Corporate-network install: `uv sync` via a package mirror with `UV_SYSTEM_CERTS`, or a hash-locked pip fallback with an offline wheel build — Phase 1 (quick tasks 261116-kqf, 261117-i8j; UAT on the pilot workstation)

### Active

**Collector (Step 1 spec = source of truth; replaces parent M0/M1)**
- [ ] Site input by URL, server-relative path, or display name (delegated only); batch by CSV (BOM, tab/comma, unknown columns passed through, dedupe by site ID, 500-row cap)
- [ ] Auth via one `TokenProvider`: `delegated` (device code / browser, encrypted MSAL cache) first; `app_certificate` and `managed_identity` for server runs; client secrets rejected
- [ ] Collectors C1–C7, sample candidates (no download), C9 SAM join → `fact_sheet.json` validated against `schemas/fact_sheet.schema.json` v1.0
- [ ] `doctor`, `collect`, `resume`, `grants plan`, `prune`; `resolution.csv`, `collection_summary.csv`, `run.json`, `logs/run.jsonl`; path modes full/tokens/hashed; hashed contributors

**Scoring & reports (parent M2)**
- [ ] Deterministic scorecard from `config/rubric.yaml`: 6 weighted dimensions → effort band, action rules, prerequisites, backfill strategy; every sub-score records its inputs and rubric version
- [ ] Per-site `report.html` + `report.md`, batch `portfolio.csv` + `portfolio.html`; `--no-llm` mode; neutral theme default, client themes as separate files

**LLM providers (parent M3)**
- [ ] `LLMProvider` interface with strict-mode JSON schemas, local jsonschema validation, one repair retry
- [ ] Azure OpenAI via the corporate LLM gateway as the primary implementation
- [ ] Anthropic Bedrock provider as a placeholder stub behind the same interface (raises "not configured" until approved)

**Agent (parent M4)**
- [ ] A2 schema proposal, A3 plan, A4 verifier (code pointer/number checks + model check) on the metadata tier; `needs_review` on second failure
- [ ] Sample tier: C8 content download, local text extraction, A1 classification, untrusted-document wrapping, confirmation prompt, redaction hook

**Batch hardening (parent M5)**
- [ ] Per-site state machine through to reported, `resume`, `rescore`, `report`, `--estimate`, progress view, exit codes, time limits

**Claude Code skill (parent M6)**
- [ ] `skills/recover-assessment/SKILL.md`: runs doctor → assess, reads recommendations/report to answer follow-ups, never edits results

**Pilot**
- [ ] Hand-assessed calibration on ~10 pilot sites in the pilot tenant and rubric tuning toward the 8/10 and 9/10 targets

### Out of Scope

- Any write to Microsoft 365 (tagging, moving, archiving, permission changes) — the tool is read-only by design; the backfill write-back pipeline is a separate project (Playbook Module 2)
- Crawling or enumerating tenant sites — sites come only from `--site` / `--csv`
- Track 2 (structured capture / content contracts / "File this" skill) — separate project
- SharePoint Knowledge MCP (Serve layer over enriched libraries) — separate project
- Results MCP server and local web form (parent M7) — deferred to v2
- Golden-question-set answer-accuracy measurement — playbook measurement kit, not this tool
- Client secrets — certificate, managed identity or delegated only
- Graph beta endpoints — v1.0 only
- Replacing SAM reports — their exports are joined as evidence (C9)

## Context

- Greenfield repo at `C:\SPCollector`; two specs present: `Recover Assessment Collector Build Spec (Step 1).md` (detailed Collector spec) and the AI-Ready SharePoint framework draft. Parent build spec (M0–M7, rubric, agent, providers) lives in a Claude Doc.
- Where Step 1 and the parent spec disagree (auth modes, site states, outputs), Step 1 wins for the Collector; parent spec governs M2 onwards, adjusted for the decisions below.
- Pilot runs on the user's Windows 11 workstation with the user's own delegated credentials against designated SharePoint URLs, behind the corporate proxy/TLS inspection. Batch/scheduled runs move to a Windows Server (Azure VM managed identity or on-prem certificate) once Security approves.
- Pilot-stack quirks for Azure OpenAI via the corporate LLM gateway (403 `upstream_auth_403`, empty streamed tokens) are captured in the user's local gateway-troubleshooting skill (not in repo); the corporate Anthropic proxy (Apigee-fronted Bedrock) shape is in the user's local Anthropic-proxy skill (not in repo) (for when the stub is filled).
- Framework rationale: AI tools are limited by findability/trust/filterability of content; Recover triages existing content so only valuable, governed content gets enriched and opened to AI.

## Constraints

- **Security**: Read-only against M365 — only GET and `POST /$batch` of GETs, enforced in `core/graph.py` and tested — this is the tool's central trust promise
- **Privacy**: Metadata tier by default; no file content leaves the tenant unless the sample tier is explicitly chosen and confirmed; run folders are Confidential
- **Portability / IP**: No pilot-organisation data, names, endpoints or pilot inputs in the repo; the pilot organisation's theme and gateway config are external config — required to take the playbook to other companies
- **Platform**: Windows first (Win 11, Server 2019+), also macOS/Linux; pathlib only, short output paths, `truststore`, `HTTPS_PROXY`/`NO_PROXY`
- **Tech stack**: Python 3.12 with `uv`; msal, msal-extensions, azure-identity, httpx2 (replaces frozen httpx; shared with the openai SDK), tenacity, truststore, pydantic v2, pydantic-settings, pyyaml, jsonschema, typer, rich, jinja2; openai SDK; ruff, mypy strict, import-linter, pytest, pytest-asyncio, httpx2 MockTransport (replaces respx), hypothesis. Approved if needed: msal[broker] (only if Conditional Access blocks device code and browser); extraction libs + defusedxml for the v2 sample tier. Ask before adding other dependencies
- **Architecture**: `core` never imports `cli`; only `core/providers` imports LLM SDKs; collectors are async functions returning pydantic models; inventories are streamed, never held in memory
- **Contract**: `fact_sheet.json` schema v1.0 is the contract with later stages — add = minor, rename/remove = major; schema generated from pydantic models and kept in sync with golden files
- **Model route**: Azure OpenAI via the corporate LLM gateway is the only approved LLM route for now

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Scope v1 = parent milestones M0–M6 | Delivers the full assessment (Module 1) incl. agent and skill; results MCP/web form not needed for pilot | — Pending |
| Step 1 Collector spec supersedes parent M0/M1 | More detailed and later; adds managed identity, path modes, prune | — Pending |
| Delegated auth with user's own credentials first | Pilot runs on workstation against designated sites; no app approval needed to start | — Pending |
| Azure OpenAI via the corporate LLM gateway as primary LLM; Anthropic Bedrock as stub | Only approved route today; keep interface ready for Claude | — Pending |
| Scores/actions computed in code, LLM only explains | Repeatable, traceable, defensible to Security and clients | — Pending |
| Track 2, backfill write-back and Knowledge MCP are separate projects | Keeps this tool read-only and focused on Module 1 | — Pending |
| Done = pilot calibration first, then portable packaging | Calibrated numbers are the playbook's credibility | — Pending |
| httpx2 + MockTransport instead of httpx + respx | httpx frozen; openai 3.x uses httpx2; one HTTP stack | ✓ Good — Phase 1 (948 tests on MockTransport, no respx needed) |
| Display-name lookup out of v1 (URL/path only) | /sites?search needs Sites.Read.All, conflicts with Sites.Selected | — Pending |
| Sample tier (C8, A1) deferred to v2 | Riskiest/costliest; no document text leaves tenant in v1; add only if calibration shows need | — Pending |
| Vertical MVP phase structure, fine granularity (12 phases) | Walking skeleton by Phase 2; --no-llm product by Phase 8 | — Pending |
| Accept non-TransportError exceptions escaping the HTTP layer for now (AR-01) | No URL or token in their text; fix with review items IN-03 / WR-01 | — Pending (Phase 01 SECURITY.md) |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-11-17 after Phase 1*
