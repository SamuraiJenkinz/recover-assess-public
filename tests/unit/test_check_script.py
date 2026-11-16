"""scripts/check.py aggregation, step order and the CI workflow shape (FND-02, D-02, D-03)."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECK_PATH = ROOT / "scripts" / "check.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"

GATE_STEPS = [
    "uv-lock-check",
    "ruff-check",
    "ruff-format",
    "mypy",
    "import-contracts",
    "blocked-terms",
    "pytest",
]
SHA_USES = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_script", CHECK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_script"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def check() -> ModuleType:
    return _load_check()


def _names(steps: Sequence[Any]) -> list[str]:
    return [step.name for step in steps]


def _fake_runner(
    check: ModuleType, failing: set[str]
) -> tuple[Callable[[Sequence[str]], int], list[tuple[str, ...]]]:
    """A runner that fails exactly the named steps and records every argv it was handed."""
    by_argv = {
        tuple(step.argv): step.name for step in check.build_steps(fix=False, fast=False, environ={})
    }
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str]) -> int:
        calls.append(tuple(argv))
        return 1 if by_argv.get(tuple(argv)) in failing else 0

    return runner, calls


def test_step_names_are_the_seven_gate_steps(check: ModuleType) -> None:
    assert list(check.STEP_NAMES) == GATE_STEPS


def test_build_steps_default_order(check: ModuleType) -> None:
    steps = check.build_steps(fix=False, fast=False, environ={})
    assert _names(steps) == GATE_STEPS


def test_build_steps_argv_shapes(check: ModuleType) -> None:
    steps = {s.name: list(s.argv) for s in check.build_steps(fix=False, fast=False, environ={})}
    py = sys.executable
    assert steps["uv-lock-check"] == ["uv", "lock", "--check"]
    assert steps["ruff-check"] == [py, "-m", "ruff", "check", "."]
    assert steps["ruff-format"] == [py, "-m", "ruff", "format", "--check", "."]
    assert steps["mypy"] == [py, "-m", "mypy"]
    contracts = steps["import-contracts"]
    assert Path(contracts[0]).name in {"lint-imports", "lint-imports.exe"}
    assert Path(contracts[0]).parent == Path(py).parent
    assert contracts[1:] == ["--config", "pyproject.toml", "--no-cache"]
    assert steps["blocked-terms"] == [py, str(CHECK_PATH.parent / "blocked_terms.py")]
    assert steps["pytest"] == [py, "-m", "pytest", "-q"]


def test_build_steps_fix_prepends_writers(check: ModuleType) -> None:
    steps = check.build_steps(fix=True, fast=False, environ={})
    assert _names(steps) == ["ruff-fix", "ruff-format-write", *GATE_STEPS]
    by_name = {s.name: list(s.argv) for s in steps}
    py = sys.executable
    assert by_name["ruff-fix"] == [py, "-m", "ruff", "check", "--fix", "."]
    assert by_name["ruff-format-write"] == [py, "-m", "ruff", "format", "."]


def test_build_steps_fast_deselects_slow(check: ModuleType) -> None:
    steps = {s.name: list(s.argv) for s in check.build_steps(fix=False, fast=True, environ={})}
    assert steps["pytest"][-2:] == ["-m", "not slow"]


def test_one_failure_fails_overall_and_nothing_is_skipped(check: ModuleType) -> None:
    runner, calls = _fake_runner(check, {"ruff-format"})
    steps = check.build_steps(fix=False, fast=False, environ={})
    results = check.run_steps(steps, runner=runner, uv_available=True, in_ci=False)
    assert {r.name: r.status for r in results} == {
        "uv-lock-check": "PASS",
        "ruff-check": "PASS",
        "ruff-format": "FAIL",
        "mypy": "PASS",
        "import-contracts": "PASS",
        "blocked-terms": "PASS",
        "pytest": "PASS",
    }
    assert len(calls) == len(steps)


def test_main_exit_code_one_when_a_step_fails(
    check: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    runner, calls = _fake_runner(check, {"ruff-format"})
    code = check.main([], runner=runner, environ={}, uv_available=True)
    assert code == 1
    assert len(calls) == 7
    out = capsys.readouterr().out
    for name in GATE_STEPS:
        assert name in out
    assert "FAIL" in out


def test_main_exit_code_zero_when_all_pass(
    check: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    runner, _ = _fake_runner(check, set())
    code = check.main([], runner=runner, environ={}, uv_available=True)
    assert code == 0
    out = capsys.readouterr().out
    assert "FAIL" not in out
    assert out.count("PASS") >= 7


def test_every_single_failure_position_gives_exit_one(check: ModuleType) -> None:
    for name in GATE_STEPS:
        runner, calls = _fake_runner(check, {name})
        assert check.main([], runner=runner, environ={}, uv_available=True) == 1
        assert len(calls) == 7


def test_all_pass_results(check: ModuleType) -> None:
    runner, _ = _fake_runner(check, set())
    steps = check.build_steps(fix=False, fast=False, environ={})
    results = check.run_steps(steps, runner=runner, uv_available=True, in_ci=False)
    assert [r.status for r in results] == ["PASS"] * 7
    assert all(r.seconds >= 0 for r in results)


def test_uv_missing_outside_ci_is_skip(check: ModuleType) -> None:
    runner, calls = _fake_runner(check, set())
    steps = check.build_steps(fix=False, fast=False, environ={})
    results = check.run_steps(steps, runner=runner, uv_available=False, in_ci=False)
    first = results[0]
    assert (first.name, first.status, first.detail) == ("uv-lock-check", "SKIP", "uv not on PATH")
    assert len(calls) == 6
    assert check.main([], runner=runner, environ={}, uv_available=False) == 0


def test_uv_missing_in_ci_is_fail(check: ModuleType) -> None:
    runner, _ = _fake_runner(check, set())
    steps = check.build_steps(fix=False, fast=False, environ={"CI": "true"})
    results = check.run_steps(steps, runner=runner, uv_available=False, in_ci=True)
    assert results[0].status == "FAIL"
    assert check.main([], runner=runner, environ={"CI": "true"}, uv_available=False) == 1


def test_render_table_has_header_and_a_row_per_result(check: ModuleType) -> None:
    results = [
        check.StepResult("mypy", "PASS", 1.5, ""),
        check.StepResult("pytest", "FAIL", 2.0, "exit 1"),
    ]
    lines = check.render_table(results).splitlines()
    assert lines[0].split() == ["STEP", "STATUS", "SECONDS", "DETAIL"]
    assert "mypy" in lines[1]
    assert "PASS" in lines[1]
    assert "exit 1" in lines[2]


def test_help_lists_fix_and_fast() -> None:
    proc = subprocess.run(
        [sys.executable, str(CHECK_PATH), "--help"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert proc.returncode == 0
    assert "--fix" in proc.stdout
    assert "--fast" in proc.stdout


# --- CI workflow shape (D-02, T-01-08) ---


@pytest.fixture(scope="module")
def workflow() -> dict[Any, Any]:
    loaded = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _steps(workflow: dict[Any, Any]) -> list[dict[str, Any]]:
    steps = workflow["jobs"]["check"]["steps"]
    assert isinstance(steps, list)
    return steps


def test_workflow_triggers_push_and_pull_request(workflow: dict[Any, Any]) -> None:
    # PyYAML parses the bare key `on` as boolean True.
    triggers = workflow[True] if True in workflow else workflow["on"]
    assert set(triggers) == {"push", "pull_request"}


def test_workflow_matrix_is_windows_and_ubuntu(workflow: dict[Any, Any]) -> None:
    job = workflow["jobs"]["check"]
    assert job["strategy"]["matrix"]["os"] == ["windows-latest", "ubuntu-latest"]
    assert job["strategy"]["fail-fast"] is False
    assert job["runs-on"] == "${{ matrix.os }}"
    assert job["env"]["PYTHONUTF8"] == "1"
    assert job["env"]["HYPOTHESIS_PROFILE"] == "ci"


def test_workflow_permissions_are_contents_read_only(workflow: dict[Any, Any]) -> None:
    assert workflow["permissions"] == {"contents": "read"}


def test_workflow_every_action_is_sha_pinned(workflow: dict[Any, Any]) -> None:
    uses = [step["uses"] for step in _steps(workflow) if "uses" in step]
    assert len(uses) == 2
    for value in uses:
        assert SHA_USES.match(value), value


def test_workflow_pins_uv_version(workflow: dict[Any, Any]) -> None:
    setup = [
        s for s in _steps(workflow) if str(s.get("uses", "")).startswith("astral-sh/setup-uv@")
    ]
    assert len(setup) == 1
    assert setup[0]["with"]["version"] == "0.13.8"


def test_workflow_runs_the_single_gate_last(workflow: dict[Any, Any]) -> None:
    runs = [s["run"] for s in _steps(workflow) if "run" in s]
    assert runs == ["uv python install", "uv sync --locked", "uv run python scripts/check.py"]
    assert "uv run python scripts/check.py" in WORKFLOW_PATH.read_text(encoding="utf-8")
