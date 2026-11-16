---
phase: 01-foundation-contract-read-only-graph-client
plan: 04
subsystem: config
tags: [config, cli, pydantic-settings, typer, yaml]

requires:
  - phase: 01-foundation-contract-read-only-graph-client
    provides: "ConfigError in core/errors.py and the Typer app with --version (Plan 01-01)"
provides:
  - "core/config.py: Settings with TenantSettings, AuthSettings, CollectSettings, HttpSettings, OutputSettings; load_settings, resolve_config_path, unknown_env_vars, ENV_PREFIX, CONFIG_ENV_VAR, DEFAULT_CONFIG_NAME"
  - "Precedence defaults < YAML < RECOVER_ASSESS__ env < CLI overrides, nested groups deep-merged"
  - "Typo-proof loading: unknown YAML keys, mistyped nested and top-level env keys, client secrets and any allow-list key are ConfigError with closest-match hints"
  - "recover-assess config show [--config --max-items --out --path-mode] printing effective settings as JSON"
  - "recover-assess.example.yaml: neutral contoso/synthetic example of every operator key"
affects: [01-09, 01-10, phase-02-doctor, phase-03-collect]

actuals:
  tokens: 10100
  tasks: 2
  commits: 4
plan_head_before: fd04c3c9843ecf8a9b95963a7f48557543733b8c
plan_head_after: 578fb6cecae4d6a07f405cc6204aefd2e877e8d1

tech-stack:
  added: []
  patterns:
    - "Config load context is a ContextVar (yaml path + environ mapping) set and reset inside load_settings, never class-level state"
    - "A small EnvSettingsSource subclass reads the mapping given to load_settings, so tests pass plain dicts instead of mutating os.environ"
    - "ValidationError rendered via errors(include_input=False, include_context=False) and re-raised with 'from None', so no submitted value or chained input reaches a message"
    - "CLI flags forwarded to load_settings only when not None, as nested dicts, so an unset flag never overrides YAML"

key-files:
  created:
    - src/recover_assess/core/config.py
    - recover-assess.example.yaml
    - tests/unit/test_config.py
    - tests/unit/test_env_typo_scan.py
    - tests/unit/test_config_show.py
  modified:
    - src/recover_assess/cli.py

key-decisions:
  - "load_settings honours its environ argument for the build, not only for the typo scan, by overriding EnvSettingsSource._load_env_vars (private hook, pydantic-settings pinned ~=2.16.3)"
  - "Client-secret keys are matched by casefolding and dropping underscores and hyphens, so client_secret, clientSecret and client-secret are all rejected"
  - "The rejection message constant is named UNSUPPORTED_CREDENTIAL_MESSAGE to avoid ruff S105 treating an error message as a hardcoded password"
  - "YAML syntax errors report only the file and line, never the parser's content snippet"
  - "The scan for a client-secret env variable runs before the generic typo scan, so the specific pointer message wins"

patterns-established:
  - "No allow-list field exists in any settings model; a test walks every field recursively and fails on any name containing 'allow' (D-08)"
  - "certificate_password_env holds only a variable NAME; configuration code never reads the variable, and a test proves a runtime canary value is never printed"

requirements-completed: [FND-03]

coverage:
  - id: D1
    description: "Layered Settings and loader: defaults < YAML < env < CLI with deep merge, lower-case env names, JSON list values"
    requirement: FND-03
    verification:
      - kind: unit
        ref: "tests/unit/test_config.py (precedence, deep-merge, lower-case, JSON list tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Unknown YAML keys, mistyped env keys at both levels, client secrets and allow-list keys are ConfigError with hints; no submitted value is echoed"
    requirement: FND-03
    verification:
      - kind: unit
        ref: "tests/unit/test_config.py and tests/unit/test_env_typo_scan.py (47 tests)"
        status: pass
    human_judgment: false
  - id: D3
    description: "config show prints effective settings as JSON, exits 1 with the message on stderr for a bad config, never prints a secret env value"
    requirement: FND-03
    verification:
      - kind: unit
        ref: "tests/unit/test_config_show.py (14 tests, CliRunner)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Neutral example config loads cleanly and lists every operator key"
    requirement: FND-03
    verification:
      - kind: unit
        ref: "tests/unit/test_config_show.py#test_example_config_*"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-11-16
status: complete
---

# Phase 1 Plan 04: Layered configuration and `config show` Summary

**Typo-proof layered settings (defaults < YAML < `RECOVER_ASSESS__*` env < CLI, nested groups deep-merged) with an env typo scan that catches the top-level mistakes pydantic-settings ignores, client-secret and allow-list rejection, and a `recover-assess config show` command.**

## Performance

- **Duration:** about 15 min (start time was not captured; estimated from the commit timeline)
- **Tasks:** 2 (each as a RED test commit then a GREEN implementation commit)
- **Files:** 6 changed (5 created, 1 modified), 1060 insertions

## Accomplishments

