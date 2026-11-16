"""Deliberate architecture violations, run against the REAL import-linter contracts (D-04).

Each case adds one forbidden import to a tmp copy of the COMMITTED src tree (``git archive
HEAD``, so a sibling's uncommitted in-progress write cannot change a verdict) and runs
``lint-imports --config <real pyproject.toml> --no-cache`` against it. The contracts are never
copied or edited, and the real working tree is never touched.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_PYPROJECT = REPO_ROOT / "pyproject.toml"
PACKAGE_DIR = "src/recover_assess"


@dataclass(frozen=True)
class ViolationCase:
    case_id: str
    relative_module_path: str  # under src/recover_assess
    source_text: str
    expected_contract_name: str


CASES: tuple[ViolationCase, ...] = (
    ViolationCase(
        "core-imports-cli",
        "core/zz_violation.py",
        "import recover_assess.cli\n",
        "core never imports cli",
    ),
    ViolationCase(
        "collect-imports-httpx2",
        "core/collect/zz_violation.py",
        "import httpx2\n",
        "httpx2 only in graph and providers",
    ),
    ViolationCase(
        "score-imports-requests",
        "core/score/zz_violation.py",
        "import requests\n",
        "score/agent/report import no network libs",
    ),
    ViolationCase(
        "agent-imports-openai",
        "core/agent/zz_violation.py",
        "import openai\n",
        "LLM SDKs only in providers",
    ),
    ViolationCase(
        "score-imports-graph",
        "core/score/zz_violation.py",
        "from recover_assess.core import graph\n",
        "score/agent/report import no network libs",
    ),
    ViolationCase(
        "report-from-httpx2",
        "core/report/zz_violation.py",
        "from httpx2 import AsyncClient\n",
        "httpx2 only in graph and providers",
    ),
    ViolationCase(
        "core-imports-typer",
        "core/zz_violation.py",
        "import typer\n",
        "typer and rich only in cli",
    ),
)


def has_git_checkout() -> bool:
    """True when the repository root has a .git entry (directory, or file in a worktree)."""
    return (REPO_ROOT / ".git").exists()


def snapshot_committed_src(dest: Path) -> None:
    """Extract the committed ``src/recover_assess`` tree into ``dest``."""
    archive = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD", PACKAGE_DIR],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        tar.extractall(dest, filter="data")


def _lint_imports_executable() -> str:
    suffix = ".exe" if sys.platform == "win32" else ""
    return str(Path(sys.executable).parent / f"lint-imports{suffix}")


def run_lint_imports_on_copy(tmp_path: Path, case: ViolationCase | None) -> tuple[int, str]:
    """Snapshot the committed tree into ``tmp_path``, apply ``case``, run lint-imports.

    Returns ``(exit code, stdout + stderr)``. ``--no-cache`` keeps parallel or interrupted runs
    from leaving a grimp cache that could hide a violation.
    """
    snapshot_committed_src(tmp_path)
    if case is not None:
        target = tmp_path / "src" / "recover_assess" / case.relative_module_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(case.source_text, encoding="utf-8", newline="\n")
    src = str(tmp_path / "src")
    existing = os.environ.get("PYTHONPATH")
    env = {**os.environ, "PYTHONPATH": src if not existing else src + os.pathsep + existing}
    proc = subprocess.run(
        [_lint_imports_executable(), "--config", str(REAL_PYPROJECT), "--no-cache"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr
