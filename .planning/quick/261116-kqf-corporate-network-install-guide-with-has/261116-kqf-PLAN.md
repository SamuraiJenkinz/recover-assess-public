---
phase: 261116-kqf-corporate-network-install-guide-with-has
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - uv.lock
  - .gitattributes
  - scripts/export_requirements.py
  - requirements/locked.txt
  - requirements/build.txt
  - tests/unit/test_export_requirements.py
  - scripts/check.py
  - tests/unit/test_check_script.py
  - README.md
autonomous: true
requirements: [QUICK-261116-kqf]

estimate:
  tokens: 110000
  raw_tokens: 110000
  tasks: 3
  confidence: low

must_haves:
  truths:
    - "`requirements/locked.txt` (runtime) and `requirements/build.txt` (the uv_build backend) are exported from uv.lock with a sha256 hash on every pin; `uv run --frozen python scripts/export_requirements.py --check` exits 0 on the committed tree and exits 1 without writing when either file differs from a fresh export"
    - "`scripts/check.py` runs a `requirements-export` step straight after `uv-lock-check`, so the gate (and CI, which runs the gate) fails if the exports drift from uv.lock; both uv-needing steps are SKIP locally and FAIL in CI when uv is missing"
    - "Following the README pip fallback in a fresh clone (git archive copy) and a fresh venv, with no PYTHONPATH change and no wrapper script, ends with the real console script printing `0.1.0` for `recover-assess --version` and `python -c \"import httpx2\"` succeeding"
    - "The README TLS section gives a verified `SSL_CERT_FILE` recipe (PowerShell and bash) built from the Windows user and machine root stores without admin rights, plus a certutil export of a single root from the user store"
    - "The README mirror section uses only env var names uv 0.13.8 actually has (`UV_DEFAULT_INDEX`, `UV_INDEX_<NAME>_USERNAME`, `UV_INDEX_<NAME>_PASSWORD`; `UV_INDEX_URL` noted as deprecated), keeps credentials in the session only, states the uv.lock index caveat as observed, and has a generic diagnosis note for the doubled `/packages/packages/` 403"
    - "`uv run --frozen python scripts/check.py` exits 0 with eight steps; no organisation, mirror-product, hostname, ticket or person name enters any tracked file or commit message; `.planning/config.json` and `.planning/state.json` are in no commit"
  artifacts:
    - path: scripts/export_requirements.py
      provides: "Stdlib-only generator and --check drift gate for requirements/*.txt from uv.lock"
      contains: "--check"
    - path: requirements/locked.txt
      provides: "Hash-locked runtime requirements for pip install --require-hashes --no-deps"
      contains: "httpx2==2.16.0"
    - path: requirements/build.txt
      provides: "Hash-locked uv_build pin for pip install --no-build-isolation"
      contains: "uv-build==0.13.8"
    - path: tests/unit/test_export_requirements.py
      provides: "Unit tests with an injected exporter plus offline consistency tests of the committed exports against uv.lock and pyproject.toml"
      contains: "def test_"
    - path: scripts/check.py
      provides: "Single gate with the requirements-export step"
      contains: "requirements-export"
    - path: README.md
      provides: "Corporate-network install guide: TLS bundle, private mirror, pip fallback, last-resort wheel"
      contains: "## Fallback: install with pip when uv cannot reach the network"
  key_links:
    - from: scripts/check.py
      to: scripts/export_requirements.py
      via: "Step(\"requirements-export\", (sys.executable, str(ROOT / \"scripts\" / \"export_requirements.py\"), \"--check\")) in build_steps"
      pattern: "export_requirements\\.py"
    - from: scripts/export_requirements.py
      to: uv.lock
      via: "uv export --frozen --offline --format requirements.txt --no-emit-project --no-header (--no-dev | --only-group build)"
      pattern: "--frozen"
    - from: pyproject.toml
      to: requirements/build.txt
      via: "[dependency-groups] build = the same specifier string as [build-system] requires, locked in uv.lock and exported with --only-group build"
      pattern: "uv_build>=0.13.8,<0.14"
    - from: README.md
      to: requirements/locked.txt
      via: "pip install --require-hashes --no-deps --only-binary=:all: -r requirements\\locked.txt"
      pattern: "requirements.locked\\.txt"
---

<objective>
Give operators on locked-down corporate workstations a working, Windows-first, no-admin install route when uv is blocked by a TLS-inspecting proxy or by a broken private package mirror, without weakening the integrity guarantees of uv.lock.

Purpose: a field report showed (a) uv still failing certificate checks after the proxy root CA was added to the Windows store and `UV_SYSTEM_CERTS` was set, and (b) a private PyPI mirror returning 403 because it builds download URLs with a doubled `/packages/packages/` segment, so resolution through it fails. The ad-hoc workaround in that report (unpinned versions, missing httpx2, PYTHONPATH plus launcher scripts) is NOT adopted. Instead the repo ships hash-locked pip requirement files exported from uv.lock, gated against drift, and a README that documents verified commands only.

Output: `scripts/export_requirements.py`, `requirements/locked.txt`, `requirements/build.txt`, a `build` dependency group (pyproject + uv.lock), a `.gitattributes` rule, tests, an eighth gate step, and three README sections.

