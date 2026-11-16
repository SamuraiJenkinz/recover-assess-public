# Project Research Summary

**Project:** recover-assess
**Domain:** Read-only SharePoint Online AI-readiness assessment CLI (Microsoft Graph collector, deterministic scorer, verified LLM explanation layer)
**Researched:** 2026-11-15
**Confidence:** MEDIUM-HIGH

## Executive Summary

recover-assess is a staged, artifact-boundary pipeline: resolve, collect (Graph GET and `$batch`-of-GET only), score (pure function over a rubric), optional LLM agent (A2 schema, A3 plan, A4 verifier), then render. Experts build this as a single network choke point (`core/graph.py`) with a machine-enforced allow-list, one provider boundary for LLM SDKs, and stage boundaries that are files rather than in-memory objects, so `resume`, `rescore`, `report` and golden tests share one code path. The market is crowded on oversharing and lifecycle (SAM, Purview DSPM, AvePoint, Syskit, ShareGate) but open on metadata and structure readiness, per-site Enrich/Archive/Restrict/Delete triage, effort sizing and schema proposal. That open gap is the product. Competing on tenant-wide governance automation is explicitly an anti-feature.

Recommended approach: keep the spec's layout, with refinements. Split `models/` into published contracts, LLM wire models and run state. Add `net.py` and `evidence.py`. Make `run/` a stage registry with input fingerprints from day one. Ship Collector (M0/M1), then deterministic scoring and reports as the first complete, LLM-free product (the Core Value), then providers and agent. Calibrate on the pilot before building more agent surface. The scorecard is metadata-only, and the LLM only explains: code computes, the verifier checks pointers and numbers, and `needs_review` is the failure state.

The biggest risks are (1) spec statements that are wrong against current Graph behaviour (delta has no `parentReference.path` and repeats items; truncation biases ratios and can drive a confident wrong Delete), (2) trust-promise holes (nextLink and redirect token leaks, loose allow-list templates), (3) unknown-versus-zero confusion (caller-scoped `/permissions`, 403 read as 0 links, schema with no representable "unavailable" state), (4) environment blockers on the pilot (Conditional Access vs device code, TLS inspection across three HTTP stacks, corporate LLM gateway quirks), and (5) calibration that cannot discriminate with about 10 sites. Mitigations are mostly design-time: id-keyed accumulators, a status/coverage/confidence vocabulary in the fact sheet before v1.0 freezes, a process-wide throttle gate, schema lowering for strict outputs, and early live spikes.

## Decisions Needing User Sign-off

These are blockers or spec/dependency deviations. The roadmapper should surface them as explicit decision gates, not assume them.

1. **httpx2 vs httpx + respx.** `httpx` 0.28.1 is frozen since Dec 2024. `httpx2` (Pydantic-stewarded, now 2.16) is what `openai` 3.x and `anthropic` 2.x depend on. `respx` and `vcrpy` cannot mock `httpx2`. Recommendation: use `httpx2` plus its built-in `MockTransport` through a client factory (no extra test dependency). This replaces two spec lines (httpx, respx). Fallback if refused: pin `httpx==0.28.1` and `respx==0.23.1` for Graph only, accepting two HTTP stacks and weaker maintenance.
2. **Display-name resolution needs delegated `Sites.Read.All`.** `/sites?search` does not support Sites.Selected, which conflicts with "delegated Sites.Selected (preferred)". Options: (a) names require `Sites.Read.All` delegated and `doctor` states it, or (b) drop names from the pilot and require URL or path. Recommendation: (b) for the pilot, (a) only as an explicit opt-in. Never fall back to guessing.
3. **Whether A1 (sample-tier content classification) may influence effort or action.** Recommendation: no. A1 output is advisory, a closed enum, and lives in a separate `content_profile` evidence block that A2/A3 may cite. The scorecard stays metadata-only so `--no-llm` is complete and deterministic. This also blocks document-driven injection from moving a band.
4. **Dependencies outside the approved list.**
   - `jinja2` (reports; required by M2).
   - Text-extraction libraries for the sample tier, as an optional extra: python-docx, python-pptx (dormant), openpyxl, pypdf (>=7.1,<8), extract-msg. Required by M4 part 2.
   - `defusedxml` (hardens openpyxl on hostile files; recommended).
   - `msal[broker]` (WAM; only if Conditional Access blocks both device code and loopback browser).
   - Optional `pytest-cov`.
   - `httpx2` itself (see 1).
   - `anthropic` is NOT needed for the stub (zero new dependencies).

