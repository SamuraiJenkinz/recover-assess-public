"""Each architecture rule turns the gate red when violated (FND-02, D-04).

Every case runs against its own tmp copy of the committed src tree and the real, unmodified
contracts in pyproject.toml.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tests.support.import_violations import (
    CASES,
    REPO_ROOT,
    ViolationCase,
    has_git_checkout,
    run_lint_imports_on_copy,
)

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not has_git_checkout(), reason="no .git directory"),
]


@pytest.mark.parametrize("case", CASES, ids=[c.case_id for c in CASES])
def test_violation_breaks_expected_contract(case: ViolationCase, tmp_path: Path) -> None:
    code, output = run_lint_imports_on_copy(tmp_path, case)
    assert code == 1, output
    broken = [line for line in output.splitlines() if "BROKEN" in line]
    assert any(case.expected_contract_name in line for line in broken), output


def test_control_copy_kept(tmp_path: Path) -> None:
    code, output = run_lint_imports_on_copy(tmp_path, None)
    assert code == 0, output
    assert "BROKEN" not in output


def _manifest(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def test_whole_tree_untouched_by_violation_run(tmp_path: Path) -> None:
    src = REPO_ROOT / "src" / "recover_assess"
    before = _manifest(src)
    code, output = run_lint_imports_on_copy(tmp_path, CASES[0])
    assert code == 1, output
    assert _manifest(src) == before
    assert not (src / "core" / "zz_violation.py").exists()
