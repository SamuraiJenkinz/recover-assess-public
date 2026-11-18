# Roadmap: recover-assess

## Overview

recover-assess is built as a vertical MVP: lock the trust promise first (a tested read-only Graph client and a generated fact-sheet contract), cut a thin walking skeleton early (sign in, `doctor`, resolve one site by URL, collect its identity into a schema-valid partial `fact_sheet.json`), then deepen the Collector in dependency order (site structure, library inventory, exposure/ownership/fill rates) and make runs durable and pilot-ready. With a complete fact sheet in hand, ship the Core Value: deterministic scoring and reports that work with `--no-llm`. Only then layer on LLM providers and the agent (schema proposal, plan, verifier), harden batch and unattended server runs, and finish with the Claude Code skill and the pilot calibration (effort band >=8/10, action >=9/10).

Granularity is `fine` (12 phases). The sample tier (C8 download, A1 classification) is deferred to v2 per REQUIREMENTS.md. Hard dependencies respected: read-only Graph client and fact-sheet contract first; C1-C3 before C4; C4 before C5-C7; scoring before agent.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation, Contract & Read-Only Graph Client** - CI-enforced scaffold, generated fact-sheet v1.0 contract, and the single tested read-only path to Microsoft 365 (completed 2026-11-17)
- [ ] **Phase 2: Walking Skeleton: Sign In, Doctor, Resolve & Collect One Site** - Thin end-to-end slice: delegated sign-in, `doctor`, resolve a site by URL, collect C1 into a schema-valid partial fact sheet
- [ ] **Phase 3: Batch Intake & Site Structure (C2, C3)** - CSV batches, `--validate-only`, `grants plan`, libraries/lists/columns/content types, per-site run states
- [ ] **Phase 4: Library Inventory & Folder Patterns (C4)** - Streaming drive-delta inventory, truncation/coverage disclosure, folder-pattern mining, `last_activity`, deterministic sample candidates
- [ ] **Phase 5: Exposure, Ownership & Metadata Fill (C5-C7, C9)** - Fill rates, permission exposure with honest unknowns, ownership, SAM join: the complete fact sheet
- [ ] **Phase 6: Durable Runs & Pilot-Ready Collector** - Resume, exit codes, path/contributor redaction, progress, prune, and Step 1 acceptance on pilot sites
- [ ] **Phase 7: Deterministic Scoring & Calibration Harness** - Rubric-driven scorecard (effort band, action, prerequisites, backfill strategy) and the `calibrate` command
- [ ] **Phase 8: Reports & Portfolio (`--no-llm` Product)** - Per-site HTML/Markdown reports, batch portfolio, themes, escaped rendering: the Core Value delivered with zero model calls
- [ ] **Phase 9: LLM Providers & Capability Probe** - `LLMProvider` interface, Azure OpenAI via the corporate LLM gateway, Bedrock stub, strict-schema lowering, `doctor` LLM probe
- [ ] **Phase 10: Agent: Schema Proposal, Plan & Verifier** - A2 starter schema, A3 plan, A4 verifier with `needs_review`, injection-safe, `--estimate`
- [ ] **Phase 11: Batch Hardening & Unattended Server Runs** - Stage-level resume, `rescore`, `report`, certificate and managed-identity auth, README, golden end-to-end tests
- [ ] **Phase 12: Claude Code Skill & Pilot Calibration** - `SKILL.md`, hand-assessed calibration on ~10 pilot sites, workstation and server runs with the same code

## Phase Details

