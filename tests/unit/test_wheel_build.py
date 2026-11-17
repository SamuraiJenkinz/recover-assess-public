"""The wheel builds offline with uv's built-in backend and ships the console script."""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.needs_uv]

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRY_POINT = "recover-assess = recover_assess.cli:app"


def build_wheel_entry_points(out_dir: Path) -> list[str]:
    uv = shutil.which("uv")
    if uv is None:
        if os.environ.get("CI"):
            pytest.fail("uv is required in CI to build the wheel")
        pytest.skip("uv is not installed; wheel build not checked")
    # --no-cache: a PEP 517 fallback could otherwise be satisfied from the local cache
    # and hide a build-system pin that stops admitting uv's own version.
    subprocess.run(
        [
            uv,
            "build",
            "--wheel",
            "--offline",
            "--no-cache",
            "--out-dir",
            str(out_dir),
            str(REPO_ROOT),
        ],
        check=True,
        capture_output=True,
        timeout=600,
    )
    wheels = sorted(out_dir.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        names = [n for n in archive.namelist() if n.endswith(".dist-info/entry_points.txt")]
        assert len(names) == 1
        text = archive.read(names[0]).decode("utf-8")
    return [line.strip() for line in text.splitlines()]


@pytest.fixture(scope="module")
def entry_points(tmp_path_factory: pytest.TempPathFactory) -> list[str]:
    return build_wheel_entry_points(tmp_path_factory.mktemp("wheel"))


def test_wheel_builds_offline_and_ships_the_console_script(entry_points: list[str]) -> None:
    assert ENTRY_POINT in entry_points
