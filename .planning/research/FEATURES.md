# Feature Landscape

**Domain:** SharePoint AI-readiness / content-assessment tooling (site triage, effort rating, schema proposals, oversharing exposure), delivered as a read-only, consultant-run CLI
**Project:** recover-assess
**Researched:** 2026-11-15
**Overall confidence:** MEDIUM-HIGH (Microsoft Learn facts HIGH; third-party vendor capability claims MEDIUM/LOW, as they are marketing pages and comparison sites)

## How to read this file

Milestone tags map to the project's roadmap: **COL** = Collector (Step 1), **SCR** = Scoring/Reports (M2), **PRV** = Providers (M3), **AGT** = Agent (M4), **BAT** = Batch hardening (M5), **SKL** = Claude Code skill (M6), **PIL** = Pilot calibration. Complexity is Low / Med / High for a solo developer using Claude Code.

## Landscape summary (what the market actually does)

| Product family | What it is | What it covers | What it does NOT cover |
|---|---|---|---|
| **SAM Content Management Assessment (CMA)** (HIGH, Microsoft Learn) | One-click, tenant-wide admin-centre assessment. Five reports: inactive sites (no activity 180 days), site ownership (no owner / one owner), broken inheritance, EEEU (Everyone Except External Users) sharing, sharing links. Takes 2 to 72 hours; re-run every 30 days | Flags impacted sites with recommended steps; takes no action without admin consent | No metadata or schema assessment, no per-site Enrich/Archive/Restrict/Delete verdict, no effort estimate, no content-structure analysis, no folder-to-metadata mining |
| **SAM Data Access Governance (DAG) reports** (HIGH) | Snapshot: site permissions (broadest access, guests, EEEU), site permissions for a user, files shared via EEEU/Everyone, sensitivity label for files. Activity (last 28 days): sharing links created, EEEU sharing | Site-level exposure ranking; activity reports cap at 10,000 sites; E5-only tenants get no snapshot reports | Site-level not item-level for most reports; no content/structure view; "concealed names" tenant setting can pseudonymise reports |
| **SAM site lifecycle** (HIGH) | Inactive-site policy, site-ownership policy, site attestations, read-only then Microsoft 365 Archive | Automated notify, read-only, archive | Needs SAM licence; archive unsupported for some site types (publishing, channel sites; partial for Teams private/shared channels) |
| **SharePoint Admin Agent** (HIGH) | Conversational admin agent over SAM data (content distribution, low-activity sites by department, overshared sites with risk levels, storage, lifecycle, agents accessing content). Needs SAM Administrator role | Q&A plus guided remediation | Not an assessment deliverable; no evidence-verified narrative; tenant-admin only |
| **Purview DSPM for AI** (HIGH) | Weekly default oversharing assessment of top 100 SharePoint sites by usage; custom assessments; correlates sensitivity labels vs access breadth vs Copilot queries | Label-vs-exposure mismatch flagging | Needs E5-class licensing; usage-ranked top 100 only by default; reactive, no content-structure view |
| **AvePoint** (MEDIUM) | Data Security Risk Assessment, Confidence Platform; baseline of where sensitive data lives and who can reach it; prioritised fix list; lifecycle policies; access recertification | Oversharing plus remediation plus ongoing governance | Metadata/IA readiness not a described capability |
| **ShareGate Protect** (MEDIUM) | See exposed, fix risky, cut wasted; bulk-remove broad permissions and sharing links; owner reviews of links/guests; storage/version policies; MCP to query governance data | Operational clean-up | Copilot support rated "partial" by a competitor; no AI inventory |
| **Syskit Point** (MEDIUM) | Group Access, Sharing Links, Sites Overview reports with bulk actions; alerts; access reviews; governance automation; inactive workspace disposal; Copilot Readiness score | Permissions-centric governance | No metadata/IA assessment described |
| **Rencore Governance** (MEDIUM/LOW) | Pre-rollout scan ranking risky sites, anonymous links, broadly shared sites and unlabeled content by "Copilot exposure"; agents and Power Platform coverage; ROT-reduction guidance | Broadest Copilot/agent governance | Export format not documented; metadata not a stated focus |
| **Orchestry / SWOOP / CoreView** (MEDIUM) | Orchestry: 0-100 AI readiness score, archival policies, owner reviews. SWOOP: 0-100 AI Readiness (Content 60%, Engagement 30%, Search 10%; Pages and News only, files excluded). CoreView: cleanup and licence reports | Exec-friendly scores | SWOOP explicitly excludes files |
| **Consultancy "Copilot readiness assessment" offerings** (LOW) | Managed engagements: permissions audit, labels, ROT clean-up, checklist reports | Human-led, slide/report deliverable | Mostly manual; no repeatable deterministic engine |

