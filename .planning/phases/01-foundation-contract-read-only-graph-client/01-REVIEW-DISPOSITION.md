---
phase: 01
review: 01-REVIEW.md
updated: 2026-11-17T00:00:00Z
---

# Phase 01 code review disposition

One row per finding. `open` = not yet triaged.

| Finding | Severity | Title | Disposition | Note |
|---|---|---|---|---|
| WR-01 | warning | A non-ASCII `user_agent_company` passes validation, then crashes every request | open | |
| WR-02 | warning | Paging has no page limit or loop detection; a repeating or empty-page `nextLink` loops forever | open | |
| WR-03 | warning | nextLink validation uses the narrow, case-sensitive query-key allow-list, so legitimate Graph paging links may be refused | open | |
| WR-04 | warning | The published JSON Schema carries Python-only `A`/`Z` anchors, which breaks the "contract with later stages" outside Python | open | |
| WR-05 | warning | A single throttled or over-budget sub-request discards the whole `batch()` result, and 20 throttled sub-responses in one batch open the breaker immediately | open | |
| WR-06 | warning | Transport errors and 502/504 are never retried; one connection reset fails the whole site | open | |
| WR-07 | warning | `config.py` overrides the private `EnvSettingsSource._load_env_vars` and silently drops base-class behaviour | open | |
| WR-08 | warning | CI has no job timeout or concurrency control, and runs twice for pushed pull-request branches | open | |
| WR-09 | warning | `sweep_orphans` can delete another live run's in-flight temp file | open | |
| IN-01 | info | `strip_annotations` removes only `@microsoft.graph.*`; other bearer-like URLs pass through to callers | open | |
| IN-02 | info | `WarningEvent.detail` is a free-text field, contradicting the "no free-text body field" guarantee | open | |
| IN-03 | info | httpx2 exceptions that are not `TransportError` escape `_hop` unwrapped | open | |
| IN-04 | info | A session stays usable after its context exits, and `batch()` has a hard-coded item cap | open | |
| IN-05 | info | `verify_sha256.py` fails with a traceback on bad input and rejects BSD-style sidecars | open | |
| WR-10 | warning | The blocked-term scan silently skips any file that contains a NUL byte or is not valid UTF-8 | open | incremental review 2026-11-17 |
| WR-11 | warning | Unsalted SHA-256 digests of single words are reversible by dictionary attack, so the committed list effectively discloses the terms | open | incremental review 2026-11-17 |
| WR-12 | warning | File paths are never scanned, and a path hit would echo the term | open | incremental review 2026-11-17 |
| WR-13 | warning | The sdist ships `tests/**` and `scripts/**` but not `requirements/`, so the new committed-file tests fail when run from the sdist | open | incremental review 2026-11-17 |
| WR-14 | warning | The `<0.14` upper bound makes the README's "uv 0.11 or later" offline build break on newer uv, and the widened lower bound is untested | open | incremental review 2026-11-17 |
| IN-06 | info | README claims pip "uses the Windows trust store by default", which depends on the pip version in the new venv | open | incremental review 2026-11-17 |
| IN-07 | info | The retry cap is enforced only in the settings layer, not in `GraphClient` | open | incremental review 2026-11-17 |
| IN-08 | info | Lower-case concatenated forms of a multi-word name are not matched, and the real-digest test pins an exact count | open | incremental review 2026-11-17 |
| IN-09 | info | A tracked file name that is not valid UTF-8 crashes the scanner with a traceback and exit code 1 | open | incremental review 2026-11-17 |
| IN-10 | info | `generate()` can leave the two requirements files out of step, and a stale `.tmp` on failure | open | incremental review 2026-11-17 |
| IN-11 | info | `build_steps(environ=...)` is a parameter that is deliberately ignored | open | incremental review 2026-11-17 |
