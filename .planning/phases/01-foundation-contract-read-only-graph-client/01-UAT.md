---
status: complete
phase: 01-foundation-contract-read-only-graph-client
source: [01-VERIFICATION.md]
started: 2026-11-16T01:24:36Z
updated: 2026-11-17T20:38:18.791Z
---

## Current Test

[testing complete]

## Tests

### 1. FND-01 clean-machine install (non-admin, behind TLS-inspecting proxy if available)
expected: On a clean Windows 11 machine or fresh user profile without admin rights, following README "Install" and "Behind a TLS-inspecting proxy" verbatim: uv installs to the user profile; `uv python install 3.12` and `uv sync --locked` succeed; `uv run recover-assess --version` prints 0.1.0; no elevation prompt and no TLS verification disabled.
result: pass
note: "Run on the non-admin corporate workstation behind the TLS-inspecting proxy, fresh clone, uv 0.11.24, UV_SYSTEM_CERTS=true plus UV_DEFAULT_INDEX/UV_INDEX_MIRROR_* pointing at the private mirror. uv sync --locked first refused (lock needs update under a different index, as the README predicts); uv lock re-resolved through the mirror, then uv sync --locked installed 47 packages and uv run recover-assess --version printed 0.1.0. Local uv.lock diff checked: no version lines changed and no new sha256 hashes (URLs only); local change discarded, not committed."

### 2. CI enforcement on a real runner
expected: After pushing to GitHub, `.github/workflows/ci.yml` is green on windows-latest and ubuntu-latest; a throwaway branch with a deliberate violation (e.g. `core/zz.py` importing `recover_assess.cli`) turns the `check` job red at the import-contracts step.
result: pass
note: "Phase branch CI green on ubuntu-latest and windows-latest. Throwaway branch uat/import-contract-violation added src/recover_assess/core/zz.py importing recover_assess.cli (ruff/mypy clean); local gate failed only at import-contracts; CI run 44171140888 failed on both runners with 'core never imports cli BROKEN' (recover_assess.core.zz -> recover_assess.cli). Branch deleted locally and on origin."

## Summary

total: 2
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