Decision made at plan time (reversible): uv_build is added to a `build` dependency group whose specifier is the exact `[build-system] requires` string. It is the project's existing build backend, not a new dependency; the group is not a default group, so `uv sync --locked` installs nothing new. This makes `requirements/build.txt` a uv.lock export with hashes for every platform, drift-gated like `locked.txt`, instead of a hand-maintained hash list. A separate dev export is NOT produced: the gate itself needs uv and git, so a pip-installed dev environment buys nothing (runtime is the priority).

IMPORTANT for the executor: this PLAN.md, your SUMMARY.md, the README and every commit message are scanned by the blocked-terms gate. Never write any organisation name, the mirror product or its vendor, any real hostname, ticket or person name. Use generic words: "private package mirror", "corporate proxy", `<mirror-host>`.
</objective>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@README.md
@scripts/check.py
@scripts/gen_schemas.py
@scripts/blocked_terms.py
@tests/unit/test_check_script.py
@pyproject.toml

Facts established at plan time (HEAD 0841816, uv 0.13.8, Windows 11, Git Bash + PowerShell 5.1):
- `uv export --frozen --offline --no-emit-project --no-dev --no-header` works offline, writes LF, and lists 24 runtime packages: annotated-doc, annotated-types, anyio, colorama (win32 marker), h11, httpcore2, httpx2 2.16.0, httpx2-jsfetch (emscripten marker), idna, markdown-it-py, mdurl, pydantic 2.14.3, pydantic-core, pydantic-settings, pygments, python-dotenv, pyyaml, rich, shellingham, tenacity, truststore, typer, typing-extensions, typing-inspection. Each pin is followed by `--hash=sha256:` lines and `# via` annotations.
- Adding `build = ["uv_build==0.13.8"]` to `[dependency-groups]` in a scratch copy and running `uv lock` only ADDED lines to uv.lock (two group blocks plus one `[[package]] name = "uv-build"` block with an sdist and 18 wheels); no existing version changed. `uv export --frozen --offline --only-group build --no-emit-project --no-header` then printed `uv-build==0.13.8` with 19 hashes. The plan uses the `[build-system]` specifier string `uv_build>=0.13.8,<0.14` instead of `==`, which locks to the same 0.13.8.
- End-to-end pip fallback VERIFIED in PowerShell in a throwaway `git archive` copy with public PyPI (pip 26.3 in a Python 3.12.16 venv): `python -m venv .venv`, then `$env:PATH = "$PWD\.venv\Scripts;$env:PATH"`, then `python -m pip install --require-hashes --no-deps --only-binary=:all: -r requirements\locked.txt`, then the same for `requirements\build.txt`, then `python -m pip install --no-index --no-deps --no-build-isolation .`; `recover-assess --version` printed `0.1.0`, `import httpx2` worked, `pip check` was clean, and the source tree gained no build artefacts.
- Without the venv Scripts folder on PATH, the project install fails with `RuntimeError: uv-build was not properly installed`, because the uv_build shim finds its binary with `shutil.which("uv-build")`. Prepending PATH (rather than running `Activate.ps1`) also avoids execution-policy blocks on locked-down machines.
- Last resort VERIFIED: `python -m pip download --no-deps --only-binary=:all: --python-version 3.12 --platform win_amd64 -d wheels "httpx2==2.16.0"` fetched `httpx2-2.16.0-py3-none-any.whl`; `python -m pip hash <wheel>` printed `--hash=sha256:fd2c5d79...` which matches the line in the export; `python -m pip install --no-deps --no-index <wheel>` installed it; re-running the locked install reported `Requirement already satisfied: httpx2==2.16.0` and fetched only the rest.
- pip 26.3 builds its SSL context with its vendored truststore by default (`pip/_internal/cli/index_command.py`), so it trusts the Windows store directly; `--cert <bundle>` overrides.
- uv 0.13.8 env vars confirmed from `uv sync --help`, `uv export --help` and strings in the uv binary: `UV_SYSTEM_CERTS` (flag `--system-certs`; `UV_NATIVE_TLS` is the older alias), `SSL_CERT_FILE`, `SSL_CERT_DIR`, `UV_DEFAULT_INDEX`, `UV_INDEX`, `UV_INDEX_URL` and `UV_EXTRA_INDEX_URL` (both marked "Deprecated: use --default-index / --index"), `UV_INDEX_<NAME>_USERNAME` / `UV_INDEX_<NAME>_PASSWORD`, `UV_INSECURE_HOST`, `UV_OFFLINE`, `UV_KEYRING_PROVIDER`. The named form `UV_DEFAULT_INDEX="mirror=https://<host>/simple"` parses. `uv auth login` exists but stores credentials in the uv credentials directory on disk (`uv auth dir`), so the README must not recommend it.
- `SSL_CERT_FILE` REPLACES uv's trust set: with a PEM holding one unrelated root, `uv pip compile` failed with `invalid peer certificate: UnknownIssuer`; with a missing path uv warns "Invalid `SSL_CERT_FILE`. Path does not exist: ... No default certificates will be trusted." A bundle built from `Cert:\CurrentUser\Root` plus `Cert:\LocalMachine\Root` (52 certificates, deduplicated by thumbprint, no admin) made `uv pip compile` against public PyPI succeed, from both a Windows path and a Git Bash `$HOME/...` style path.
- `certutil -user -store Root <thumbprint> one.cer` then `certutil -f -encode one.cer one.pem` exported a single user-store root to PEM without admin (`-----BEGIN CERTIFICATE-----` header).
- uv.lock records `source = { registry = "https://pypi.org/simple" }`. With `UV_DEFAULT_INDEX` set to a DIFFERENT URL, `uv lock --check` re-resolves through that URL (observed GETs to `<mirror>/simple/<pkg>/`), so `uv sync --locked` cannot use the committed lock through a mirror. `uv sync --frozen` ignores the mirror and downloads from the lock's `files.pythonhosted.org` URLs (observed in `-v` output). A named default index with the SAME pypi.org URL kept the lock valid.
- Tooling quirks seen in this environment: Windows PowerShell 5.1 started from Git Bash inherits a PSModulePath that hides the `Cert:` drive and `Get-FileHash`; start probes with `env -u PSModulePath powershell.exe -NoProfile -ExecutionPolicy Bypass -File <probe.ps1>`. In Git Bash, prepend PATH with the `/c/...` form, never `C:/...` (the colon splits PATH).
- `tests/support/repo_scan.py` scans README.md, `tests/` and `scripts/` for e-mail-like `\w@domain` text (only `example.com` and `contoso.com` allowed), GUIDs, JWTs, bearer tokens and `apis.` hosts. So never write `user:token@host` style URLs; use `<mirror-host>` placeholders.
- `.gitattributes` forces LF for py/json/toml/yaml/yml/uv.lock/.python-version only; `core.autocrlf=true`. README.md is LF in the working tree today; keep its line endings as they are.
- `.planning/config.json` has uncommitted user changes and `.planning/state.json` is untracked: never stage either. Use explicit file lists for every `git add`; never `git add -A`, `git add .` or `git commit -a`. Work on the current branch `gsd/phase-01-foundation-contract-read-only-graph-client`.
- `$SCRATCH` below means your session scratchpad directory (outside the repo). Never create probe files inside the repo.
- Fixed-string occurrence counts at HEAD (the per-task gate lists repeat them as baselines): README.md has SSL_CERT_FILE once and none of UV_DEFAULT_INDEX, require-hashes, no-build-isolation, packages/packages, certutil, pip hash, export_requirements; scripts/check.py and tests/unit/test_check_script.py have no requirements-export; uv.lock has no uv-build package; `requirements/` does not exist.
</context>

