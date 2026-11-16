# recover-assess

`recover-assess` is a read-only command-line tool. It collects evidence about
SharePoint sites from Microsoft Graph and produces a per-site assessment: an
effort rating calculated in code, a recommended action and a plain-English
plan. It only ever issues `GET` requests (and `POST /$batch` wrapping `GET`s),
so it never writes to Microsoft 365.

## Install (Windows 11, no admin rights)

Everything installs into your user profile. No step needs an elevated shell.

1. Download the versioned uv 0.13.8 release archive
   (`uv-x86_64-pc-windows-msvc.zip`) and its `.sha256` file from the uv
   GitHub releases page. Do not pipe a remote installer script into a shell.
2. Compare the archive hash with the published value, either with
   `(Get-FileHash <archive> -Algorithm SHA256).Hash` or with
   `python scripts/verify_sha256.py <archive> <sidecar>`. Stop if they differ.
3. Extract `uv.exe` into `%USERPROFILE%\.local\bin` and make sure that folder
   is on your `PATH`.
4. Install the pinned interpreter, then the locked environment:

```powershell
uv python install 3.12
uv sync --locked
uv run recover-assess --version
```

The last command prints `0.1.0`.

## Behind a TLS-inspecting proxy

uv ships its own set of root certificates, so a corporate proxy that
re-signs HTTPS traffic can make `uv python install` and `uv sync` fail with a
certificate error. Set `UV_SYSTEM_CERTS=true` so uv uses the operating system
trust store instead.

PowerShell:

```powershell
$env:UV_SYSTEM_CERTS = "true"
```

bash:

```bash
export UV_SYSTEM_CERTS=true
```

`SSL_CERT_FILE` and `SSL_CERT_DIR` override the certificate source entirely if
you need to point at a specific CA bundle. `HTTPS_PROXY` and `NO_PROXY` are
honoured.

If `uv python install` itself cannot download an interpreter behind the proxy,
install Python 3.12 by another approved route and tell uv not to download one:

```powershell
$env:UV_PYTHON_DOWNLOADS = "never"
```

```bash
export UV_PYTHON_DOWNLOADS=never
```

## Configuration

Operator and client settings live only in an external `recover-assess.yaml`
file. Point the tool at it with `--config` or the `RECOVER_ASSESS_CONFIG`
environment variable. That file is never committed to this repository.

## Quality gate

Run the single local and CI quality gate with:

```powershell
uv run python scripts/check.py
```

## Developer quick check

Four commands cover everything a contributor needs to know the tree is healthy:

```powershell
uv run python scripts/check.py
uv run pytest tests/integration/test_phase1_acceptance.py -q
uv run python scripts/gen_schemas.py --check
uv run recover-assess config show --config recover-assess.example.yaml
```

- `uv run python scripts/check.py` runs the same gate as CI: ruff, format,
  mypy strict, import contracts, the blocked-term check and the tests.
- `uv run pytest tests/integration/test_phase1_acceptance.py -q` runs the
  read-only client end to end on a fake Graph: five sites through two slots, one
  of them throttled until its breaker opens.
- `uv run python scripts/gen_schemas.py --check` confirms the checked-in
  fact-sheet schema matches the models.
- `uv run recover-assess config show --config recover-assess.example.yaml`
  prints the effective configuration.