### Phase 1: Foundation, Contract & Read-Only Graph Client
**Goal**: A developer has a CI-enforced scaffold in which the only path to Microsoft 365 is a tested read-only Graph client, and the fact-sheet v1.0 contract is generated from code
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: FND-01, FND-02, FND-03, FND-04, FND-05, FND-06, FND-07, GRPH-01, GRPH-02, GRPH-03, GRPH-04, GRPH-05, GRPH-06, GRPH-07, GRPH-08
**Success Criteria** (what must be TRUE):
  1. `uv sync --locked` on a clean Windows 11 machine without admin rights installs the pinned Python 3.12 environment (with `UV_SYSTEM_CERTS` guidance for TLS-inspecting proxies), and CI runs ruff, mypy strict and import-linter; a deliberate violation (core importing cli, a module other than `graph.py` importing httpx2, a non-provider importing an LLM SDK, score/agent/report importing a network library) turns CI red
  2. Against a fake Graph on a mock transport, every verb other than GET, every non-allow-listed path, `/content`, a beta URL, a `POST /$batch` containing a non-GET sub-request, and hostile `@odata.nextLink`/redirect URLs are rejected with `WriteAttemptError` (or a validation error) before any network call
  3. Under simulated throttling the client pages to the end (cap marks results `truncated`), sends `$batch` groups of <=20 and re-queues throttled sub-requests, honours Retry-After then jittered backoff (<=6 retries, 5-minute give-up), shares one throttle gate across sites, fails a site as `throttled_out` when its breaker trips, never exceeds 4 in-flight per site / 2 sites, and records `graph_stats`
  4. A log-capture test proves `run.jsonl` carries path template, status, duration, retries and request-id for every request and never contains response bodies, tokens or `downloadUrl` values
  5. Config precedence (defaults, YAML, `RECOVER_ASSESS__*` env, CLI flags) works and unknown keys or mistyped env vars are errors; `schemas/fact_sheet.schema.json` is generated from the pydantic models (provisional v1.0 with `privacy`, `collect_limits`, per-section `status`/`reason`, `coverage`, `truncated_reason`, `path_unresolved`, `hash_coverage`, `owners_source`, `last_activity` basis) and a drift test fails when models and schema diverge; an interrupted write leaves no half-written file; a repo scan finds no client-specific data, names, endpoints or themes
**Plans:** 12/12 plans complete (waves: 1 = 01-01; 2 = 01-02, 01-03, 01-04, 01-11; 3 = 01-06, 01-12; 4 = 01-05, 01-07; 5 = 01-08; 6 = 01-09; 7 = 01-10)

Plans:
**Wave 1**
- [x] 01-01-PLAN.md — Toolchain bootstrap (checksum-verified uv, Python 3.12, pinned manifest, lock) with blocking package-legitimacy checkpoint, package skeleton, errors and clock (FND-01)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 01-02-PLAN.md — Walking-skeleton tracer: one allow-listed GET through policy, client, hook and MockTransport to one typed run.jsonl line; hardened second guard, failure paths and run.jsonl repair-on-open (GRPH-01, GRPH-07, FND-06)
- [x] 01-03-PLAN.md — Single quality gate scripts/check.py, CI workflow, deliberate-violation import-contract fixtures and AST bans (FND-02)
- [x] 01-04-PLAN.md — Layered typo-proof config and `config show` (FND-03)
- [x] 01-11-PLAN.md — Contract slice: fact-sheet envelope models generate the checked-in schema with a parsed-JSON drift test (FND-04)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 01-06-PLAN.md — Pinned 13-template allow-list, complete canonicaliser and $batch body validator with hostile corpus (GRPH-01, GRPH-02)
- [x] 01-12-PLAN.md — Atomic writer with Windows lock retry, client-data repo scan and sdist guard (FND-06, FND-07)

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 01-05-PLAN.md — Full provisional fact-sheet v1.0 contract with status/coverage vocabulary and unknown-vs-zero invariant (FND-04, FND-05)
- [x] 01-07-PLAN.md — Paging with cap and truncation, validated nextLinks and manual redirects, annotation stripping (GRPH-02, GRPH-03)

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 01-08-PLAN.md — Retry-After and full-jitter retries, 300 s budget, shared throttle gate, per-site breaker (GRPH-05)

**Wave 6** *(blocked on Wave 5 completion)*
- [x] 01-09-PLAN.md — $batch with re-queue and nextLink fallback, 2-site / 4-in-flight limits, graph_stats, from_settings (GRPH-04, GRPH-06, GRPH-08)

**Wave 7** *(blocked on Wave 6 completion)*
- [x] 01-10-PLAN.md — Canary log-capture audit, multi-site throttled acceptance scenario, developer quick check (GRPH-07)