<tasks>

<task type="tracer" tdd="true">
  <name>Task 1: Tracer - hash-locked exports from uv.lock, drift check, proven by a real pip install</name>
  <files>pyproject.toml, uv.lock, .gitattributes, scripts/export_requirements.py, requirements/locked.txt, requirements/build.txt, tests/unit/test_export_requirements.py</files>
  <precondition>Public PyPI is reachable from this machine (needed once for `uv lock` and for the throwaway-venv proof); `uv --version` prints 0.13.8.</precondition>
  <behavior>
    - check(root, exporter=fake) prints `OK requirements/locked.txt` and `OK requirements/build.txt` and returns 0 when both files equal header + fake body
    - check returns 1 and prints `DRIFT <path>: regenerate with uv run python scripts/export_requirements.py` when a file is edited, and also when a file is missing; the file bytes (or absence) are unchanged afterwards (never writes)
    - a file whose content differs only by CRLF line endings is NOT drift
    - generate(root, exporter=fake) creates `requirements/`, writes both files as UTF-8 with LF only (no `\r` byte), each starting with the fixed two-line header; a following check returns 0
    - the exporter receives, for locked.txt, exactly `export --frozen --offline --format requirements.txt --no-emit-project --no-header --no-dev`, and for build.txt the same base plus `--only-group build` instead of `--no-dev`; never `lock`, `--upgrade` or `sync`
    - main(["--check"]) returns 2 and prints a reason when uv is not on PATH (module `shutil.which` patched to return None) and when uv export exits non-zero (fail closed, never a silent pass)
    - offline consistency of the COMMITTED files (no uv needed): every requirement entry in requirements/locked.txt is `name==version` with at least one `--hash=sha256:<64 hex>`; each name/version matches the `[[package]]` entry in uv.lock (tomllib); every `[project].dependencies` name (PEP 503 normalised) is present; no dev-group or build-group name (pytest, ruff, mypy, hypothesis, import-linter, jsonschema, uv-build) is present; requirements/build.txt contains exactly one entry, `uv-build`, at the uv.lock version
    - pyproject `[dependency-groups].build` equals `[build-system].requires` exactly
  </behavior>
  <action>
1. Lock: add `build = ["uv_build>=0.13.8,<0.14"]` as the first entry of `[dependency-groups]` in pyproject.toml (same string as `[build-system] requires`; per the plan-time decision in the objective). Run `uv lock` (network). Confirm `git diff --numstat -- uv.lock` shows 0 deleted lines and that `uv lock --check` passes. Do not run `uv lock --upgrade`. At plan time this range resolved to uv-build 0.13.8 (checked with `uv pip compile`); if a newer 0.13.x has appeared since, that is acceptable because it is inside the `[build-system]` range, but record it in the SUMMARY and read the 0.13.8 in the criteria below as the locked version. Run `uv sync --locked` afterwards so the venv matches (it should install nothing new because `build` is not a default group).

2. Add the line `requirements/*.txt text eol=lf` to .gitattributes (keep the existing lines and their order; append after `.python-version`).