## Key Findings

### Recommended Stack

Python 3.12 with uv (pinned lockfile, `uv sync --locked`; `UV_SYSTEM_CERTS=true` behind TLS inspection). The stack is largely spec-pinned and verified current on PyPI; the changes that matter are the `httpx2` shift, the pinned-major churn (typer 0.29, ruff 0.17 with 413 default rules, mypy 2.x, pypdf 7), and the LLM client choice. Full detail in `STACK.md`.

**Core technologies:**
- **httpx2 ~=2.16 (pending sign-off):** Graph client and LLM adapters. OS trust store by default, shared stack with the OpenAI SDK.
- **msal ~=1.39 + msal-extensions 1.3.1 (DPAPI, fail closed) + azure-identity ~=1.27:** delegated, certificate and managed identity. All synchronous, so wrap in `asyncio.to_thread`. Never a plaintext cache fallback.
- **truststore ~=0.10.5:** `inject_into_ssl()` at CLI start for the `requests`-based MSAL path. Better still, one explicit `SSLContext` built in `net.py`.
- **pydantic ~=2.14.3 (pin the minor) + pydantic-settings[yaml] + jsonschema:** models are the source of truth for the published schemas. Add a startup check for mistyped `RECOVER_ASSESS__*` env vars, which `extra="forbid"` does not catch.
- **openai ~=3.51 using plain `OpenAI(base_url=...)`, Chat Completions, strict `json_schema`, non-streaming:** matches the corporate LLM gateway shape (`/coreapi/openai/v1/deployments/<d>/chat/completions`, `api-key` header). Not `AzureOpenAI`, not Responses. A `strictify()` lowering step is required (no min/max/pattern/format, all-required, `additionalProperties:false`, 100 properties, depth 5).
- **Anthropic stub:** raises `ProviderNotConfigured`, no SDK dependency. When filled, the corporate Anthropic proxy route is a hand-written httpx2 adapter. Reserve an empty `bedrock` extra.
- **typer ~=0.29.1 (`pretty_exceptions_show_locals=False`, to keep tokens out of tracebacks), rich, jinja2 (`autoescape=True`, `StrictUndefined`).**
- **Quality:** ruff with explicit `select`, mypy strict, import-linter contracts, pytest + pytest-asyncio + hypothesis, `httpx2.MockTransport`. Reject `msgraph-sdk` (cannot enforce read-only by construction).

### Expected Features

**Must have (table stakes):**
- Per-site activity, ownership, sharing exposure, broken inheritance, EEEU/Everyone and guest counts, volume/age/storage, ROT indicators (duplicates, age, largest files). These are what SAM and the vendors already show.
- A per-site verdict from a fixed action set, a ranked portfolio (CSV and HTML), a plain-English per-site report, remediation pointers, reproducible re-runs.
- Safe handling: path modes and hashed contributors honoured by reports too, honest coverage/truncation disclosure, pre-flight `doctor`, `grants plan`.

**Should have (differentiators, the reason to buy):**
- Metadata-readiness scoring (custom columns, fill rate, default-content-types-only), folder-pattern mining (path to metadata).
- Effort rating with backfill strategy, deterministic traceable scorecard, rubric as config with client overrides.
- A2 starter schema, evidence-verified A3 plan, `--no-llm`, strictly read-only enforced and tested, offline portability, SAM join (C9) as evidence.
- Ordered prerequisites (fix oversharing before Enrich), portfolio exec summary, Claude Code skill.

