<!-- GSD:project-start source:PROJECT.md -->

## Project

**recover-assess**

`recover-assess` is a read-only Python CLI that takes one named SharePoint site (or a CSV of sites), collects evidence from Microsoft Graph, and returns a Recover-track assessment per site: an effort rating (Low / Medium / High) calculated in code, a recommended action (Enrich / Archive / Restrict / Delete), the best backfill strategy, a proposed starter schema, and a plain-English plan written by an LLM agent and checked by a verifier. It is the engine behind **Module 1 (AI-readiness assessment)** of the AI-Ready SharePoint Framework & Enablement Playbook: first piloted at the pilot organisation, then packaged as a portable asset for other companies.

**Core Value:** Every site's effort rating, action and strategy is **deterministic, traceable to evidence in the fact sheet, and produced without ever writing to Microsoft 365**. If the LLM layer fails, the Collector + scoring must still give a credible, defensible triage.

### Constraints

- **Security**: Read-only against M365 — only GET and `POST /$batch` of GETs, enforced in `core/graph.py` and tested — this is the tool's central trust promise
- **Privacy**: Metadata tier by default; no file content leaves the tenant unless the sample tier is explicitly chosen and confirmed; run folders are Confidential
- **Portability / IP**: No pilot-organisation data, names, endpoints or pilot inputs in the repo; the pilot organisation's theme and gateway config are external config — required to take the playbook to other companies
- **Platform**: Windows first (Win 11, Server 2019+), also macOS/Linux; pathlib only, short output paths, `truststore`, `HTTPS_PROXY`/`NO_PROXY`
- **Tech stack**: Python 3.12 with `uv`; msal, msal-extensions, azure-identity, httpx2 (replaces frozen httpx; shared with the openai SDK), tenacity, truststore, pydantic v2, pydantic-settings, pyyaml, jsonschema, typer, rich, jinja2; openai SDK; ruff, mypy strict, import-linter, pytest, pytest-asyncio, httpx2 MockTransport (replaces respx), hypothesis. Approved if needed: msal[broker] (only if Conditional Access blocks device code and browser); extraction libs + defusedxml for the v2 sample tier. Ask before adding other dependencies
- **Architecture**: `core` never imports `cli`; only `core/providers` imports LLM SDKs; collectors are async functions returning pydantic models; inventories are streamed, never held in memory
- **Contract**: `fact_sheet.json` schema v1.0 is the contract with later stages — add = minor, rename/remove = major; schema generated from pydantic models and kept in sync with golden files
- **Model route**: Azure OpenAI via the corporate LLM gateway is the only approved LLM route for now

<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

## Headline Findings (read these first)

### 1. `httpx` has been superseded by `httpx2`. The spec's "httpx + respx" pairing no longer works cleanly. (HIGH)

- `httpx` 0.28.1 was last released **2024-12-06**. Only `1.0.dev*` pre-releases have appeared since, the latest in Aug 2026.
- Pydantic took over stewardship as **`httpx2`** (first release May 2026, now **2.16.0**, 22 releases in 6 months). Migration is "swap the dependency, swap the import" (`import httpx2`).
- **`openai` 3.x (since 3.0.0, 2026-08-12) and `anthropic` 2.x now depend on `httpx2`, not `httpx`.** `httpx` is no longer installed transitively. `AzureOpenAI` is typed `httpx2.Client`. If `core/graph.py` used legacy `httpx` it would be a second, separate HTTP stack in the same process, with different exception classes and a different TLS default (certifi vs OS store).
- `httpx2` verifies TLS against the **OS trust store via `truststore` by default** (`SSL_CERT_FILE` / `SSL_CERT_DIR` are honoured first). That is exactly what the spec wanted `truststore` for, so the Graph client and the OpenAI SDK get corporate-TLS-inspection support with no extra code.
- **`respx` cannot mock `httpx2`.** respx 0.23.1 (Apr 2026) patches `httpx` / `httpcore` only. The upstream PRs for httpx2 support (#334 open, #335 closed) are unmerged and unreleased. `vcrpy` (hence `pytest-recording`) has the same gap.
- **Recommendation:** use `httpx2` for the Graph client and all outbound HTTP. Test with the built-in `httpx2.MockTransport`, injected through a client factory. This needs no extra dependency. It is a substitution for two spec lines, so **it needs explicit sign-off** under the "ask before adding other dependencies" rule.
- **Fallback if sign-off is refused:** pin `httpx==0.28.1` + `respx==0.23.1` for Graph only and accept two HTTP stacks. Not recommended: legacy `httpx` is effectively unmaintained for security fixes.

### 2. Azure OpenAI: use the plain `OpenAI` client with Chat Completions and strict `json_schema`, not `AzureOpenAI` or Responses. (MEDIUM-HIGH)

- The corporate LLM gateway's ingress shape (from the user's local gateway-troubleshooting skill, not in repo) is `…/coreapi/openai/v1/deployments/<deployment>/chat/completions` with an `api-key` header. That is neither the classic Azure shape (`/openai/deployments/{d}/…?api-version=`) that `AzureOpenAI` builds, nor the Azure "v1" shape (`/openai/v1/…`). `AzureOpenAI` would build the wrong URL.
- Microsoft's own direction is the **v1 API**: plain `OpenAI(base_url=".../openai/v1/", api_key=<key or token-provider callable>)`, no `api-version`. The `openai` 3.x client accepts `api_key: str | Callable[[], str]`, so Entra tokens refresh automatically.
- One provider class therefore covers both the corporate LLM gateway and any normal Azure resource at a portability target. Only `base_url`, auth header and `model` differ.
- Strict structured outputs are supported on **both** Chat Completions (`response_format`) and Responses (`text.format`) for the gpt-4o / 4.1 / 5 / o-series deployments. Chat Completions is "supported indefinitely" per the SDK README, and it is the only route evidenced for the corporate LLM gateway. The task is single-shot, stateless JSON generation, so Responses buys nothing.
- Azure's strict-schema subset is narrower than pydantic's output (details under "LLM structured output" below). Plan a schema "strictifier" and keep the full schema for local `jsonschema` validation.

