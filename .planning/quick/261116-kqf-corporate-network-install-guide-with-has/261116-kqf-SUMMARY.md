---
phase: 261116-kqf-corporate-network-install-guide-with-has
plan: 01
subsystem: install-and-supply-chain
tags: [uv, pip, requirements, hash-locking, tls, readme, quality-gate]
requires:
  - uv.lock
provides:
  - requirements/locked.txt (hash-locked runtime pins, 24 packages)
  - requirements/build.txt (hash-locked uv_build pin, 19 hashes)
  - scripts/export_requirements.py (generator and --check drift gate)
  - eighth gate step requirements-export
  - README corporate-network install guide
affects:
  - scripts/check.py
  - pyproject.toml
  - uv.lock
tech-stack:
  added: []
  patterns:
    - injected exporter for testing a uv-driven script without uv
    - drift gate for generated artefacts (mirrors gen_schemas.py)
key-files:
  created:
    - scripts/export_requirements.py
    - requirements/locked.txt
    - requirements/build.txt
    - tests/unit/test_export_requirements.py
  modified:
    - pyproject.toml
    - uv.lock
    - .gitattributes
    - scripts/check.py
    - tests/unit/test_check_script.py
    - README.md
decisions:
  - "uv_build is locked in a non-default build dependency group using the exact [build-system] requires string, so build.txt is a drift-gated uv.lock export with hashes for every platform"
  - "No dev export: the gate needs uv and git, so a pip-installed dev environment adds nothing"
metrics:
  duration: "about 40 minutes"
  completed: 2026-11-16
status: complete
commits: 3
plan_head_before: 0841816b4e22b7c4ed71545a82a34bca552d902c
plan_head_after: f241972cc9cc415c355bf972e47c94798a1b950e
actuals:
  tokens: 14800
  tasks: 3
  commits: 3
---

# Phase 261116-kqf Plan 01: Corporate-network install guide with hash-locked pip fallback Summary

Hash-locked pip requirement files exported from uv.lock, a drift check wired in as the eighth gate step, and a README with verified commands for a TLS bundle, a private package mirror, a pip fallback that ends in the real `recover-assess` console script, and a hash-checked single-wheel last resort.

## Commits

| Task | Commit | Message |
| ---- | ------ | ------- |
| 1 (tracer) | 96b5038 | feat: export hash-locked pip requirements from uv.lock with a drift check |
| 2 | 10cc442 | feat: gate the requirements export against uv.lock drift |
| 3 | f241972 | docs: corporate-network install guide with a hash-locked pip fallback |

Each commit used an explicit file list. `git diff --name-only 0841816 HEAD -- .planning/config.json .planning/state.json` prints nothing.

## What was built

- `pyproject.toml`: `build = ["uv_build>=0.13.8,<0.14"]` added to `[dependency-groups]`, equal to `[build-system] requires`. `uv lock` added 30 lines to `uv.lock` and deleted 0 (`git diff --numstat 0841816 HEAD -- uv.lock` prints `30 0`). It locked uv-build 0.13.8, the same version as at plan time. `uv sync --locked` installed nothing new.
- `scripts/export_requirements.py` (standard library only): `uv export --frozen --offline` for runtime (`--no-dev`) and for the build group (`--only-group build`), written with a two-line header, UTF-8, LF, atomically. `--check` never writes; CRLF-only differences are not drift; missing file is drift; uv missing or uv export failing returns 2.
- `requirements/locked.txt`: 24 runtime packages, every pin hashed, no uv-build. `requirements/build.txt`: only `uv-build==0.13.8`, 19 hashes. Both LF-only (`.gitattributes` rule added).
- `scripts/check.py`: `requirements-export` is the second of eight steps; a `NEEDS_UV` set makes both uv-needing steps SKIP locally and FAIL in CI when uv is missing.
- README: extended TLS section, "Using a private package mirror", "Fallback: install with pip when uv cannot reach the network" (with last-resort subsection), updated developer quick check.

## Verification evidence

Final gate `uv run --frozen python scripts/check.py`, all eight steps PASS (943 tests):

| Step | Status |
| ---- | ------ |
| uv-lock-check | PASS |
| requirements-export | PASS |
| ruff-check | PASS |
| ruff-format | PASS |
| mypy | PASS |
| import-contracts | PASS |
| blocked-terms | PASS |
| pytest | PASS |