**Defer (v2+ or post-pilot):**
- Sample tier (C8 + A1): highest risk and cost; build after pilot shows A2 needs content evidence.
- `compare` between runs (needs a frozen schema and rubric), `--include-subsites` (pending pilot answer), composite readiness number, per-file sensitivity labels beyond C9.

**Anti-features (do not build):** any M365 write, tenant crawl, continuous monitoring, LLM-computed scores, a single opaque 0-100 readiness score as headline, PII/DLP detection, web app or results MCP, client secrets, Graph beta.

**Small additions to fold into the Collector spec now (low cost, avoid post-freeze churn):** guest/external and EEEU principal counts in C6; site kind in C1; drive quota; `last_activity` basis field and inclusion of list/page/drive timestamps; pluggable C9 column mapping with concealed-URL detection.

### Architecture Approach

Keep the layout in the spec; refine it. A thin `cli.py` over `core/run/` (RunStore with atomic, coalesced writes and a lock; stage registry with input fingerprints; scheduler). Stages (`collect`, `score`, `agent`, `report`) are independent packages that communicate only through files. `graph.py` is the single M365 I/O point, with a `ReadOnlyPolicy` (anchored per-segment template regexes, `tier: metadata|sample`, re-validation of every nextLink and every `$batch` sub-request, `follow_redirects=False`) and a transport-level belt-and-braces check. One `GraphClient` per run (shared throttle barrier) with cheap per-site `GraphSession`s (semaphore, breaker, deadline). Import-linter contracts make "read-only" and "no content leaves the tenant" machine-checked properties.

**Major components:**
1. **`core/graph.py` + `net.py` + `auth.py`:** the only M365 I/O; TLS and proxy; three-mode `TokenProvider` (device-code completes in preflight, never in a worker).
2. **`core/collect/*` (C1-C9):** async functions returning typed outputs; C4 is a streaming, id-keyed, order-independent accumulator (hash-priority sampling, dedupe by id, paths resolved at `finalize()`), the riskiest collector.
3. **`core/score.py` + `evidence.py`:** pure `score(fact_sheet, rubric)`; closed rule vocabulary, first-match-wins predicates, every sub-score records evidence pointers; no expression engine.
4. **`core/providers/*` + `agent/*`:** `LLMProvider` is transport; `StructuredCaller` owns lowering, local validation and one repair retry; verifier does code checks first, then a model check; LLM cannot restate scored fields.
5. **`core/run/*` + `report/*` + `output.py`:** fingerprinted resume and rescore; redaction applied once at the emit boundary; deterministic rendering.

### Critical Pitfalls

1. **Delta omits `parentReference.path` and repeats items** — id-keyed folder map, dedupe by id, resolve paths in a post-pass; amend "never hold inventories in memory" to "never hold raw JSON; compact records allowed". Record real delta fixtures.
2. **Truncation biases ratios and `last_activity` (confident wrong Delete)** — store coverage (counted bytes over root `size`) and `truncated_reason`, cross-check `last_activity` against list and drive timestamps, and forbid Archive/Delete from truncated data without `needs_review`.
3. **Permissions are caller-scoped and 403 must never become 0** — add `exposure.status` and `caller_is_owner` to the schema; unknown is its own state that lowers confidence.
4. **Throttling is tenant-and-app-wide, not per-site** — one process-wide gate, RU accounting, `NONISV|...` User-Agent, larger `$top`, parse both Retry-After forms, fail fast with `throttled_out`.
5. **Read-only holes: nextLink, redirects, loose templates, `downloadUrl`** — validate host and prefix on every absolute URL, no wildcards, strip `@microsoft.graph.*` annotations at the response boundary, hostile-URL hypothesis corpus, log-audit script.
6. **Strict structured outputs reject default pydantic schemas** — own a `lower_for_strict()` step plus a budget lint; validate against the un-lowered schema.
7. **Prompt injection arrives via metadata; LLM output reaches HTML, Markdown and CSV** — LLM can never change scored fields, metadata passed as data, escaped renderers, adversarial test corpus.
8. **Calibration on ~10 sites cannot discriminate** — pre-register labels, report the trivial baseline, keep a holdout, separate veto rules from the weighted sum, model unknown explicitly.
9. **Environment blockers:** Conditional Access vs device code, TLS inspection across MSAL/httpx/openai, gateway empty-200 and deployment-scoped keys. All need live spikes first.
10. **Schema frozen too early / no "unavailable" state** — mark v1.0 provisional until pilot; add `status`, `coverage`, `truncated_reason`, `privacy`, `collect_limits`, `sources` before first release.

