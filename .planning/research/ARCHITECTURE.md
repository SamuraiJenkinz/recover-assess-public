# Architecture Research

**Domain:** Read-only, staged assessment pipeline CLI (Microsoft Graph collector, deterministic scorer, LLM agent, report renderer) with batch resume
**Project:** recover-assess
**Researched:** 2026-11-15
**Confidence:** HIGH on layering, Graph client, delta streaming, state/resume (verified against Microsoft Learn and the Step 1 spec). MEDIUM on LLM provider design (Azure OpenAI strict-schema limits verified; the corporate LLM gateway's support for strict `json_schema` is NOT verified and must be spiked).

---

## Verdict on the proposed layout

The layout in the Step 1 spec and PROJECT.md (thin `cli.py`; `core/` with `graph.py`, `auth.py`, `resolve.py`, `collect/`, `score.py`, `agent/`, `providers/`, `report.py`, `run.py`) is **sound and should be kept**. It already encodes the three decisions that matter most: one network choke point (`graph.py`), SDK isolation (`providers/`), and a thin CLI. Refinements, in priority order:

1. **Stage boundaries are files, not objects.** Every stage reads its input artifact from disk and writes its output artifact atomically. `score` never receives an in-memory fact sheet from `collect`. This is what makes `resume`, `rescore`, `report` and golden-file tests the same code path.
2. **Split `models.py` into a `models/` package** (published contracts vs LLM wire models vs internal run state). A single `models.py` becomes a god-module by the time scoring and the agent land.
3. **Add `net.py`** (TLS/proxy/httpx client factory) and **`evidence.py`** (evidence-pointer index shared by score, agent verifier and reports). Neither exists in the spec layout; both have more than one consumer.
4. **Turn `run.py` into a facade over `run/` (RunStore + Stage registry + scheduler)** from day one, with `run.json` designed for per-stage state, so Step 1's state machine extends to `scored -> planned -> verified -> reported` without a migration.
5. **Enforce the boundaries with import-linter contracts**, not convention (concrete contracts below). "Read-only" and "no content leaves the tenant" are architectural properties, so they must be machine-checked.
6. **Two spec corrections found during research** (see "Spec corrections" below): delta does not return `parentReference.path`, and the same item can appear more than once in a delta feed. Both change how C4 is built.

---

## Standard Architecture

### System Overview

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ CLI layer (cli.py: Typer + Rich ONLY)                                         │
│  parse flags -> build Settings -> call core.run.* -> render ProgressReporter  │
│  events -> map RunResult to exit code (0/1/2/130)                             │
└──────────────────────────────────────┬────────────────────────────────────────┘
                                       │ (core never imports cli; progress via Protocol)
┌──────────────────────────────────────▼────────────────────────────────────────┐
│ Orchestration layer: core/run/                                                │
│  RunStore (run.json, lock, atomic IO) · Stage registry · Site scheduler       │
│  resume/rescore planning (pure fn over run state + input fingerprints)        │
└───┬──────────────┬───────────────┬────────────────┬─────────────────┬─────────┘
    │              │               │                │                 │
┌───▼────┐   ┌─────▼─────┐   ┌─────▼─────┐   ┌──────▼──────┐   ┌──────▼──────┐
│resolve │   │ collect/  │   │  score    │   │  agent/     │   │  report     │
│inputs  │   │ C1..C7,   │   │ (pure,    │   │ A1..A4      │   │ (pure render│
│        │   │ samples,  │   │ no I/O)   │   │ (no Graph)  │   │ no I/O but  │
│        │   │ C8, C9    │   │           │   │             │   │ file write) │
└───┬────┘   └─────┬─────┘   └─────┬─────┘   └──────┬──────┘   └──────┬──────┘
    │              │               │                │                 │
    │              │               └──────┬─────────┘                 │
    │              │                      │ shared                    │
    │              │              ┌───────▼────────┐                  │
    │              │              │ evidence.py    │◄─────────────────┘
    │              │              │ (pointer index)│
    │              │              └───────┬────────┘
┌───▼──────────────▼───────┐      ┌───────▼───────────────────────────────────┐
│ graph.py (ONLY M365 I/O) │      │ providers/ (ONLY LLM SDK imports)         │
│ ReadOnlyPolicy+allowlist │      │ LLMProvider · StructuredCaller · Azure    │
│ paging · $batch · throttle│     │ OpenAI(gateway) · Bedrock stub · Fake/Replay │
│ GraphSession per site    │      └───────┬───────────────────────────────────┘
└───┬──────────────────────┘              │
┌───▼───────────┐   ┌──────────┐   ┌──────▼─────┐
│ auth.py       │   │ net.py   │   │ (net.py)   │
│ TokenProvider │   │ truststore│  │            │
│ x3 modes      │   │ + httpx   │  │            │
└───────────────┘   └──────────┘   └────────────┘
┌───────────────────────────────────────────────────────────────────────────────┐
│ Leaf layer (imports nothing above it): models/ · config.py · errors.py · log.py│
│ Published contracts: FactSheet, Scorecard, Recommendation -> schemas/*.json   │
└───────────────────────────────────────────────────────────────────────────────┘
```

### The pipeline as artifact flow (stage boundary = file)

```
input row ──resolve──▶ resolution.csv + site_id
                          │
                          ▼ collect (Graph GETs, no content)
              sites/<slug>/fact_sheet.json   ◄── schemas/fact_sheet.schema.json (v1.0)
                          │ (read from disk)
                          ▼ score (pure; rubric.yaml)
              sites/<slug>/scorecard.json    (effort, action, strategy, sub-scores+inputs, rubric ver+sha)
                          │
          ┌───────────────┴───────────────┐ (skipped entirely with --no-llm)
          │ [sample tier only] C8 fetch + extract -> A1 classify (untrusted docs)
          │ A2 schema proposal -> A3 plan -> A4 verify (code checks, then model check)
          ▼
              sites/<slug>/agent/*.json + recommendation.json (needs_review on 2nd verify failure)
                          │
                          ▼ report (pure render)
              sites/<slug>/report.html|md      portfolio.csv|html (batch)
```

`--no-llm` is simply "the stage list stops after `score`, report renders without the plan section". Core Value (credible triage with the LLM layer dead) falls out of the structure instead of needing special handling.

### Component Responsibilities

| Component | Owns | Must NOT | Talks to |
|-----------|------|----------|----------|
| `cli.py` | Typer commands, flag parsing, Rich progress rendering, exit-code mapping | Contain logic; be imported by core | `core.run`, `core.config` |
| `core/config.py` | pydantic-settings models; layering default < YAML < env < CLI; `extra="forbid"`; config fingerprints | Hold secrets (only env-var *names*) | leaf |
| `core/errors.py` | Stable error-code enum (spec list), exception hierarchy, `WriteAttemptError` | | leaf |
| `core/log.py` | JSONL structured logger, typed event schema, scrub filter, contextvar site key | Accept free-form bodies/tokens | leaf |
| `core/net.py` | `truststore` activation, `httpx.AsyncClient` factory (timeouts, proxy env, HTTP/2 off) | Know about Graph or LLMs | graph, providers, auth |
| `core/auth.py` | `TokenProvider` (delegated / app_certificate / managed_identity), token decode for `doctor`, single-flight refresh | Perform requests to Graph | net (indirectly MSAL) |
| `core/graph.py` | **The only M365 I/O.** Read-only policy, allow-list, paging, `$batch`, throttle barrier, circuit breaker, per-site session stats | Be bypassed; log bodies/tokens | auth, net, log, errors |
| `core/resolve.py`, `inputs.py` | `normalize()` (pure), CSV parsing (pure), resolution via a `GraphSession` | Enumerate tenant sites | graph |
| `core/collect/*` | Async functions `(session, ctx, cfg) -> CollectorOutput`; pure aggregators (`patterns.py`, accumulators) | Import each other (except `patterns.py`), write files, import `score`/`agent` | graph (session type only), models |
| `core/score.py` | Pure `score(fact_sheet, rubric) -> Scorecard`; rubric loading/validation | Do I/O, import graph/providers, call LLMs | models, evidence |
| `core/evidence.py` | Build `EvidenceIndex` (stable ids -> JSON Pointer + value + label) from fact sheet + scorecard; resolve/validate pointers | Know about LLMs | models |
| `core/agent/*` | Prompts (versioned files), A1-A4 orchestration, verifier code checks | Import `graph`/`collect`; override scored fields | providers, evidence, models |
| `core/providers/*` | `LLMProvider` protocol, `StructuredCaller` (wire-schema lowering, local validation, one repair retry), Azure OpenAI/gateway adapter, Bedrock stub, Fake/Replay | Leak SDK types outside the package | net, models, errors |
| `core/report/*` | Deterministic render of HTML/MD/portfolio from artifacts; neutral theme + external theme files | Call anything over the network | models, evidence |
| `core/output.py` | Atomic write, slugging, path-mode/contributor redaction at emit time, CSV writers | | models |
| `core/run/*` | `RunStore`, stage registry, site scheduler, resume/rescore planner, prune, run lock, signal handling | Contain stage business logic | everything below |

---

## Recommended Project Structure

```
recover-assess/
  CLAUDE.md  README.md  pyproject.toml  Makefile  recover-assess.example.yaml  .importlinter
  config/
    builtin_columns.yaml  file_types.yaml  patterns.yaml  graph_allowlist.yaml
    rubric.yaml                      # Stage 2 (scoring)
  schemas/                           # GENERATED from pydantic; checked in; drift-tested
    fact_sheet.schema.json  scorecard.schema.json  recommendation.schema.json
    archive/fact_sheet-1.0.schema.json   # frozen released copies for compat test
  scripts/gen_schemas.py             # one registry: PUBLISHED = {"fact_sheet": FactSheet, ...}
  skills/recover-assessment/SKILL.md # Stage 6
  src/recover_assess/
    cli.py                           # Typer only
    core/
      errors.py  config.py  log.py  net.py  auth.py  graph.py
      models/
        common.py                    # shared value types (Share, Iso8601Utc, Pointer...), round4, canonical_bytes
        fact_sheet.py                # PUBLISHED contract v1.0
        scorecard.py  recommendation.py   # PUBLISHED
        agent_io.py                  # LLM output models (wire models; NOT published)
        run_state.py                 # run.json (internal, own schema version)
        rubric.py                    # validates config/rubric.yaml
      inputs.py  resolve.py
      collect/
        __init__.py                  # collect_site(): ordered collector runner, warnings capture
        c1_site.py c2_lists.py c3_columns.py c4_inventory.py c5_fill.py
        c6_exposure.py c7_ownership.py samples.py c9_sam.py c8_content.py(Stage 5)
        patterns.py accumulators.py  # pure, hypothesis-tested
      evidence.py
      score.py
      agent/  a1_classify.py a2_schema.py a3_plan.py a4_verify.py  prompts/*.md  untrusted.py
      providers/  base.py structured.py wire_schema.py azure_openai.py anthropic_bedrock.py fake.py
      report/  render.py  templates/  themes/neutral/
      output.py
      run/
        __init__.py                  # facade: run_collect, resume, rescore, report, prune
        store.py                     # RunStore: run.json, lock file, atomic IO, coalesced flush
        stages.py                    # Stage protocol + registry + fingerprint rules
        scheduler.py                 # site concurrency, cancellation, deadlines
        prune.py
  tests/
    unit/ graph/ integration/ fixtures/ golden/ fakes/fake_graph.py
```

### Structure Rationale

- **`models/` package, three tiers:** `fact_sheet/scorecard/recommendation` are *published contracts* (schema-generated, semver'd). `agent_io` are *wire models* for LLM output (strict-mode constraints, never published). `run_state` is *internal* and versioned separately. Mixing them in one file is how a "harmless" refactor silently becomes a major contract break.
- **`evidence.py` at core level, not under `agent/`:** score records its inputs as evidence pointers, the verifier checks pointers, reports render pointers. If it lived in `agent/`, `score` would have to import `agent` (a layering inversion).
- **`net.py`:** MSAL (via `requests`), azure-identity, httpx (Graph) and the openai SDK all hit TLS-inspected corporate egress. One module decides trust store + proxy so there is a single place to debug "works at home, fails inside the pilot organisation".
- **`run/` package:** `RunStore` (durability) is separable from `stages.py` (what a stage is) and `scheduler.py` (concurrency). Step 1 builds them minimally; later stages register additional `Stage` objects.
- **`config/` vs `src/`:** YAML data files (allow-list, builtin columns, patterns, rubric) are package data loaded through `importlib.resources`, validated by pydantic at startup. A malformed allow-list must fail `doctor`, not mid-run.

---

## Architectural Patterns

### Pattern 1: Single choke point + capability-restricted policy (read-only guarantee)

**What:** `graph.py` has exactly one private `_send()` that performs all network I/O. Before the socket is touched, `ReadOnlyPolicy.check(method, path, query, batch_items)` runs. The policy is constructed with capabilities, e.g. `ReadOnlyPolicy(allow_content=False)`. Allow-list entries in `graph_allowlist.yaml` carry a `tier: metadata|sample`; `/content` templates are `tier: sample` and are unreachable unless the sample tier was explicitly confirmed and the client built with `allow_content=True`.

**When:** Always. This is the central trust promise.

**Details that matter:**
- Match on **templates**, not prefixes. Compile each template to an anchored regex over decoded path segments; reject `..`, empty segments, encoded slashes (`%2F`), and unknown query parameters (`$select,$expand,$top,$filter?,token` as a global set).
- The matched **template string is also the log path template** (IDs already `{id}`), so request logs cannot leak IDs by construction.
- **`@odata.nextLink` is absolute and server-supplied: re-validate it** (https, host exactly `graph.microsoft.com`, path under `/v1.0/`, template-matches) before following. Never follow an arbitrary URL with a bearer token attached.
- `$batch`: policy validates **every sub-request** (`method == "GET"`, no `body`, no `dependsOn`, relative URL template-matches). A `$batch` containing anything else raises `WriteAttemptError` before send.
- `follow_redirects=False` for Graph calls. (Stage 5, sample tier: `/content` answers 302 to a pre-authenticated SharePoint URL; handle that single hop explicitly with a host check and without the Authorization header. Flag for phase research.)
- Defense in depth: a thin `httpx` transport wrapper asserts `method in {GET, POST}` and `POST` only to `/$batch`, so a bug in request building still cannot emit a write. Plus an import-linter rule that `httpx`/`requests` are importable only from `net`, `graph`, `providers`, and an AST test that no other module calls `.post/.put/.patch/.delete`.

```python
class ReadOnlyPolicy:
    def __init__(self, allowlist: Allowlist, *, allow_content: bool = False): ...
    def check(self, method: str, url: str, batch: list[BatchItem] | None = None) -> MatchedTemplate:
        if method == "GET": return self._match_get(url)
        if method == "POST" and self._is_batch(url):
            for item in batch or []:
                if item.method != "GET" or item.body is not None: raise WriteAttemptError(...)
                self._match_get(item.url)
            return BATCH_TEMPLATE
        raise WriteAttemptError(method, url)   # raised BEFORE any network call
```

### Pattern 2: One shared `GraphClient`, many cheap `GraphSession`s

**What:** One `GraphClient` per run owns the `httpx.AsyncClient` (connection pool), the `TokenProvider`, the policy, and a **shared throttle barrier**. Each site gets a `GraphSession` (a lightweight bound view) carrying: site key, in-flight semaphore (default 4), per-site circuit breaker (20 throttles / 60 s), wall-clock deadline (`site_wall_clock_minutes`), and `graph_stats` counters. Collectors receive only the `GraphSession`.

**Why a shared barrier:** Graph throttling is per app + tenant, not per site. If 2 sites x 4 in-flight requests all independently honour their own Retry-After, 7 other requests hit 429 while the first waits. On any 429, set `resume_at = now + Retry-After` on the *client*; every `_send()` awaits the barrier first. The per-site breaker (spec) still trips on that site's 429 count.

**Retry loop:** hand-rolled (not tenacity) because it must coordinate the barrier, deadline and breaker: 429/503 -> honour `Retry-After`, else full-jitter exponential (1 s base, 60 s cap); max 6 retries; 5-minute give-up per request; never retry other 4xx. Inject a `Clock` (monotonic + `sleep`) so respx tests of 429/backoff run in milliseconds. (tenacity stays in `providers/`, where a simple policy suffices.)

**`$batch` rules (verified, Microsoft Learn):**
- Max 20 sub-requests; sub-request `id`s must be unique (duplicate = whole-batch 400).
- A 200 on the batch says nothing about sub-responses; check each `status`. Responses can arrive out of order: correlate by `id`.
- Throttling is evaluated per sub-request; a sub-response 429 carries its own `Retry-After` header. Re-queue those sub-requests after the longest `Retry-After` in the batch (spec) and feed the barrier.
- Sub-responses can carry `@odata.nextLink` (absolute URL). Batch helpers must fall back to plain paged GETs for those, not assume one page.
- Sub-request errors (403/404) are returned as `BatchResult(status, error)` values, not raised, so a collector can turn one bad list into a warning instead of losing the site.

### Pattern 3: Streaming accumulator with order-independent sampling (C4)

**What:** `iter_pages()` is an async generator; C4 feeds each page into a `LibraryAccumulator.add(item)`; `finalize()` returns the published `LibraryInventory` model plus an internal `InventorySideData` (top-level folders, file priority-samples for C6, contributor counters, sample pool). Closing the generator at `max_items_per_library` sets `truncated: true, counted: N`.

**Memory model (be honest about it):** state is O(folders + distinct hashes + distinct modifiers + seen-ids), all bounded by the 50,000-item cap; no per-file records, no per-file paths. The spec's own "hash index" and "candidate pool" are already O(files) within the cap, so this is consistent with "stream, don't store".

**Design rules (each solves a concrete failure):**

| Rule | Why |
|------|-----|
| Track items by **id**; keep a `folders: dict[id -> (name, parent_id)]` and count files per `parent_id`. Resolve paths **only at `finalize()`** by walking the folder map to the root item. | Delta does **not** return `parentReference.path` (see Spec corrections) and does not guarantee parents-before-children. |
| Roll up folder-pattern coverage from per-folder file counts: for depth d in 1..4, `segment_at_depth(folder_path, d) += files_directly_in_folder`. Depth histogram weighted by folder depth gives exact p50/p90 in O(max_depth). | Gives pattern shares and depth percentiles without ever storing per-file paths. |
| **Dedupe by item id** (seen-set; first occurrence wins; count `delta_repeats` in debug log). | Delta "may return the same item more than once" (docs); naive running totals double count. First-wins is acceptable for a full initial enumeration; document it. |
| **Seeded sampling by hash priority, not reservoir/`random`:** keep the k items with smallest `sha256(seed ‖ item_id)` in a bounded heap (per stratum for samples; one global heap for C6 random files). `seed = sha256(site_id)`. Never use builtin `hash()` (salted per process). | Delta page/item order is not stable between runs. Reservoir sampling depends on order and would break the acceptance test "re-run gives the same sample_candidates". Priority sampling is order-independent, streaming and deterministic. |
| Stratified samples: bounded heaps keyed by (top-level folder, age bucket); apportion across strata after the stream ends (spec: proportional to folder size, 5 largest folders >= 1 each). | Needs final stratum sizes, so selection is two-phase: keep top-k per stratum while streaming, apportion in `finalize()`. |
| Top-5 largest: min-heap of size 5 (store item id, resolve path in `finalize()`). Extension shares: `Counter` capped at a sane distinct limit with an `other` bucket. | Bounded memory against pathological extension cardinality. |
| Duplicates: `Counter[(quickXorHash, size)]`; denominator = files **with** a hash (spec); files lacking a hash are excluded, not counted as unique. | Matches spec definition; SharePoint exposes quickXorHash only. |
| When truncated, pattern/depth results come from an order-biased subset (delta order is not breadth-first). Record `truncated` and pass it to scoring as a confidence downgrade; never present counts as exact. | Lower bounds, spec-mandated; the bias is the hidden part. |

**Testing:** differential/property tests (hypothesis): for any generated item list and any permutation (with injected duplicate items), `accumulator(items) == naive_reference(items)` and `finalize()` is permutation-invariant. A `tracemalloc` test over ~200k synthetic items (cap raised) asserts peak memory stays far below a list-of-items baseline.

### Pattern 4: Collector contract = typed output + internal side data

**What:** Each collector is `async def cN(session: GraphSession, ctx: SiteContext, cfg: CollectCfg) -> CollectorOutput`, where `CollectorOutput` is a published model fragment (goes into the fact sheet) plus optional internal data written onto `SiteContext` (never persisted): drive ids (C2 -> C4/C6), top-level folder ids and file priority-samples (C4 -> C6, samples), contributor counters (C4 -> C7).

**Failure isolation:** `collect_site()` runs collectors in spec order (C1, C2, C3, C4, C5, C6, C7, samples, C9), wraps each in try/except mapping known exceptions to stable error codes -> `warnings[]`, emits `collector_start/end` log events, and downgrades site status to `partial` rather than aborting. Within a collector, fan out with `asyncio.TaskGroup` bounded by the session semaphore (e.g. libraries in C4/C5/C6 in parallel; batches in C3); delta paging for one drive is inherently sequential.

**Dependency note:** C6 needs C4's folders/files (top-level folders + seeded random files) and C7 needs C4's last-modifier counters. This is why C4's side data exists, and why "C4 + pattern mining" is the pivotal collector in the build order.

### Pattern 5: Artifact-boundary stages with input fingerprints (resume / rescore)

**What:** A stage is `(name, run(site_ctx), inputs() -> fingerprint, artifact_path)`. `run.json` per site stores, per stage: `status` (`pending|running|done|partial|failed|skipped`), `started`, `finished`, `artifact` (relative path), `artifact_sha256`, `inputs_fingerprint`, `error_code`.

```
fingerprint(collect)  = hash(collect-affecting config subset, tool_major)   # http tuning excluded
fingerprint(score)    = hash(fact_sheet_sha256, rubric_sha256)
fingerprint(agent_*)  = hash(scorecard_sha256, prompt_set_sha256, model_id, provider)
fingerprint(report)   = hash(scorecard_sha256, recommendation_sha256, theme_sha256, template_sha256)
```

- **`resume`** = for each site, run from the first stage whose status != `done` or whose stored fingerprint != current fingerprint. This subsumes the spec rule (`pending|collecting|partial|failed` -> redo collection) because `collect` is the first stage and is cheap to redo.
- **`rescore`** = recompute fingerprints with the current rubric; only `score` and downstream stages are invalidated; `collect` is untouched. No Graph access, no auth needed.
- **`report`** = invalidates only `report`.
- The planner is a **pure function** `plan(run_state, current_fingerprints) -> list[(site, from_stage)]`: property-test it with hypothesis (idempotent; never reruns a `done` stage with matching fingerprint; monotone).
- Spec-visible states map onto this: `collecting` = collect stage `running`; `complete|partial|failed` = collect stage terminal status. Keep the spec's labels in `collection_summary.csv`.
- Step 1 must write `run.json` with a `run_schema_version` and a `stages` map even though only `resolve` and `collect` exist, so later stages are additive.

### Pattern 6: Atomic, crash-consistent writes

**Write order:** (1) write artifact to a temp file in the **same directory**, `flush`, `os.fsync`, `os.replace`; (2) *then* update `run.json` (same procedure). Crash between (1) and (2) leaves an artifact the state doesn't claim yet; resume re-runs that stage; harmless because stages are idempotent. Never the reverse (state says `complete`, artifact missing).

**Windows specifics:** `os.replace` is atomic on the same volume, but raises `PermissionError` when the target is momentarily held open (antivirus, Search indexer, Excel on `collection_summary.csv`). Wrap in a bounded retry (about 10 tries, 50-250 ms jittered); never fall back to non-atomic copy. Temp name `.{name}.tmp-{pid}` in the same dir; sweep orphan `*.tmp-*` at `resume` start. Directory `fsync` is not available on Windows; do not pretend otherwise.

**`RunStore`:** single owner of `run.json`; asyncio lock; coalesced flushes (at most about 1 write/s, forced flush on site-terminal transitions, shutdown, and SIGINT) so 500 sites do not rewrite a 200 KB file thousands of times under AV scanning. A `run.lock` file (pid, host, start time, created with `O_EXCL`) prevents two `resume` invocations on one run; stale-lock detection by pid liveness on the same host, otherwise require `--force-unlock`. On resume, verify each `done` artifact exists and its sha256 matches before trusting it.

### Pattern 7: Redaction at the emit boundary

**What:** Collectors work with real names/emails in memory. `output.py` applies `redact(fact_sheet, PrivacyPolicy)` **once, when serializing** (path modes `full|tokens|hashed`, contributor `email|hashed`, per-run salt stored in `run.json` and reused on resume). Not inside collectors.

**Why:** Pattern mining needs real folder names (`year`, `FY25`) before they are tokenized; redacting early would destroy the classification. Redacting at write time gives one audited place and one test ("no literal folder name appears in a `tokens` output"). Logs never carry paths or emails at all (typed event schema), so redaction applies to artifacts only.

**Implication for the contract:** downstream stages cannot assume literal paths. Record `privacy: {path_mode, contributors}` **inside the fact sheet v1.0** (missing from the spec's example JSON; adding it later is only a minor bump, but A3/A4 and reports need it from the start so they do not present `<literal:3f9a>` as a folder name).

### Pattern 8: Deterministic scoring as a pure function over a closed rule vocabulary

**What:** `score(fact_sheet: FactSheet, rubric: Rubric) -> Scorecard`. No I/O, no clock, no randomness. `config/rubric.yaml` is validated by a pydantic `Rubric` model; its version string **and** content sha256 are recorded in every scorecard.

**Rule vocabulary (closed, implemented in code, parameterized by YAML):** `threshold_bands`, `linear_clamp`, `ratio_bands`; action/prerequisite/strategy rules are ordered **first-match-wins** lists of structured predicates `{all|any: [{evidence: "<pointer>", op: ">=", value: 0.3}]}`. No `eval`, no embedded expressions: the rubric is data, the interpreter is 150 lines of reviewed code. Resist an expression engine.

**Every sub-score records** `{dimension, rule_id, inputs: [{pointer, value}], normalized, weight, contribution}`. The `inputs[].pointer` use the same evidence-pointer scheme as the agent (Pattern 9), so "traceable to evidence in the fact sheet" is literally checkable.

**Edge handling to design in now:** truncated libraries (counts are lower bounds), `partial` fact sheets (missing collector -> dimension marked `insufficient_evidence`, scorecard `confidence` reduced, never a silent zero), `owners_source: unavailable`, no libraries. Scorecard carries `evidence_coverage` and `confidence`.

**Scoring reads the on-disk fact sheet** (4-dp rounded values), never pre-rounded in-memory numbers, so `score` after `collect` and `rescore` weeks later are bit-identical.

### Pattern 9: Evidence pointers (shared by score, agent, verifier, report)

**What:** `evidence.py` builds an `EvidenceIndex` from `FactSheet + Scorecard`: stable ids (`E012`) -> `{pointer (RFC 6901), value, label, unit}`. Arrays are addressed by stable keys where possible (library `id`), not positional index, in the *human label*; the pointer itself is regenerated deterministically from the same sorted data.

**Agent protocol:** the prompt includes the evidence table (id, label, value). Model output is *structured claims*: `{text, evidence_ids[], numbers: [{value, unit, evidence_id}]}`. The A4 verifier runs **code checks first**: (a) every `evidence_id` exists; (b) every structured number matches its evidence (tolerance by unit/rounding: percent, GB, counts); (c) any numeric token in free prose that appears in no cited evidence is flagged; (d) `effort`, `action`, `strategy` in the plan equal the scorecard (the agent cannot override scored fields). Then the model-check pass (semantic claims). Failure -> one regeneration with the verifier's findings -> second failure sets `needs_review` and keeps the deterministic result.

### Pattern 10: `LLMProvider` = transport; `StructuredCaller` = contract

**What:**

```python
class ProviderCapabilities(BaseModel):
    strict_json_schema: bool      # server-enforced schema (Azure strict json_schema, Bedrock strict tools)
    supports_system_role: bool = True
    max_input_tokens: int | None = None

class LLMProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities
    async def complete_json(self, *, task: str, system: str, user: str,
                            wire_schema: dict, schema_name: str) -> RawCompletion: ...
    # raises: ProviderNotConfigured, ProviderRefusal, ProviderContentFiltered (guardrail_intervened),
    #         ProviderTransientError (after its own retries), ProviderAuthError
```

`providers/structured.py::StructuredCaller(provider)` is **provider-independent** and owns the contract: derive the **wire schema** from the pydantic output model (lowering, below) -> call -> parse JSON -> validate with the **full** pydantic model + `jsonschema` against the *un-lowered* schema -> on failure, **one** repair call that sends back the validation errors (and nothing else sensitive) -> else raise `StructuredOutputError`. The Bedrock stub then only has to raise `ProviderNotConfigured` and, later, implement transport (`strict` tools mode per the user's local Anthropic-proxy skill, not in repo).

**Wire-schema lowering (a real component, not a helper):** Azure OpenAI strict mode (verified, Microsoft Learn, 2026-08) requires `additionalProperties: false` and **all** properties in `required` (optional = union with `null`); forbids `minLength/maxLength/pattern/format`, `minimum/maximum/multipleOf`, `minItems/maxItems/uniqueItems`, `minProperties/maxProperties`, `patternProperties`; max **100 properties and 5 nesting levels**; root cannot be `anyOf`; first structured-output API version is `2024-08-01-preview`. So:
- Write LLM output models with constraints for *local* validation (`Field(ge=..., max_length=...)`), then run a `lower_for_strict(schema)` pass that strips unsupported keywords and enforces required/additionalProperties. Do not assume the SDK's pydantic helper strips unsupported keywords for you; own the lowering and test it.
- **No `dict[str, X]` fields in LLM output models** (open maps cannot satisfy `additionalProperties: false`). Use lists of `{key, value}` objects.
- A unit test lints every LLM output model against the strict limits (depth <= 5, props <= 100, all required) so a model edit cannot ship a schema the server rejects.
- Handle `refusal` and `finish_reason == "length"` as typed errors, not as parse failures.

**The corporate LLM gateway is not stock Azure OpenAI (from the user's local gateway-troubleshooting skill, not in repo):** deployment name lives in the URL path (`.../coreapi/openai/v1/deployments/<name>/chat/completions`), auth is the `api-key` header (not Bearer), keys are deployment-scoped (wrong deployment -> `upstream_auth_403`), and a wrong URL yields a **200 with an empty body**. Consequences: use non-streaming calls (we need whole JSON anyway), treat empty content / null usage as a provider error, make `deployment` a per-task config entry (A1-A4 may use different deployments with different keys), and include an `llm doctor` check that does a real structured round-trip. **Whether the corporate LLM gateway forwards `response_format: json_schema, strict: true` is unverified.** Hence `capabilities.strict_json_schema` is a flag: if false, `StructuredCaller` degrades to "schema in prompt + JSON mode if available + local validation + one repair". Spike this in week one; it decides how much repair-path code matters.

**Test doubles:** `FakeProvider` (scripted per-task responses, can emit malformed JSON/refusals) and `ReplayProvider` (cassette keyed by `sha256(task, system, user, schema_name)`) so every agent test and `--estimate` dry run is network-free and deterministic. Sample-tier documents are untrusted: wrap in delimiters, constrain A1 output to enums (injected text cannot produce free-form actions), and A1 output never alters effort/action (see Open decisions).

### Pattern 11: Pydantic models are the source of truth for published schemas

- One registry `PUBLISHED = {"fact_sheet": FactSheet, "scorecard": Scorecard, "recommendation": Recommendation}`; `scripts/gen_schemas.py` writes `schemas/*.schema.json`; `make schemas` regenerates; **a pytest asserts `model_json_schema() == checked-in file`** (spec) and a second pytest asserts **compat against `schemas/archive/<name>-<released>.schema.json`**: every released property still exists with the same type/required-ness (add = minor, rename/remove/retype = major). Compat check is about 60 lines walking `properties`/`$defs`.
- Published models: `ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)` (available since pydantic 2.4) so "every key present, `null` where allowed" in the spec shows up as `required` in the generated schema. Generate with `mode="serialization"`, since consumers validate *outputs*.
- Shares rounded to 4 dp via an `AfterValidator(round4)` on a `Share = Annotated[float, Field(ge=0, le=1)]` type; datetimes `AwareDatetime` serialized as UTC `Z`; `schema_version: Literal["1.0"]`; one `canonical_bytes()` (sorted keys, fixed separators) used for every sha256 in the system.
- Add to v1.0 now (cheap now, a minor bump later): `privacy` block, `collect_limits` echo (`max_items_per_library`, `fill_rate_sample`, `permission_checks_per_library`, `sample_size`) so scoring can interpret `truncated`/`checked` without the config file.
- LLM wire models live in `agent_io.py`, are *not* in the registry, and have no compatibility promise.

### Pattern 12: Dependency inversion for progress and time

`core` emits `ProgressEvent`s to a `ProgressReporter` Protocol (`NullReporter` for `--quiet`/tests); `cli.py` supplies the Rich implementation. Time and sleep are injected (`Clock`) into graph client, scheduler and RunStore. Both exist to keep "core never imports cli/rich" true and to make retry/backoff/deadline tests instantaneous.

---

## Data Flow

### Request flow for `collect --csv`

```
cli ──Settings──▶ run.collect(inputs)
  run: RunStore.open(run-id) ; lock ; preflight (config valid, TokenProvider.get_token() once,
       interactive device-code happens HERE, before concurrency, never in a worker)
  parse CSV (pure) ──▶ resolve each row via GraphSession (sequential or small fan-out) ──▶ resolution.csv
  scheduler: TaskGroup, Semaphore(2 sites)
     per site: RunStore.transition(site, collect, running)
       collect_site(): C1 → C2 → C3 → C4 (+patterns) → C5 → C6 → C7 → samples → C9
          each Graph call: GraphSession ─▶ GraphClient._send:
              barrier wait → policy.check → token → httpx → retry/backoff → log(template,status,ms)
       FactSheet(model) ─▶ output.redact ─▶ atomic write sites/<slug>/fact_sheet.json
       RunStore.transition(site, collect, done|partial|failed, artifact, sha256)
  after all sites: collection_summary.csv (atomic), run.json final, exit code
```

### Key data flows

1. **C4 delta stream:** `GET /drives/{id}/root/delta?$select=...` -> async page iterator -> per-item `accumulator.add` -> (pages discarded) -> `finalize()` resolves folder paths from the folder map -> `LibraryInventory` + side data to `SiteContext`.
2. **Evidence:** `fact_sheet.json` (disk) -> `score()` -> `scorecard.json` (inputs as pointers) -> `EvidenceIndex(fact_sheet, scorecard)` -> prompt table -> LLM structured claims -> verifier resolves each `evidence_id` back to a value.
3. **Secrets/PII:** tokens exist only in `auth` and the `_send` header; never in models, logs, or run.json. Emails/paths exist in memory and in artifacts (Confidential), pass through `redact` at write; run.json stores config with secret-bearing keys absent (config only holds env-var *names*).
4. **Sample tier (Stage 5):** `samples` (C4 candidates: ids only) -> confirmation prompt -> `c8_content` (GET `/content` through a `allow_content=True` GraphClient) -> local extraction -> `sites/<slug>/samples/` (ephemeral/Confidential) -> A1 (untrusted-wrapped) -> `content_profile`. The agent package receives *extracted text via a `DocumentSource` protocol* and never imports Graph.

### State machine (per site, extensible)

```
resolve:  pending → resolved | failed(not_found|not_granted|no_access|ambiguous|name_requires_delegated)
collect:  pending → running → done | partial | failed          (spec: collecting/complete/partial/failed)
score:    pending → running → done | failed                    (failed only on rubric/schema error)
agent:    pending → running → done | needs_review | skipped(--no-llm) | failed(llm_unavailable)
report:   pending → running → done | failed
```

Terminal site status for exit codes: any `partial|failed|needs_review` -> exit 2; unable to start -> 1; SIGINT -> flush state, exit 130.

---

## Concurrency and Runtime Notes (Windows-first)

- **MSAL is synchronous:** call `acquire_token_silent` / `acquire_token_for_client` via `asyncio.to_thread`; cache the token in memory with expiry skew (about 5 min) and a single-flight `asyncio.Lock` so 8 concurrent requests trigger one refresh. Use `azure.identity.aio.ManagedIdentityCredential` for the managed identity mode.
- **Delegated token expiry mid-run** (refresh token revoked): raise `AuthExpired`; the run marks affected sites `failed(auth_expired)`, flushes state, exits 2; the user re-auths and `resume`s. Never prompt from inside a worker.
- **truststore:** `truststore.inject_into_ssl()` once at CLI start (`net.configure_tls()`), not at import. Injection covers `requests` (used by MSAL), `urllib3`, and httpx's default context; this is necessary because TLS inspection breaks MSAL's calls to `login.microsoftonline.com` exactly as it breaks Graph. Proxy: `httpx` and `requests` both honour `HTTPS_PROXY`/`NO_PROXY` (`trust_env=True`).
- **Ctrl+C:** `loop.add_signal_handler` is not supported on the Windows Proactor loop. Catch `KeyboardInterrupt` around `asyncio.run` (and `SIGBREAK` for Task Scheduler stop), cancel the TaskGroup, flush `RunStore` in `finally`, exit 130. Sites left in `running` are treated as "redo" on resume.
- **asyncio structure:** Python 3.12 `asyncio.TaskGroup`; cancellation-safe collectors (no swallowed `CancelledError`); per-site deadline via `asyncio.timeout`.
- **Paths:** `pathlib` only; slug <= 40 chars + 6-char hash; reject output roots inside OneDrive-synced folders in `doctor`; keep `\\?\` prefixes out of scope by keeping paths short.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Passing in-memory results between stages
**Why bad:** `rescore`/`resume`/golden tests then exercise different code than the live path; float rounding differs between memory and disk; stages cannot be re-run independently.
**Instead:** each stage loads its input artifact, verifies schema version/sha, and writes its own artifact.

### Anti-Pattern 2: Building `parentReference.path` assumptions into C4
**Why bad:** delta omits `path`; code written against `children` listings silently produces empty paths and a dead folder-pattern miner.
**Instead:** id-based folder map, resolve at `finalize()`.

### Anti-Pattern 3: Order-dependent sampling (`random.sample`, reservoir, `hash()`)
**Why bad:** breaks "same sample_candidates on re-run"; `hash()` is process-salted.
**Instead:** `sha256(seed ‖ item_id)` priority sampling.

### Anti-Pattern 4: One semaphore per site as the only throttle control
**Why bad:** throttling is app/tenant-wide; N sites each independently hammer into 429s and trip breakers.
**Instead:** shared barrier on the `GraphClient`, per-site breaker on the `GraphSession`.

### Anti-Pattern 5: Letting the LLM restate scored fields
**Why bad:** the model can "explain" an effort band differently from the scorecard; Core Value (deterministic, traceable) is lost.
**Instead:** inject effort/action/strategy from the scorecard into the report; the verifier asserts equality; schema for A3 has no field to carry them as claims the model authors.

### Anti-Pattern 6: Publishing LLM wire models as contracts, or reusing published models as LLM schemas
**Why bad:** strict-mode limits (100 props, depth 5, no min/max/pattern, no open maps) distort the contract; contract changes break prompts.
**Instead:** separate model tiers; lowering function between pydantic and wire schema.

### Anti-Pattern 7: Free-text logging and "debug dumps" of responses
**Why bad:** one `logger.debug(resp.text)` violates the privacy promise.
**Instead:** typed `LogEvent` schema (spec's fields only), scrub filter, and the log-capture test already specified. Fixtures are anonymised and checked by a scanner test (no real hostnames/emails).

### Anti-Pattern 8: Expression engine in `rubric.yaml`
**Why bad:** turns config into code, kills reviewability and the "defensible to Security" story.
**Instead:** closed rule vocabulary + first-match-wins predicates.

---

## Import-linter contracts (concrete)

```ini
[importlinter]
root_packages = recover_assess
include_external_packages = True

[importlinter:contract:layers]
name = Layered architecture
type = layers
layers =
    recover_assess.cli
    recover_assess.core.run
    recover_assess.core.agent | recover_assess.core.report | recover_assess.core.collect | recover_assess.core.score | recover_assess.core.resolve
    recover_assess.core.evidence | recover_assess.core.providers | recover_assess.core.graph | recover_assess.core.output
    recover_assess.core.auth
    recover_assess.core.net
    recover_assess.core.models | recover_assess.core.config | recover_assess.core.errors | recover_assess.core.log

[importlinter:contract:independent-stages]
name = Stage packages do not import each other
type = independence
modules = recover_assess.core.collect
          recover_assess.core.score
          recover_assess.core.agent
          recover_assess.core.report

[importlinter:contract:no-network-in-pure-stages]
name = score/agent/report/models never touch network libs
type = forbidden
source_modules = recover_assess.core.score
                 recover_assess.core.agent
                 recover_assess.core.report
                 recover_assess.core.models
                 recover_assess.core.evidence
forbidden_modules = httpx
                    requests
                    msal
                    azure
                    openai
                    anthropic
                    boto3

[importlinter:contract:agent-has-no-graph]
name = Agent cannot reach Microsoft 365
type = forbidden
source_modules = recover_assess.core.agent
forbidden_modules = recover_assess.core.graph
                    recover_assess.core.collect

[importlinter:contract:llm-sdks-only-in-providers]
name = LLM SDKs only in providers
type = forbidden
source_modules = recover_assess.core.graph
                 recover_assess.core.collect
                 recover_assess.core.score
                 recover_assess.core.agent
                 recover_assess.core.report
                 recover_assess.core.run
forbidden_modules = openai
                    anthropic
                    boto3

[importlinter:contract:cli-libs-only-in-cli]
name = typer and rich only in cli
type = forbidden
source_modules = recover_assess.core
forbidden_modules = typer
                    rich
```

Plus: an AST test that `httpx` / `requests` are imported only from `core/net.py`, `core/graph.py`, `core/providers/*`, and nothing outside `graph.py` calls a non-GET verb (belt and braces for the central trust promise).

Note: the `collect -> score -> agent` independence contract implies the scorer/agent/report consume **published models and files only**. Verify the layers contract syntax against the installed import-linter version when scaffolding (the `|` sibling syntax and `include_external_packages` behaviour are the parts to confirm).

---

## Spec corrections found during research

| # | Spec text | Finding | Action |
|---|-----------|---------|--------|
| 1 | C4: per-file "path relative to the library root, depth" from `delta ... parentReference` | Microsoft Learn (driveItem-delta): delta's `parentReference` **will not include `path`**; "when using delta you should always track items by id". Ordering parent-before-child is not documented. | Id-based folder map + path resolution at `finalize()` (Pattern 3). HIGH. |
| 2 | C4: "Items with `deleted` are ignored" (only) | Same page: "the same item may appear more than once in a delta feed ... use the last occurrence". Streaming running totals would double count. | Dedupe by id (first-wins, documented), count repeats. HIGH. |
| 3 | Sample candidates: "seed derived from the site ID so re-runs pick the same files" | Seeding alone does not give determinism if input order varies (delta order is not stable). | Hash-priority sampling (Pattern 3). HIGH (logic). |
| 4 | Fact sheet v1.0 example | No `privacy` block (path/contributor mode) and no echo of collection limits. Needed by scoring/agent/reports. | Add to v1.0 before first release. MEDIUM-HIGH. |
| 5 | `$batch` of columns/permissions | Sub-responses can carry `@odata.nextLink`; spec only discusses paging for plain GETs. | Batch helper falls back to paged GETs. HIGH. |
| 6 | httpx uses `truststore` | MSAL uses `requests`; it needs the same trust store or login fails behind TLS inspection. | `truststore.inject_into_ssl()` in `net.configure_tls()`. MEDIUM-HIGH. |
| 7 | Dependency list | Reports need an HTML templating engine; sample tier needs text extractors (docx/pptx/xlsx/pdf/msg). None are in the approved list. | Raise as explicit dependency decisions (jinja2; python-docx/openpyxl/python-pptx/pypdf/extract-msg or equivalents) before Stages 3 and 5. |

---

## Scalability Considerations

The load profile is "few sites, huge inventories", not "many users".

| Concern | 1 site (pilot) | 25-500 sites (batch) | Very large library |
|---------|----------------|----------------------|--------------------|
| Memory | Accumulator state well under 10 MB at the 50k cap | Bounded per site, freed after `finalize()`; 2 sites at once | Raising the cap is safe for aggregates; seen-id set and hash counter grow O(n); beyond about 1M items switch seen-set to a Bloom filter/xxhash and accept approximate dedupe (not needed for v1) |
| Throughput | Sequential delta paging per drive; parallelism only across libraries | 2 sites x 4 in-flight; shared throttle barrier; expect 429 storms to dominate wall time | `max_items_per_library` + `truncated` is the pressure valve; per-site wall-clock limit -> `partial` |
| Throttling | Honour Retry-After | Barrier + per-site breaker; `--concurrency` tunable | Prefer fewer, bigger `$select`ed pages; `$batch` for small GET fan-out |
| `run.json` size/IO | Trivial | Coalesced atomic writes, about 200 KB at 500 sites | Same; sharded per-site state files only if profiling shows AV-induced stalls |
| LLM cost/time | 4 calls/site | `--estimate` (tokens from evidence table size x tasks), per-site deadline, bounded LLM concurrency (separate semaphore, default 2) | n/a |

---

## Integration Points

### External services

| Service | Pattern | Notes |
|---------|---------|-------|
| Microsoft Graph v1.0 | `GraphClient` choke point, GET + `$batch`-of-GETs | Base URL fixed; v1.0 only; each endpoint needs a Microsoft Learn URL comment (spec rule) |
| Entra ID (login.microsoftonline.com) | `TokenProvider` x3 | Device code must complete in preflight; encrypted MSAL cache (msal-extensions/DPAPI) |
| Azure OpenAI via the corporate LLM gateway | `providers/azure_openai.py` using the `openai` SDK with custom `base_url` + `api-key` header + deployment in path | Non-streaming; deployment-scoped keys; strict-schema support unverified; see the user's local gateway-troubleshooting skill (not in repo) |
| Anthropic via the corporate Anthropic proxy (Bedrock) | `providers/anthropic_bedrock.py` stub raising `ProviderNotConfigured` | When filled: `/model/{model}/messages`, `X-Api-Key`, `Accept: application/json`, no `temperature/top_p/top_k`, handle `guardrail_intervened`, strict-tools for schema (see the user's local Anthropic-proxy skill, not in repo) |
| SAM export | CSV join (C9), no network | Column names unresolved (open question) |

### Internal boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| collect -> score | `fact_sheet.json` (file, schema v1.0) | Scorer must work from golden fact sheets alone, so it can be built before live collection is finished |
| score -> agent | `scorecard.json` + `EvidenceIndex` | Agent receives scored fields as inputs, cannot change them |
| agent -> report | `recommendation.json` (verified plan, `needs_review` flag) | Report renders without it when `--no-llm` or `needs_review` |
| run -> stages | `Stage` protocol + fingerprints | Adding a stage = register + fingerprint rule |
| skill -> tool | CLI + exit codes + `run.json`/`portfolio.csv` (read-only) | Provide `--json` summary on stdout for the Claude Code skill |

---

## Suggested Build Order (dependencies)

### Dependency graph

```
errors/log/config/models(fact_sheet)  ──┬──▶ net ─▶ auth ─▶ graph(+fake_graph) ─▶ resolve/inputs ─▶ collectors C1..C9 ─▶ run/ (store, stages, resume)
                                        │                                                                  │
                                        ├──▶ evidence ─▶ score(+rubric, calibration harness) ─────────────┤
                                        │                         │                                         ▼
                                        │                         └───────────────▶ report (deterministic) ─▶ [FIRST USABLE PRODUCT: --no-llm]
                                        └──▶ providers(base, structured, fake, azure) ─▶ agent A2-A4 ─▶ [sample tier: C8 + extract + A1]
                                                                                              │
                                                              batch hardening (rescore/report/--estimate/time limits) ─▶ skill ─▶ pilot calibration
```

Parallelisable once `FactSheet` v1.0 and the three synthetic golden fact sheets exist: **scoring + evidence + reports** (depends on the contract only) and **providers + StructuredCaller** (depends on nothing in collect). The corporate LLM gateway strict-schema spike is independent of everything and should start on day one because it depends on an external key/deployment.

### Order refinements to the Step 1 task list (spec tasks 1-9 stay; changes marked)

1. **Scaffold (spec task 1) + contract first.** Add: `errors.py`, `log.py` (typed events + scrub filter), full `FactSheet` model (complete v1.0 incl. `privacy`, `collect_limits`) and `gen_schemas.py` + drift test, `output.py` atomic writer, import-linter contracts above. *Why:* every later task codes against the model; schema authored once, deliberately, and drift/compat tests exist from commit one. *Also start:* corporate LLM gateway strict-schema spike (outside the code path).
2. **Auth (task 2)** unchanged, plus `net.py` (truststore, client factory) here, since `doctor` needs it. Demo: `doctor` prints token scopes/roles behind the proxy.
3. **Graph client (task 3)** + **`tests/fakes/fake_graph.py`** (httpx `MockTransport` serving fixtures, delta paging, `$batch`, injectable 429s, request recorder). Build the fake here, not later: collector tests all need it. Deliver: policy/allow-list tests (every other verb, batch with non-GET, nextLink host check, `/content` blocked at metadata tier), paging, batch re-queue, barrier, breaker, log-capture test, injected `Clock`.
4. **Inputs & resolution (task 4)**, unchanged. Demo: `collect --csv ... --validate-only`; `grants plan`.
5. **C1-C3 (task 5)**. Demo: partial fact sheet validating against the schema.
6. **C4 + patterns (task 6)** is the riskiest collector: accumulator + differential/property tests + memory test + truncation + delta repeat handling + id-based path resolution. *Run a live read-only smoke on one real library early here* to validate assumption #1/#2 (delta shape on SharePoint) before building C5-C7 on `SiteContext` side data.
7. **C5-C7, samples, C9 (task 7)**: seeded priority sampling shared by C6 and samples; compare-to-root logic.
8. **Run orchestration (task 8)**: `RunStore` (atomic, coalesced, locked), Stage registry with fingerprints (only `resolve`, `collect` registered), `resume`, summary CSV, progress reporter, exit codes, path modes via `redact`, `prune`. Design `run.json` per-stage from the start.
9. **Hardening (task 9)**: golden integration tests for tidy/sprawl/orphan, README (Task Scheduler, managed identity), Windows Server dry run, kill-and-resume acceptance test.

Then (parent milestones M2-M6):

10. **Scoring + evidence index** (M2 part 1): `Rubric` model, closed rule vocabulary, scorecard with pointer-recorded inputs, truncation/partial handling, `calibrate` command comparing scorecards to `calibration/expected.csv` (pilot metric 8/10 effort, 9/10 action). Start from golden fact sheets; can overlap with Steps 7-9.
11. **Reports + portfolio** (M2 part 2): deterministic `report.md/html`, `portfolio.csv/html`, neutral theme, `--no-llm`. **Milestone: first complete, LLM-free product (Core Value delivered).** Needs the jinja2 decision.
12. **Providers** (M3): `LLMProvider`, `StructuredCaller`, wire-schema lowering + strict-limit lint, Azure/gateway adapter with capability flag, Bedrock stub, Fake/Replay. (Can start earlier in parallel; listed here because nothing consumes it until agent.)
13. **Agent, metadata tier** (M4 part 1): A2 schema proposal, A3 plan, A4 verifier (code checks then model check), `needs_review`, `--estimate`.
14. **Sample tier** (M4 part 2): `allow_content=True` client tier, C8 download (302 hop handling), extraction deps decision, untrusted wrapper, confirmation prompt, redaction hook, A1.
15. **Batch hardening** (M5): `rescore`, `report` commands, stage fingerprints for agent/report, time limits, progress view polish, exit-code audit across stages.
16. **Claude Code skill** (M6) then **pilot calibration** and rubric tuning on the real pilot sites (calibration harness already in place from step 10).

---

## Open decisions to carry into roadmap/phase research

| Decision | Recommendation | Where it bites |
|----------|---------------|----------------|
| Does A1 (sample-tier classification) influence effort/action? | **No in v1.** It adds a separate `content_profile` evidence block that A2/A3 may cite; scorecard is metadata-only, so `--no-llm` score is complete and deterministic. Revisit only if calibration shows a systematic miss. | Rubric design; pipeline order (score precedes A1 in the stated flow) |
| Corporate LLM gateway strict `json_schema` support | Spike now; build `capabilities.strict_json_schema` fallback regardless | Provider phase; repair-path weight |
| Delta repeat semantics (first-wins vs last-wins) | First-wins + counter; revisit if live smoke shows material repeats | C4 |
| Per-site state files vs single `run.json` | Single `run.json`, coalesced; revisit only on measured stalls | Run orchestration |
| HTML templating / text extraction dependencies | Ask user: jinja2 (reports); extractor libraries (sample tier) | Stages 3 and 5 |
| `--include-subsites` | Out of Step 1 (spec); if pilot needs it, a subsite is just another site in the same pipeline (resolve -> its own fact sheet), no architecture change | Resolve/inputs |

## Sources

- Step 1 Collector Build Spec (C:/SPCollector/Recover Assessment Collector Build Spec (Step 1).md) and PROJECT.md (project source of truth). HIGH.
- Microsoft Learn, JSON batching (max 20 requests per batch; unique ids; per-sub-request status and 429; out-of-order responses; `dependsOn`): https://learn.microsoft.com/en-us/graph/json-batching . HIGH (fetched 2026-11-15).
- Microsoft Learn, driveItem delta (no `parentReference.path`; track by id; item may appear more than once, use last; `$select`/`$top` supported; nextLink/deltaLink; 410 resync): https://learn.microsoft.com/en-us/graph/api/driveitem-delta . HIGH (fetched 2026-11-15).
- Microsoft Learn, Azure OpenAI structured outputs (strict mode keyword limits, 100 properties/5 levels, all-required, root not `anyOf`, refusal handling, supported models/API versions): https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/structured-outputs . HIGH (page dated 2026-08-24).
- Pydantic config docs (`json_schema_serialization_defaults_required`, new in v2.4): https://pydantic.dev/docs/validation/latest/api/pydantic/config/ . HIGH.
- The user's local gateway-troubleshooting skill, not in repo (corporate LLM gateway Azure-OpenAI shape: deployment in path, `api-key` header, deployment-scoped keys, empty-200 on wrong route) and the user's local Anthropic-proxy skill, not in repo (Bedrock proxy shape, strict-tools mode, guardrail handling). MEDIUM-HIGH (internal, validated against live deployments per the skills; strict `json_schema` through the corporate LLM gateway not covered).
- Engineering judgement, not externally verified: Windows `os.replace` retry behaviour under AV/indexer locks; `truststore.inject_into_ssl()` coverage of MSAL's `requests` calls; import-linter contract syntax details; Ctrl+C handling on the Windows asyncio Proactor loop. MEDIUM. Each should be confirmed by a small test in the scaffold/auth/orchestration tasks.