### 3. Anthropic-on-Bedrock now has two endpoints, and neither SDK client fits the corporate Anthropic proxy (Apigee-fronted). (HIGH on facts, MEDIUM on fit)

- AWS now has **`bedrock-runtime`** (InvokeModel/Converse, `AnthropicBedrock` client, `global./us./eu.` inference-profile IDs) and **`bedrock-mantle`** (native Messages API at `/anthropic/v1/messages`, **`AnthropicBedrockMantle`** client, IDs like `anthropic.claude-sonnet-5-5`, SigV4 or bearer token).
- `anthropic` 2.x sends API version `2026-10-21`, which Bedrock rejects (HTTP 400) for models numbered 4.6 or lower. Anyone on Sonnet 4.5 (which the corporate Anthropic proxy requires, `eu.anthropic.claude-sonnet-4-5-…`) must pin `anthropic[bedrock]<2`.
- The corporate Anthropic proxy (`POST …/coreapi/llm/anthropic/v1/model/{model}/messages`, `X-Api-Key`, `Accept: application/json`, `anthropic_version: bedrock-2023-05-31`) matches **neither** SDK client. The pilot organisation's route needs a thin hand-written `httpx2` adapter (per the user's local Anthropic-proxy skill, not in repo).
- **The stub needs zero new dependencies today.** Decision tree under "Anthropic / Bedrock provider stub" below.

### 4. Several pinned tools had major-version changes since the spec's assumptions. (HIGH)

| Tool | Now | What changed | Action |
|------|-----|--------------|--------|
| `mypy` | 2.4.1 | 2.0 (May 2026): `--local-partial-types` and `--strict-bytes` now default; parallel checking | Pin; budget one pass of fixes at scaffold |
| `ruff` | 0.17.5 | 0.16 enabled **413 rules by default (was 59), even alongside `select`/`extend-select`** | Pin; set an explicit `select`; check output on every bump |
| `typer` | 0.29.1 | 0.29.0 (2026-11-09, 6 days old) moved parameter validation to Pydantic; `click_type` removed; stricter defaults | Pin `~=0.29.1`; expect churn |
| `pypdf` | 7.1.0 | 7.0 (2026-11-06) is a security-heavy major; four security fixes in the last two weeks alone | Pin `>=7.1,<8` and track releases |
| `openai` | 3.51.0 | 3.0 = httpx2 default; very frequent minors (~daily) | Pin `~=3.51`; the interface boundary insulates us |
| `rich` | 15.0.0 | Major bump (Apr 2026) | Fine; Typer pulls it |

## Recommended Stack

### Core Platform

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Python | **3.12.x** (`.python-version` = `3.12`; `requires-python = ">=3.12"`) | Runtime | Spec-pinned. Every dependency supports 3.12 (the strictest floor is `pydantic-settings` / `hypothesis` / `import-linter` at 3.11). 3.12 is in security-only support to Oct 2028, which is fine for a pilot tool. Test 3.12 only; treat 3.13 as a free bonus. | HIGH |
| uv | **0.13.8** | Env, lockfile, Python install, `uv tool install` for end users | Spec-pinned. No admin rights needed. **Corporate TLS caveat:** uv ships its own Mozilla roots. Set `UV_SYSTEM_CERTS=true` (older docs call it `UV_NATIVE_TLS`) on proxied machines, or `uv python install` and `uv sync` will fail behind TLS inspection. | HIGH |
| uv_build | latest (declared in `[build-system]`) | Build backend, `src/` layout | Same vendor, zero config, fast. Console script: `recover-assess = "recover_assess.cli:app"`. | MEDIUM |