## Collector Spec Corrections (apply before coding)

| # | Spec text | Correction |
|---|-----------|------------|
| 1 | C4 path and depth from `delta ... parentReference` | Delta never returns `path`. Track folders by id; resolve paths in a post-pass at `finalize()`; count `path_unresolved`. |
| 2 | C4 ignores only `deleted` items | Dedupe by id (document first-wins vs last-wins and count repeats); `deleted` removes an earlier id; sum `size` for `file` facets only; classify file, folder, package, other. Docs say "use the last occurrence", architecture proposes first-wins for a full initial enumeration; decide deliberately and confirm with a live smoke. |
| 3 | "Seed derived from site ID" for sample candidates and permission checks | Order-independent hash-priority sampling: keep the k smallest `sha256(seed \|\| item_id)`; seed from `sha256(site_id)`; never builtin `hash()` or reservoir sampling. Two-process determinism test. |
| 4 | Throttle unit: per-site breaker (20 in 60 s) and 2 sites x 4 in flight | Tenant-and-app-wide: shared barrier on `GraphClient`, RU token bucket (~50% of lowest tier), per-site breaker retained, decorated User-Agent, fail fast if wait exceeds budget. |
| 5 | Duplicate rate wording ("minus one per group") | Define `duplicate_rate = redundant_copies / files_with_hash`; add `hash_coverage`; exclude zero-byte; label as lower-bound estimate. |
| 6 | Exposure counts; 403/empty implicitly 0 | Add `exposure.status` (`ok` / `partial_caller_scoped` / `forbidden` / `not_run`) and `caller_is_owner`; unknown never becomes 0; open `link.scope` enum; normalise both `grantedToV2` and `grantedToIdentitiesV2`; `differs_from_root` documented as a proxy. |
| 7 | Truncated counts are "lower bounds" | True for counts and bytes only. Shares, `last_activity`, duplicate rate and pattern coverage are biased. Add `coverage`, `truncated_reason` (cap / time / throttle / resync), `last_activity` sources; scoring caps confidence. |
| 8 | `$batch` of columns and permissions | Sub-responses may carry `@odata.nextLink`; fall back to paged GETs; use smaller batches for permission calls (5 RU each); per-id results, never trust outer 200. |
| 9 | C5 fill rate via `$expand=fields($select=...)` | Internal names, `<Name>LookupId` for person and lookup, at most 12 lookup columns per call, drop folder rows, exclude calculated and defaulted columns, record method and sample, straddle column-creation dates. |
| 10 | Custom-column detection by exclusion list; content types by name | Use `columnGroup` primary, ID-prefix content-type checks (`0x0101`, `0x0120`, `0x01`), `unclassified_column` warning. Skip lists by template or slug first, display name second. |
| 11 | Schema v1.0 example | Add before freeze: `privacy` block, `collect_limits` echo, per-section `status` + `reason`, `coverage`, `truncated_reason`, `path_unresolved`, `fill_rate_skipped`, `hash_coverage`, `owners_source`, `last_activity` basis, guest/EEEU principal counts, site kind, drive quota. Mark `schema_version 1.0` provisional until pilot completes. |
| 12 | httpx plus `truststore` suffices | MSAL uses `requests`; wire one explicit `SSLContext` from `net.py` into httpx2, openai and MSAL; `doctor` tests all three stacks. PAC and authenticated proxies are not covered by `HTTPS_PROXY`. |
| 13 | Delta robustness | Raise `$top`; on 410 follow `Location` once then mark `truncated_reason: resync`; time-limit hits mark `partial`, never `complete`; record `remoteItem` and `package` separately. |
| 14 | Dependencies | Reports need jinja2; sample tier needs extractors (see sign-off item 4). |