**Key market finding.** An independent vendor comparison (Orchestry) found metadata was "not mentioned" for any tool, and no tool does dedicated ROT detection. Oversharing and lifecycle are crowded; **content-structure and metadata readiness, per-site action triage, effort sizing, and schema proposal are an open gap**. That gap is exactly what recover-assess targets, so the differentiators below concentrate there rather than competing on tenant-wide governance automation.

## Table Stakes

Features a consultant-run AI-readiness assessment must have, or the output will not be credible next to SAM CMA and the vendors. Missing any = the client asks "SAM already tells me that".

| Feature | Why expected | Complexity | Milestone | Notes |
|---|---|---|---|---|
| Inactivity / last-activity per site | CMA inactive report (180 days) is the baseline everyone cites | Low | COL (C4, C1) | Spec derives `last_activity` from file modifications only. Microsoft's definition spans SharePoint plus Teams, Exchange, Viva Engage. Pitfall: a Teams-heavy site can look dead. Include list and page `lastModifiedDateTime` in the activity calc and let C9 (SAM inactive report) corroborate. See Gaps |
| Ownership: owner count, active contributors, owner-hint match | CMA ownership report (none or one owner); every governance tool has owner reviews | Low | COL (C7) | Already specced. Owners need `GroupMember.Read.All` (open question); contributors fallback is good |
| Sharing exposure by link scope (anyone / org / specific / direct) | Core of every oversharing product; DAG sharing-links report | Med | COL (C6) | Already specced as budgeted sampling. Report must say "sampled N of M" prominently |
| Broken inheritance / unique permissions signal | CMA broken inheritance report | Med | COL (C6) | `compare_to_root` is a sound workaround for the missing `inheritedFrom`. Label as approximate |
| Broad-group exposure (EEEU / Everyone) | CMA and DAG both have a dedicated report; Syskit, Rencore, ShareGate all headline it | Med | COL (C6) + C9 | Direct-grants sampling may show EEEU as a principal; capture it explicitly as a counted principal type. SAM EEEU report via C9 is the authoritative site-level source |
| External / guest principal presence | DAG site permissions report highlights guests; AvePoint, ShareGate, Syskit review guests | Low | COL (C6) | Cheap add: count direct grants whose principal is an external user (`#EXT#` UPN / guest). Not in current fact sheet. Add before schema 1.0 freezes (add = minor, but freeze avoids churn) |
| Sensitivity-label awareness | DAG has a labels-for-files report; DSPM correlates label vs exposure; Rencore ranks unlabeled content first | Med | COL (C9), research | No v1.0 read path for per-file labels without writes or beta. Pragmatic path: ingest SAM/Purview export via C9 (label counts per site) and record site-level label if readable. **Research flag** |
| Content volume / storage / age profile | Needed to justify Archive/Delete; Admin Agent and CoreView report storage | Low | COL (C4) | Counts, bytes, age buckets, extension mix already specced. Add drive `quota` (used bytes; `GET /sites/{id}/drive?$select=quota` is v1.0) if cheap |
| Redundant / obsolete / trivial (ROT) indicators | ROT is the stated top Copilot-quality concern across vendors, yet no tool does it well | Med | COL (C4) | `duplicate_rate` via quickXorHash plus age buckets plus largest files already cover a defensible first pass. Do not claim content-level near-duplicate detection |
| Per-site verdict into a small fixed set of actions | CMA gives "recommended steps"; the playbook defines Enrich/Archive/Restrict/Delete | Med | SCR | Core of this product. Must be rule-driven from `config/rubric.yaml` |
| Ranked, filterable portfolio output (CSV plus HTML) | Every competitor ranks sites by risk; consultants live in Excel | Med | SCR | `collection_summary.csv` is already a decent pre-scoring view. Portfolio needs action x effort matrix, sort/filter, drill-through to per-site report |
| Per-site report a non-technical owner can read | CMA findings panel; Syskit/AvePoint reports for owners | Med | SCR | `report.html` plus `report.md`. Plain English, one-page "what we found / what to do / how hard" |
| Reproducible re-run with comparable numbers | CMA "rerun every 30 days"; AvePoint criticises SAM staleness | Low | COL, BAT | Seeded sampling and deterministic aggregates already specced. Table stakes because it supports before/after |
| Safe handling of sensitive output (path modes, hashed contributors, no bodies in logs) | Enterprise buyers and Security approval gate everything | Med | COL | Already specced. **Reports must also honour `--path-mode` and hashed contributors**, not just fact sheets |
| Coverage and truncation honesty (lower bounds, sampled, partial) | Any tool producing counts from capped reads must disclose it | Low | COL, SCR | Surface `truncated`, `fill_rate_method: first_n`, sample sizes in every report; downgrade confidence when partial |
| Pre-flight access checks and admin hand-off for grants | Sites.Selected is the least-privilege norm; admins need a script | Med | COL | `doctor` and `grants plan` already specced. Table stakes for enterprise pilots |
| Remediation pointers per action | CMA gives "recommended steps"; vendors tie findings to fixes | Low | SCR | Static mapping in the rubric: Archive to Microsoft 365 Archive / inactive-site policy (check site-type eligibility); Restrict to Restricted Content Discovery (hide from Copilot, access unchanged) or Restricted Access Control (limit to named group); Delete to inactive policy then deletion; Enrich to autofill columns / document processing / custom pipeline |