**Spikes & gates**: Confirm sign-off 1 (httpx2 + built-in `MockTransport`, replacing httpx + respx) before planning; REQUIREMENTS.md FND-02 already assumes httpx2 but PROJECT.md constraints still list httpx/respx. Graph client mechanics are standard patterns: invest in tests, not research. Start the gateway key request and the auth/TLS spikes (Phase 2) on day one because they depend on external keys, consent and Security input.

### Phase 2: Walking Skeleton: Sign In, Doctor, Resolve & Collect One Site
**Goal**: A user can sign in with their own credentials, run `doctor`, resolve one SharePoint site by URL, and collect its identity into a schema-valid partial `fact_sheet.json` inside a standard run folder
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: AUTH-01, AUTH-04, AUTH-05, AUTH-06, INP-01, INP-02, INP-04, COL-01, RUN-01, RUN-08
**Success Criteria** (what must be TRUE):
  1. `recover-assess doctor` signs in by device code (or `--browser`), prints decoded scopes/roles, checks proxy/TLS to Graph and the login endpoint, warns when `--out` is in a synced OneDrive folder, reports each target as `reachable`/`not_granted`/`not_found`, and exits non-zero with a fix on the first blocking failure
  2. The delegated token cache is DPAPI-encrypted and fails closed (no plaintext fallback) when encryption is unavailable; a configured client secret stops the run with a message pointing to certificate or managed-identity auth
  3. `recover-assess collect --site <URL or server-relative path>` resolves and collects C1 (identity, dates, group/Teams-connected vs communication kind, subsites recorded with a `has_subsites` warning) and writes `out/<run-id>/` containing `run.json`, `resolution.csv`, `collection_summary.csv`, `sites/<slug>/fact_sheet.json` and `logs/run.jsonl`; the fact sheet validates against `schemas/fact_sheet.schema.json` with not-yet-collected sections recorded as not run
  4. A display-name input prints the `name_requires_url` message (no `/sites?search` call); nonexistent and ungranted URLs resolve to `not_found`/`not_granted` or `no_access` and are recorded in `resolution.csv` without a stack trace; `normalize` passes 30+ unit cases; CSV cells starting with `=`, `+`, `-` or `@` are escaped
**Plans**: TBD
**Spikes & gates**: Live auth matrix on the pilot workstation (is device code blocked by Conditional Access; does loopback browser work; is WAM / `msal[broker]` needed, which would require dependency approval; does delegated Sites.Selected consent work; does MSAL work behind the TLS proxy). Three-stack TLS/proxy check (MSAL, httpx2 now; openai in Phase 9) through one `SSLContext`; PAC and authenticated proxies are not covered by `HTTPS_PROXY`. Resolve 403-vs-404 spike (nonexistent, ungranted and policy-blocked sites; subsite vs library path; `/sites/{host}:/{path}` walk-up). These spikes cannot be settled from docs.

### Phase 3: Batch Intake & Site Structure (C2, C3)
**Goal**: A user can run a CSV of sites, validate and plan access before collecting, and see each site's libraries, lists, columns and content types in its fact sheet
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: INP-03, INP-05, INP-06, COL-02, COL-03, COL-13, RUN-02
**Success Criteria** (what must be TRUE):
  1. A CSV (UTF-8 with or without BOM, comma or tab, case-insensitive headers, only `site` required) runs in priority order; unknown columns land in `input.extra`, duplicates resolving to the same site ID are collected once, bad rows are recorded and skipped, and more than 500 rows is rejected unless the cap is configured
  2. `collect --validate-only --csv` resolves every row to `resolved`/`not_found`/`not_granted`/`no_access` and writes `resolution.csv` without collecting any site data
  3. `grants plan --csv` prints site IDs, `POST /sites/{id}/permissions` read-grant bodies and Graph PowerShell lines for an admin, and the allow-list test proves the tool never calls the grant endpoint
  4. Each collected site's fact sheet lists visible libraries, lists and pages tagged `library`/`pages`/`list` (hidden and configured system lists skipped, drive ID per library), columns (type from facet, custom-column detection by column group, term-set ID) and content types (ID-prefix checks, `default_content_types_only`); forcing one collector to fail yields a coded warning while the remaining collectors and sites still complete
  5. `run.json` records each site moving through pending, resolved, collecting, then complete, partial or failed, and a per-site time limit marks the site `partial` rather than `complete`