## Live Spikes Recommended (resolve before or at the start of the phase they gate)

| Spike | Gates | Question to answer |
|-------|-------|--------------------|
| Auth matrix on the pilot workstation | AUTH | Is device code blocked by Conditional Access? Does loopback browser work with a registered redirect? Is WAM needed? Does delegated Sites.Selected consent work? Does MSAL work behind the TLS proxy? |
| Three-stack TLS and proxy check | AUTH, GRAPH, PROVIDER | MSAL, httpx2 and openai each reach login, Graph and the LLM gateway via one `SSLContext`; PAC and authenticated proxy behaviour. |
| Resolve 403 vs 404 semantics | RESOLVE | Real responses for nonexistent, ungranted and policy-blocked sites; subsite vs library path; `/sites/{host}:/{path}` walk-up. |
| Delta shape on a >50k library | C4 | `parentReference.path` absent, repeat frequency, ordering, page size and `$top`, root `size` populated for coverage, hash availability, 410 behaviour. Record and scrub fixtures. |
| `/permissions` as the pilot identity | C6 | Full output or caller-scoped only; link-permission shapes; `differs_from_root` validity; compare to the UI as non-owner. |
| Fill-rate field shapes | C5 | Person, lookup, managed-metadata, multi-choice, boolean shapes; 12-lookup behaviour; folder rows. |
| Corporate LLM gateway capability probe | PROVIDER | Strict `json_schema` passes through; reasoning-model parameters; empty-200 signature; `upstream_auth_403` mapping; WAF and request-size limits (use synthetic SQL- or script-like text). |
| Sandbox Sites.Selected grant | AUTH, RESOLVE (`grants plan`) | Client ID vs object ID in the grant body; managed-identity role visibility delay (up to about 24 h). |
| Windows scenarios | RUN | Deep `--out`, site named `Con`, Excel holding the summary, Ctrl+C, OneDrive path, `os.replace` retry. |

Start the corporate LLM gateway spike and the auth matrix on day one; both depend on external keys, consent or Security input and have long lead times.

## Implications for Roadmap

Suggested phase structure (maps to scope M0-M6 plus pilot). Seven phases; the collector is split because it is large and ordered by dependency.

### Phase 1: Foundation, contracts and Graph choke point
**Rationale:** Everything codes against the FactSheet model and the read-only client; the trust promise must be enforced from the first commit.
**Delivers:** Scaffold (uv, ruff, mypy strict, import-linter contracts, CI), `errors`, typed-event `log` with scrub filter, `output` atomic writer (Windows retry), `config`, `net` (single SSLContext), `auth` (three modes, preflight device code, DPAPI cache fail-closed), full provisional `FactSheet` v1.0 with status/coverage/privacy fields, `gen_schemas` plus drift and compat tests, `GraphClient`/`ReadOnlyPolicy`/`GraphSession` with shared throttle barrier, injected `Clock`, `fake_graph` on `MockTransport`, `doctor`.
**Addresses:** Read-only guarantee, safe-by-construction logging, pre-flight checks.
**Avoids:** Pitfalls 8, 9, 13 to 15, 34, 39; schema freeze (25); wrong-stack choice (httpx2).
**Gates:** sign-off 1 (httpx2) and 4 (deps); auth and TLS spikes.

