"""scripts/export_requirements.py: generation, drift check and offline consistency (quick-kqf)."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "export_requirements.py"

HASH_LINE = "    --hash=sha256:" + "a" * 64
FAKE_BODY = "pkg==1.0 \\\n" + HASH_LINE + "\n"
BASE_ARGS = (
    "export",
    "--frozen",
    "--offline",
    "--format",
    "requirements.txt",
    "--no-emit-project",
    "--no-header",
)
DEV_ONLY_NAMES = {
    "pytest",
    "ruff",
    "mypy",
    "hypothesis",
    "import-linter",
    "jsonschema",
    "uv-build",
}
ENTRY = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[^\s;\\]+)")
HASH = re.compile(r"--hash=sha256:[0-9a-f]{64}")


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("export_requirements_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["export_requirements_script"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def exp() -> ModuleType:
    return _load()


class FakeExporter:
    def __init__(self, body: str = FAKE_BODY) -> None:
        self.body = body
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, root: Path, args: Sequence[str]) -> str:
        self.calls.append(tuple(args))
        return self.body


def _expected(exp: ModuleType, relpath: str, body: str = FAKE_BODY) -> str:
    export = next(e for e in exp.EXPORTS if e.relpath == relpath)
    return str(exp.header(export)) + body


def test_header_is_two_comment_lines(exp: ModuleType) -> None:
    for export in exp.EXPORTS:
        lines = exp.header(export).splitlines()
        assert len(lines) == 2
        assert all(line.startswith("# ") for line in lines)
        assert "uv run python scripts/export_requirements.py" in lines[1]


def test_generate_writes_lf_only_files_with_header(exp: ModuleType, tmp_path: Path) -> None:
    code = exp.generate(tmp_path, FakeExporter())
    assert code == 0
    for relpath in ("requirements/locked.txt", "requirements/build.txt"):
        data = (tmp_path / relpath).read_bytes()
        assert b"\r" not in data
        assert data.decode("utf-8") == _expected(exp, relpath)
    assert exp.check(tmp_path, FakeExporter()) == 0


def test_check_ok_prints_both_paths(
    exp: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exp.generate(tmp_path, FakeExporter())
    capsys.readouterr()
    assert exp.check(tmp_path, FakeExporter()) == 0
    out = capsys.readouterr().out
    assert "OK requirements/locked.txt" in out
    assert "OK requirements/build.txt" in out


def test_check_edited_file_is_drift_and_never_writes(
    exp: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exp.generate(tmp_path, FakeExporter())
    target = tmp_path / "requirements" / "locked.txt"
    target.write_bytes(target.read_bytes() + b"extra==9.9\n")
    before = target.read_bytes()
    capsys.readouterr()
    assert exp.check(tmp_path, FakeExporter()) == 1
    out = capsys.readouterr().out
    assert "DRIFT requirements/locked.txt: regenerate with uv run python scripts/" in out
    assert target.read_bytes() == before


def test_check_missing_file_is_drift_and_never_creates(
    exp: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exp.generate(tmp_path, FakeExporter())
    missing = tmp_path / "requirements" / "build.txt"
    missing.unlink()
    capsys.readouterr()
    assert exp.check(tmp_path, FakeExporter()) == 1
    assert "DRIFT requirements/build.txt" in capsys.readouterr().out
    assert not missing.exists()


def test_crlf_only_difference_is_not_drift(exp: ModuleType, tmp_path: Path) -> None:
    exp.generate(tmp_path, FakeExporter())
    for relpath in ("requirements/locked.txt", "requirements/build.txt"):
        target = tmp_path / relpath
        target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
    assert exp.check(tmp_path, FakeExporter()) == 0


def test_exporter_arguments_select_runtime_and_build_group(exp: ModuleType, tmp_path: Path) -> None:
    fake = FakeExporter()
    exp.generate(tmp_path, fake)
    assert (*BASE_ARGS, "--no-dev") in fake.calls
    assert (*BASE_ARGS, "--only-group", "build") in fake.calls
    for call in fake.calls:
        assert call[0] == "export"
        assert not {"lock", "sync", "--upgrade"} & set(call)


def test_main_returns_2_when_uv_is_missing(
    exp: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(exp.shutil, "which", lambda _name: None)
    assert exp.main(["--check"], root=tmp_path) == 2
    err = capsys.readouterr().err
    assert "export-requirements:" in err
    assert "uv" in err


def test_main_returns_2_when_uv_export_fails(
    exp: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(exp.shutil, "which", lambda _name: "uv")

    def fake_run(argv: Sequence[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(list(argv), 3, b"", b"first\nlockfile needs update\n")

    monkeypatch.setattr(exp.subprocess, "run", fake_run)
    assert exp.main(["--check"], root=tmp_path) == 2
    err = capsys.readouterr().err
    assert "export-requirements:" in err
    assert "lockfile needs update" in err
    assert not (tmp_path / "requirements").exists()


def test_main_check_uses_injected_exporter(exp: ModuleType, tmp_path: Path) -> None:
    assert exp.main([], root=tmp_path, exporter=FakeExporter()) == 0
    assert exp.main(["--check"], root=tmp_path, exporter=FakeExporter()) == 0


# --- offline consistency of the committed files -------------------------------------------------


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _entries(relpath: str) -> dict[str, tuple[str, int]]:
    """Map normalised name to (version, hash count) for one committed requirements file."""
    text = (ROOT / relpath).read_text(encoding="utf-8")
    found: dict[str, tuple[str, int]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = ENTRY.match(line)
        if match:
            current = _normalise(match.group("name"))
            found[current] = (match.group("version"), 0)
            continue
        if current is not None and HASH.search(line):
            version, count = found[current]
            found[current] = (version, count + 1)
    return found


def _lock_versions() -> dict[str, str]:
    data = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    return {_normalise(p["name"]): p["version"] for p in data["package"]}


def _pyproject() -> dict[str, object]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_committed_locked_txt_pins_are_hashed_and_match_uv_lock() -> None:
    entries = _entries("requirements/locked.txt")
    lock = _lock_versions()
    assert entries
    for name, (version, hashes) in entries.items():
        assert hashes >= 1, f"{name} has no sha256 hash"
        assert lock[name] == version, f"{name} pin differs from uv.lock"


def test_committed_locked_txt_covers_runtime_dependencies_only() -> None:
    entries = _entries("requirements/locked.txt")
    project = _pyproject()["project"]
    assert isinstance(project, dict)
    for spec in project["dependencies"]:
        name = _normalise(re.split(r"[\[~=<>!; ]", spec, maxsplit=1)[0])
        assert name in entries, f"runtime dependency {name} missing from locked.txt"
    assert not DEV_ONLY_NAMES & set(entries)


def test_committed_build_txt_is_only_the_build_backend() -> None:
    entries = _entries("requirements/build.txt")
    assert list(entries) == ["uv-build"]
    version, hashes = entries["uv-build"]
    assert version == _lock_versions()["uv-build"]
    assert hashes >= 1


REQUIRES_PATTERN = re.compile(r"uv_build>=(?P<low>\d+(?:\.\d+){0,2}),<(?P<high>\d+(?:\.\d+){0,2})")


def _version_tuple(text: str) -> tuple[int, int, int]:
    parts = [int(part) for part in text.split(".")]
    padded = [*parts, 0, 0, 0][:3]
    return (padded[0], padded[1], padded[2])


def _requires_range(requires: object) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Return (low, high) of the single ``uv_build>=LOW,<HIGH`` entry, padded to three integers."""
    assert isinstance(requires, list)
    assert len(requires) == 1
    match = REQUIRES_PATTERN.fullmatch(str(requires[0]))
    assert match is not None, f"unexpected build requirement {requires[0]!r}"
    return _version_tuple(match.group("low")), _version_tuple(match.group("high"))


def _build_ranges() -> tuple[
    tuple[tuple[int, int, int], tuple[int, int, int]],
    tuple[tuple[int, int, int], tuple[int, int, int]],
]:
    data = _pyproject()
    build_system = data["build-system"]
    groups = data["dependency-groups"]
    assert isinstance(build_system, dict)
    assert isinstance(groups, dict)
    assert build_system["build-backend"] == "uv_build"
    return _requires_range(build_system["requires"]), _requires_range(groups["build"])


def test_build_system_requires_admits_uv_0_11() -> None:
    """uv uses its built-in backend, and so builds offline, only when its own version fits."""
    (low, high), _group = _build_ranges()
    assert low <= (0, 11, 0)
    locked = _version_tuple(_lock_versions()["uv-build"])
    assert low <= locked < high


def test_build_group_range_sits_inside_build_system_requires() -> None:
    """The offline wheel route supports uv 0.11+, and the build.txt backend must stay accepted."""
    (sys_low, sys_high), (group_low, group_high) = _build_ranges()
    assert group_low >= sys_low
    assert group_high <= sys_high
    locked = _version_tuple(_lock_versions()["uv-build"])
    assert group_low <= locked < group_high