### HTTP, Auth and TLS

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| **httpx2** | **~=2.16.0** | Graph client (`core/graph.py`), LLM gateway adapters. Do **not** install the `http2` extra. | Maintained successor to `httpx` (see Headline 1). Same API. HTTP/2 stays off because `h2` is not installed and `http2=False` is the default. Honours `HTTPS_PROXY` / `NO_PROXY` (2.14+ also matches CIDR ranges in `NO_PROXY`). OS trust store by default. Requires Python 3.11+. | HIGH (facts), MEDIUM (project age: 6 months) |
| tenacity | **~=9.2.1** | Graph request retry: honour `Retry-After`, else exponential backoff with full jitter; `stop_any(stop_after_attempt(6), stop_after_delay(300))` | Spec-pinned; `AsyncRetrying` and custom `wait` callables fit. Does **not** cover `$batch` partial-throttle re-queueing or the 20-throttles-in-60s circuit breaker. Hand-write those in `graph.py`. Do not layer tenacity on LLM calls; the OpenAI SDK's own retries are enough. | HIGH |
| truststore | **~=0.10.5** | `truststore.inject_into_ssl()` once at CLI start-up | `httpx2` already uses truststore internally (and depends on it). The explicit call is still **required** for the `requests`-based libraries (`msal`, `azure-identity` via `azure-core`) so device-code and token calls work behind TLS inspection. Call it before those libraries make a connection. App-level only, never inside library code. | HIGH |
| msal | **~=1.39.0** | `delegated` (`PublicClientApplication`) and `app_certificate` (`ConfidentialClientApplication`) | Spec-pinned; current. Blocking API, so wrap calls in `asyncio.to_thread`. Also contains `ManagedIdentityClient` (see note below). | HIGH |
| msal-extensions | **==1.3.1** | DPAPI-encrypted token cache (`build_encrypted_persistence` + `PersistedTokenCache`) | Still the latest release (Mar 2025). Windows DPAPI is done with ctypes. No `pywin32` needed. `portalocker` is an optional extra because it falls back to a built-in file lock. **Never** use the sample's `fallback_to_plaintext=True`; fail closed. The upstream `dev` branch has an unreleased plaintext file-permission fix (Oct/Nov 2026), so rely on DPAPI, not on file-permission hardening. | HIGH |
| azure-identity | **~=1.27.0** | `ManagedIdentityCredential` for the Azure VM path | Spec-pinned; current. Use the **sync** credential and call `get_token("https://graph.microsoft.com/.default")` through `asyncio.to_thread`. Avoid `azure.identity.aio` (drags in `aiohttp`). | HIGH |
- **IMDS and proxies:** on an Azure VM with `HTTP_PROXY` set, the managed-identity metadata call (`http://169.254.169.254`) goes to the proxy and fails. `doctor` must check that `NO_PROXY` contains `169.254.169.254` and print the fix. (MEDIUM: well-known Azure gotcha, not re-verified against 1.27.)
- **msal vs azure-identity for managed identity:** `msal` 1.39 already ships `ManagedIdentityClient`. It could replace `azure-identity` and drop `azure-core` plus its transitive deps. The spec lists `azure-identity`, so keep it. Flag this as an optional simplification for a later "trim dependencies" decision. (MEDIUM)
- **Delegated sign-in risk:** many enterprise tenants block the device-code flow through a Conditional Access policy. The spec makes device code the default and browser the flag. Make `--browser` (loopback `http://localhost` redirect URI) a first-class, tested path, and register that redirect URI on the pilot app. If both fail on a compliant-device CA policy, the fallback is the Windows broker (`msal[broker]`, `pymsalruntime` 0.20). That is an extra dependency, so ask first. (MEDIUM, needs an early pilot smoke test.)