### Phase 2: Inputs, resolution and collectors C1-C3
**Rationale:** Resolution and site/list/column metadata are prerequisites for every other collector and are lower risk than C4.
**Delivers:** CSV and name/URL normalisation (40+ URL shapes, walk-up resolution, dedupe on triple), `resolution.csv`, `grants plan`, C1 (with site kind), C2, C3, per-collector warning capture, partial fact sheets validating against the schema.
**Addresses:** Site input, grants hand-off, custom-column detection (columnGroup plus ID-prefix content types).
**Avoids:** Pitfalls 4, 5, 11, 12, 16, 36, 40.
**Gates:** sign-off 2 (name resolution scope); resolve spike.

### Phase 3: C4 inventory and folder-pattern mining
**Rationale:** The pivotal and riskiest collector; C5-C7 depend on its side data (folders, priority samples, contributor counters). Validate real delta shape here before building on it.
**Delivers:** Streaming id-keyed accumulator, dedupe, post-pass paths, hash-priority sampling, truncation with coverage and `truncated_reason`, `last_activity` multi-source, duplicate-rate definition, pattern classifier (priority order, min distinct, share of folders and files), differential and property tests, `tracemalloc` test, one live smoke on a real library.
**Addresses:** Volume, age, ROT, folder-pattern mining (key differentiator).
**Avoids:** Pitfalls 1, 2, 3, 18, 26, 28, 30, 37, 38.
**Gates:** needs deeper research (delta spike).

### Phase 4: C5-C7, samples, C9, run orchestration and Collector hardening
**Rationale:** Completes the fact sheet and makes batch runs durable; Step 1 acceptance lives here.
**Delivers:** C5 fill rate, C6 exposure (status, caller-scoped handling, guest/EEEU), C7 ownership, sample candidates (no download), C9 SAM join (concealed-URL detection), `RunStore` (lock, atomic, coalesced), stage registry with fingerprints (only `resolve` and `collect` registered), `resume`, `prune`, summary CSV, path modes via single `redact`, progress reporter, exit codes (0/1/2/130), golden integration tests (tidy, sprawl, orphan), kill-and-resume, README, Windows Server dry run, canary-string leak test, CSV formula escaping.
**Addresses:** Per-site exposure, ownership, reproducibility, safe output handling.
**Avoids:** Pitfalls 6, 7, 10, 17, 27, 29, 31, 32.
**Gates:** permissions and fill-rate spikes. Pilot-ready Collector delivered here.

### Phase 5: Deterministic scoring, evidence and reports (first complete product, `--no-llm`)
**Rationale:** Delivers the Core Value (credible, defensible triage with zero model calls); can start on golden fact sheets in parallel with phase 4.
**Delivers:** `Rubric` model with closed rule vocabulary, six weighted dimensions, veto rules separate from weighted sum, explicit unknown state, confidence and `insufficient_evidence`, truncation guard (no Archive/Delete without `needs_review`), prerequisites and remediation pointers, `evidence.py`, `calibrate` command with trivial-baseline and holdout support, per-site `report.html`/`.md`, `portfolio.csv`/`.html`, neutral theme, escaped renderers (autoescape, Markdown allow-list).
**Addresses:** Verdict, ranked portfolio, per-site report, effort rating, traceable scorecard.
**Avoids:** Pitfalls 3 (guard), 22 (renderers), 24, 25.
**Gates:** sign-off 3 (A1 does not influence score); jinja2 approval; needs design research on veto rules, unknown handling and calibration protocol. Run the pilot calibration round here, before expanding agent surface.