- `core/config.py` models the full spec key block plus `http.max_concurrent_sites` and `http.user_agent_company`. Strings are `StrictStr` so an unquoted YAML `no` is rejected while env strings still parse for ints and floats.
- Precedence and deep merge are test-proven: a CLI override of `collect.sample_size` keeps the YAML `collect.max_items_per_library`.
- `unknown_env_vars` flags `RECOVER_ASSESS__COLECT__SAMPLE_SIZE` (hint `collect`), `...COLLECT__SAMPEL_SIZE` (hint `sample_size`) and `...AUTH__MODE__X`, and ignores `PATH` and the single-underscore `RECOVER_ASSESS_CONFIG`.
- `auth.client_secret` / `clientSecret` (YAML) and `RECOVER_ASSESS__AUTH__CLIENT_SECRET` (env) fail with a message pointing at `app_certificate` or `managed_identity`; the value is never echoed.
- No settings field name contains "allow"; YAML `graph: {allowlist: ...}` and env `RECOVER_ASSESS__GRAPH__ALLOWLIST` are both errors (D-08).
- `config show` maps only explicitly given flags (`--max-items`, `--out`, `--path-mode`) to overrides, prints JSON, and on `ConfigError` prints to stderr with exit 1. `--config` also reads `RECOVER_ASSESS_CONFIG`.
- Demo: `uv run recover-assess config show --config recover-assess.example.yaml` prints the example with `tenant.default_hostname` `contoso.sharepoint.com`.

## RED/GREEN evidence

| Task | RED commit | GREEN commit | RED evidence |
|------|-----------|--------------|--------------|
| 1 | 016e942 | 8de1588 | pytest collection failed with ImportError on the missing `core.config` module. Semantic assessment: the target tests could not run at all, so this is a missing-implementation RED rather than an assertion RED. |
| 2 | d92a2ce | 578fb6c | 12 of 14 tests failed on assertions (no `config` command, example file missing); the two version tests passed as intended regression guards. |

`workflow.tdd_mode` is not enabled in this project, so no RED classifier gate applied.

## Task Commits

1. **Task 1 RED:** `016e942` test(01-04): add failing tests for layered settings and env typo scan
2. **Task 1 GREEN:** `8de1588` feat(01-04): layered Settings with typo-proof env scan and client-secret rejection
3. **Task 2 RED:** `d92a2ce` test(01-04): add failing tests for config show and the example config
4. **Task 2 GREEN:** `578fb6c` feat(01-04): config show command and neutral example configuration

## Verification

- `uv run pytest tests/unit/test_config.py tests/unit/test_env_typo_scan.py tests/unit/test_config_show.py -q`: 61 passed.
- Scoped `ruff check` and `mypy` on every plan file: exit 0.
- `uv run recover-assess config show --max-items 10` prints `"max_items_per_library": 10`; the default prints `50000`.
- `grep -c "contoso.sharepoint.com" recover-assess.example.yaml` is 1.
- `uv run --frozen python scripts/check.py`: exit 0, all six steps PASS, 201 tests passed, 5 import contracts kept (includes the 01-03 AST source bans).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Lint] Error-message constant tripped ruff S105**
- **Found during:** Task 1 verification
- **Issue:** a constant named `CLIENT_SECRET_MESSAGE` was flagged as a hardcoded password.
- **Fix:** renamed to `UNSUPPORTED_CREDENTIAL_MESSAGE` rather than adding a noqa.
- **Files modified:** `src/recover_assess/core/config.py`
- **Commit:** 8de1588

**2. [Rule 2 - Missing critical] Build honours the `environ` argument**
- **Found during:** Task 1 design
- **Issue:** the plan's `load_settings(environ=...)` signature implied the mapping drives the load, but pydantic-settings' env source always reads `os.environ`, so the typo scan and the build could disagree.
- **Fix:** a small `EnvSettingsSource` subclass reads the mapping held in the load ContextVar. Costs one override of a private method; pydantic-settings is pinned `~=2.16.3` and tests cover the behaviour.
- **Files modified:** `src/recover_assess/core/config.py`
- **Commit:** 8de1588

**Total deviations:** 2 auto-fixed. **Impact:** none on scope or contract.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None. The plan's register (T-01-11, T-01-12, T-01-13) is mitigated and test-covered; no new network, auth or file-access surface was added.

## Issues Encountered

None. Per FA-2, the empty-env-string, flag-equals-default and YAML-null edges are implemented and tested as the plan assumed; confirm them with operators at Phase 2 doctor design.

## Next Phase Readiness

Ready for Plan 01-09 (`GraphClient.from_settings(Settings)`) and Plan 01-10's README quick check. The wave-2 join runs `scripts/check.py` on the merged tree, which passes here.

## Self-Check: PASSED

- Files exist: `src/recover_assess/core/config.py`, `recover-assess.example.yaml`, `tests/unit/test_config.py`, `tests/unit/test_env_typo_scan.py`, `tests/unit/test_config_show.py`, `src/recover_assess/cli.py`
- Commits reachable from HEAD: 016e942, 8de1588, d92a2ce, 578fb6c
