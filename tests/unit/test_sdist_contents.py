"""The sdist ships the schema and allow-list and never ships planning docs or drafts (D-10)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.needs_uv]

REPO_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_FRAGMENTS = (
    ".planning",
    ".claude",
    "docs/private",
    "Recover Assessment",
    "AI-Ready",
    ".pem",
    ".pfx",
)


def build_sdist_members(out_dir: Path) -> list[str]:
    uv = shutil.which("uv")
    if uv is None:
        if os.environ.get("CI"):
            pytest.fail("uv is required in CI to build the sdist")
        pytest.skip("uv is not installed; sdist contents not checked")
    subprocess.run(
        [uv, "build", "--sdist", "--out-dir", str(out_dir), str(REPO_ROOT)],
        check=True,
        capture_output=True,
        timeout=600,
    )
    archives = sorted(out_dir.glob("*.tar.gz"))
    assert len(archives) == 1
    with tarfile.open(archives[0]) as archive:
        return archive.getnames()


@pytest.fixture(scope="module")
def members(tmp_path_factory: pytest.TempPathFactory) -> list[str]:
    return build_sdist_members(tmp_path_factory.mktemp("sdist"))


def test_the_schema_and_the_allow_list_ship(members: list[str]) -> None:
    assert any(name.endswith("/schemas/fact_sheet.schema.json") for name in members)
    assert any(name.endswith("/src/recover_assess/core/graph_allowlist.yaml") for name in members)


def test_planning_docs_drafts_and_secrets_never_ship(members: list[str]) -> None:
    leaked = [
        name
        for name in members
        if any(fragment in name for fragment in FORBIDDEN_FRAGMENTS)
        or name.endswith("recover-assess.yaml")
    ]

    assert leaked == []
