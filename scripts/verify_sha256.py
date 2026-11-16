"""Verify a downloaded release archive against its published SHA-256 sidecar.

This is the uv bootstrap integrity check (threat T-01-30). It runs before uv
and Python 3.12 exist, so it uses only the standard library and syntax that
works on any Python 3.10 or newer. It never downloads anything itself.

Usage: python scripts/verify_sha256.py ARCHIVE SIDECAR
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

_HEX64 = re.compile(r"[0-9a-f]{64}")
_BLOCK = 1024 * 1024


def read_expected_digest(sidecar: Path) -> str:
    """Return the lower-case digest from a ``.sha256`` sidecar file.

    Accepts both the bare ``HEX`` form and the ``HEX  filename`` form.
    """
    text = sidecar.read_text(encoding="utf-8").strip()
    tokens = text.split()
    token = tokens[0].lower() if tokens else ""
    if not _HEX64.fullmatch(token):
        msg = "sidecar does not start with a 64-character hex SHA-256 digest"
        raise ValueError(msg)
    return token


def file_sha256(path: Path) -> str:
    """Return the SHA-256 hex digest of a file, read in 1 MiB blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(_BLOCK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    """Compare the archive digest with the sidecar. Return 0 on a match, else 1."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="downloaded release archive")
    parser.add_argument("sidecar", type=Path, help="published .sha256 sidecar file")
    args = parser.parse_args(argv)

    expected = read_expected_digest(args.sidecar)
    actual = file_sha256(args.archive)
    if actual == expected:
        print(f"OK sha256={actual} {args.archive.name}")
        return 0
    print(f"MISMATCH expected={expected} actual={actual}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