### Configuration and Contracts

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pydantic | **~=2.14.3** | Config models, collector return types, `fact_sheet` models, schema generation | Spec-pinned. Pin the minor: the checked-in `fact_sheet.schema.json` is generated by `model_json_schema()`, and its text can change between pydantic minors. Treat schema regeneration as an explicit commit, not a side effect of `uv lock --upgrade`. | HIGH |
| pydantic-settings | **~=2.16.3**, with the `yaml` extra | Layered config: defaults, YAML, env, CLI | Spec-pinned. `pydantic-settings[yaml]` pulls `pyyaml`. See config notes below. | HIGH |
| pyyaml | **~=6.0.3** | `rubric.yaml`, `builtin_columns.yaml`, `file_types.yaml`, `patterns.yaml`, `graph_allowlist.yaml` | Use `yaml.safe_load` only. Never `yaml.load`. | HIGH |
| jsonschema | **~=4.26.0** | Local validation of LLM output and of fact sheets against `schemas/*.json` | Use `Draft202012Validator`, leave format checking off. Keep the **full** schema for validation; send only the strictified subset to the model. | HIGH |
- Source order is decided by the tuple returned from `settings_customise_sources`, first item wins. Use `(init_settings, env_settings, YamlConfigSettingsSource(settings_cls), )` so that CLI flags (passed as init kwargs) beat env, which beats YAML, which beats model defaults. This matches the spec's order.
- Set `env_prefix="RECOVER_ASSESS__"`, `env_nested_delimiter="__"` to get the spec's `RECOVER_ASSESS__COLLECT__SAMPLE_SIZE`.
- **`extra="forbid"` does not catch env-var typos at the top level.** Environment variables that match no field are silently ignored, so `RECOVER_ASSESS__COLECT__SAMPLE_SIZE` does nothing. Unknown keys inside a matched nested model do raise. The spec says "unknown keys are an error", so add a small start-up check that scans `os.environ` for the `RECOVER_ASSESS__` prefix and diffs it against the model's known paths.
- Client secrets: because the auth model forbids extras, catch a configured `client_secret` key in a `model_validator(mode="before")` to emit the spec's "use certificate or managed identity" message instead of a generic extra-forbidden error.

### CLI and Output

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| typer | **~=0.29.1** | CLI (`doctor`, `collect`, `resume`, `grants plan`, `prune`, later `assess`) | Spec-pinned. Commands are sync; call `asyncio.run(...)` inside. Construct with `typer.Typer(pretty_exceptions_show_locals=False)`. **The default rich traceback prints local variables, which can include bearer tokens.** That would break the "no tokens in logs" promise. Exit codes: 0 / 1 / 2 / 130 as per spec. | HIGH (version), MEDIUM (0.29 is brand new) |
| rich | **~=15.0.0** | Progress view, tables, `--quiet` off-switch | Spec-pinned. On Windows, always write files as UTF-8 explicitly (`encoding="utf-8"`); only the console is cp1252-risky. | HIGH |
| jinja2 | **~=3.1.6** | `report.html`, `report.md`, `portfolio.html` | Use `Environment(autoescape=True, undefined=StrictUndefined)`. File and folder names from SharePoint are untrusted strings. For the `.md` report use a separate environment with explicit escaping of pipes and backticks. | HIGH |

### LLM Providers

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| **openai** | **~=3.51.0** | `AzureOpenAIProvider` (only imported inside `core/providers/`) | Use `OpenAI` (not `AzureOpenAI`) with Chat Completions and `response_format={"type":"json_schema",…,"strict":True}`. Details below. | HIGH (version), MEDIUM (gateway behaviour) |
| anthropic | **not installed in v1** (latest 2.8.0) | Future Bedrock provider | See "Anthropic / Bedrock provider stub". Reserve an empty optional extra `bedrock`. | HIGH |

### Text Extraction (sample tier only)

| Library | Version | Purpose | Why / caveat | Confidence |
|---------|---------|---------|--------------|------------|
| python-docx | **~=1.2.0** | `.docx` text | Last release Jun 2025; stable. | HIGH |
| python-pptx | **~=1.0.2** | `.pptx` text | **Dormant:** last release Aug 2024, last commit Aug 2024. Still works; plan an "if it breaks, replace" note. Pulls `Pillow`, `XlsxWriter`, `lxml`. | MEDIUM |
| openpyxl | **~=3.1.5** | `.xlsx` text (`read_only=True`, `data_only=True`) | Jun 2024 release; stable. Does not defend against XML entity-expansion attacks. Consider `defusedxml` (**dependency, ask first**) because the sample tier reads untrusted files. | MEDIUM |
| pypdf | **>=7.1,<8** | `.pdf` text | Very active, many recent security fixes for malformed PDFs. Keep it current and treat every PDF as hostile. | HIGH |
| extract-msg | **~=0.58.2** | `.msg` text | Active (Nov 2026). Pins `olefile==0.47`; keep an eye on resolver conflicts. Do not use the `image` extra (`Pillow<10`). | MEDIUM |

### Testing and Quality

