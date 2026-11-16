"""Atomic output writers (FND-06).

Every output file other than the append-only ``run.jsonl`` is written through
this module (D-14, the 2026-11-15 FND-06 amendment). The sequence is: create a
temp file in the target's own directory, write, flush, fsync, close, then
replace the target. A reader therefore sees the old file or the new file, never
a half-written one.

On Windows ``replace`` raises ``PermissionError`` while another process holds the
target open (antivirus, an indexer, a viewer). That is retried a bounded number
of times with jittered waits. Persistent failure raises ``OutputError``; there is
never a fallback to a non-atomic copy.

The containing directory is not fsynced: Windows cannot open a directory for
fsync, so the guarantee is atomic replacement, not durability of the rename.

``run.jsonl`` is an append stream, so it gets its FND-06 safety from
repair-on-open in ``core/log.py`` (Plan 01-02), not from this module.
"""

from __future__ import annotations

import itertools
import json
import os
import random
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Final, TypedDict, Unpack

from recover_assess.core.clock import SYSTEM_CLOCK
from recover_assess.core.errors import OutputError

__all__ = ["atomic_write_bytes", "atomic_write_json", "atomic_write_text", "sweep_orphans"]

_WAIT_MIN: Final = 0.05
_WAIT_MAX: Final = 0.25
_TEMP_NAME: Final = re.compile(r"\A\..+\.tmp-\d+-\d+\Z")

_counter = itertools.count()
_counter_lock = threading.Lock()


class WriteOptions(TypedDict, total=False):
    """Injection points for the retry loop (tests; the defaults are the real thing)."""

    replace: Callable[[Path, Path], object]
    sleep: Callable[[float], None]
    attempts: int
    rng: random.Random


def _default_replace(source: Path, target: Path) -> None:
    source.replace(target)


def _temp_path(path: Path) -> Path:
    with _counter_lock:
        number = next(_counter)
    return path.parent / f".{path.name}.tmp-{os.getpid()}-{number}"


def atomic_write_bytes(
    path: Path,
    data: bytes,
    *,
    replace: Callable[[Path, Path], object] | None = None,
    sleep: Callable[[float], None] | None = None,
    attempts: int = 10,
    rng: random.Random | None = None,
) -> None:
    """Write ``data`` to ``path`` atomically.

    ``path.parent`` must already exist. A ``PermissionError`` from the replace is
    retried up to ``attempts`` tries in total, sleeping a jittered 50 to 250 ms
    between tries. Any failure raises ``OutputError``, leaves the previous target
    bytes untouched (or the target absent) and removes the temp file.
    """
    if not path.parent.is_dir():
        msg = f"parent_missing: {path.name}"
        raise OutputError(msg)
    do_replace = _default_replace if replace is None else replace
    wait = SYSTEM_CLOCK.sleep_sync if sleep is None else sleep
    jitter = random.Random() if rng is None else rng  # noqa: S311 - retry jitter, not security
    temp = _temp_path(path)
    try:
        try:
            with temp.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            msg = f"write_failed: {path.name}"
            raise OutputError(msg) from exc
        _replace_with_retry(temp, path, do_replace, wait, attempts, jitter)
    finally:
        temp.unlink(missing_ok=True)


def _replace_with_retry(
    temp: Path,
    path: Path,
    do_replace: Callable[[Path, Path], object],
    wait: Callable[[float], None],
    attempts: int,
    jitter: random.Random,
) -> None:
    tries = max(attempts, 1)
    for attempt in range(1, tries + 1):
        try:
            do_replace(temp, path)
        except PermissionError as exc:
            if attempt == tries:
                msg = f"replace_denied: {path.name} after {tries} attempts"
                raise OutputError(msg) from exc
            wait(jitter.uniform(_WAIT_MIN, _WAIT_MAX))
        except OSError as exc:
            msg = f"replace_failed: {path.name}"
            raise OutputError(msg) from exc
        else:
            return


def atomic_write_text(path: Path, text: str, **options: Unpack[WriteOptions]) -> None:
    """Write ``text`` as UTF-8, byte for byte (no newline translation)."""
    atomic_write_bytes(path, text.encode("utf-8"), **options)


def atomic_write_json(path: Path, obj: object, **options: Unpack[WriteOptions]) -> None:
    """Write ``obj`` as two-space-indented UTF-8 JSON with one trailing newline."""
    text = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    atomic_write_bytes(path, text.encode("utf-8"), **options)


def sweep_orphans(directory: Path) -> list[Path]:
    """Remove stale temp files left by a killed process; return what was removed.

    Non-recursive. Only names of the form ``.{name}.tmp-{pid}-{n}`` match.
    """
    removed: list[Path] = []
    for entry in sorted(directory.iterdir()):
        if entry.is_file() and _TEMP_NAME.fullmatch(entry.name):
            entry.unlink(missing_ok=True)
            removed.append(entry)
    return removed
