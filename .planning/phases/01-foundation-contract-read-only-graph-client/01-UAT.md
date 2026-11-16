---
status: testing
phase: 01-foundation-contract-read-only-graph-client
source: [01-VERIFICATION.md]
started: 2026-11-16T01:24:36Z
updated: 2026-11-16T01:24:36Z
---

## Current Test

number: 1
name: FND-01 clean-machine install (non-admin, behind TLS-inspecting proxy if available)
expected: |
  uv installs to the user profile; `uv python install 3.12` and `uv sync --locked` succeed (with UV_SYSTEM_CERTS=true behind the proxy, or the UV_PYTHON_DOWNLOADS=never fallback); `uv run recover-assess --version` prints 0.1.0; no step asks for elevation or disables TLS verification.
awaiting: user response

## Tests

### 1. FND-01 clean-machine install (non-admin, behind TLS-inspecting proxy if available)
expected: On a clean Windows 11 machine or fresh user profile without admin rights, following README "Install" and "Behind a TLS-inspecting proxy" verbatim: uv installs to the user profile; `uv python install 3.12` and `uv sync --locked` succeed; `uv run recover-assess --version` prints 0.1.0; no elevation prompt and no TLS verification disabled.
result: [pending]

### 2. CI enforcement on a real runner
expected: After pushing to GitHub, `.github/workflows/ci.yml` is green on windows-latest and ubuntu-latest; a throwaway branch with a deliberate violation (e.g. `core/zz.py` importing `recover_assess.cli`) turns the `check` job red at the import-contracts step.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