Task 1 acceptance greps: `uv-build==` in locked.txt 0, in build.txt 1; `httpx2==2.16.0` in locked.txt 1; carriage returns 0 in both files. Task 3 acceptance greps all met (headings 1 each, `SSL_CERT_FILE` 7, `--require-hashes` 5, `--no-build-isolation` 3, `UV_INDEX_MIRROR_PASSWORD` 5, and the rest at least 1).

### Tracer proof (throwaway venv, `git archive HEAD`, Python 3.12, public index)

Locked install, build install, then `--no-index --no-deps --no-build-isolation .`, with PATH prepended (no Activate.ps1):

```
Successfully installed ... httpx2-2.16.0 ... (23 wheels; httpx2-jsfetch skipped by marker)
Successfully installed uv-build-0.13.8
Successfully installed recover-assess-0.1.0
0.1.0                          <- recover-assess --version
httpx2 import ok 2.16.0
No broken requirements found. <- pip check
```

### README commands run as written (extracted from the README text by a script)

- TLS bundle recipe (output folder swapped for a scratch folder): 52 certificates, 52 BEGIN lines, first bytes `45,45,45` (no byte order mark), and `uv pip compile` of `httpx2==2.16.0` against public PyPI exited 0 with `SSL_CERT_FILE` pointing at it. The certutil single-root export from the user store produced a PEM starting `-----BEGIN CERTIFICATE-----` (the probe used a user-store thumbprint).
- Pip fallback sequence in a second fresh archive copy: printed `0.1.0`, `pip check` clean.
- Last resort after `pip uninstall -y httpx2`: `pip download` fetched `httpx2-2.16.0-py3-none-any.whl`, `pip hash` printed `--hash=sha256:fd2c5d79...`, `Select-String` matched that line in `requirements/locked.txt`, `pip install --no-deps --no-index <wheel>` installed it, import worked, and the locked install reported `Requirement already satisfied: httpx2==2.16.0`.
- Mirror credential conversion (`[System.Net.NetworkCredential]::new("", $secure).Password`) round-tripped a test value on Windows PowerShell 5.1 (a `ConvertTo-SecureString` stand-in replaced the interactive `Read-Host`); the named `UV_DEFAULT_INDEX` value was read back unchanged.
- Observed `--locked` behaviour with a different default index, in a `git archive` copy: `uv sync --locked --offline` without the variable succeeded; with `UV_DEFAULT_INDEX="mirror=https://mirror.example.invalid/simple"` it exited 1 with "No solution found when resolving dependencies ... httpx2 was not found in the cache", i.e. uv re-resolved instead of using the lock. `uv sync --frozen --offline` with the same variable exited 0 ("Checked 47 packages"). The README states this in neutral words.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Verification probes could not use `py -3.12`**
- **Found during:** Task 3 step 5
- **Issue:** The `py` launcher on this machine has no registered 3.12 interpreter (only a uv-managed one), so the README's first fallback line could not run as written.
- **Fix:** In the probe only, that one line was replaced by the full path to the uv-managed 3.12 `python.exe` (the same interpreter used for the tracer proof). Every other README line ran unchanged. The README keeps `py -3.12`, which is the standard per-user python.org install route, but that exact line was not exercised here.
- **Files modified:** none (probe only, in the scratchpad)

**2. [Style - lint] Header line length and tuple style**
- **Found during:** Task 1 verification
- **Issue:** ruff E501 on the header f-string and C409 in the test.
- **Fix:** header built from a `source` variable; test constant made a tuple. Same behaviour.
- **Commit:** 96b5038 (fixed before the commit)

None of the plan's behavioural requirements changed.

## Known Stubs

None.

## Threat Flags

None. No new network endpoints, auth paths or schema changes at trust boundaries; the new script only runs `uv export --frozen --offline`.

## Notes

- uv-build resolved to 0.13.8, the version recorded at plan time; no newer 0.13.x had appeared.
- The README's "bash" blocks (PATH sequence, `read -rsp`, `export SSL_CERT_FILE`) were not executed on this machine; the PowerShell blocks were.
- `.planning/config.json` and `.planning/state.json` were never staged.

## Self-Check: PASSED

- FOUND: scripts/export_requirements.py, requirements/locked.txt, requirements/build.txt, tests/unit/test_export_requirements.py
- FOUND commits 96b5038, 10cc442, f241972 (all ancestors of HEAD)
- Final gate: eight steps PASS
