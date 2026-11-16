"""Generate or check the published JSON schemas (FND-04, D-07).

Usage:
    uv run python scripts/gen_schemas.py            # regenerate every published schema
    uv run python scripts/gen_schemas.py --check    # exit 1 on drift, never write

The drift comparison is on parsed JSON, so a checkout with CRLF line endings is not drift.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from recover_assess.core.models.registry import PUBLISHED, build_schema, render_schema, schema_path
from recover_assess.core.output import atomic_write_text

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
REGENERATE_HINT = "regenerate with uv run python scripts/gen_schemas.py"


def _is_current(path: Path, name: str) -> bool:
    """True when the file at ``path`` parses to exactly the schema built for ``name``."""
    if not path.is_file():
        return False
    try:
        on_disk = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(on_disk == build_schema(name))


def check(root: Path) -> int:
    """Report drift for every published schema; return 1 if any has drifted."""
    drifted = False
    for name in PUBLISHED:
        if _is_current(schema_path(root, name), name):
            print(f"OK {name}")
        else:
            print(f"DRIFT {name}: {REGENERATE_HINT}")
            drifted = True
    return 1 if drifted else 0


def generate(root: Path) -> int:
    """Write every published schema under ``root`` atomically (FND-06; LF endings, UTF-8)."""
    for name in PUBLISHED:
        target = schema_path(root, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(target, render_schema(name))
        print(f"WROTE {name}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or check published JSON schemas.")
    parser.add_argument("--check", action="store_true", help="exit 1 on drift; never write")
    parser.add_argument(
        "--root", type=Path, default=DEFAULT_ROOT, help="repository root (default: this repo)"
    )
    args = parser.parse_args(argv)
    return check(args.root) if args.check else generate(args.root)


if __name__ == "__main__":
    raise SystemExit(main())