**Plans**: TBD
**Spikes & gates**: Sandbox Sites.Selected grant spike to confirm client ID vs object ID in the grant body (gates `grants plan`). Display-name resolution is out of v1 (sign-off 2 resolved: URL or path only; V2-03 is the explicit opt-in).

### Phase 4: Library Inventory & Folder Patterns (C4)
**Goal**: A user gets an accurate, streaming inventory of each library (volume, age, depth, duplicates, folder naming patterns) with honest truncation and coverage disclosure
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: COL-04, COL-05, COL-06, COL-07, COL-11
**Success Criteria** (what must be TRUE):
  1. On a real library with more than 50k items the run completes within bounded memory (tracemalloc test; no raw items held) and the fact sheet reports counts, bytes, depth max/p50/p90, category shares, top extensions, age buckets, created-by-year, largest files and `duplicate_rate` with `hash_coverage`; a live smoke reconciles counts to the SharePoint UI for an untruncated library
  2. Repeated items, out-of-order pages and `deleted` entries in recorded delta fixtures give the same result as a reference implementation (property and differential tests); folder paths are resolved in a post-pass and unresolved ones are counted as `path_unresolved`
  3. When `max_items_per_library` or a time cap is hit, the fact sheet records `truncated`, `truncated_reason` and `coverage`, flags shares, `last_activity` and duplicate rate as biased (not merely lower bounds), and a time-limit hit marks the site `partial`
  4. Folder pattern mining classifies segments at depths 1-4 (year, fiscal_year, quarter, month, date, numeric_id, categorical literal) per `config/patterns.yaml` and records depth, kind, share, distinct count and examples
  5. `last_activity` combines file, list, page and drive timestamps and lists the sources used; sample candidates (supported types <= `max_file_mb`, spread across top-level folders and age buckets) are identical across re-runs and across two processes, and no content is requested (allow-list test)
**Plans**: TBD
**Spikes & gates**: Needs deeper research and a live delta spike before planning: confirm `parentReference.path` is absent, repeat frequency, ordering, `$top`/page size, root `size` populated for coverage, hash availability, 410 behaviour; decide first-wins vs last-wins deliberately; record and scrub fixtures. This is the riskiest collector; C5-C7 depend on its side data (folder map, priority samples, contributor counters).

### Phase 5: Exposure, Ownership & Metadata Fill (C5-C7, C9)
**Goal**: The fact sheet gains metadata fill rates, permission exposure, ownership and SAM context so every scoring dimension has real evidence or an explicit "unknown"
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: COL-08, COL-09, COL-10, COL-12
**Success Criteria** (what must be TRUE):
  1. Each column carries `fill_rate` and the library a `mean_fill_rate`, computed on the first N non-folder items using internal names (person and lookup fields handled, 12-lookup limit respected), with method and sample size recorded; lists also get an item count
  2. Permission checks run on a fixed budget (root, top-level folders, then hash-priority files) and record link scopes, direct grants, guest/external and EEEU principals and `differs_from_root`; a 403, an empty or a caller-scoped result is recorded as `exposure.status` unknown or partial and never as zero (fixtures for each case)
  3. Top contributors and `active_contributors_90d` come from C4 counters; with `owners_via_groups: true` group owners are listed; `owner_hint_matched` compares case-insensitively against both
  4. An optional SAM export is joined on normalized site URL via a configurable URL column copying only listed columns, and an unmatched site emits `sam_no_match` (with a hint when URLs look concealed)
  5. A complete fact sheet for a real pilot site validates against schema v1.0 with every section carrying a `status` and `reason`
**Plans**: TBD
**Spikes & gates**: Live `/permissions` spike as the pilot identity (full output or caller-scoped only; link-permission shapes; `differs_from_root` validity; compare to the UI as a non-owner). Fill-rate field-shape spike (person, lookup, managed-metadata, multi-choice, boolean; 12-lookup behaviour; folder rows). Open: Sites.Selected plus `/permissions` read may force Sites.Read.All or caller-scoped results; `owners` via `GroupMember.Read.All` awaits a pilot answer.

