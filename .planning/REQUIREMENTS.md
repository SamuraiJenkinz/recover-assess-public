# Requirements: recover-assess

**Defined:** 2026-11-15
**Core Value:** Every site's effort rating, action and strategy is deterministic, traceable to evidence in the fact sheet, and produced without ever writing to Microsoft 365.

Sources: `Recover Assessment Collector Build Spec (Step 1).md` (Collector source of truth), parent build spec (M2–M6), `.planning/research/SUMMARY.md` (corrections and sign-offs).

## v1 Requirements

### Foundation

- [x] **FND-01**: Developer can install with `uv` on pinned Python 3.12 without admin rights, with `UV_SYSTEM_CERTS` guidance for TLS-inspecting proxies
- [x] **FND-02**: CI enforces ruff (explicit rule select), mypy strict and import-linter contracts (core ↛ cli; only `graph.py` and `providers/` import httpx2; only `providers/` import LLM SDKs; score/agent/report import no network libs)
- [x] **FND-03**: Operator configures the tool via `recover-assess.yaml` with precedence defaults → YAML → `RECOVER_ASSESS__*` env → CLI flags; unknown keys and mistyped env vars are errors
- [x] **FND-04**: Fact sheet pydantic models generate `schemas/fact_sheet.schema.json` (provisional v1.0, every key required, null where allowed); a test fails if models and checked-in schema drift
- [x] **FND-05**: Fact sheet v1.0 includes `privacy`, `collect_limits`, per-section `status`/`reason`, `coverage`, `truncated_reason`, `path_unresolved`, `hash_coverage`, `owners_source` and `last_activity` basis before first release
- [x] **FND-06**: All output files are written atomically (temp file + replace, with Windows lock retry) so an interrupted run never leaves a half-written file. *Amendment (2026-11-15, user-approved, Phase 1 decision D-14):* append-only logs (`run.jsonl`) satisfy FND-06 via one write per line plus flush, repair of an unterminated tail on open, and tolerant reading that skips a trailing partial line; all other output files remain strictly atomic (temp file + replace, Windows lock retry).
- [x] **FND-07**: Repo contains no client-specific data, names, endpoints or themes; pilot-organisation and gateway settings live only in external config

### Authentication

- [ ] **AUTH-01**: User can sign in with delegated auth (device code by default, `--browser` for interactive) using their own credentials; token cache encrypted with DPAPI and fails closed rather than falling back to plaintext
- [ ] **AUTH-02**: Operator can run with `app_certificate` (PEM or PFX + password env var) on a server
- [ ] **AUTH-03**: Operator can run with `managed_identity` (system- or user-assigned) on an Azure VM
- [ ] **AUTH-04**: A configured client secret causes the run to fail with a message pointing to certificate or managed-identity auth
- [ ] **AUTH-05**: One TLS context (OS trust store via truststore) is used by MSAL, the Graph client and the LLM client; `HTTPS_PROXY`/`NO_PROXY` honoured
- [ ] **AUTH-06**: User can run `doctor` to check config, auth mode validity, token acquisition with decoded scopes/roles, per-target reachability (`reachable`/`not_granted`/`not_found`), proxy/TLS to Graph and login endpoints, and warn when `--out` is in a synced OneDrive folder; it exits non-zero with a fix on the first blocking failure

### Graph Client

- [x] **GRPH-01**: All Microsoft 365 traffic goes through one module whose allow-list permits only GET on templated v1.0 paths and `POST /$batch` whose sub-requests are allowed GETs; anything else raises `WriteAttemptError` before any network call (tested for every verb)
- [x] **GRPH-02**: Every absolute `@odata.nextLink` and redirect is validated against host and path prefix before following; `/content` is not allowed in v1
- [x] **GRPH-03**: Paged calls follow `@odata.nextLink` to the end with a configurable cap that marks results `truncated`
- [x] **GRPH-04**: Small independent GETs are sent in `$batch` groups of ≤20; each sub-response is checked separately; throttled sub-requests are re-queued; sub-responses with nextLink fall back to paged GETs
- [x] **GRPH-05**: On 429/503 the client honours Retry-After (else exponential backoff with full jitter, 1 s base, 60 s cap), retries ≤6 times, gives up after 5 minutes per request, and throttling is coordinated across the whole run (tenant/app-wide), with a per-site breaker that fails the site as `throttled_out`
- [x] **GRPH-06**: Concurrency is limited to 4 in-flight requests per site and 2 sites at a time by default
- [x] **GRPH-07**: Every request is logged to `run.jsonl` with path template, status, duration, retries and request-id; response bodies, tokens and `downloadUrl` values never appear in logs, fixtures or outputs (log-capture test)
- [x] **GRPH-08**: Each fact sheet records `graph_stats` (requests, batches, throttles, retries, seconds)

