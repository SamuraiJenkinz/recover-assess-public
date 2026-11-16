"""Typed JSONL run log (GRPH-07) with a scrub filter and interruption safety (FND-06).

``run.jsonl`` is an append-only stream: one JSON object per line, written in
emission order, flushed after every line. Every event is a pydantic model from a
closed set with no free-text body field, so a response body cannot be logged by
construction. As defence in depth, every serialised line also passes through
:func:`scrub_text`, which redacts bearer tokens, JWT-shaped strings, signed-URL
parameters and ``downloadUrl`` members.

FND-06 and why this is the one output that is not replaced atomically (D-14,
the user-approved 2026-11-15 amendment of FND-06): an append-only stream cannot
be atomically replaced once per line, so the guarantee is built differently.

* Each event is serialised to one complete line and written with a single
  ``write`` call followed by ``flush``, so an interruption can leave at most one
  unterminated trailing line.
* :class:`RunLog` repairs that tail when the file is opened: it truncates the
  file back to the last newline before anything is appended.
* :func:`read_run_log` ignores an unterminated tail, so no reader ever sees a
  half-written line. A newline-terminated line that is not a JSON object is
  corruption, not interruption, and raises :class:`OutputError`.

Imports are limited to pydantic, the standard library and the two leaf modules
``core.clock`` and ``core.errors``.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Final, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from recover_assess.core.clock import Clock
from recover_assess.core.errors import OutputError, is_error_code

__all__ = [
    "CollectorEndEvent",
    "CollectorStartEvent",
    "LogEvent",
    "RequestEvent",
    "RetryEvent",
    "RunLog",
    "RunLogContents",
    "SiteStateEvent",
    "WarningEvent",
    "read_run_log",
    "repair_run_log",
    "scrub_text",
]

_REDACTED: Final = "[REDACTED]"
_BLOCK_SIZE: Final = 64 * 1024

Level = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class LogEvent(BaseModel):
    """Base of every run-log event.

    ``ts`` is stamped by :meth:`RunLog.emit` from the injected clock, under the
    writer lock, so timestamps follow emission order. There is deliberately no
    free-text body field on any event.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ts: AwareDatetime | None = None
    level: Level
    event: str
    site: str | None = None


class RequestEvent(LogEvent):
    """One HTTP attempt against Graph."""

    event: Literal["request"] = "request"
    method: Literal["GET", "POST"]
    template: str
    status: int | None
    duration_ms: float = Field(ge=0)
    retry: int = Field(ge=0)
    request_id: str | None
    via_batch: bool = False
    batch_size: int | None = None


class RetryEvent(LogEvent):
    """A retry was scheduled after a throttled response."""

    event: Literal["retry"] = "retry"
    template: str
    attempt: int
    delay_s: float
    status: int


class WarningEvent(LogEvent):
    """A collector or the client recorded a stable warning code."""

    event: Literal["warning"] = "warning"
    code: str
    detail: str | None = None

    @field_validator("code")
    @classmethod
    def _stable_code(cls, value: str) -> str:
        if not is_error_code(value):
            msg = "code must be a stable error code"
            raise ValueError(msg)
        return value


class SiteStateEvent(LogEvent):
    """A site moved to a new state."""

    event: Literal["site_state"] = "site_state"
    state: Literal["pending", "resolved", "collecting", "complete", "partial", "failed"]


class CollectorStartEvent(LogEvent):
    """A collector began."""

    event: Literal["collector_start"] = "collector_start"
    collector: str


class CollectorEndEvent(LogEvent):
    """A collector finished."""

    event: Literal["collector_end"] = "collector_end"
    collector: str
    status: Literal["ok", "partial", "failed"]
    duration_ms: float