| Tool | Version | Purpose | Why / caveat | Confidence |
|------|---------|---------|--------------|------------|
| pytest | **~=9.2.0** | Runner | | HIGH |
| pytest-asyncio | **~=1.5.0** | Async tests | Set `asyncio_mode = "auto"`. | HIGH |
| **httpx2.MockTransport** | (part of httpx2) | Fake Graph server for the allow-list, paging, 429, `$batch`, circuit-breaker and no-secrets-in-logs tests | **Replaces respx.** Build the `AsyncClient` through one factory that accepts a `transport=` argument; tests pass a `MockTransport(handler)` whose handler is a fixture router keyed on method plus path template. The allow-list test asserts the handler was never called. | HIGH |
| respx | 0.23.1 | **Do not use for httpx2** | Patches `httpx`/`httpcore` only; no released httpx2 support. | HIGH |
| pytest-httpx2 | 1.0.0 (optional) | Only if router-style `respx` ergonomics are wanted | Third-party, 1.0.0 from May 2026, a small plugin that registers a `httpcore2` mocker with respx. It would pull legacy `httpx` into the **dev** group. Do not adopt unless MockTransport proves too clumsy. | LOW-MEDIUM |
| hypothesis | **~=6.170** | Property tests for `normalize`, pattern classifier, percentiles, duplicate rate | Needs Python 3.11+. | HIGH |
| pytest-recording / vcrpy | 0.15.0 / 9.4.2 | **Do not use** | vcrpy's patcher targets `httpx`, not `httpx2`. It is also not in the spec's dependency list. Cassettes of real Graph traffic risk committing tenant IDs, names and tokens, which violates the "no pilot-organisation data in the repo" constraint. Use hand-anonymised JSON fixtures, as the spec already plans. | HIGH |
| ruff | **~=0.17.5** | Lint and format | Explicit `select`, for example `["E","F","I","B","UP","S","SIM","RUF","ASYNC","PTH","TID"]`. `PTH` enforces the "pathlib only" rule. `S` (bandit) flags `yaml.load`, `verify=False`, `assert` misuse. | HIGH |
| mypy | **~=2.4.1** | `strict = true`, `plugins = ["pydantic.mypy"]`, `python_version = "3.12"` | `msal` / `msal_extensions` / `jsonschema` are loosely typed: add `[[tool.mypy.overrides]] ignore_missing_imports` for them as needed. Dev stubs: `types-pyyaml`, `types-jsonschema`. Verify the pydantic mypy plugin works on mypy 2.4 in the scaffold task. | HIGH (versions), MEDIUM (plugin compat) |
| import-linter | **~=2.16** | Architecture contracts | Needs Python 3.11+. Contracts below. | HIGH |

## LLM Structured Output: Design Notes (Azure OpenAI via the corporate gateway)

| Factor | Chat Completions | Responses |
|--------|------------------|-----------|
| Evidenced on the corporate LLM gateway | Yes (`/deployments/<d>/chat/completions`) | No evidence |
| Strict `json_schema` on Azure | Yes (`response_format`) | Yes (`text.format`) |
| Microsoft's recommendation for new Azure code | Supported, v1 API still serves it | Preferred for Azure OpenAI models |
| Needed features (state, built-in tools, reasoning items) | n/a | Not needed: one-shot JSON generation |
| SDK status | "Supported indefinitely" (README) | Primary API |

# gateway mode (gateway-style): deployment in the URL path, api-key header

# azure v1 mode (portable): standard Azure resource, key or Entra token provider

# only if a classic ?api-version= endpoint is forced on us: AzureOpenAI(azure_endpoint=..., api_version=...)