### Inputs & Resolution

- [ ] **INP-01**: User can collect one site by full URL or server-relative path; `normalize` is a pure, unit-tested function (30+ input cases)
- [ ] **INP-02**: A display-name input returns a clear "use the URL" message (`name_requires_url`); no `/sites?search` call in v1
- [ ] **INP-03**: User can supply a CSV (UTF-8 with/without BOM, comma or tab, case-insensitive headers); only `site` is required; unknown columns pass through to `input.extra`; rows run in priority order; duplicates resolving to the same site ID are collected once; bad rows are recorded and skipped; 500-row cap (configurable)
- [ ] **INP-04**: Resolution maps 200/404/403 to `resolved`/`not_found`/`not_granted` or `no_access`, and writes `resolution.csv` with the specified columns
- [ ] **INP-05**: User can run `collect --validate-only` to resolve every row without collecting
- [ ] **INP-06**: User can run `grants plan --csv` to print site IDs, `POST /sites/{id}/permissions` read-grant bodies and Graph PowerShell lines for an admin; the tool never calls the grant endpoint

### Collectors

- [ ] **COL-01**: C1 records site identity, dates, site kind (group/Teams-connected vs communication) and subsites (recorded, not collected, with `has_subsites` warning)
- [ ] **COL-02**: C2 records visible lists and libraries tagged `library`/`pages`/`list`, skipping hidden and configured system lists, and resolves each library's drive ID
- [ ] **COL-03**: C3 records columns (type from facet, custom-column detection by column group and built-in list, term-set ID) and content types (ID-prefix checks, `default_content_types_only`)
- [ ] **COL-04**: C4 streams the drive delta inventory with an id-keyed, order-independent accumulator (dedupe by id, folder paths resolved in a post-pass, no raw items held), producing counts, bytes, depth max/p50/p90, category shares, top extensions, age buckets, created-by-year, largest files and `duplicate_rate` with `hash_coverage`
- [ ] **COL-05**: C4 stops at `max_items_per_library` and records `truncated`, `truncated_reason` and `coverage`; truncated ratios and `last_activity` are flagged as biased, not just lower bounds
- [ ] **COL-06**: Folder pattern mining classifies segments at depths 1–4 (year, fiscal_year, quarter, month, date, numeric_id, categorical literal) per `config/patterns.yaml` and records depth, kind, share, distinct count and examples
- [ ] **COL-07**: `last_activity` combines file, list, page and drive timestamps and records which sources it used
- [ ] **COL-08**: C5 computes per-column `fill_rate` and `mean_fill_rate` on the first N non-folder items using internal names (handling lookup/person fields and the 12-lookup limit), recording method and sample size; lists also get an item count
- [ ] **COL-09**: C6 checks permissions on a fixed budget (root, top-level folders, then hash-priority files) and records link scopes, direct grants, guest/external and EEEU principals, and `differs_from_root`; a 403 or caller-scoped result is recorded as `exposure.status` unknown/partial, never as zero
- [ ] **COL-10**: C7 records top contributors and `active_contributors_90d` from C4; with `owners_via_groups: true` it lists group owners; `owner_hint_matched` compares case-insensitively against both
- [ ] **COL-11**: Sample candidates are chosen deterministically (hash-priority from a site-ID seed), restricted to supported types ≤ `max_file_mb`, spread across top-level folders and age buckets; no content is requested
- [ ] **COL-12**: C9 joins an optional SAM export on normalized site URL using a configurable URL column, copying only listed columns, and warns `sam_no_match` (including a hint when URLs look concealed)
- [ ] **COL-13**: A failing collector records a coded warning and the site continues with the remaining collectors

### Run & Outputs

