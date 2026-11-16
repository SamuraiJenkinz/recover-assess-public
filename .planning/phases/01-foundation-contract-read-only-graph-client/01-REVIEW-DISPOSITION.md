---
phase: 01
review: 01-REVIEW.md
updated: 2026-11-16T01:20:52Z
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