_SCRUB_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    # A downloadUrl member in its escaped form (inside an already-serialised JSON
    # string) and in its plain form. The escaped form is replaced inside the outer
    # string, so a scrubbed line stays valid JSON.
    re.compile(
        r'\\"[^"\\]*downloadurl[^"\\]*\\"\s*:\s*\\"(?:[^\\]|\\(?!"))*?\\"',
        re.IGNORECASE,
    ),
    re.compile(r'"[^"\\]*downloadurl[^"\\]*"\s*:\s*"(?:[^"\\]|\\.)*"', re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]*)?"),
    re.compile(
        r"\b(?:sig|tempauth|access_token|code|api-key|apikey|client_secret)=[^&\s\"'\\]*",
        re.IGNORECASE,
    ),
    re.compile(r"\bapi-?key\s*:\s*[^\s\"',}\\]+", re.IGNORECASE),
)


def scrub_text(text: str) -> str:
    """Return ``text`` with token-like and signed-URL material replaced by ``[REDACTED]``."""
    for pattern in _SCRUB_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


def repair_run_log(path: Path) -> int:
    """Truncate an unterminated trailing line from ``path`` and return the bytes removed.

    A missing or empty file, or one whose last byte is a newline, needs no repair
    (returns 0). Otherwise the file is scanned backwards in 64 KiB blocks for the
    last newline and truncated to just after it (or to zero bytes when there is
    none).
    """
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return 0
    if size == 0:
        return 0
    with path.open("rb+") as handle:
        handle.seek(size - 1)
        if handle.read(1) == b"\n":
            return 0
        end = size
        while end > 0:
            start = max(0, end - _BLOCK_SIZE)
            handle.seek(start)
            block = handle.read(end - start)
            index = block.rfind(b"\n")
            if index != -1:
                keep = start + index + 1
                handle.truncate(keep)
                return size - keep
            end = start
        handle.truncate(0)
        return size


@dataclass(frozen=True)
class RunLogContents:
    """What :func:`read_run_log` found: complete events and whether a tail was ignored."""

    events: list[dict[str, Any]]
    partial_tail: bool


def read_run_log(path: Path) -> RunLogContents:
    """Read the complete lines of a run log.

    Every newline-terminated line must be UTF-8 and parse to a JSON object, else
    :class:`OutputError` is raised naming only the 1-based line number. A final
    segment without a terminating newline is an interrupted append: it is ignored
    and reported through ``partial_tail``. Its text is never returned or printed.
    """
    segments = path.read_bytes().split(b"\n")
    tail = segments.pop()
    events: list[dict[str, Any]] = []
    for number, raw in enumerate(segments, start=1):
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            msg = f"run_log_corrupt_line: line {number}"
            raise OutputError(msg) from None
        if not isinstance(parsed, dict):
            msg = f"run_log_corrupt_line: line {number}"
            raise OutputError(msg)
        events.append(parsed)
    return RunLogContents(events=events, partial_tail=tail != b"")


class RunLog:
    """Single-writer, append-only JSONL log.

    The parent directory must already exist. An unterminated tail left by an
    interrupted run is repaired before the file is opened for append; the number
    of bytes removed is available as :attr:`repaired_bytes`.
    """

    def __init__(self, sink: Path, clock: Clock) -> None:
        if not sink.parent.is_dir():
            msg = "run_log_parent_missing"
            raise OutputError(msg)
        self._clock = clock
        self._lock = threading.Lock()
        self._repaired_bytes = repair_run_log(sink)
        self._handle = sink.open("a", encoding="utf-8", newline="\n")

    @property
    def repaired_bytes(self) -> int:
        """Bytes of unterminated tail removed when the log was opened."""
        return self._repaired_bytes

    def emit(self, event: LogEvent) -> None:
        """Stamp, serialise, scrub and append one event as one flushed line."""
        with self._lock:
            stamped = event.model_copy(update={"ts": self._clock.utcnow()})
            line = scrub_text(stamped.model_dump_json()) + "\n"
            self._handle.write(line)
            self._handle.flush()

    def close(self) -> None:
        """Close the file. Safe to call more than once."""
        with self._lock:
            if not self._handle.closed:
                self._handle.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