### Phase 6: Durable Runs & Pilot-Ready Collector
**Goal**: An operator can interrupt, resume and clean up batch collections on real pilot sites with outputs safe to share, and the Collector passes Step 1 acceptance
**Mode:** mvp
**Depends on**: Phase 5
**Requirements**: RUN-03, RUN-04, RUN-05, RUN-06, RUN-07, PIL-01
**Success Criteria** (what must be TRUE):
  1. After Ctrl+C or a crash, `resume <run-id>` re-runs only non-complete sites using the original config (unless `--use-current-config`); exit codes are 0 (all complete), 2 (any partial/failed), 1 (could not start) and 130 (interrupted, state saved)
  2. `--path-mode full|tokens|hashed` and `output.contributors: email|hashed` (salt per run) redact once at output time, and a canary-string leak test finds no raw path or contributor email in any output when hashing is on
  3. A per-site progress view shows current stage, files counted, requests and throttles unless `--quiet`; `prune --older-than 90d` is a dry run by default, deletes only with `--yes`, and only inside the output root
  4. Pilot acceptance: `doctor` reachability is correct for granted, ungranted and nonexistent sites; a 25-row CSV completes with failures isolated; file counts are within 1% of the UI for untruncated libraries, custom columns are exact, sharing links match on 10 hand-checked items; a re-run within an hour yields identical samples and aggregates
**Plans**: TBD
**Spikes & gates**: Windows scenarios spike (deep `--out`, a site named `Con`, Excel holding the summary CSV, Ctrl+C under Proactor, OneDrive path, `os.replace` retry). Needs designated pilot sites with read grants in place (Security lead time); request them early. Delivers the pilot-ready Collector.

### Phase 7: Deterministic Scoring & Calibration Harness
**Goal**: Any saved fact sheet yields a deterministic, evidence-traceable scorecard (effort band, action, prerequisites, backfill strategy) with no network and no model call, plus a harness to measure it against hand labels
**Mode:** mvp
**Depends on**: Phase 5
**Requirements**: SCR-01, SCR-02, SCR-03, SCR-04, SCR-05, SCR-06
**Success Criteria** (what must be TRUE):
  1. Scoring a saved fact sheet (golden tidy/sprawl/orphan fixtures and real pilot output) produces six 0-100 dimension scores (volume, structure debt, exposure, ownership, content difficulty, hygiene), an effort score and a Low/Medium/High band from `config/rubric.yaml`; import-linter proves scoring imports no network library
  2. Action rules (Archive, Delete-candidate-for-owner-review, Enrich) apply first-match-wins, prerequisites (Restrict while fixing, Find an owner, Map folders to columns) are appended, and a backfill strategy (autofill, document processing, custom pipeline) is chosen for Enrich sites; editing only the rubric file changes the outcome
  3. The scorecard records the rubric version, every input value and an evidence pointer per sub-score, and scoring the same fact sheet twice yields a byte-identical scorecard
  4. Unknown evidence appears as its own state that lowers confidence, and an Archive or Delete derived from truncated or unknown data is flagged `needs_review` instead of being emitted confidently
  5. `calibrate` compares tool results to pre-registered hand labels and reports effort-band and action match rates next to a trivial baseline and a holdout set
**Plans**: TBD
**Spikes & gates**: Design research before planning: veto rules kept separate from the weighted sum, unknown handling and confidence, the calibration protocol (pre-registered labels, baseline, holdout; about 10 sites cannot discriminate on their own), and the activity-definition mismatch with SAM (Archive/Delete should need corroboration or lower confidence). Can start on golden fixtures in parallel with Phases 5-6. Human task: record the pilot hand labels before anyone views tool output for those sites (formal PIL-02 sign-off is Phase 12).

