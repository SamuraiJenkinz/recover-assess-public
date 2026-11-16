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

### If uv still reports certificate errors

Point uv at a PEM bundle with `SSL_CERT_FILE`. Two behaviours matter:

- The file replaces uv's trust set entirely. A bundle that holds only the proxy
  root CA makes every other site fail with `UnknownIssuer`.
- A wrong path does not fall back: uv warns that no default certificates will
  be trusted.

So build the bundle from the whole Windows root store, which already contains
the proxy root CA. Reading the user and machine stores needs no admin rights.

PowerShell:

```powershell
$dir = "$env:USERPROFILE\.certs"
New-Item -ItemType Directory -Force $dir | Out-Null
$certs = @(Get-ChildItem Cert:\CurrentUser\Root) + @(Get-ChildItem Cert:\LocalMachine\Root) |
    Sort-Object Thumbprint -Unique
$pem = foreach ($c in $certs) {
    "-----BEGIN CERTIFICATE-----"
    [Convert]::ToBase64String($c.RawData, "InsertLineBreaks")
    "-----END CERTIFICATE-----"
}
Set-Content -Path "$dir\windows-roots.pem" -Value $pem -Encoding ascii
$env:SSL_CERT_FILE = "$dir\windows-roots.pem"
```

`-Encoding ascii` avoids the byte order mark that Windows PowerShell 5.1 adds
with `utf8`. To confirm the proxy root CA is in the store (use part of its
name):

```powershell
Get-ChildItem Cert:\CurrentUser\Root | Where-Object Subject -like "*<part of the proxy CA name>*"
```

A CA imported under "Intermediate Certification Authorities" is not a root.
Import it again under "Trusted Root Certification Authorities" for the current
user.

To export one root from the user store instead (for example to append the proxy
root to another bundle), use its thumbprint:

```powershell
certutil -user -store Root <thumbprint> proxy-root.cer
certutil -f -encode proxy-root.cer proxy-root.pem
```

bash (Git Bash reads the same file):

```bash
export SSL_CERT_FILE="$HOME/.certs/windows-roots.pem"
```

On macOS or Linux, point `SSL_CERT_FILE` at a bundle that contains the proxy
root CA.

`recover-assess` honours `SSL_CERT_FILE` too (its HTTP client checks it before
the operating system store), so a bundle built this way is safe to leave set.
`Remove-Item Env:SSL_CERT_FILE` clears it for the current session.