3. Write the RED tests first in tests/unit/test_export_requirements.py, loading the script with `importlib.util.spec_from_file_location` exactly like `_load_check` in tests/unit/test_check_script.py (module name `export_requirements_script`). Use `tmp_path` roots and a fake exporter that records the argument tuples and returns a fixed body such as `pkg==1.0 \` + newline + `    --hash=sha256:` + 64 `a` characters + newline. Cover every bullet in the behavior block. Run them and confirm they fail because the script does not exist.

4. Implement scripts/export_requirements.py, standard library only (argparse, collections.abc, dataclasses, pathlib, shutil, subprocess, sys), mirroring the shape of scripts/gen_schemas.py and the injection style of scripts/blocked_terms.py:
   - Module docstring: purpose, the two usages (`uv run python scripts/export_requirements.py` regenerates; `--check` exits 1 on drift and never writes), exit codes 0/1/2, "Standard library only", and that CRLF on disk is not drift.
   - `ROOT = Path(__file__).resolve().parent.parent`; `REGENERATE_HINT = "regenerate with uv run python scripts/export_requirements.py"`.
   - Frozen dataclass `Export(relpath: str, purpose: str, selector: tuple[str, ...])` and `EXPORTS` holding `requirements/locked.txt` (purpose "runtime dependencies for the pip fallback install, see README", selector `("--no-dev",)`) and `requirements/build.txt` (purpose "build backend for pip install --no-build-isolation, see README", selector `("--only-group", "build")`).
   - `BASE_ARGS = ("export", "--frozen", "--offline", "--format", "requirements.txt", "--no-emit-project", "--no-header")`. `--frozen` means uv.lock is read, never updated; `--offline` guarantees the gate never touches the network.
   - `header(export) -> str`: exactly two comment lines, `# Hash-locked <purpose>, exported from uv.lock by scripts/export_requirements.py.` and `# Do not edit. Regenerate with: uv run python scripts/export_requirements.py`, each ending in `\n`.
   - Type alias `Exporter = Callable[[Path, Sequence[str]], str]`. Default `run_uv_export(root, args)`: resolve uv with `shutil.which("uv")`; if None raise `ExportError("uv is not on PATH")`; run `[uv, *args]` with `cwd=root`, `capture_output=True`, `check=False`; on non-zero exit raise `ExportError` carrying the exit code and the last stderr line; return stdout decoded as UTF-8.
   - `expected_text(root, export, exporter)`: header + exporter output with `\r\n` normalised to `\n`.
   - `check(root, exporter) -> int` (OK/DRIFT lines as in the behavior block; compare on-disk text read as UTF-8 with `\r\n` normalised to `\n`; a missing or unreadable file is drift) and `generate(root, exporter) -> int` (mkdir parents; write to a sibling `.tmp` path with `write_text(..., encoding="utf-8", newline="\n")` then `Path.replace` onto the target so a crash never leaves a half file; print `WROTE <relpath>`).
   - `main(argv=None, *, root=None, exporter=None) -> int`: `--check` flag; catch `ExportError` and `OSError`, print `export-requirements: <reason>` to stderr, return 2. Tests reach the two exit-2 paths by monkeypatching the module's `shutil.which` (returns None) and the module's `subprocess.run` (returns a `CompletedProcess` with a non-zero return code and a short stderr).
   - Must pass ruff with the repo's explicit select (PTH: Path methods only, no `os.replace`) and mypy strict (scripts are in `[tool.mypy] files`).

5. Run `uv run --frozen python scripts/export_requirements.py` to write both files, then `--check` (exit 0). Inspect: locked.txt has the 24 runtime packages from the context and no `uv-build`; build.txt has only `uv-build==0.13.8` with 19 hashes. Make the GREEN tests pass, including the offline consistency tests against the committed files.

6. Commit with an explicit list: `git add pyproject.toml uv.lock .gitattributes scripts/export_requirements.py requirements/locked.txt requirements/build.txt tests/unit/test_export_requirements.py`; message `feat(quick-261116-kqf): export hash-locked pip requirements from uv.lock with a drift check`.

