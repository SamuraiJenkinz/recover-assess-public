"""Blocked-term scanner (FND-07): tokenisation, scanning, CLI and exit codes.

The real term list is stored only as SHA-256 digests, so these tests inject the digest of
a harmless word instead. No test rebuilds a real term from fragments.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "blocked_terms.py"

WORD = "zebra"
ZEBRA_DIGEST = hashlib.sha256(WORD.encode()).hexdigest()
ZEBRA = frozenset({ZEBRA_DIGEST})
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("blocked_terms_script", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["blocked_terms_script"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bt() -> ModuleType:
    return _load()


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def make_repo(root: Path, files: dict[str, bytes]) -> None:
    git(root, "init", "-q")
    for name, body in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    if files:
        git(root, "add", "--", *files)


# --- tokenisation ---


@pytest.mark.parametrize(
    "text",
    ["ZEBRA.example", "under_zebra-x", "ZebraTheme", "XMLZebraParser", "zebra2", "a zebra b"],
)
def test_the_word_is_found_in_every_separator_and_case_shape(bt: ModuleType, text: str) -> None:
    assert WORD in bt.tokens(text)


@pytest.mark.parametrize("text", ["zebras", "sebrazebrafish", "xzebra", "zebrax"])
def test_substrings_are_never_matches(bt: ModuleType, text: str) -> None:
    assert WORD not in bt.tokens(text)


def test_token_hash_is_sha256_of_the_utf8_token(bt: ModuleType) -> None:
    assert bt.token_hash(WORD) == ZEBRA_DIGEST


# --- scan_text ---


def test_scan_text_is_one_based_crlf_safe_and_one_hit_per_line(bt: ModuleType) -> None:
    text = "ok\r\nsee the Zebra here\r\nzebras only\nzebra zebra\n"
    hits = bt.scan_text(text, path="a.md", blocked=ZEBRA)
    assert hits == [bt.Hit("a.md", 2), bt.Hit("a.md", 4)]


def test_hit_has_only_path_and_line(bt: ModuleType) -> None:
    assert list(bt.Hit.__dataclass_fields__) == ["path", "line"]


# --- digest set ---


def test_the_real_digest_set_is_five_lowercase_sha256_values(bt: ModuleType) -> None:
    digests = bt.BLOCKED_TOKEN_SHA256
    assert len(digests) == 5
    assert all(HEX64.match(d) for d in digests)


# --- scan_repo ---


def test_staged_file_is_a_hit_and_untracked_file_is_not_scanned(
    bt: ModuleType, tmp_path: Path
) -> None:
    make_repo(tmp_path, {"docs/a.md": b"fine\nthe zebra\n"})
    (tmp_path / "untracked.md").write_text("zebra\n", encoding="utf-8")

    assert bt.scan_repo(tmp_path, ZEBRA) == [bt.Hit("docs/a.md", 2)]


def test_binary_invalid_utf8_and_deleted_files_are_skipped(bt: ModuleType, tmp_path: Path) -> None:
    make_repo(
        tmp_path,
        {
            "bin.dat": b"zebra\x00zebra",
            "latin.txt": b"caf\xe9 zebra\n",
            "gone.txt": b"zebra\n",
            "ok.txt": b"clean\n",
        },
    )
    (tmp_path / "gone.txt").unlink()

    assert bt.scan_repo(tmp_path, ZEBRA) == []


# --- main ---


def test_main_reports_path_and_line_without_the_term(
    bt: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_repo(tmp_path, {"a.md": b"x\nZebra here\n", "b.md": b"clean\n"})

    code = bt.main([], root=tmp_path, blocked=ZEBRA)

    captured = capsys.readouterr()
    assert code == 1
    assert "a.md:2: blocked term" in captured.out
    assert "blocked-terms: 1 hit(s) in 1 file(s)" in captured.out
    assert WORD not in (captured.out + captured.err).lower()


def test_main_clean_repo_returns_zero(
    bt: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_repo(tmp_path, {"a.md": b"clean\n"})

    assert bt.main([], root=tmp_path, blocked=ZEBRA) == 0
    assert "blocked-terms: clean (1 tracked files scanned, 0 skipped" in capsys.readouterr().out


def test_main_outside_a_git_repo_fails_closed(
    bt: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert bt.main([], root=tmp_path, blocked=ZEBRA) == 2
    assert "cannot list tracked files" in capsys.readouterr().err


def test_hash_term_prints_the_digest(bt: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    assert bt.main(["--hash-term", "Zebra"]) == 0
    assert capsys.readouterr().out.strip() == ZEBRA_DIGEST


def test_hash_term_rejects_multi_word_input(
    bt: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert bt.main(["--hash-term", "two words"]) == 2
    assert capsys.readouterr().err


# --- the real repository ---


def test_the_repository_has_no_blocked_terms(bt: ModuleType) -> None:
    if not (REPO_ROOT / ".git").exists():
        pytest.skip("no .git directory (sdist or exported tree)")
    assert bt.scan_repo(REPO_ROOT) == []