### Phase 8: Reports & Portfolio (`--no-llm` Product)
**Goal**: A user runs `assess --no-llm` and gets a credible, defensible per-site report and batch portfolio with zero model calls, which is the Core Value delivered end to end
**Mode:** mvp
**Depends on**: Phase 6, Phase 7
**Requirements**: RPT-01, RPT-02, RPT-03, RPT-04, RPT-05
**Success Criteria** (what must be TRUE):
  1. `recover-assess assess --site <URL> --no-llm` goes from URL to a self-contained `report.html` and `report.md` (headline, why-this-effort table, evidence, review flags, version footer; agent-only sections such as plan and starter schema are marked not generated) with zero model calls recorded in the run log
  2. `assess --csv ... --no-llm` writes `portfolio.csv` and a sortable `portfolio.html` showing counts by band/action/BU, top quick wins and top exposure
  3. Reports use a neutral theme by default and `--theme <file>` selects a client theme from a separate file; no client theme ships in the repo
  4. Hostile site, library and column names (script tags, Markdown, formula characters) render escaped in HTML, Markdown and CSV; reports never contain document excerpts and honour the chosen path and contributor redaction modes
**Plans**: TBD
**UI hint**: yes
**Spikes & gates**: Dependency approval for `jinja2` (autoescape, StrictUndefined) is required before planning. Recommended: an informational calibration pass on the pilot sites at the end of this phase, before Phases 9-10 expand agent surface.

### Phase 9: LLM Providers & Capability Probe
**Goal**: The tool can call the approved Azure OpenAI route through one provider interface with strict, validated JSON output, and fails clearly and early when the route is unavailable
**Mode:** mvp
**Depends on**: Phase 8
**Requirements**: LLM-01, LLM-02, LLM-03, LLM-04, LLM-05, LLM-06, LLM-07, LLM-08
**Success Criteria** (what must be TRUE):
  1. `doctor`'s LLM probe against the corporate Azure OpenAI gateway confirms the key is authorised, a strict JSON schema is accepted and usage tokens are returned; a gateway `upstream_auth_403` and an empty 200 response each fail fast with a distinct, clear error code
  2. `llm.allowed_providers` blocks any unlisted provider before collection starts, and configuring the Anthropic Bedrock stub fails with `ProviderNotConfigured`
  3. A step schema is lowered to the strict-mode subset (all required, nullable unions, `additionalProperties: false`, size/depth limits), responses are validated locally against the full schema, and an invalid response gets exactly one repair retry; transient errors retry with backoff honouring retry-after
  4. Provider, model, prompt version and token counts appear in every output and the run log, and prompt text is logged only with `--log-prompts`
  5. Import-linter confirms only `core/providers` imports LLM SDKs and the LLM client shares the single TLS context built for MSAL and Graph
**Plans**: TBD
**Spikes & gates**: Corporate LLM gateway capability spike (strict `json_schema` pass-through, reasoning-model parameters, empty-200 signature, `upstream_auth_403` mapping, WAF and request-size limits using synthetic SQL- or script-like text); the result decides how heavily the repair path is weighted. The gateway key and deployment name are external config and must never enter the repo. Technically depends only on Phase 1 and can be pulled forward in parallel with Phases 3-8.

### Phase 10: Agent: Schema Proposal, Plan & Verifier
**Goal**: A user gets an LLM-written starter schema and plain-English plan for each site that has been checked against the scorecard and evidence, and a failing LLM step never costs them the deterministic result
**Mode:** mvp
**Depends on**: Phase 7, Phase 8, Phase 9
**Requirements**: AGT-01, AGT-02, AGT-03, AGT-04, AGT-05, AGT-06
**Success Criteria** (what must be TRUE):
  1. `assess` on a site adds an A2 starter schema (name, type, source, allowed values or term-set candidate, required, evidence pointers) and an A3 plan (<=120-word summary, why-this-effort per dimension with evidence, ordered steps with owner role and size, risks, optional override suggestion) to the report
  2. A4 verifies in code that every pointer resolves, quoted numbers match, and effort/action/strategy equal the scorecard, then with a model check; one retry follows a failure, then `needs_review: true` puts the issues at the top of the report (a planted fabricated number proves the path)
  3. The agent has no tools, and an adversarial corpus of injection text in site names, paths and column names cannot change any scored field
  4. When the provider is down or the LLM step fails, the site still gets its scorecard and a `--no-llm` style report
  5. `assess --estimate` prints expected Graph calls, tokens and cost per site without making any model call
**Plans**: TBD
**Spikes & gates**: Standard patterns; the real work is the adversarial test corpus and verifier design. LLM output reaches HTML, Markdown and CSV, so it must go through the Phase 8 escaped renderers.