pip uses the Windows trust store directly (it ships its own copy of truststore
and uses it by default), so if uv still cannot connect, the
[pip fallback](#fallback-install-with-pip-when-uv-cannot-reach-the-network)
works with the store as it is. `--cert <bundle.pem>` overrides it.

If `uv python install` itself cannot download an interpreter behind the proxy,
install Python 3.12 by another approved route and tell uv not to download one:

```powershell
$env:UV_PYTHON_DOWNLOADS = "never"
```

```bash
export UV_PYTHON_DOWNLOADS=never
```

## Using a private package mirror

If your organisation reaches PyPI only through a private package mirror, point
uv at it with `UV_DEFAULT_INDEX` in the named form. Use the mirror's PyPI
remote URL ending in `/simple`. `UV_INDEX_URL` still works, but uv 0.13.8
marks it deprecated.

Credentials stay in the session. Never put them in `pyproject.toml`, `uv.toml`,
`pip.ini` or any file in the checkout, and do not use `uv auth login`, which
saves them on disk. The name after `UV_INDEX_` is the index name from the URL,
upper-cased, so `mirror` becomes `MIRROR`. The password is normally the
mirror's access token.

PowerShell (the token is typed without echo):

```powershell
$env:UV_DEFAULT_INDEX = "mirror=https://<mirror-host>/<path-to-pypi-remote>/simple"
$env:UV_INDEX_MIRROR_USERNAME = "<your-mirror-user-name>"
$secure = Read-Host "Mirror access token" -AsSecureString
$env:UV_INDEX_MIRROR_PASSWORD = [System.Net.NetworkCredential]::new("", $secure).Password
```

bash:

```bash
export UV_DEFAULT_INDEX="mirror=https://<mirror-host>/<path-to-pypi-remote>/simple"
export UV_INDEX_MIRROR_USERNAME="<your-mirror-user-name>"
read -rsp "Mirror access token: " UV_INDEX_MIRROR_PASSWORD; echo
export UV_INDEX_MIRROR_PASSWORD
```

When you are done, clear them: `Remove-Item Env:UV_INDEX_MIRROR_PASSWORD` in
PowerShell, `unset UV_INDEX_MIRROR_PASSWORD` in bash.

### What this does to `uv.lock`

`uv.lock` records the public index. With a different default index, uv
re-resolves through the mirror, so `uv sync --locked` cannot use the committed
lock (observed: it stops with a resolution error instead of installing).
`uv sync --frozen` ignores the mirror setting and downloads the exact files
listed in `uv.lock` from the public file host. If that host is reachable
through your proxy, you do not need the mirror at all.

If only the mirror is reachable, run `uv sync` (without `--locked`), then
`git diff uv.lock`. Only URLs may change. If any version or hash changed, stop
and use the pip fallback below. Never commit that local `uv.lock` change.

For pip, set the index for the session only. pip asks for the user name and
token when the mirror answers 401; do not store them in `pip.ini`:

```powershell
$env:PIP_INDEX_URL = "https://<mirror-host>/<path-to-pypi-remote>/simple"
```

```bash
export PIP_INDEX_URL="https://<mirror-host>/<path-to-pypi-remote>/simple"
```

### Diagnosis note for whoever runs the mirror

Symptom: downloads fail with HTTP 403, and the failing URL (shown by
`uv sync -v` or `python -m pip download -v --no-deps <name>==<version>`)
contains `/packages/packages/`.

Likely cause: the mirror's PyPI remote has its file-host URL set to the files
host plus `/packages`, so the mirror adds `/packages/` twice. Fix on the mirror
side: set the remote's file-host URL to the bare host
`https://files.pythonhosted.org`. No client setting fixes it.

This also explains why packages the mirror has already cached download while
packages it has never fetched (often the newest) fail. Until it is fixed, use
the pip fallback and the last-resort step below.

## Fallback: install with pip when uv cannot reach the network

`requirements/locked.txt` and `requirements/build.txt` are exported from
`uv.lock` with a sha256 hash for every file. pip therefore installs exactly the
locked versions from any index (public, or the mirror through `PIP_INDEX_URL`)
and refuses any file whose hash differs. This route is for running the tool;
development still needs uv.

Prerequisite: Python 3.12 installed for the current user (the python.org
installer's per-user option needs no admin rights). If a half-made `.venv` is
left over from a failed `uv sync`, delete it first.

PowerShell, from the repository checkout:

```powershell
py -3.12 -m venv .venv
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"
python -m pip install --require-hashes --no-deps --only-binary=:all: -r requirements\locked.txt
python -m pip install --require-hashes --no-deps --only-binary=:all: -r requirements\build.txt
python -m pip install --no-index --no-deps --no-build-isolation .
recover-assess --version
```

The last command prints `0.1.0`. What the flags do:

- `--require-hashes` checks every downloaded file against the hash from `uv.lock`.
- `--no-deps` is safe because the file already lists the full locked set.
- `--only-binary=:all:` never builds a source archive, so no downloaded build
  code runs.
- `--no-build-isolation` with `build.txt`: pip would otherwise download the build
  backend itself, through the same mirror, outside the locked set.
- `--no-index` on the last step: installing the project never touches the network.

The `PATH` line replaces `Activate.ps1`, which script execution policy often
blocks, and the build backend looks for its helper program on `PATH`.

bash (on Git Bash for Windows use `.venv/Scripts` instead of `.venv/bin`):

```bash
python3.12 -m venv .venv
export PATH="$PWD/.venv/bin:$PATH"
python -m pip install --require-hashes --no-deps --only-binary=:all: -r requirements/locked.txt
python -m pip install --require-hashes --no-deps --only-binary=:all: -r requirements/build.txt
python -m pip install --no-index --no-deps --no-build-isolation .
recover-assess --version
```

This gives the real `recover-assess` console script, so no environment-variable
tricks or wrapper scripts are needed. In a later session, prepend the `PATH`
again or run `.venv\Scripts\recover-assess.exe` directly. After `git pull`,
rerun the two locked installs and the last step.

### If one package still will not download

On a machine that can reach public PyPI, fetch the single wheel at the version
listed in `requirements/locked.txt` (here `httpx2` 2.16.0 as the example):

```powershell
python -m pip download --no-deps --only-binary=:all: --python-version 3.12 --platform win_amd64 -d wheels "httpx2==2.16.0"
python -m pip hash wheels\httpx2-2.16.0-py3-none-any.whl
Select-String -Path requirements\locked.txt -SimpleMatch "<the --hash=sha256 value printed above>"
```

A match is required. If `Select-String` prints nothing, stop: the wheel is not
the one that was locked. Copy the wheel across and install it:

```powershell
python -m pip install --no-deps --no-index wheels\httpx2-2.16.0-py3-none-any.whl
```

Then rerun the locked install. pip skips the package that is already installed
and fetches only the rest.

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

- `uv run python scripts/check.py` runs the same gate as CI: the `uv.lock` and
  requirements export drift checks, ruff, format, mypy strict, import
  contracts, the blocked-term check and the tests.
- `uv run pytest tests/integration/test_phase1_acceptance.py -q` runs the
  read-only client end to end on a fake Graph: five sites through two slots, one
  of them throttled until its breaker opens.
- `uv run python scripts/gen_schemas.py --check` confirms the checked-in
  fact-sheet schema matches the models.
- `uv run recover-assess config show --config recover-assess.example.yaml`
  prints the effective configuration.

After changing dependencies, run `uv lock`, then
`uv run python scripts/export_requirements.py`, and commit `uv.lock` and
`requirements/` together.