- [ ] **RUN-01**: Each run writes `out/<run-id>/` with `run.json` (versions, secret-free config, auth mode, per-site state), `resolution.csv`, `collection_summary.csv`, `sites/<slug>/fact_sheet.json` (slug ≤40 chars + hash) and `logs/run.jsonl`, staying under Windows path limits
- [ ] **RUN-02**: Sites move through recorded states (pending → resolved → collecting → complete | partial | failed) and per-site time limits mark `partial`
- [ ] **RUN-03**: User can `resume <run-id>` to re-run every non-complete site without repeating completed ones, using the original config unless `--use-current-config`
- [ ] **RUN-04**: Exit codes are 0 (all complete), 2 (any partial/failed), 1 (couldn't start), 130 (interrupted, state saved)
- [ ] **RUN-05**: User can choose `--path-mode full|tokens|hashed` and `output.contributors: email|hashed` (salt per run); redaction is applied once at output time and honoured by every output and report
- [ ] **RUN-06**: User sees a per-site progress view (current stage, files counted, requests, throttles) unless `--quiet`
- [ ] **RUN-07**: User can `prune --older-than 90d` (dry run by default, deletes only with `--yes`, only inside the output root)
- [ ] **RUN-08**: CSV outputs escape formula-leading characters

### Scoring

- [ ] **SCR-01**: Scoring is a pure function of fact sheet + `config/rubric.yaml`: six weighted dimensions (volume, structure debt, exposure, ownership, content difficulty, hygiene) each 0–100, effort score and band (Low/Medium/High)
- [ ] **SCR-02**: Action rules (Archive, Delete-candidate-for-owner-review, Enrich) apply first-match-wins; prerequisites (Restrict while fixing, Find an owner, Map folders to columns) are added
- [ ] **SCR-03**: Backfill strategy (autofill, document processing, custom pipeline) is selected for Enrich sites
- [ ] **SCR-04**: Unknown evidence is a distinct state that lowers confidence; Archive/Delete from truncated or unknown data is flagged `needs_review`
- [ ] **SCR-05**: The scorecard records rubric version, every input value and an evidence pointer per sub-score; the same fact sheet always yields an identical scorecard
- [ ] **SCR-06**: User can run `calibrate` to compare tool results with pre-registered hand labels, reporting match rates against a trivial baseline and a holdout set

### Reports

- [ ] **RPT-01**: Each site gets self-contained `report.html` and `report.md` (headline, why-this-effort table, plan, starter schema, evidence, review flags, footer with versions)
- [ ] **RPT-02**: Each batch gets `portfolio.csv` and a sortable `portfolio.html` (counts by band/action/BU, top quick wins, top exposure)
- [ ] **RPT-03**: User can run `assess --no-llm` to get scorecards and reports with zero model calls
- [ ] **RPT-04**: Reports use a neutral theme by default; client themes are separate files selected with `--theme`
- [ ] **RPT-05**: All rendered text is escaped (HTML autoescape, Markdown allow-list); reports never contain document excerpts

### LLM Providers

- [ ] **LLM-01**: The agent calls one `LLMProvider` interface; only `core/providers` imports LLM SDKs
- [ ] **LLM-02**: Azure OpenAI via the corporate LLM gateway is implemented (OpenAI client with base URL, Chat Completions, strict JSON schema, non-streaming, `api-key` header) with configurable endpoint, deployment and key from env
- [ ] **LLM-03**: An Anthropic Bedrock provider stub exists behind the same interface and fails with `ProviderNotConfigured`
- [ ] **LLM-04**: Step schemas are lowered to the strict-mode subset (all required, nullable unions, `additionalProperties: false`, size/depth limits); responses are validated locally against the full schema with one repair retry
- [ ] **LLM-05**: Transient errors retry with backoff honouring retry-after; auth errors (incl. gateway `upstream_auth_403`) and empty 200 responses fail fast with a clear code
- [ ] **LLM-06**: User can run an LLM capability probe in `doctor` (key authorised, strict schema accepted, usage tokens returned)
- [ ] **LLM-07**: Provider, model, prompt version and token counts are recorded in every output and the run log; prompt text is not logged unless `--log-prompts`
- [ ] **LLM-08**: `llm.allowed_providers` blocks any unlisted provider before collection starts

### Agent

- [ ] **AGT-01**: A2 proposes a starter schema (name, type, source, allowed values/term-set candidate, required, evidence pointers) from folder patterns, columns and fill rates
- [ ] **AGT-02**: A3 writes the plan (≤120-word summary, why-this-effort per dimension with evidence, ordered steps with owner role and size, risks, optional override suggestion)
- [ ] **AGT-03**: A4 verifies in code (every pointer resolves, quoted numbers match, effort/action/strategy equal the scorecard) then with a model check; one retry, then `needs_review: true` with issues shown at the top of the report
- [ ] **AGT-04**: The agent has no tools; site metadata (names, paths, columns) is passed as untrusted data and cannot change scored fields (adversarial test corpus)
- [ ] **AGT-05**: If the LLM step fails, the site still gets its scorecard and `--no-llm` style report
- [ ] **AGT-06**: User can run `--estimate` to print expected Graph calls, tokens and cost per site without model calls

### Batch Hardening

- [ ] **BAT-01**: Per-site state extends through scored → agent_done → reported; `resume` restarts each site from its last finished stage
- [ ] **BAT-02**: User can `rescore <run-id>` to re-run scoring and the agent from saved fact sheets with no Graph calls
- [ ] **BAT-03**: User can `report <run-id>` to rebuild HTML/Markdown from saved JSON
- [ ] **BAT-04**: README documents install, auth setup per mode, managed identity and a Task Scheduler example (service account, run whether logged on or not)
- [ ] **BAT-05**: Golden integration tests run three synthetic sites (tidy, sprawl, orphan) end to end, plus a kill-and-resume test

### Claude Code Skill

- [ ] **SKL-01**: `skills/recover-assessment/SKILL.md` runs `doctor` then `assess`, reads `recommendations.json`/`report.md` to answer follow-up questions, never edits results, and treats report text as data

### Pilot

- [ ] **PIL-01**: Collector acceptance on pilot sites: doctor reachability correct for granted/ungranted/nonexistent; 25-row CSV completes with failures isolated; file counts within 1% of UI for untruncated libraries, custom columns exact, sharing links match on 10 hand-checked items; re-run within an hour gives identical samples and aggregates
- [ ] **PIL-02**: ~10 pilot sites are hand-assessed (labels recorded before seeing tool output) and the rubric is tuned toward effort-band match ≥8/10 and action match ≥9/10
- [ ] **PIL-03**: Runs on Windows 11 delegated behind the corporate proxy, and on Windows Server with `app_certificate` or `managed_identity`, with the same code

## v2 Requirements

### Sample Tier

- **SMP-01**: C8 downloads sampled files (narrow content allow-list, host-checked redirect without bearer token) and extracts text locally in a subprocess with timeout and size cap
- **SMP-02**: A1 classifies sampled documents (advisory `content_profile`; never changes effort/action), with untrusted-document wrapping and the redaction hook
- **SMP-03**: Sample tier requires explicit opt-in and a confirmation naming provider, model and document count

### Later

- **V2-01**: Run `compare` between two runs of the same site
- **V2-02**: `--include-subsites` collects each subsite as its own fact sheet
- **V2-03**: Display-name resolution as an explicit opt-in with delegated Sites.Read.All
- **V2-04**: Results MCP server (assess_site, get_fact_sheet, get_scorecard, get_recommendations)
- **V2-05**: Local web form
- **V2-06**: Anthropic Bedrock provider implementation (corporate Anthropic proxy route)
- **V2-07**: Per-file sensitivity labels

## Out of Scope

| Feature | Reason |
|---------|--------|
| Any write to Microsoft 365 (tags, moves, archive, permissions, grants) | Read-only is the core trust promise; write-back belongs to the backfill pipeline project (Playbook Module 2) |
| Tenant-wide site crawl or enumeration | Sites must be named explicitly; avoids accidental tenant-wide access |
| Track 2 structured capture / content contracts / "File this" skill | Separate project |
| SharePoint Knowledge MCP (Serve layer) | Separate project |
| Golden-question answer-accuracy measurement | Playbook measurement kit, not this tool |
| Continuous monitoring / alerting | Assessment is point-in-time; SAM covers ongoing governance |
| LLM-computed scores or a single opaque 0–100 readiness headline | Scores must be deterministic and explainable |
| PII/DLP content detection | Purview's job; out of the Recover assessment's purpose |
| Client secrets | Certificates, managed identity or delegated only |
| Graph beta endpoints | Stability; v1.0 only |
| Hosted web app / telemetry | Local CLI; nothing leaves the machine except Graph and approved LLM calls |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FND-01 | Phase 1 | Complete |
| FND-02 | Phase 1 | Complete |
| FND-03 | Phase 1 | Complete |
| FND-04 | Phase 1 | Complete |
| FND-05 | Phase 1 | Complete |
| FND-06 | Phase 1 | Complete |
| FND-07 | Phase 1 | Complete |
| AUTH-01 | Phase 2 | Pending |
| AUTH-02 | Phase 11 | Pending |
| AUTH-03 | Phase 11 | Pending |
| AUTH-04 | Phase 2 | Pending |
| AUTH-05 | Phase 2 | Pending |
| AUTH-06 | Phase 2 | Pending |
| GRPH-01 | Phase 1 | Complete |
| GRPH-02 | Phase 1 | Complete |
| GRPH-03 | Phase 1 | Complete |
| GRPH-04 | Phase 1 | Complete |
| GRPH-05 | Phase 1 | Complete |
| GRPH-06 | Phase 1 | Complete |
| GRPH-07 | Phase 1 | Complete |
| GRPH-08 | Phase 1 | Complete |
| INP-01 | Phase 2 | Pending |
| INP-02 | Phase 2 | Pending |
| INP-03 | Phase 3 | Pending |
| INP-04 | Phase 2 | Pending |
| INP-05 | Phase 3 | Pending |
| INP-06 | Phase 3 | Pending |
| COL-01 | Phase 2 | Pending |
| COL-02 | Phase 3 | Pending |
| COL-03 | Phase 3 | Pending |
| COL-04 | Phase 4 | Pending |
| COL-05 | Phase 4 | Pending |
| COL-06 | Phase 4 | Pending |
| COL-07 | Phase 4 | Pending |
| COL-08 | Phase 5 | Pending |
| COL-09 | Phase 5 | Pending |
| COL-10 | Phase 5 | Pending |
| COL-11 | Phase 4 | Pending |
| COL-12 | Phase 5 | Pending |
| COL-13 | Phase 3 | Pending |
| RUN-01 | Phase 2 | Pending |
| RUN-02 | Phase 3 | Pending |
| RUN-03 | Phase 6 | Pending |
| RUN-04 | Phase 6 | Pending |
| RUN-05 | Phase 6 | Pending |
| RUN-06 | Phase 6 | Pending |
| RUN-07 | Phase 6 | Pending |
| RUN-08 | Phase 2 | Pending |
| SCR-01 | Phase 7 | Pending |
| SCR-02 | Phase 7 | Pending |
| SCR-03 | Phase 7 | Pending |
| SCR-04 | Phase 7 | Pending |
| SCR-05 | Phase 7 | Pending |
| SCR-06 | Phase 7 | Pending |
| RPT-01 | Phase 8 | Pending |
| RPT-02 | Phase 8 | Pending |
| RPT-03 | Phase 8 | Pending |
| RPT-04 | Phase 8 | Pending |
| RPT-05 | Phase 8 | Pending |
| LLM-01 | Phase 9 | Pending |
| LLM-02 | Phase 9 | Pending |
| LLM-03 | Phase 9 | Pending |
| LLM-04 | Phase 9 | Pending |
| LLM-05 | Phase 9 | Pending |
| LLM-06 | Phase 9 | Pending |
| LLM-07 | Phase 9 | Pending |
| LLM-08 | Phase 9 | Pending |
| AGT-01 | Phase 10 | Pending |
| AGT-02 | Phase 10 | Pending |
| AGT-03 | Phase 10 | Pending |
| AGT-04 | Phase 10 | Pending |
| AGT-05 | Phase 10 | Pending |
| AGT-06 | Phase 10 | Pending |
| BAT-01 | Phase 11 | Pending |
| BAT-02 | Phase 11 | Pending |
| BAT-03 | Phase 11 | Pending |
| BAT-04 | Phase 11 | Pending |
| BAT-05 | Phase 11 | Pending |
| SKL-01 | Phase 12 | Pending |
| PIL-01 | Phase 6 | Pending |
| PIL-02 | Phase 12 | Pending |
| PIL-03 | Phase 12 | Pending |

**Coverage:**
- v1 requirements: 82 total
- Mapped to phases: 82
- Unmapped: 0 ✓

---
*Requirements defined: 2026-11-15*
*Last updated: 2026-11-15 after roadmap creation (traceability mapped to 12 phases)*
