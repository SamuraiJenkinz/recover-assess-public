"""Single local and CI quality gate for recover-assess (D-03).

Runs, in order: uv lock --check, the requirements export drift check, ruff check,
ruff format --check, mypy, lint-imports, the blocked-term scan of every tracked file, pytest.
Every step runs even after an earlier failure, so one run reports everything.
The exit code is 0 only when no step failed.

Usage: uv run python scripts/check.py [--fix] [--fast]

Standard library only, so it runs before the project environment is trusted.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent

STEP_NAMES: tuple[str, ...] = (
    "uv-lock-check",
    "requirements-export",
    "ruff-check",
    "ruff-format",
    "mypy",
    "import-contracts",
    "blocked-terms",
    "pytest",
)

# Steps that shell out to uv: skipped locally, failed in CI, when uv is not on PATH.
NEEDS_UV: frozenset[str] = frozenset({"uv-lock-check", "requirements-export"})

Status = Literal["PASS", "FAIL", "SKIP"]
Runner = Callable[[Sequence[str]], int]


@dataclass(frozen=True)
class Step:
    name: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class StepResult:
    name: str
    status: Status
    seconds: float
    detail: str


def _lint_imports_executable() -> str:
    suffix = ".exe" if sys.platform == "win32" else ""
    return str(Path(sys.executable).parent / f"lint-imports{suffix}")


def build_steps(*, fix: bool, fast: bool, environ: Mapping[str, str]) -> list[Step]:
    """Return the ordered steps. ``environ`` is accepted so callers can pass the CI context."""
    del environ  # reserved: the argv does not currently vary with the environment
    py = sys.executable
    steps: list[Step] = []
    if fix:
        steps.append(Step("ruff-fix", (py, "-m", "ruff", "check", "--fix", ".")))
        steps.append(Step("ruff-format-write", (py, "-m", "ruff", "format", ".")))
    pytest_argv: tuple[str, ...] = (py, "-m", "pytest", "-q")
    if fast:
        pytest_argv = (*pytest_argv, "-m", "not slow")
    steps.extend(
        [
            Step("uv-lock-check", ("uv", "lock", "--check")),
            Step(
                "requirements-export",
                (py, str(ROOT / "scripts" / "export_requirements.py"), "--check"),
            ),
            Step("ruff-check", (py, "-m", "ruff", "check", ".")),
            Step("ruff-format", (py, "-m", "ruff", "format", "--check", ".")),
            Step("mypy", (py, "-m", "mypy")),
            Step(
                "import-contracts",
                (_lint_imports_executable(), "--config", "pyproject.toml", "--no-cache"),
            ),
            Step("blocked-terms", (py, str(ROOT / "scripts" / "blocked_terms.py"))),
            Step("pytest", pytest_argv),
        ]
    )
    return steps


def default_runner(argv: Sequence[str]) -> int:
    """Run one step in the repository root, streaming its output to the console."""
    try:
        return subprocess.run(list(argv), cwd=ROOT, check=False).returncode
    except FileNotFoundError:
        return 127


def run_steps(
    steps: Sequence[Step], *, runner: Runner, uv_available: bool, in_ci: bool
) -> list[StepResult]:
    """Run every step, never stopping early, and return one result per step."""
    results: list[StepResult] = []
    for step in steps:
        started = time.perf_counter()
        if step.name in NEEDS_UV and not uv_available:
            status: Status = "FAIL" if in_ci else "SKIP"
            results.append(StepResult(step.name, status, 0.0, "uv not on PATH"))
            continue
        code = runner(step.argv)
        elapsed = time.perf_counter() - started
        if code == 0:
            results.append(StepResult(step.name, "PASS", elapsed, ""))
        else:
            results.append(StepResult(step.name, "FAIL", elapsed, f"exit {code}"))
    return results


def render_table(results: Sequence[StepResult]) -> str:
    """Return an aligned STEP / STATUS / SECONDS / DETAIL table."""
    rows = [(r.name, r.status, f"{r.seconds:.1f}", r.detail) for r in results]
    header = ("STEP", "STATUS", "SECONDS", "DETAIL")
    widths = (
        [max(len(header[i]), *(len(row[i]) for row in rows)) for i in range(4)]
        if rows
        else [len(h) for h in header]
    )
    lines = [
        "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip()
        for row in (header, *rows)
    ]
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check.py",
        description=(
            "Run the full quality gate: lock, requirements export, lint, format, types, "
            "contracts, blocked terms, tests."
        ),
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="run 'ruff check --fix' and 'ruff format' before the read-only steps",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="deselect tests marked slow",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Runner | None = None,
    environ: Mapping[str, str] | None = None,
    uv_available: bool | None = None,
) -> int:
    """Run the gate. The keyword arguments exist so tests can inject a fake runner."""
    args = _parser().parse_args(list(argv) if argv is not None else None)
    env: Mapping[str, str] = environ if environ is not None else os.environ
    in_ci = bool(env.get("CI"))
    available = uv_available if uv_available is not None else shutil.which("uv") is not None
    steps = build_steps(fix=args.fix, fast=args.fast, environ=env)
    results = run_steps(
        steps,
        runner=runner if runner is not None else default_runner,
        uv_available=available,
        in_ci=in_ci,
    )
    print()
    print(render_table(results))
    return 1 if any(r.status == "FAIL" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
