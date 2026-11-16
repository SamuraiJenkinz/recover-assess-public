"""Generic client-data scanner for the shippable tree (FND-07, D-10, D-11).

Every rule here is generic. No client name, client host or gateway path appears in
this file: client-specific terms live only in the external file named by
``RECOVER_ASSESS_PRIVATE_TERMS_FILE`` and are scanned for when that variable is set.

``Finding`` deliberately has no excerpt field, so a failing test never re-prints
the secret it found.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = [
    "PRIVATE_TERMS_ENV",
    "RULES",
    "SHIPPABLE_FILES",
    "SHIPPABLE_PREFIXES",
    "Finding",
    "Rule",
    "load_private_terms",
    "scan_text",
    "scan_tree",
    "shippable_files",
]

PRIVATE_TERMS_ENV: Final = "RECOVER_ASSESS_PRIVATE_TERMS_FILE"
SHIPPABLE_PREFIXES: Final = ("src/", "tests/", "config/", "schemas/", "scripts/", ".github/")
SHIPPABLE_FILES: Final = ("README.md", "pyproject.toml", "recover-assess.example.yaml")

_BINARY_PROBE_BYTES: Final = 8192
_SYNTHETIC_TENANTS: Final = frozenset({"contoso", "fabrikam"})
_ALLOWED_EMAIL_DOMAINS: Final = frozenset({"example.com", "contoso.com"})
_TENANT_SUFFIXES: Final = ("-my", "-admin")


@dataclass(frozen=True)
class Finding:
    """One rule hit. No excerpt, by design."""

    path: str
    line: int
    rule: str


@dataclass(frozen=True)
class Rule:
    """A compiled pattern plus a test for the matches that are allowed."""

    name: str
    pattern: re.Pattern[str]
    allowed: Callable[[re.Match[str]], bool]


def _never_allowed(match: re.Match[str]) -> bool:
    del match
    return False


def _synthetic_tenant(match: re.Match[str]) -> bool:
    label = match.group("label").casefold()
    for suffix in _TENANT_SUFFIXES:
        label = label.removesuffix(suffix)
    return label in _SYNTHETIC_TENANTS


def _example_domain(match: re.Match[str]) -> bool:
    return match.group("domain").casefold() in _ALLOWED_EMAIL_DOMAINS


def _synthetic_guid(match: re.Match[str]) -> bool:
    groups = match.group(0).casefold().split("-")
    return all(len(set(group)) == 1 for group in groups)


def _rule(
    name: str, pattern: str, allowed: Callable[[re.Match[str]], bool] = _never_allowed
) -> Rule:
    return Rule(name, re.compile(pattern, re.IGNORECASE), allowed)


RULES: Final[tuple[Rule, ...]] = (
    _rule(
        "sharepoint_host",
        r"\b(?P<label>[a-z0-9][a-z0-9-]*)\.sharepoint\.(?:com|us|de|cn)\b",
        _synthetic_tenant,
    ),
    _rule(
        "email_domain",
        r"\w@(?P<domain>(?:[a-z0-9-]+\.)+[a-z]{2,})",
        _example_domain,
    ),
    _rule(
        "guid",
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        _synthetic_guid,
    ),
    _rule("jwt", r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]*"),
    _rule("bearer", r"Bearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    _rule("gateway_host", r"\bapis\.[a-z0-9-]+\.[a-z]{2,}"),
)


def scan_text(text: str, *, path: str, private_terms: Sequence[str] = ()) -> list[Finding]:
    """Return the findings in ``text``; line numbers are 1-based."""
    findings: list[Finding] = []
    for number, line in enumerate(text.split("\n"), start=1):
        for rule in RULES:
            findings.extend(
                Finding(path, number, rule.name)
                for match in rule.pattern.finditer(line)
                if not rule.allowed(match)
            )
        folded = line.casefold()
        findings.extend(
            Finding(path, number, "private_term") for term in private_terms if term in folded
        )
    return findings


def load_private_terms(environ: Mapping[str, str]) -> list[str]:
    """Read the external terms file named by the environment, or return no terms.

    Unset or empty variable: no terms. A path that does not exist raises
    ``FileNotFoundError``, so a misconfigured private job fails instead of passing.
    """
    location = environ.get(PRIVATE_TERMS_ENV, "")
    if not location:
        return []
    lines = Path(location).read_text(encoding="utf-8", errors="replace").splitlines()
    return [
        stripped.casefold()
        for stripped in (line.strip() for line in lines)
        if stripped and not stripped.startswith("#")
    ]


def shippable_files(root: Path) -> list[str]:
    """Repository-relative POSIX paths that could ship, including untracked files.

    ``--others`` means a new file is scanned before it is staged.
    """
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    names = {name for name in result.stdout.decode("utf-8", errors="replace").split("\0") if name}
    return sorted(
        name
        for name in names
        if (name.startswith(SHIPPABLE_PREFIXES) or name in SHIPPABLE_FILES)
        and (root / name).is_file()
    )


def scan_tree(root: Path, private_terms: Sequence[str] = ()) -> list[Finding]:
    """Scan every shippable file. A binary file is itself a finding, never skipped."""
    findings: list[Finding] = []
    for name in shippable_files(root):
        data = (root / name).read_bytes()
        if b"\x00" in data[:_BINARY_PROBE_BYTES]:
            findings.append(Finding(name, 1, "binary_file"))
            continue
        text = data.decode("utf-8", errors="replace")
        findings.extend(scan_text(text, path=name, private_terms=private_terms))
    return findings
