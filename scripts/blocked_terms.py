"""Blocked-term scanner for every tracked file (FND-07).

Scans each file listed by ``git ls-files`` (read from the working tree) for a list of
words that must never appear in the repository. The list is stored only as SHA-256
digests of lowercase tokens, because the repository must never spell those words.
Findings carry a path and a line number only, never an excerpt, so CI logs do not echo
the word that was found.

Tokenisation: every ``[A-Za-z0-9]+`` run is a token, lowercased. Each run is also split
into camelCase, ALLCAPS-prefix and digit segments. Underscore, hyphen, dot and all
non-ASCII characters are separators. Matching is on whole tokens, never substrings, so
a short blocked word cannot match inside an unrelated longer word.

To add a term: run ``python scripts/blocked_terms.py --hash-term WORD`` and paste the
digest into ``BLOCKED_TOKEN_SHA256``. Add each word of a multi-word name separately.
Never write the word itself into any tracked file.

Exit codes: 0 clean, 1 hits found, 2 usage error or git failure (fail closed).

Standard library only.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

BLOCKED_TOKEN_SHA256: Final[frozenset[str]] = frozenset(
    {
        "428e626f22d0273bb2741c8747418eaff1828bcd397fe7d00f3ec30d4519d95d",
        "d5f29c56ba0bd9695cfa44ce6e31d3d064ac66ca225d18b3d9ec2657b838ebf7",
        "d528922e9c007497cd062185a01363c12fa21478b08f580f8da89ae109b08f15",
        "064a5c7c635fe6832f1aa2786668ff4100772a8c97aebf07808631612d831715",
        "8b07bbd6750380b4ceeff6453593ca4ec4289c51ac319be07421a91e1012db5c",
    }
)

ROOT = Path(__file__).resolve().parent.parent

_RUN = re.compile(r"[A-Za-z0-9]+")
_SEGMENT = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
_SINGLE_WORD = re.compile(r"[A-Za-z0-9]+")


@dataclass(frozen=True)
class Hit:
    """A blocked-term location. Deliberately has no excerpt."""

    path: str
    line: int


def tokens(line: str) -> set[str]:
    """Return the lowercase word tokens of one line, including camelCase segments."""
    found: set[str] = set()
    for run in _RUN.findall(line):
        found.add(run.lower())
        found.update(segment.lower() for segment in _SEGMENT.findall(run))
    return found


@functools.lru_cache(maxsize=65536)
def token_hash(token: str) -> str:
    """Return the SHA-256 hex digest of a token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def scan_text(text: str, *, path: str, blocked: frozenset[str]) -> list[Hit]:
    """Return one Hit per 1-based line that contains a blocked token."""
    hits: list[Hit] = []
    for number, line in enumerate(text.split("\n"), start=1):
        if any(token_hash(token) in blocked for token in tokens(line)):
            hits.append(Hit(path, number))
    return hits


def tracked_files(root: Path) -> list[str]:
    """Return the sorted names of every tracked file. Git failures propagate."""
    proc = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    names = proc.stdout.decode("utf-8").split("\0")
    return sorted(name for name in names if name)


def _scan(root: Path, blocked: frozenset[str]) -> tuple[list[Hit], int, int]:
    """Return (hits, files considered, files skipped as binary or non-UTF-8)."""
    hits: list[Hit] = []
    considered = 0
    skipped = 0
    for name in tracked_files(root):
        target = root / name
        if not target.is_file():
            continue
        considered += 1
        data = target.read_bytes()
        if b"\x00" in data:
            skipped += 1
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            skipped += 1
            continue
        hits.extend(scan_text(text, path=name, blocked=blocked))
    return sorted(hits, key=lambda hit: (hit.path, hit.line)), considered, skipped


def scan_repo(root: Path, blocked: frozenset[str] = BLOCKED_TOKEN_SHA256) -> list[Hit]:
    """Scan every tracked file under ``root`` and return the hits sorted by path and line."""
    return _scan(root, blocked)[0]


def main(
    argv: Sequence[str] | None = None,
    *,
    root: Path | None = None,
    blocked: frozenset[str] | None = None,
) -> int:
    """Run the scan or hash a term. The keyword arguments exist so tests can inject both."""
    parser = argparse.ArgumentParser(
        prog="blocked_terms.py",
        description="Fail if any tracked file contains a blocked term (matched by hash).",
    )
    parser.add_argument(
        "--hash-term",
        metavar="WORD",
        help="print the SHA-256 digest to add to BLOCKED_TOKEN_SHA256 and exit",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.hash_term is not None:
        word: str = args.hash_term
        if not _SINGLE_WORD.fullmatch(word):
            print("blocked-terms: --hash-term takes exactly one [A-Za-z0-9]+ word", file=sys.stderr)
            return 2
        print(token_hash(word.lower()))
        return 0

    repo = root if root is not None else ROOT
    digests = blocked if blocked is not None else BLOCKED_TOKEN_SHA256
    try:
        hits, considered, skipped = _scan(repo, digests)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        print(f"blocked-terms: cannot list tracked files: {exc}", file=sys.stderr)
        return 2

    if hits:
        for hit in hits:
            print(f"{hit.path}:{hit.line}: blocked term")
        files = len({hit.path for hit in hits})
        print(f"blocked-terms: {len(hits)} hit(s) in {files} file(s)")
        return 1
    print(
        f"blocked-terms: clean ({considered} tracked files scanned, "
        f"{skipped} skipped as binary or non-UTF-8)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
