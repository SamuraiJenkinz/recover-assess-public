"""Generate or check the hash-locked pip requirement files exported from uv.lock.

Usage:
    uv run python scripts/export_requirements.py            # regenerate requirements/*.txt
    uv run python scripts/export_requirements.py --check    # exit 1 on drift, never write

Exit codes: 0 in sync (or written), 1 drift found by --check, 2 the export could not run
(uv missing, uv export failed, a file could not be written). The gate treats 2 as a failure,
so a broken export can never pass silently.

The files let an operator install the locked runtime set with pip when uv cannot reach the
network; see the README. A file whose content differs only by CRLF line endings is not drift.

Standard library only, so it runs before the project environment is trusted.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGENERATE_HINT = "regenerate with uv run python scripts/export_requirements.py"

# --frozen: uv.lock is read and never updated. --offline: the gate never touches the network.
BASE_ARGS: tuple[str, ...] = (
    "export",
    "--frozen",
    "--offline",
    "--format",
    "requirements.txt",
    "--no-emit-project",
    "--no-header",
)


@dataclass(frozen=True)
class Export:
    relpath: str
    purpose: str
    selector: tuple[str, ...]


EXPORTS: tuple[Export, ...] = (
    Export(
        "requirements/locked.txt",
        "runtime dependencies for the pip fallback install, see README",
        ("--no-dev",),
    ),
    Export(
        "requirements/build.txt",
        "build backend for pip install --no-build-isolation, see README",
        ("--only-group", "build"),
    ),
)

Exporter = Callable[[Path, Sequence[str]], str]


class ExportError(Exception):
    """The export could not be produced; the cause is carried in the message."""


def header(export: Export) -> str:
    """The fixed two-line comment header written above every export."""
    source = "exported from uv.lock by scripts/export_requirements.py."
    return (
        f"# Hash-locked {export.purpose}, {source}\n"
        "# Do not edit. Regenerate with: uv run python scripts/export_requirements.py\n"
    )


def run_uv_export(root: Path, args: Sequence[str]) -> str:
    """Run ``uv <args>`` in ``root`` and return its stdout; raise ExportError on any failure."""
    uv = shutil.which("uv")
    if uv is None:
        raise ExportError("uv is not on PATH")
    done = subprocess.run([uv, *args], cwd=root, capture_output=True, check=False)
    if done.returncode != 0:
        lines = done.stderr.decode("utf-8", errors="replace").strip().splitlines()
        last = lines[-1] if lines else "no error output"
        raise ExportError(f"uv export exited {done.returncode}: {last}")
    return done.stdout.decode("utf-8")


def expected_text(root: Path, export: Export, exporter: Exporter) -> str:
    """The exact text the file must hold: header plus a fresh export, LF line endings."""
    body = exporter(root, (*BASE_ARGS, *export.selector))
    return header(export) + body.replace("\r\n", "\n")


def _on_disk(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError):
        return None


def check(root: Path, exporter: Exporter) -> int:
    """Report drift for every export; return 1 if any file differs or is missing."""
    drifted = False
    for export in EXPORTS:
        wanted = expected_text(root, export, exporter)
        if _on_disk(root / export.relpath) == wanted:
            print(f"OK {export.relpath}")
        else:
            print(f"DRIFT {export.relpath}: {REGENERATE_HINT}")
            drifted = True
    return 1 if drifted else 0


def generate(root: Path, exporter: Exporter) -> int:
    """Write every export under ``root`` (UTF-8, LF), replacing each file atomically."""
    for export in EXPORTS:
        text = expected_text(root, export, exporter)
        target = root / export.relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + ".tmp")
        temp.write_text(text, encoding="utf-8", newline="\n")
        temp.replace(target)
        print(f"WROTE {export.relpath}")
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    root: Path | None = None,
    exporter: Exporter | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Generate or check hash-locked requirements exported from uv.lock."
    )
    parser.add_argument("--check", action="store_true", help="exit 1 on drift; never write")
    args = parser.parse_args(list(argv) if argv is not None else None)
    base = root if root is not None else ROOT
    run = exporter if exporter is not None else run_uv_export
    try:
        return check(base, run) if args.check else generate(base, run)
    except (ExportError, OSError) as exc:
        print(f"export-requirements: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