## Differentiators

Where recover-assess is different from SAM, Purview, and the vendors. These are the reasons a client buys Module 1 from a consultant instead of clicking "Start assessment".

| Feature | Value proposition | Complexity | Milestone | Notes |
|---|---|---|---|---|
| **Metadata-readiness scoring** (custom columns, fill rate, default-content-types-only, term-set use) | Playbook's central premise: Copilot grounding uses library column metadata. No competitor assesses this | Med | COL (C3, C5), SCR | Strongest differentiator. Fill-rate is first-N sample; say so |
| **Folder-pattern mining (path to metadata)** | Finds the only structure that exists (year, FY, quarter, client, region) and proposes columns from it | Med-High | COL (patterns), AGT (A2) | Competitor-free. Regex classifier plus 30% coverage rule is deterministic; LLM only names the columns |
| **Effort rating (Low/Med/High) with backfill strategy** | Turns findings into a sized work package; no competitor sizes enrichment effort | High | SCR | Needs calibration: 8/10 bands, 9/10 actions on pilot. Drives the 2-week Module 1 estimate and next-module sales |
| **Deterministic, traceable scorecard** (every sub-score lists inputs plus rubric version) | Defensible to Security and clients; reproducible; answer to "why did the AI say Delete?" | Med | SCR | Competitor scores (0-100 readiness) are opaque. This is the Core Value |
| **Rubric as config with client overrides** | Portable across companies; calibrate per client without code changes | Low-Med | SCR, PIL | `config/rubric.yaml` versioned and embedded in output |
| **Proposed starter schema per site (A2)** | Concrete "AI-ready minimum" column set proposal tied to the site's real folders and content | High | AGT | Grounded in C3/C4 evidence; map to the 6-8 field baseline from the playbook |
| **Evidence-verified LLM plan (A3 plus A4 verifier)** | Narrative that can be trusted: pointer and number checks against the fact sheet, `needs_review` on failure | High | AGT, PRV | Microsoft's Admin Agent is conversational and unverified. Verified prose is a real trust differentiator |
| **LLM-optional operation (`--no-llm`)** | Credible triage with zero model calls; fits restrictive tenants | Low | SCR | Core Value requirement. Build SCR so it never depends on AGT |
| **Strictly read-only, allow-list enforced and tested** | Most vendors sell remediation, which raises approval friction. Read-only is a sales asset for Security sign-off | Med | COL | Allow-list and log audit already in acceptance criteria |
| **Offline, portable, consultant-controlled** (no SaaS, no telemetry, no tenant crawl) | Works in locked-down tenants; no vendor data egress; no licensing prerequisite (SAM needs Copilot or SAM licence; DSPM needs E5) | Med | COL | Contrast: CMA needs licensing and admin role. Only needs Sites.Selected read per site |
| **SAM/Purview join (C9) as evidence, not replacement** | Corroborates inactivity, EEEU, labels at site level where Graph cannot; reuses what the client already paid for | Med | COL | Generic column mapping and `sam_keep_columns`. Gotcha: tenant "concealed names" setting breaks URL joins |
| **Sample tier: content classification (A1) with confirmation, untrusted-document wrapping, redaction hook** | Doc-type classification to ground the schema; opt-in, tenant-local | High | AGT | Rencore flags unlabeled content only; none propose schema from content. Keep strictly opt-in |
| **Estimate and cost control (`--estimate`)** | Predictable LLM spend for large batches | Low-Med | BAT | Token estimate from fact-sheet size |
| **Run-to-run comparison (`compare`)** | Before/after and monthly progress (CMA's re-run story) at per-site granularity | Med | BAT / post-v1 | Cheap because fact sheets are deterministic. Strong playbook measurement hook. Candidate for v1.x |
| **Claude Code skill that runs and interrogates results** | Natural-language follow-ups over local results without a server | Low-Med | SKL | Skill never edits results. Parallels the Admin Agent but local and read-only |
| **Prerequisites and sequencing in the plan** (e.g. "fix oversharing before Enrich") | Mirrors playbook governance: AI reflects permissions, so Enrich on an overshared library is unsafe | Med | SCR | Rubric emits ordered prerequisites. Combine Restrict-first guidance with Enrich |
| **Portfolio exec summary** (deterministic distribution plus optional LLM narrative) | Consultant deliverable: one page of "N sites: x Enrich, y Archive, z Restrict, w Delete; top risks" | Low-Med | SCR (+AGT optional) | Deterministic numbers must come from code; LLM only phrases them |

## Anti-Features

Things to deliberately NOT build. Several are table stakes for the competitors but violate this project's trust promise or scope.

| Anti-Feature | Why Avoid | What to Do Instead |
|---|---|---|
| Any write to M365 (tagging, moving, archiving, permission changes, applying SAM policies, label assignment) | Central trust promise. ShareGate/Syskit/AvePoint remediation is exactly what makes their approvals harder | Emit remediation pointers and `grants plan`-style admin scripts as text. Write-back is a separate project (Module 2) |
| Tenant-wide crawl / auto-discovery of sites | Sites come only from `--site`/`--csv`; 500-row cap prevents accidental tenant sweeps; SAM CMA already does tenant scale | Join SAM CMA exports via C9 if the client wants tenant context |
| Continuous monitoring, real-time alerts, scheduled drift detection as a product | Governance-platform territory (Syskit alerts, Rencore, AvePoint). Needs a service, state and approvals | Re-runs plus `compare`; scheduled via Task Scheduler on a server |
| LLM-computed scores, effort bands or actions | Breaks determinism and defensibility | LLM only explains; code computes; verifier checks numbers |
| Single opaque 0-100 "AI Readiness Score" as the headline | Competitor pattern (SWOOP, Orchestry, Syskit) but false precision and uncalibrated; undermines traceability | Headline = action plus effort band; show six weighted dimension scores. An optional composite can be rendered from dimensions later, labelled as derived |
| Full item-level permission crawl of every file | Throttling, runtime and approval risk; low marginal value over sampling | Budgeted sampling with disclosed coverage |
| Downloading file content by default | Privacy promise: metadata tier by default | Sample tier opt-in, confirmation prompt, local extraction, redaction hook |
| PII / sensitive-information detection and DLP-style classification | Purview already does this; regulatory liability if misreported | Consume labels/exposure via C9; use LLM classification only for document type, not sensitivity verdicts |
| Copilot usage / adoption analytics, licence reporting, agent inventory | Different problem (CoreView, Rencore, Agent 365); not content readiness | Out of scope. Mention in report as adjacent assessments |
| Golden-question-set answer-accuracy measurement | Playbook Measurement Kit, not Module 1 engine | Separate asset; reports can reference it |
| Web app, dashboards server, results MCP, chat UI | Deferred to v2; adds hosting, auth and review surface | Static HTML/CSV plus the Claude Code skill |
| Multi-tenant SaaS, cross-client benchmarking, telemetry | Portability/IP and zero-egress promises | Per-engagement local runs; benchmarks built manually from anonymised pilot data |
| Version-history and storage-optimisation analytics per file | Requires per-item calls; Admin Agent and ShareGate already do version trimming | Record total bytes and largest files only |
| Migration/restructure tooling, term-store editing, content-type hub changes | ShareGate and others own this; writes to tenant | Propose schema and term candidates; hand off to Module 2 |
| Client secrets, Graph beta endpoints | Security approval and stability | Delegated, certificate or managed identity; v1.0 only |
| Silent guessing for ambiguous site names | Wrong-site assessment is a trust failure | `ambiguous` status with candidates; `--pick N` |

## Feature Dependencies

```
Auth (TokenProvider) -> Graph client (allow-list) -> site resolution (inputs, CSV)
Site resolution -> C1 site -> C2 lists -> C3 columns/content types
C2 (drive id) -> C4 inventory/streaming aggregates -> folder-pattern mining
C2 + C3 -> C5 fill rate (needs custom column list from C3)
C2 (drive id) + C4 (candidate pool) -> C6 exposure (item IDs)
C4 (last modifier) -> C7 contributors ; C7 owners also needs GroupMember.Read.All (optional)
C4 candidate pool -> sample candidates ; C9 SAM join (needs normalized URL from resolve)
All collectors -> fact_sheet.json (schema v1.0 is the contract)
fact_sheet.json -> deterministic scorecard (rubric.yaml) -> action + effort + prerequisites + backfill strategy
scorecard -> per-site report.html/.md -> portfolio.csv/.html -> exec summary
scorecard + fact sheet -> LLMProvider interface -> A2 schema proposal -> A3 plan -> A4 verifier
sample tier (C8 download + extraction) -> A1 classification -> improves A2 (optional; requires confirmation prompt)
run state machine (BAT) -> resume / rescore / report / --estimate; compare requires two scored runs
Claude Code skill -> requires doctor + collect + scoring + reports (reads, never edits)
Pilot calibration -> requires scorecard + reports on ~10 hand-assessed sites; feeds rubric.yaml tuning
```

**Notable cross-feature dependencies**
- Folder-pattern mining must exist before A2 can propose columns from paths. A2 quality depends on C3 (existing columns) as well as patterns.
- Effort rating depends on three collectors at once: C4 (volume, depth, duplicates), C5 (fill rate), C6 (exposure prerequisites). Partial or truncated collection must lower confidence, not silently score.
- `--path-mode tokens/hashed` must be applied before the LLM sees paths (privacy) and before reports render (sharing). Single redaction seam, tested.
- Remediation pointers depend on site kind (group/Teams-connected, communication, publishing) because Microsoft 365 Archive does not support all site types. Record site kind in C1 or the Archive pointer will be wrong for some sites.
- `compare` depends on a stable fact-sheet schema and stable rubric versioning. Do not ship before the schema freezes.

## MVP Recommendation

Prioritise (order = dependency order, aligned to milestones):

1. **COL: Collector C1-C7 plus samples, with the small additions below** (table stakes plus the metadata differentiator data). Without trustworthy fact sheets nothing else is credible.
2. **SCR: Deterministic scorecard, rubric.yaml, action rules, effort band, remediation pointers, per-site and portfolio outputs, `--no-llm`.** This is the minimum viable product and already beats a manual audit. Ship and calibrate here.
3. **PIL: Calibrate on ~10 hand-assessed pilot sites** before building more agent surface area. Calibrated numbers are the credibility asset.
4. **PRV + AGT (metadata tier): A2 schema proposal, A3 plan, A4 verifier.** Primary differentiator layered on a solid base. Azure OpenAI via the corporate LLM gateway, Anthropic as a stub.
5. **BAT: resume/rescore/report/`--estimate`, progress, exit codes.** Needed before portfolio runs at scale.
6. **SKL: Claude Code skill.** Thin and cheap, after the above are stable.

**Small additions to fold into the Collector spec now (all Low complexity, avoid schema churn before 1.0):**
- External/guest principal counts in C6; EEEU/Everyone as an explicit principal type.
- Site kind (group-connected, Teams-connected, communication, publishing) in C1.
- Drive quota/used bytes.
- Include list and page `lastModifiedDateTime` in `last_activity`; add a field naming the activity basis (`file_modified`, plus `sam_inactive` when C9 matches).
- C9: pluggable column mapping so CMA exports, DAG site-permission exports and DSPM exports can be joined; detect pseudonymised (concealed) URLs and emit `sam_no_match` with a hint.

**Defer:**
- **Sample tier (C8 plus A1):** highest risk and cost. Ship metadata tier first; build sample tier after pilot calibration shows A2 needs content evidence.
- **`compare` between runs:** valuable, but only after the schema and rubric stabilise.
- **`--include-subsites`:** wait for the pilot answer to the open question; promote to Medium-complexity feature if pilot sites rely on subsites.
- **Composite readiness number:** only if clients demand it, rendered from dimensions.
- **Per-file sensitivity labels beyond C9 joins:** needs research (see Gaps).

## Gaps to Address

- **Sensitivity labels.** Competitors and DAG treat label coverage as table stakes. Graph v1.0 read-only options for per-file labels are unclear to me (assign/extract actions are POST and fall outside the allow-list). Needs phase-specific research; interim answer is C9 join. Confidence LOW.
- **Activity definition mismatch.** Microsoft inactivity (180 days across SharePoint, Teams, Exchange, Viva Engage) is not equal to file-modification recency. Archive/Delete rules should require corroboration (C9 or multiple signals) or reduce confidence. Needs rubric design attention in SCR.
- **Vendor capability claims** (AvePoint SAM-staleness claim of 28-day refresh; Rencore export format; Syskit readiness score) came from vendor marketing or comparison sites and were not verified. Treat as MEDIUM/LOW.
- **SAM export formats.** The open question on which SAM report and exact columns remains unresolved. CMA is tenant-wide with 2 to 72 hour runtime; DAG activity reports cap at 10,000 sites and cover 28 days only.
- **Terms and licensing facts** (SAM included with Copilot licence; E5 gives only partial DAG) are from Microsoft Learn but change often. Re-verify at pilot time.
- Third-party "metadata coverage" benchmarks do not exist; the rubric thresholds are original and must be calibrated, not cited.

## Sources

- [Microsoft Learn: Content Management Assessment](https://learn.microsoft.com/en-us/sharepoint/content-management-assessment) (HIGH; updated 2026-07)
- [Microsoft Learn: Data access governance reports](https://learn.microsoft.com/en-US/SharePoint/data-access-governance-reports) (HIGH; updated 2026-07)
- [Microsoft Learn: SharePoint Admin Agent overview](https://learn.microsoft.com/en-us/sharepoint/content-governance-agent) (HIGH; updated 2026-10)
- [Microsoft Learn: Get ready for Microsoft 365 Copilot and agents with SharePoint Advanced Management](https://learn.microsoft.com/sharepoint/sharepoint-copilot-best-practices) (HIGH)
- [Microsoft Learn: Site lifecycle management and inactive site policy](https://learn.microsoft.com/en-au/sharepoint/site-lifecycle-management) (HIGH)
- [Microsoft Learn: Assess SharePoint overexposure (Purview DSPM for AI)](https://learn.microsoft.com/en-in/training/modules/identify-ai-data-risks-purview/3-assess-sharepoint-overexposure) and [DSPM for AI](https://learn.microsoft.com/purview/dspm-for-ai) (HIGH/MEDIUM)
- [Orchestry: Best Copilot readiness tools](https://www.orchestry.com/insight/best-copilot-readiness-tools) (MEDIUM; competitor-authored comparison)
- [Syskit: 4 steps to minimise oversharing for Copilot](https://www.syskit.com/blog/4-steps-to-minimize-oversharing-for-copilot) (MEDIUM; vendor)
- [Rencore: Microsoft 365 Copilot governance / readiness](https://hub.rencore.com/product/ai-readiness/m365-copilot-governance/) (MEDIUM/LOW; vendor marketing)
- [AvePoint: Copilot readiness and oversharing](https://www.avepoint.com/blog/protect/secure-data-microsoft-365-copilot) and [Confidence Platform vs SAM](https://www.avepoint.com/blog/solutions-blog/gearing-up-for-copilot-how-avepoints-confidence-platform-soars-above-sharepoint-advanced-management) (MEDIUM/LOW; vendor)
- [SWOOP Analytics: AI Readiness for SharePoint](https://support.swoopanalytics.com/hc/en-us/articles/55643393535129-ai-readiness-swoop-for-sharepoint) (MEDIUM; vendor documentation)
- Project inputs: `.planning/PROJECT.md`, `Recover Assessment Collector Build Spec (Step 1).md`, `AI-Ready SharePoint Framework & Enablement Playbook (Draft).md`