7. End-to-end proof (the tracer's far end), on the committed tree: extract `git archive HEAD` into `$SCRATCH/kqf-e2e/src`; write `$SCRATCH/kqf-e2e/probe.ps1` that does `Set-Location` into that copy, creates `.venv` with a base Python 3.12 (get its path by running `uv python find 3.12 --system` from `$SCRATCH`, NOT from the repo, where uv returns the project venv), prepends `$PWD\.venv\Scripts` to `$env:PATH`, runs the three pip installs exactly as listed in the context facts (locked.txt, build.txt, then `--no-index --no-deps --no-build-isolation .`), then `recover-assess --version`, `python -c "import httpx2"` and `python -m pip check`. Run it with `env -u PSModulePath powershell.exe -NoProfile -ExecutionPolicy Bypass -File <windows path of probe.ps1>`. Record the output lines in the SUMMARY. If it fails, fix the export or script (never the expected result) in a follow-up commit with an explicit file list, and repeat.
  </action>
  <verify>
    <automated>uv lock --check && uv run --frozen python scripts/export_requirements.py --check && uv run --frozen pytest tests/unit/test_export_requirements.py -q && uv run --frozen ruff check scripts/export_requirements.py tests/unit/test_export_requirements.py && uv run --frozen ruff format --check scripts/export_requirements.py tests/unit/test_export_requirements.py && uv run --frozen mypy</automated>
  </verify>
  <acceptance_criteria>
  Run after the step-6 commit (0841816 is the plan-time base commit):
  - `git diff --numstat 0841816 HEAD -- uv.lock` prints one line whose second column (deleted lines) is 0 [HEAD=0 EXPECT==0 @0841816 GUARD MUTATION: uv lock --upgrade]
  - `grep -c 'name = "uv-build"' uv.lock` [HEAD=0 EXPECT==1]
  - `grep -c '^uv-build==' requirements/locked.txt` [HEAD=error:2 EXPECT==0]
  - `grep -c '^uv-build==0.13.8' requirements/build.txt` [HEAD=error:2 EXPECT==1]
  - `grep -c -F 'httpx2==2.16.0' requirements/locked.txt` [HEAD=error:2 EXPECT==1]
  - `grep -c $'\r' requirements/locked.txt` [HEAD=error:2 EXPECT==0]
  - `grep -c $'\r' requirements/build.txt` [HEAD=error:2 EXPECT==0]
  </acceptance_criteria>
  <done>Both exports exist, match a fresh `uv export`, are LF-only and hash-locked; the drift check returns 0/1/2 as specified and is unit-tested without uv; uv.lock only gained the uv-build entries; the throwaway-venv probe printed `0.1.0`, imported httpx2 and `pip check` was clean; the task is committed with an explicit file list.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wire the requirements-export drift check into the single gate</name>
  <files>scripts/check.py, tests/unit/test_check_script.py</files>
  <behavior>
    - STEP_NAMES and the default build_steps order are: uv-lock-check, requirements-export, ruff-check, ruff-format, mypy, import-contracts, blocked-terms, pytest (eight steps)
    - the requirements-export argv is `[sys.executable, str(ROOT / "scripts" / "export_requirements.py"), "--check"]`
    - with `--fix`, ruff-fix and ruff-format-write still come first, followed by the eight gate steps
    - one failing step gives exit 1 and every one of the eight steps still runs; all-pass gives eight PASS results
    - uv unavailable outside CI: both uv-lock-check and requirements-export are SKIP with detail "uv not on PATH", the runner is called 6 times and main returns 0; uv unavailable in CI: both are FAIL and main returns 1
  </behavior>
  <action>
1. RED: update tests/unit/test_check_script.py first. Insert "requirements-export" after "uv-lock-check" in `GATE_STEPS`; rename `test_step_names_are_the_seven_gate_steps` to say eight; add the argv assertion for requirements-export in `test_build_steps_argv_shapes` (compare against `str(CHECK_PATH.parent / "export_requirements.py")` the same way blocked-terms is compared); add `"requirements-export": "PASS"` to the expected dict in `test_one_failure_fails_overall_and_nothing_is_skipped`; change the hard-coded counts 7 to 8 in `test_main_exit_code_one_when_a_step_fails`, `test_main_exit_code_zero_when_all_pass`, `test_every_single_failure_position_gives_exit_one` and `test_all_pass_results`; in `test_uv_missing_outside_ci_is_skip` assert results[0] and results[1] are SKIP with detail "uv not on PATH" and the call count stays 6 (8 steps minus 2 skipped); in `test_uv_missing_in_ci_is_fail` assert results[0] and results[1] are FAIL. Leave the CI workflow tests unchanged (ci.yml already runs the gate). Run and confirm the new assertions fail.

2. GREEN: in scripts/check.py add "requirements-export" to `STEP_NAMES` after "uv-lock-check"; add `Step("requirements-export", (py, str(ROOT / "scripts" / "export_requirements.py"), "--check"))` straight after the uv-lock-check step in `build_steps`; introduce a module constant `NEEDS_UV: frozenset[str] = frozenset({"uv-lock-check", "requirements-export"})` and change the skip test in `run_steps` from the single-name equality to membership in `NEEDS_UV` (same SKIP/FAIL logic, same "uv not on PATH" detail). Update the module docstring order list ("uv lock --check, the requirements export drift check, ruff check, ...") and the argparse description ("lock, requirements export, lint, format, types, contracts, blocked terms, tests").

3. Run `uv run --frozen pytest tests/unit/test_check_script.py -q`, then the full gate `uv run --frozen python scripts/check.py` and confirm the table shows eight steps, all PASS.

4. Commit: `git add scripts/check.py tests/unit/test_check_script.py`; message `feat(quick-261116-kqf): gate the requirements export against uv.lock drift`.
  </action>
  <verify>
    <automated>uv run --frozen pytest tests/unit/test_check_script.py -q && uv run --frozen python scripts/check.py</automated>
  </verify>
  <acceptance_criteria>
  - `grep -v '^ *#' scripts/check.py | grep -c '"requirements-export"'` [HEAD=0 EXPECT>=2]
  - `grep -v '^ *#' scripts/check.py | grep -c 'step.name == '` [HEAD=1 EXPECT==0]
  - `grep -c '"requirements-export"' tests/unit/test_check_script.py` [HEAD=0 EXPECT>=2]
  </acceptance_criteria>
  <done>The gate has eight steps in the specified order, the export drift check runs as the second step, both uv-needing steps skip locally and fail in CI when uv is missing, every hard-coded count in the gate tests is updated, and `uv run --frozen python scripts/check.py` exits 0.</done>
</task>

<task type="auto">
  <name>Task 3: README - TLS bundle recipe, private mirror, pip fallback and last-resort wheel, each verified as written</name>
  <files>README.md</files>
  <action>
Edit README.md only (keep its existing LF line endings; Windows-first; every step works without admin rights). Use PowerShell blocks first and bash second, matching the existing section style. Only write commands that you then run verbatim in step 5 (paths under the user profile may be replaced by `$SCRATCH` paths when running, nothing else).

1. Extend "## Behind a TLS-inspecting proxy" after the existing `UV_SYSTEM_CERTS` and `SSL_CERT_FILE` paragraph:
   - A short "If uv still reports certificate errors" subsection: point uv at a PEM bundle with `SSL_CERT_FILE`. State the verified behaviour: the file replaces uv's trust set entirely, and a wrong path makes uv warn that no default certificates will be trusted. So build the bundle from the whole Windows root store (user plus machine; reading both needs no admin), which also contains the proxy root CA.
   - PowerShell recipe (the one verified at plan time): make `$env:USERPROFILE\.certs`; collect `@(Get-ChildItem Cert:\CurrentUser\Root) + @(Get-ChildItem Cert:\LocalMachine\Root) | Sort-Object Thumbprint -Unique`; emit for each certificate the BEGIN CERTIFICATE line, `[Convert]::ToBase64String($c.RawData, "InsertLineBreaks")` and the END CERTIFICATE line; write with `Set-Content -Encoding ascii` (ascii avoids the BOM Windows PowerShell 5.1 adds with utf8) to `windows-roots.pem`; set `$env:SSL_CERT_FILE` to it.
   - How to confirm the proxy root is there: `Get-ChildItem Cert:\CurrentUser\Root | Where-Object Subject -like "*<part of the proxy CA name>*"`; note that a CA imported into "Intermediate Certification Authorities" is not a root and must be re-imported under "Trusted Root Certification Authorities" for the current user.
   - Single-certificate alternative with certutil from the user store: `certutil -user -store Root <thumbprint> proxy-root.cer` then `certutil -f -encode proxy-root.cer proxy-root.pem`, for appending the proxy root to another bundle.
   - bash: `export SSL_CERT_FILE="$HOME/.certs/windows-roots.pem"` (Git Bash reads the same file); on macOS or Linux point it at a bundle that contains the proxy root.
   - One sentence: recover-assess itself honours `SSL_CERT_FILE` too (httpx2 checks it before the OS store), so a bundle built this way is safe to leave set; `Remove-Item Env:SSL_CERT_FILE` clears it for the session.
   - One sentence pointing to the pip fallback: pip uses the Windows trust store directly (it ships truststore and uses it by default), so if uv still cannot connect, the fallback section works with the store as it is; `--cert <bundle.pem>` overrides it.

2. New section "## Using a private package mirror" (after the TLS section, before Configuration):
   - uv setting: `UV_DEFAULT_INDEX` in the named form `mirror=https://<mirror-host>/<path-to-pypi-remote>/simple`; say `UV_INDEX_URL` still exists but uv 0.13.8 marks it deprecated.
   - Credentials for the session only, as `UV_INDEX_MIRROR_USERNAME` and `UV_INDEX_MIRROR_PASSWORD` (the password is usually the mirror's access token); never put them in pyproject.toml, uv.toml, pip.ini or any file in the checkout, and do not use `uv auth login` because it saves them on disk. Show a PowerShell way to type the token without echo (for example `Read-Host -AsSecureString` converted via `[System.Net.NetworkCredential]::new("", $secure).Password`) and the bash `read -rs` equivalent; then `Remove-Item Env:UV_INDEX_MIRROR_PASSWORD` / `unset` when done. Run the conversion once yourself to confirm it works on Windows PowerShell 5.1.
   - The lock caveat, written only as observed: uv.lock records the public index, so with a different default index uv re-resolves through the mirror and `uv sync --locked` cannot use the committed lock; `uv sync --frozen` ignores the mirror and downloads the exact files listed in uv.lock from the public file host, so if that host is reachable through the proxy no mirror is needed. If only the mirror is reachable, run `uv sync` (without `--locked`), then `git diff uv.lock`: only URLs may change; if any version or hash changed, stop and use the pip fallback. Never commit that local uv.lock change. Verify the `--locked` claim before writing it: in a `git archive` copy under `$SCRATCH`, run `uv sync --locked --offline` with `UV_DEFAULT_INDEX="mirror=https://mirror.example.invalid/simple"` and confirm a non-zero exit; describe the result in neutral words, not a copied message you did not see.
   - pip setting: `PIP_INDEX_URL` (session only) set to the same `/simple` URL; pip asks for the user name and token when the mirror answers 401; do not store them in pip.ini.
   - Diagnosis note, titled for whoever raises it with IT: symptom: downloads fail with HTTP 403 and the failing URL (shown by `uv sync -v` or `python -m pip download -v --no-deps <name>==<version>`) contains `/packages/packages/`. Likely cause: the mirror's PyPI remote has its file-host URL set to the files host plus `/packages`, so the mirror adds `/packages/` twice. Fix on the mirror side: set the remote's file-host URL to the bare host `https://files.pythonhosted.org`. No client setting fixes it. This also explains why packages the mirror has already cached download while packages it has never fetched (often the newest, such as httpx2) fail. Until it is fixed, use the fallback and the last-resort step below.

3. New section "## Fallback: install with pip when uv cannot reach the network":
   - What it is: `requirements/locked.txt` and `requirements/build.txt` are exported from uv.lock with a sha256 hash for every file, so pip installs exactly the locked versions from any index (public, or the mirror via `PIP_INDEX_URL`) and refuses any file whose hash differs. This is for running the tool; development still needs uv.
   - Prerequisite: Python 3.12 installed for the current user (the python.org installer's per-user option needs no admin). If a half-made `.venv` exists from a failed `uv sync`, delete it first.
   - PowerShell sequence from the repo checkout, exactly as verified: `py -3.12 -m venv .venv` (or the full path to a 3.12 python.exe); `$env:PATH = "$PWD\.venv\Scripts;$env:PATH"`; the three pip installs with the flags from the context facts; `recover-assess --version` prints `0.1.0`. Explain each non-obvious flag in one line: `--require-hashes` (every file checked against uv.lock), `--no-deps` (the file already lists the full locked set), `--only-binary=:all:` (never builds a source archive), `--no-build-isolation` with build.txt (pip would otherwise download the build backend itself, through the same mirror), `--no-index` on the last step (the project install never touches the network). Explain the PATH line: it replaces `Activate.ps1`, which script execution policy often blocks, and the build backend looks for its helper on PATH.
   - bash sequence: `python3.12 -m venv .venv`, `export PATH="$PWD/.venv/bin:$PATH"` (Git Bash on Windows: `.venv/Scripts`), then the same pip commands with forward slashes.
   - State plainly that this gives the real `recover-assess` console script, so no environment-variable tricks or wrapper scripts are needed. In a later session prepend the PATH again or run `.venv\Scripts\recover-assess.exe` directly. After `git pull`, rerun the locked install and the last step.
   - Last resort subsection, "If one package still will not download": on a machine that can reach public PyPI run `python -m pip download --no-deps --only-binary=:all: --python-version 3.12 --platform win_amd64 -d wheels "<name>==<version from requirements/locked.txt>"` (example httpx2 2.16.0); copy the wheel across; check it with `python -m pip hash <wheel>` and `Select-String -Path requirements\locked.txt -SimpleMatch "<printed sha256>"` (a match is required; stop if there is none); install with `python -m pip install --no-deps --no-index <wheel>`; rerun the locked install, which skips the package already installed and fetches only the rest.

4. Quality-gate text: in "## Developer quick check" update the check.py bullet to list the uv.lock and requirements-export drift checks with the other steps, and add one sentence: after changing dependencies run `uv lock`, then `uv run python scripts/export_requirements.py`, and commit uv.lock and `requirements/` together.

5. Verify the README as written: (a) run the PowerShell bundle recipe verbatim except that the output folder is `$SCRATCH\kqf-tls`, then with `SSL_CERT_FILE` pointing at it run `uv pip compile` on a scratch `in.txt` holding `httpx2==2.16.0` with `--no-cache --python-version 3.12` from `$SCRATCH\kqf-tls` and confirm exit 0; (b) re-run the pip fallback PowerShell sequence verbatim in a fresh `git archive HEAD` copy under `$SCRATCH` (after the Task 1 and 2 commits) and confirm `0.1.0`; (c) run the last-resort subsection verbatim for httpx2 in that venv after `python -m pip uninstall -y httpx2`; (d) the `--locked` offline check from step 2. Start PowerShell probes with `env -u PSModulePath powershell.exe -NoProfile -ExecutionPolicy Bypass -File <probe.ps1>`. Fix the README (not the probe) on any mismatch.

6. Run the full gate `uv run --frozen python scripts/check.py` (blocked-terms and the README repo scan included), then commit: `git add README.md`; message `docs(quick-261116-kqf): corporate-network install guide with a hash-locked pip fallback`. Confirm with `git diff --name-only 0841816 HEAD -- .planning/config.json .planning/state.json` (must print nothing).
  </action>
  <verify>
    <automated>uv run --frozen python scripts/check.py</automated>
  </verify>
  <acceptance_criteria>
  README is prose, so headings are matched exactly and tokens with -F:
  - `grep -c '^## Using a private package mirror$' README.md` [HEAD=0 EXPECT==1]
  - `grep -c '^## Fallback: install with pip when uv cannot reach the network$' README.md` [HEAD=0 EXPECT==1]
  - `grep -c -F 'SSL_CERT_FILE' README.md` [HEAD=1 EXPECT>=3]
  - `grep -c -F 'Cert:\CurrentUser\Root' README.md` [HEAD=0 EXPECT>=1]
  - `grep -c -F 'certutil' README.md` [HEAD=0 EXPECT>=1]
  - `grep -c -F 'UV_DEFAULT_INDEX' README.md` [HEAD=0 EXPECT>=1]
  - `grep -c -F 'UV_INDEX_MIRROR_PASSWORD' README.md` [HEAD=0 EXPECT>=1]
  - `grep -c -F 'packages/packages' README.md` [HEAD=0 EXPECT>=1]
  - `grep -c -F -- '--require-hashes' README.md` [HEAD=0 EXPECT>=3]
  - `grep -c -F -- '--no-build-isolation' README.md` [HEAD=0 EXPECT>=1]
  - `grep -c -F 'pip hash' README.md` [HEAD=0 EXPECT>=1]
  - `grep -c -F 'export_requirements.py' README.md` [HEAD=0 EXPECT>=1]
  - `git diff --name-only 0841816 HEAD -- .planning/config.json .planning/state.json` prints no lines (neither file is in any commit of this task) [HEAD=0 EXPECT==0 @0841816 GUARD MUTATION: git add .planning/config.json]
  </acceptance_criteria>
  <done>README has the extended TLS section, the private-mirror section and the pip fallback with the last-resort wheel step; every command in them was run as written (bundle accepted by uv, fresh-clone pip install prints 0.1.0, single-wheel route works, the `--locked` caveat observed); the gate passes with eight steps; three commits with explicit file lists; no organisation, mirror-product, hostname, ticket or person name anywhere.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| package index or mirror -> workstation | Files fetched by pip or uv from the public index or a private mirror are untrusted until their hash matches uv.lock |
| operator session -> disk and logs | Mirror credentials and CA bundles are typed or built by the operator and must not land in the checkout or in logs |
| uv.lock -> requirements/*.txt | The pip fallback is only as trustworthy as its export staying identical to the reviewed lock |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-261116-kqf-01 | Tampering | pip fallback downloads through a mirror | high | mitigate | `--require-hashes` against hashes exported from uv.lock for both runtime and build files; `--only-binary=:all:` so no source archive's build code runs; `--no-index` for the project install; last-resort wheels must match a hash already in locked.txt (`pip hash` plus `Select-String`, stop on no match) |
| T-261116-kqf-02 | Tampering | requirements/*.txt drifting from uv.lock | high | mitigate | `requirements-export` gate step runs `export_requirements.py --check` (uv export --frozen --offline) on every local and CI gate run; FAIL in CI if uv is missing; offline unit tests cross-check every pin against uv.lock with tomllib |
| T-261116-kqf-03 | Information disclosure | mirror credentials | high | mitigate | README uses session-only env vars (`UV_INDEX_MIRROR_*`, `PIP_INDEX_URL` without embedded credentials, pip prompt), no-echo entry, explicit clearing, and warns against pyproject.toml, uv.toml, pip.ini and `uv auth login` (stores on disk) |
| T-261116-kqf-04 | Spoofing | `SSL_CERT_FILE` bundle | medium | accept | The bundle contains exactly the roots Windows already trusts for this user plus the machine; it adds no trust the OS does not already grant. README tells the operator how to confirm the proxy root is present and that the file replaces uv's own roots |
| T-261116-kqf-05 | Tampering (silent pass) | export_requirements.py failure modes | medium | mitigate | uv missing, uv export non-zero, or unreadable files return exit 2, recorded by the gate as FAIL; a missing export file counts as drift; unit-tested |
| T-261116-kqf-06 | Information disclosure | README, plan, summary, commit messages | high | mitigate | Generic wording only (`<mirror-host>`, "private package mirror"); blocked-terms gate and the README repo scan (no `user:token@host` URLs) run in the gate before every commit |
| T-261116-kqf-07 | Tampering | `.planning/config.json`, `.planning/state.json` | medium | mitigate | Explicit `git add` lists only; Task 3 verifies neither path appears in this task's commits |
| T-261116-kqf-SC | Tampering | package installs | low | mitigate | No new runtime or dev dependency. uv_build is the existing `[build-system]` backend from the same vendor as uv, now also locked in a non-default `build` group (only additions to uv.lock). The throwaway-venv probes install only the locked set plus that pinned backend, hash-checked, in the session scratchpad, never in the project venv |
</threat_model>

<verification>
- `uv run --frozen python scripts/check.py` exits 0; the table shows eight steps: uv-lock-check, requirements-export, ruff-check, ruff-format, mypy, import-contracts, blocked-terms, pytest.
- `uv run --frozen python scripts/export_requirements.py --check` prints `OK requirements/locked.txt` and `OK requirements/build.txt`.
- Drift detection (edited, missing or CRLF-only files) is covered by tests/unit/test_export_requirements.py on `tmp_path` roots; the committed files are never edited by hand.
- The fresh-clone PowerShell probe prints `0.1.0`, imports httpx2 and `pip check` reports no broken requirements.
- `git log --format=%s -3` shows the three quick-261116-kqf commits; none lists `.planning/config.json` or `.planning/state.json`.
</verification>

<success_criteria>
- Hash-locked runtime and build exports exist and match uv.lock (the export `--check` exits 0)
- Gate grows from seven to eight steps and passes locally; CI runs it unchanged
- README gives verified, admin-free commands for the TLS bundle, the private mirror and the pip fallback, ending in a real `recover-assess` console script
- No client, mirror-product, hostname, ticket or person name in any tracked file or commit message; user's uncommitted planning files untouched
</success_criteria>

<output>
Create `.planning/quick/261116-kqf-corporate-network-install-guide-with-has/261116-kqf-SUMMARY.md` when done, including the probe outputs (versions printed, pip check result, the observed `--locked` behaviour with a mirror index). Keep it free of blocked terms and personal paths; run `uv run --frozen python scripts/blocked_terms.py` after staging it.
</output>
