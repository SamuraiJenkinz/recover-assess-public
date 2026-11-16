"""Generic client-data guard (FND-07, D-10, D-11).

Every string that must trigger a rule is built at runtime by concatenation, so this
file never trips the scan it tests. The shippable-file behaviour runs in a throwaway
git repository under ``tmp_path``; the real tree is never written.
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
from pathlib import Path

import pytest

from tests.support.repo_scan import (
    PRIVATE_TERMS_ENV,
    Finding,
    load_private_terms,
    scan_text,
    scan_tree,
    shippable_files,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

OTHER_SHAREPOINT_HOST = "acme" + "-my.sharepoint" + ".com"
PERSON_AT_OTHER_DOMAIN = "jane" + "@" + "corp.example" + ".org"
REAL_LOOKING_GUID = "01234567-" + "89ab-cdef-0123-456789abcdef"
JWT_SHAPE = "eyJ" + "a" * 12 + "." + "b" * 12 + "." + "c" * 12
BEARER_SHAPE = "Bear" + "er " + "t" * 30
GATEWAY_HOST = "api" + "s.internal" + ".net"


def rules_of(text: str) -> list[str]:
    return [finding.rule for finding in scan_text(text, path="sample.py")]


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def make_repo(root: Path) -> None:
    git(root, "init", "-q")
    (root / ".gitignore").write_text("tests/ignored.txt\n", encoding="utf-8")
    for name, body in {
        "src/pkg/mod.py": "x = 1\n",
        "tests/new_test.py": "y = 2\n",
        "tests/ignored.txt": "ignored\n",
        ".planning/notes.md": "planning\n",
        ".claude/CLAUDE.md": "instructions\n",
        "README.md": "readme\n",
        "Working Draft.md": "draft\n",
    }.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    git(root, "add", ".gitignore", "src/pkg/mod.py", ".planning/notes.md")


def test_empty_text_has_no_findings() -> None:
    assert scan_text("", path="empty.py") == []


def test_synthetic_and_allowed_values_have_no_findings() -> None:
    text = "\n".join(
        [
            "https://contoso.sharepoint.com/sites/team",
            "https://fabrikam-my.sharepoint.com/personal/x",
            "https://FABRIKAM-admin.sharepoint.com",
            "user@example.com and USER@Contoso.COM",
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "00000000-0000-0000-0000-000000000000",
            '{"@odata.nextLink": "x"}',
        ]
    )

    assert scan_text(text, path="sample.py") == []


def test_another_tenants_sharepoint_host_is_a_finding() -> None:
    assert rules_of("host " + OTHER_SHAREPOINT_HOST) == ["sharepoint_host"]


def test_sharepoint_host_matching_is_case_insensitive() -> None:
    assert rules_of(OTHER_SHAREPOINT_HOST.upper()) == ["sharepoint_host"]


def test_a_person_at_a_non_example_domain_is_a_finding() -> None:
    assert rules_of(PERSON_AT_OTHER_DOMAIN) == ["email_domain"]
    assert rules_of(PERSON_AT_OTHER_DOMAIN.upper()) == ["email_domain"]


def test_a_non_synthetic_guid_is_a_finding() -> None:
    assert rules_of("id=" + REAL_LOOKING_GUID) == ["guid"]
    assert rules_of(REAL_LOOKING_GUID.upper()) == ["guid"]


def test_a_jwt_shape_is_a_finding() -> None:
    assert rules_of("token " + JWT_SHAPE) == ["jwt"]


def test_a_bearer_token_shape_is_a_finding() -> None:
    assert rules_of("Authorization: " + BEARER_SHAPE) == ["bearer"]
    assert rules_of(BEARER_SHAPE.lower()) == ["bearer"]


def test_an_apis_gateway_host_is_a_finding() -> None:
    assert rules_of("https://" + GATEWAY_HOST + "/v1") == ["gateway_host"]
    assert rules_of(GATEWAY_HOST.upper()) == ["gateway_host"]


def test_findings_carry_one_based_line_numbers_and_no_excerpt() -> None:
    findings = scan_text("fine\nfine\n" + REAL_LOOKING_GUID + "\n", path="a/b.py")

    assert findings == [Finding(path="a/b.py", line=3, rule="guid")]
    assert [field.name for field in dataclasses.fields(Finding)] == ["path", "line", "rule"]


def test_private_terms_match_case_insensitively(tmp_path: Path) -> None:
    term = "zz" + "qq-widgets"
    terms_file = tmp_path / "terms.txt"
    terms_file.write_text("# comment\n\n" + term.upper() + "\n", encoding="utf-8")
    terms = load_private_terms({PRIVATE_TERMS_ENV: str(terms_file)})

    findings = scan_text("see " + term.title() + " here", path="x.py", private_terms=terms)

    assert [finding.rule for finding in findings] == ["private_term"]
    assert terms == [term.casefold()]


def test_unset_env_adds_no_private_terms_and_no_findings() -> None:
    assert load_private_terms({}) == []
    assert scan_text("zzqq-widgets", path="x.py", private_terms=load_private_terms({})) == []


def test_empty_private_terms_file_adds_no_findings(tmp_path: Path) -> None:
    terms_file = tmp_path / "terms.txt"
    terms_file.write_text("", encoding="utf-8")

    assert load_private_terms({PRIVATE_TERMS_ENV: str(terms_file)}) == []


def test_set_but_missing_private_terms_path_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_private_terms({PRIVATE_TERMS_ENV: str(tmp_path / "missing.txt")})


def test_shippable_files_covers_untracked_files_and_excludes_the_rest(tmp_path: Path) -> None:
    make_repo(tmp_path)

    assert shippable_files(tmp_path) == ["README.md", "src/pkg/mod.py", "tests/new_test.py"]


def test_a_shippable_file_with_a_nul_byte_is_a_binary_file_finding(tmp_path: Path) -> None:
    make_repo(tmp_path)
    (tmp_path / "tests" / "blob.bin").write_bytes(b"abc\x00def")

    assert scan_tree(tmp_path, []) == [Finding(path="tests/blob.bin", line=1, rule="binary_file")]


def test_scan_tree_reads_untracked_files_and_replaces_undecodable_bytes(tmp_path: Path) -> None:
    make_repo(tmp_path)
    (tmp_path / "tests" / "latin.py").write_bytes(
        b"caf\xe9 = '" + REAL_LOOKING_GUID.encode() + b"'\n"
    )

    assert scan_tree(tmp_path, []) == [Finding(path="tests/latin.py", line=1, rule="guid")]


def test_scan_tree_of_a_clean_repo_has_no_findings(tmp_path: Path) -> None:
    make_repo(tmp_path)

    assert scan_tree(tmp_path, []) == []


def test_scan_tree_applies_private_terms(tmp_path: Path) -> None:
    make_repo(tmp_path)
    term = "zz" + "qq-widgets"
    (tmp_path / "tests" / "terms_test.py").write_text("# " + term.upper() + "\n", encoding="utf-8")

    findings = scan_tree(tmp_path, [term])

    assert findings == [Finding(path="tests/terms_test.py", line=1, rule="private_term")]


def test_whole_tree_scan_clean() -> None:
    if not (REPO_ROOT / ".git").exists():
        pytest.skip("no .git directory")

    findings = scan_tree(REPO_ROOT, load_private_terms(os.environ))

    assert findings == []