### Phase 6: LLM providers and agent (metadata tier)
**Rationale:** Layered on a solid, calibrated base; providers and `StructuredCaller` are independent of collect and can start earlier in parallel.
**Delivers:** `LLMProvider`, `StructuredCaller` (lowering, local validation, one repair retry, outcome classes), Azure/gateway adapter with capability flags (`OpenAI(base_url=...)`, Chat Completions, non-streaming, `max_retries=0`), Bedrock stub, Fake and Replay providers, `llm doctor` capability probe, strict-limit lint tests, A2 schema proposal, A3 plan (structured claims with evidence ids), A4 verifier (code checks, then model check), `needs_review`, `--estimate`, adversarial injection corpus.
**Addresses:** A2/A3/A4, `--no-llm` as default failure fallback.
**Avoids:** Pitfalls 19 to 21, 23.
**Gates:** Corporate LLM gateway spike result decides weight of the repair path.

### Phase 7: Sample tier, batch hardening, Claude Code skill and pilot calibration
**Rationale:** Highest-risk and lowest-urgency items last; skill is thin once outputs are stable.
**Delivers:** Sample tier (narrow `allow_content=True` tier, manual 302 hop without Authorization, extraction in a subprocess with timeout and size cap, untrusted-document wrapping, redaction hook, confirmation prompt incl. `--yes-sample-tier`, A1), `rescore`/`report` commands and fingerprints for agent and report stages, time limits, RU budgeting and off-peak Task Scheduler example, exit-code audit, `SKILL.md` (read-only, guards against reading report text as instructions), final pilot calibration with holdout.
**Addresses:** Sample-tier classification, batch operation, natural-language follow-up.
**Avoids:** Pitfalls 7 (batch RU), 22, 33.
**Gates:** sign-off 4 (extraction libraries, defusedxml); phase research on `/content` 302 handling. Consider deferring the sample tier to a post-pilot milestone if calibration shows A2 does not need content evidence.

### Phase Ordering Rationale

- Contracts and the choke point first because every stage codes against them and the trust promise must be tested from day one.
- Resolve and C1-C3 before C4, C4 before C5-C7, because of real data dependencies (drive ids, folder map, priority samples, contributor counters).
- Scoring and reports (phase 5) before the agent, so the Core Value exists independent of the LLM and calibration can start early. `--no-llm` is the natural stage-list cut.
- Providers can be built in parallel with phases 3 to 5; they depend on nothing in collect.
- Sample tier is last: opt-in, riskiest, and its value is unproven until calibration shows what A2 lacks.

### Research Flags

Phases likely needing deeper research or a live spike during planning (`/gsd-plan-phase --research-phase <N>`):
- **Phase 1:** auth matrix and TLS spike (Conditional Access, WAM, three-stack trust store). Live, cannot be settled from docs.
- **Phase 2:** short resolve spike (403 vs 404, walk-up, search scope).
- **Phase 3:** deeper research and live delta spike (shape, repeats, ordering, `$top`, root size, 410).
- **Phase 4:** live spikes for C6 permissions (caller-scoped output) and C5 field shapes.
- **Phase 5:** design research (veto rules, unknown handling, calibration protocol, activity-definition mismatch vs SAM).
- **Phase 6:** short corporate LLM gateway spike (strict schema pass-through, parameters, WAF and size limits).
- **Phase 7:** research the `/content` 302 hop and extraction hardening; Claude strict-tools request fields if the Bedrock stub is filled.

Phases with standard patterns (skip research-phase): Graph client mechanics within Phase 1 (invest in tests, not research); run orchestration and batch hardening (Phases 4 and 7); agent prompt and verifier design (Phase 6; the work is the adversarial test corpus); skill authoring (Phase 7).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | All versions read from PyPI on 2026-11-15 (HIGH). `httpx2` is only 6 months old; corporate LLM gateway behaviour and Conditional Access are unverified (MEDIUM). Fresh majors (typer 0.29, mypy 2.x, pypdf 7) add churn risk. |
| Features | MEDIUM-HIGH | Microsoft Learn facts are HIGH; vendor capability claims (AvePoint, Rencore, Syskit, SWOOP) are marketing-sourced (MEDIUM/LOW). Sensitivity-label read path is LOW. |
| Architecture | HIGH (layering, Graph, delta, state) / MEDIUM (LLM provider) | Verified against Microsoft Learn and the Step 1 spec. Windows `os.replace`, Proactor Ctrl+C and truststore coverage of MSAL are engineering judgement to confirm in tests. Corporate LLM gateway strict schema support unverified. |
| Pitfalls | MEDIUM-HIGH | Graph delta, permissions, throttling, batching, Sites.Selected, fieldValueSet and strict-schema limits are HIGH. Gateway WAF, calibration statistics, Office hash behaviour and Sites.Selected `/permissions` read behaviour are MEDIUM/LOW. |