### Phase 11: Batch Hardening & Unattended Server Runs
**Goal**: An operator can run, kill, resume, rescore and re-report large batches unattended on a Windows Server using certificate or managed-identity auth
**Mode:** mvp
**Depends on**: Phase 10
**Requirements**: BAT-01, BAT-02, BAT-03, BAT-04, BAT-05, AUTH-02, AUTH-03
**Success Criteria** (what must be TRUE):
  1. Per-site state extends through scored, agent_done and reported, and `resume <run-id>` after a kill restarts each site from its last finished stage without re-collecting completed work
  2. `rescore <run-id>` re-runs scoring and the agent from saved fact sheets with zero Graph calls (proven by the run log), and `report <run-id>` rebuilds HTML and Markdown from saved JSON
  3. `app_certificate` (PEM, or PFX with password from an env var) and `managed_identity` (system- or user-assigned) both obtain tokens through the same `TokenProvider` and run a collection with no code change from the delegated path
  4. The README documents install, auth setup per mode, managed identity and a Task Scheduler example (service account, run whether logged on or not)
  5. Golden integration tests run three synthetic sites (tidy, sprawl, orphan) end to end plus a kill-and-resume test in CI
**Plans**: TBD
**Spikes & gates**: Sandbox Sites.Selected grant spike for managed-identity role-visibility delay (up to about 24 h) and client-ID-vs-object-ID behaviour for app modes; a Windows Server dry run. Needs Security approval of the server identity. Standard patterns otherwise.

### Phase 12: Claude Code Skill & Pilot Calibration
**Goal**: The playbook's Module 1 is proven on pilot sites (calibrated numbers) and usable from Claude Code through a skill that never edits results
**Mode:** mvp
**Depends on**: Phase 11
**Requirements**: SKL-01, PIL-02, PIL-03
**Success Criteria** (what must be TRUE):
  1. About 10 pilot sites have hand-assessed labels recorded before tool output was seen, and `calibrate` reports effort-band match >=8/10 and action match >=9/10 against the trivial baseline and a holdout, after rubric tuning made only through `config/rubric.yaml` with versions recorded
  2. The same code runs on a Windows 11 workstation with delegated auth behind the corporate proxy and on a Windows Server with `app_certificate` or `managed_identity`, producing equivalent outputs for the same site
  3. In Claude Code, `skills/recover-assessment/SKILL.md` runs `doctor` then `assess`, answers follow-up questions from `recommendations.json` and `report.md`, never edits results, and treats report text as data (a report seeded with embedded instructions does not change its behaviour)
**Plans**: TBD
**Spikes & gates**: Standard patterns for the skill. Calibration is human-in-the-loop: expect a second round, keep a holdout, and do not tune against the holdout. Pilot-organisation theme and gateway settings stay in external config.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 (Phase 7 may begin on golden fixtures in parallel with Phases 5-6; Phase 9 may be pulled forward in parallel with Phases 3-8)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation, Contract & Read-Only Graph Client | 12/12 | Complete    | 2026-11-17 |
| 2. Walking Skeleton: Sign In, Doctor, Resolve & Collect One Site | 0/TBD | Not started | - |
| 3. Batch Intake & Site Structure (C2, C3) | 0/TBD | Not started | - |
| 4. Library Inventory & Folder Patterns (C4) | 0/TBD | Not started | - |
| 5. Exposure, Ownership & Metadata Fill (C5-C7, C9) | 0/TBD | Not started | - |
| 6. Durable Runs & Pilot-Ready Collector | 0/TBD | Not started | - |
| 7. Deterministic Scoring & Calibration Harness | 0/TBD | Not started | - |
| 8. Reports & Portfolio (`--no-llm` Product) | 0/TBD | Not started | - |
| 9. LLM Providers & Capability Probe | 0/TBD | Not started | - |
| 10. Agent: Schema Proposal, Plan & Verifier | 0/TBD | Not started | - |
| 11. Batch Hardening & Unattended Server Runs | 0/TBD | Not started | - |
| 12. Claude Code Skill & Pilot Calibration | 0/TBD | Not started | - |