- Non-streaming (`stream=False`). Batch JSON does not need it, and it sidesteps the gateway's "empty streamed tokens" quirk documented in the skill.
- Use `chat.completions.create(...)` with an explicit schema dict. Do not use `.parse()` or `beta.*`: we validate locally with `jsonschema` and need control of the exact wire schema.
- For gpt-5-family deployments (the gateway's model catalogue lists gpt-5, -mini, -nano): reasoning models. Send `max_completion_tokens` (not `max_tokens`), omit `temperature` / `top_p`, and optionally `reasoning_effort`. Do not depend on `seed` for determinism. The deterministic score is computed in code; the LLM only explains.
- Inspect `message.refusal` and `finish_reason == "length"` before parsing. Treat either as a repair/`needs_review` trigger.

| Rule | Consequence for us |
|------|--------------------|
| Every property must be in `required`; optional = union with `null` | Strictifier adds all keys to `required` and rewrites optionals as `["type","null"]` |
| `additionalProperties: false` on every object | Strictifier sets it recursively |
| Unsupported: `minLength`, `maxLength`, `pattern`, `format`, `minimum`, `maximum`, `multipleOf`, `minItems`, `maxItems`, `uniqueItems`, `patternProperties`, `minProperties`, `maxProperties`, `contains`… | Strip from the **wire** schema; **keep** in the canonical schema that `jsonschema` validates locally. Pydantic `Field(max_length=…)` / `ge=` emit exactly these keywords |
| Max 100 properties total, 5 levels of nesting; root may not be `anyOf` | Add a unit test that fails the build if any LLM schema exceeds the budget |
| `$defs` / `$ref` and recursion supported | Pydantic's `$defs` output is acceptable as is |
| Key order in output follows schema order | Order fields deliberately (put "evidence pointers" before "narrative") |

## Anthropic / Bedrock Provider Stub

| Route | When | Implementation | Notes |
|-------|------|----------------|-------|
| **A. Corporate Anthropic proxy (Apigee-fronted)** (the only approved Claude route in the pilot organisation) | The pilot and any run hosted by the pilot organisation | Hand-written adapter using `httpx2`: `POST {base}/model/{model}/messages`, headers `X-Api-Key`, `Accept: application/json`, body `anthropic_version: "bedrock-2023-05-31"`, top-level `system`, **no** `temperature`/`top_p`/`top_k` | Follows the user's local Anthropic-proxy skill (not in repo). No SDK fits: the proxy path and auth are bespoke. Keeps the dependency tree free of boto3. |
| **B1. Direct AWS, current models** (portability to other companies) | Models served on `bedrock-mantle` (Sonnet 5.x, Opus 5.x, Haiku 5.5, Opus 4.7/4.8, Haiku 4.5) | `anthropic[bedrock]` → **`AnthropicBedrockMantle`**, IDs like `anthropic.claude-sonnet-5-5`; SigV4 via the AWS credential chain, or a bearer token (`AWS_BEARER_TOKEN_BEDROCK`) | AWS's native Messages API. This is the forward path. |
| **B2. Direct AWS, ≤4.6 models** | Sonnet 4.5 / 4.6, Opus 4.5 / 4.6 only | `anthropic[bedrock]<2` + **`AnthropicBedrock`** with `eu.` / `us.` / `global.` inference-profile IDs | SDK 2.x sends API version `2026-10-21` and Bedrock returns 400 for these models. Hard-pin `<2`. |
| Raw `boto3` `invoke_model` / Converse | Only if the SDK dependency is vetoed | Hand-maintained request body, `anthropic_version` set manually | Not recommended: no typed responses, you own request-shape drift. `boto3` (1.44.3) is pulled in anyway by `anthropic[bedrock]` for SigV4. |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| HTTP client | `httpx2` | `httpx` 0.28.1 | Frozen since Dec 2024; the OpenAI and Anthropic SDKs have left it; a second TLS default and exception hierarchy in one process |
| HTTP client | `httpx2` | `requests` / `aiohttp` | `requests` is sync-only; `aiohttp` adds a third stack and its own TLS path. The Graph client needs async with strict transport control |
| Graph access | Hand-written `core/graph.py` over `httpx2` | `msgraph-sdk` 1.65.0 (Kiota) | Cannot structurally enforce "GET and `$batch`-of-GET only" (any request builder can issue POST/PATCH/DELETE). Pulls `kiota-*`, `azure-core`, `msgraph-core` and its own HTTP transport. Needs `$select` / `$expand` / `delta` control that is easier raw. The read-only trust promise is the product, so own the one module that enforces it |
| Auth | MSAL + certificate / managed identity / delegated | Client secret | Explicitly out of scope; the config validator must reject it |
| Test HTTP mocking | `httpx2.MockTransport` | `respx` 0.23.1 | No released httpx2 support |
| Test HTTP mocking | `httpx2.MockTransport` | `pytest-recording` / `vcrpy` | No httpx2 support; cassette-leak risk against the no-tenant-data rule |
| LLM client | `OpenAI` + `base_url` | `AzureOpenAI` | Builds `/openai/deployments/{d}/…?api-version=` URLs. Wrong for the gateway path and obsolete for Azure v1 |
| LLM wire API | Chat Completions | Responses | See the comparison table above |
| LLM schema helper | Own `strictify()` over a canonical schema | `chat.completions.parse(response_format=PydanticModel)` | Hides the wire schema; does not strip Azure-unsupported keywords; hampers the "validate locally against the full schema" design |
| Retries | tenacity (Graph only) | Hand-rolled loops everywhere | tenacity covers the standard retry and backoff cases cleanly. Hand-write only the `$batch` re-queue and the circuit breaker |
| Config | pydantic-settings | `dynaconf`, `hydra` | Spec-pinned, and the models double as the schema source |
| CLI | typer | `click`, `argparse` | Spec-pinned; note Typer 0.29's pydantic dependency is already in the tree |
| Token cache | msal-extensions (DPAPI) | `keyring`, plaintext file | `keyring` adds a dependency without better guarantees on Windows; plaintext breaks the security stance |
| Env manager | uv | pip + venv, poetry | Spec-pinned; no admin rights needed; reproducible lockfile |

## What NOT to Use

| Do not use | Reason |
|------------|--------|
| `msgraph-sdk` / `msgraph-core` / Kiota | See above: cannot enforce read-only by construction; heavy |
| Client secrets (`ConfidentialClientApplication(client_credential="secret")`) | Out of scope by design; fail the run with a pointer to certificate or managed identity |
| Graph `beta` endpoints | Out of scope; `base_url` is fixed to `/v1.0` |
| `respx`, `pytest-recording`, `vcrpy` against httpx2 | Unsupported today |
| `httpx2[http2]` / `h2` | HTTP/2 off by spec; Graph via proxies is more reliable on HTTP/1.1 |
| `azure.identity.aio` | Needs `aiohttp`; use the sync credential in a thread |
| `msal-extensions` `FilePersistence` fallback | Plaintext token cache; fail closed instead |
| `yaml.load` / `yaml.unsafe_load` | Use `safe_load` |
| `verify=False` on any HTTP client | The point of `truststore` is to avoid this |
| Typer's default `pretty_exceptions_show_locals=True` | Leaks tokens into tracebacks |
| `chat.completions` streaming for the batch path | Not needed; avoids the gateway's empty-streamed-token quirk |
| `AnthropicBedrock` with `anthropic>=2` against Sonnet 4.5 / 4.6 | API version 400s; pin `<2` or move to a ≥5.x model on the mantle client |
| `pytest-httpx` (Colin-b) | Pins `httpx==0.28.*`; wrong stack |

## Installation

# pyproject.toml (excerpt)

# One-time (workstation, no admin rights)

# Behind a TLS-inspecting proxy, uv itself needs the OS trust store

# (Windows PowerShell:  $env:UV_SYSTEM_CERTS = "true")

## Version Verification Log (PyPI, 2026-11-15)

| Package | Latest | Released | Notes |
|---------|--------|----------|-------|
| httpx | 0.28.1 | 2024-12-06 | Stale; `1.0.dev6` is the latest pre-release (2026-08-31) |
| httpx2 | 2.16.0 | 2026-10-21 | Python 3.11+; depends on truststore |
| openai | 3.51.0 | 2026-11-13 | Depends on `httpx2>=2.12,<3` |
| anthropic | 2.8.0 | 2026-11-10 | Depends on `httpx2>=2,<3`; extras `bedrock`, `aws` |
| msal | 1.39.0 | 2026-09-17 | |
| msal-extensions | 1.3.1 | 2025-03-14 | Still latest |
| azure-identity | 1.27.0 | 2026-10-26 | |
| tenacity | 9.2.1 | 2026-10-07 | |
| truststore | 0.10.5 | 2026-10-12 | |
| pydantic | 2.14.3 | 2026-11-05 | |
| pydantic-settings | 2.16.3 | 2026-11-13 | `yaml` extra = `pyyaml>=6.0.1` |
| pyyaml | 6.0.3 | 2025-09-25 | |
| jsonschema | 4.26.0 | 2026-01-07 | |
| typer | 0.29.1 | 2026-11-11 | 0.29.0 adopted pydantic validation |
| rich | 15.0.0 | 2026-04-12 | |
| jinja2 | 3.1.6 | 2025-03-05 | |
| python-docx | 1.2.0 | 2025-06-16 | |
| python-pptx | 1.0.2 | 2024-08-07 | Dormant |
| openpyxl | 3.1.5 | 2024-06-28 | |
| pypdf | 7.1.0 | 2026-11-13 | |
| extract-msg | 0.58.2 | 2026-11-05 | |
| pytest | 9.2.0 | 2026-10-27 | |
| pytest-asyncio | 1.5.0 | 2026-11-12 | |
| respx | 0.23.1 | 2026-04-08 | No httpx2 support released |
| pytest-httpx2 | 1.0.0 | 2026-05-20 | Optional |
| pytest-recording | 0.15.0 | 2026-11-15 | Not recommended |
| hypothesis | 6.170.15 | 2026-11-06 | |
| ruff | 0.17.5 | 2026-11-12 | |
| mypy | 2.4.1 | 2026-10-28 | |
| import-linter | 2.16 | 2026-11-06 | |
| uv | 0.13.8 | 2026-11-12 | |
| msgraph-sdk | 1.65.0 | 2026-10-22 | Rejected |
| boto3 | 1.44.3 | 2026-11-13 | Only via `anthropic[bedrock]` |

## Open Risks and Items Needing an Early Smoke Test

| Risk | Severity | Confidence | Mitigation |
|------|----------|------------|------------|
| Delegated device-code flow blocked by Conditional Access | High (blocks the pilot) | MEDIUM | Build and test `--browser` early; register loopback redirect URI; ask Security now; broker as last resort |
| Corporate LLM gateway passes `response_format` strict schema through unchanged, and accepts reasoning-model parameters | High (LLM layer) | LOW-MEDIUM | `llm doctor` capability probe in the first LLM phase; Core Value already requires graceful `--no-llm` degradation |
| Corporate LLM gateway exposes only `/chat/completions`, not `/responses` | Low | MEDIUM | Chat Completions is the chosen route anyway |
| `httpx2` is 6 months old | Medium | MEDIUM | Backed by Pydantic, rapid fixes, API-compatible; pin the minor; fallback documented |
| IMDS call routed via `HTTP_PROXY` on the Azure VM | Medium | MEDIUM | `doctor` checks `NO_PROXY` for `169.254.169.254` |
| pydantic minor bumps alter generated JSON Schema text | Medium | MEDIUM | Pin the minor; compare schemas semantically or regenerate deliberately |
| pypdf / python-pptx / openpyxl on hostile files | Medium (sample tier only) | MEDIUM | Optional extra, subprocess with timeout and size cap, keep pypdf current |
| `typer` 0.29 and `mypy` 2.x are fresh majors/minors | Low | MEDIUM | Pin; fix at scaffold; smoke-test the pydantic mypy plugin |

## Sources

- PyPI JSON API for every package in the verification log (versions, release dates, `requires_python`, `requires_dist`)
- httpx2 project and docs: https://github.com/pydantic/httpx2 , https://pydantic.dev/docs/httpx2/get-started/migration/ , https://pydantic.dev/docs/httpx2/advanced/ssl/ , changelog: https://github.com/pydantic/httpx2/blob/main/src/httpx2/CHANGELOG.md
- openai-python 3.0.0 breaking change and HTTPX2 guide: https://github.com/openai/openai-python/blob/main/httpx2.md , CHANGELOG https://github.com/openai/openai-python/blob/main/CHANGELOG.md , README (Azure section, Chat Completions "supported indefinitely"), `src/openai/_client.py` (`api_key: str | Callable`), `src/openai/lib/azure.py` (`AzureOpenAI` over `httpx2.Client`)
- Azure OpenAI v1 API: https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle
- Azure structured outputs (supported models, schema limits, Chat vs Responses): https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/structured-outputs
- respx repo state (PRs #334, #335, no httpx2 release): https://github.com/lundberg/respx ; pytest-httpx2: https://github.com/lundberg/pytest-httpx2 ; vcrpy patcher (`httpx` only): https://github.com/kevin1024/vcrpy
- msal-extensions README and 1.3.1 source (DPAPI via ctypes, portalocker optional, plaintext fallback): https://github.com/AzureAD/microsoft-authentication-extensions-for-python
- msal 1.39 package metadata (`ManagedIdentityClient`, `broker` extra): https://github.com/AzureAD/microsoft-authentication-library-for-python
- truststore docs (use `inject_into_ssl` in applications only, before other imports): https://truststore.readthedocs.io/en/latest/
- pydantic-settings docs (source ordering, env typo behaviour, `extra="forbid"`, nested delimiter): https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/
- Typer 0.29.0 release notes: https://github.com/fastapi/typer/blob/master/docs/release-notes.md
- Ruff 0.16.0 (default rule set expanded to 413): https://astral.sh/blog/ruff-v0.16.0
- pypdf changelog (7.0 / 7.1 security fixes): https://github.com/py-pdf/pypdf/blob/main/CHANGELOG.md
- uv certificates documentation (`UV_SYSTEM_CERTS`): https://docs.astral.sh/uv/concepts/authentication/certificates/
- Anthropic on Bedrock (runtime vs mantle, `AnthropicBedrockMantle`, API version pin, bearer tokens): https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock , https://platform.claude.com/docs/en/build-with-claude/claude-on-amazon-bedrock-legacy
- mypy 2.0 default changes (`--local-partial-types`, `--strict-bytes`): secondary write-ups (pydevtools) of the 2026-05 release notes
- Corporate LLM gateway shapes (Azure-style Chat Completions path, `api-key` header, Anthropic proxy shape): the user's local gateway-integration skills (not in repo). They are not independently verifiable and must be confirmed by a live smoke test. No pilot-organisation endpoints, hostnames or deployment names belong in the repo.
- Python 3.12 security-only support window (to Oct 2028): from PSF release policy (PEP 693), not re-fetched today
- IMDS vs `HTTP_PROXY` behaviour: well-known Azure SDK guidance, not re-verified against azure-identity 1.27

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-fast` for a trivial task inline, with no subagents and no PLAN.md
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