**Overall confidence:** MEDIUM-HIGH. The design is well supported; the remaining uncertainty is environmental (pilot tenant, proxy, gateway) and is best retired by early spikes, not more desk research.

### Gaps to Address

- **Sensitivity labels:** no confirmed v1.0 read path for per-file labels. Interim: join via C9 and record site-level label if readable. Needs phase research.
- **Activity definition mismatch:** Microsoft's 180-day inactivity spans SharePoint, Teams, Exchange and Viva Engage; file-modification recency does not. Archive/Delete rules should require corroboration (C9 or multiple signals) or lower confidence.
- **SAM export formats:** which report and which columns remain an open question; concealed-names tenant setting breaks URL joins.
- **Corporate LLM gateway strict `json_schema` pass-through and reasoning-model parameters:** unverified; `capabilities.strict_json_schema` fallback built regardless.
- **Sites.Selected plus `/permissions` read under delegated and app modes:** unproven; may force `Sites.Read.All` or caller-scoped results.
- **`owners` via `GroupMember.Read.All`, and `--include-subsites`:** open questions awaiting pilot answers.
- **Delta first-wins vs last-wins:** decide with live smoke data (see correction 2).
- **Calibration validity:** about 10 sites is statistically weak. Pre-register labels, report the trivial baseline and keep a holdout; expect a second round.
- **Licensing and SAM facts** change often; re-verify at pilot time.
- **Pilot-organisation config** (gateway hostnames, deployments, theme) must stay out of the repo (portability and IP constraint).

## Sources

### Primary (HIGH confidence)
- PyPI JSON API (all package versions, release dates, requirements), accessed 2026-11-15.
- Microsoft Learn: driveItem delta, JSON batching, Selected permissions overview, site search, site get, driveItem permissions, fieldValueSet, Graph and SharePoint throttling guidance, Azure OpenAI structured outputs and v1 API lifecycle, Conditional Access device-code blocking, managed identity guidance.
- Microsoft Learn product docs: Content Management Assessment, Data Access Governance reports, SharePoint Admin Agent, site lifecycle management, Purview DSPM for AI.
- Upstream: httpx2 and openai-python 3.0 migration notes, msal-extensions README and source, truststore docs, pydantic-settings docs, Ruff 0.16, Typer 0.29, pypdf changelog, uv certificate docs, Anthropic on Bedrock docs.
- Project inputs: `.planning/PROJECT.md`, Collector Build Spec (Step 1).

### Secondary (MEDIUM confidence)
- The user's local gateway-integration skills, not in repo (corporate LLM gateway shapes; need live confirmation).
- Vendor and comparison sources (Orchestry, Syskit, Rencore, AvePoint, SWOOP).
- Community reports on Sites.Selected 403 behaviour and unsupported operations; mypy 2.0 default changes.
- Engineering judgement: Windows `os.replace` under AV locks, Proactor Ctrl+C, import-linter contract syntax.

### Tertiary (LOW confidence, validate before relying)
- Gateway WAF and request-size behaviour, Sites.Selected plus `/permissions` read behaviour, per-file label read paths, vendor refresh-rate claims.

---
*Research completed: 2026-11-15*
*Ready for roadmap: yes*
