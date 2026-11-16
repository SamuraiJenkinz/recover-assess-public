"""Pure throttling primitives (GRPH-05): no HTTP library, every clock and rng injected.

The numbers are the spec's and are fixed: honour ``Retry-After`` else full-jitter backoff
(1 s base, 60 s cap), at most 6 retries, a 300 s budget per request, and a per-site breaker
that opens at 20 throttles inside a sliding 60 s window.
"""

from __future__ import annotations

import math
import re
from collections import deque
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Final

from recover_assess.core.errors import ThrottledOut

if TYPE_CHECKING:
    from random import Random

    from recover_assess.core.clock import Clock

__all__ = [
    "BACKOFF_BASE_S",
    "BACKOFF_CAP_S",
    "BREAKER_THRESHOLD",
    "BREAKER_WINDOW_S",
    "MAX_RETRIES_DEFAULT",
    "REQUEST_BUDGET_S",
    "RETRYABLE_STATUSES",
    "SiteBreaker",
    "ThrottleGate",
    "full_jitter_delay",
    "parse_retry_after",
]

RETRYABLE_STATUSES: Final[frozenset[int]] = frozenset({429, 503})
BACKOFF_BASE_S: Final = 1.0
BACKOFF_CAP_S: Final = 60.0
MAX_RETRIES_DEFAULT: Final = 6
REQUEST_BUDGET_S: Final = 300.0
BREAKER_THRESHOLD: Final = 20
BREAKER_WINDOW_S: Final = 60.0

_DECIMAL: Final = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)")
_MAX_EXPONENT: Final = 64


def parse_retry_after(value: str | None, *, now: datetime) -> float | None:
    """Seconds to wait from a ``Retry-After`` header value, or ``None`` when unusable.

    Accepts integer or decimal seconds (negative clamped to 0) and an HTTP-date relative to
    ``now`` (a past date gives 0). Blank, unparseable, NaN or infinite values count as absent.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if _DECIMAL.fullmatch(text):
        seconds = float(text)
        return max(0.0, seconds) if math.isfinite(seconds) else None
    try:
        when = parsedate_to_datetime(text)
    except (ValueError, TypeError, OverflowError, IndexError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - now).total_seconds())


def full_jitter_delay(
    attempt: int,
    rng: Random,
    *,
    base: float = BACKOFF_BASE_S,
    cap: float = BACKOFF_CAP_S,
) -> float:
    """Full-jitter backoff: uniform in ``[0, min(cap, base * 2 ** (attempt - 1))]``.

    ``attempt`` is 1 for the first throttle. ``rng`` is an injected ``random.Random`` used for
    non-cryptographic jitter, so a fixed seed reproduces the exact sleep sequence.
    """
    if attempt < 1:
        msg = "attempt must be at least 1"
        raise ValueError(msg)
    ceiling = min(cap, base * 2.0 ** min(attempt - 1, _MAX_EXPONENT))
    return rng.uniform(0.0, ceiling)


class ThrottleGate:
    """One shared gate per client: a throttle on any site delays the next send on every site."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._resume_at = clock.monotonic()

    @property
    def resume_at(self) -> float:
        """Monotonic time before which nothing may be sent."""
        return self._resume_at

    def trip(self, delay_s: float) -> None:
        """Hold sends for ``delay_s`` from now. The resume time never moves backwards."""
        self._resume_at = max(self._resume_at, self._clock.monotonic() + max(0.0, delay_s))

    async def wait(self) -> None:
        """Sleep until ``resume_at``; returns at once when it has already passed."""
        while True:
            remaining = self._resume_at - self._clock.monotonic()
            if remaining <= 0:
                return
            await self._clock.sleep(remaining)


class SiteBreaker:
    """Opens when ``threshold`` throttles land inside a sliding window, then stays open."""

    def __init__(
        self,
        clock: Clock,
        *,
        threshold: int = BREAKER_THRESHOLD,
        window_s: float = BREAKER_WINDOW_S,
    ) -> None:
        self._clock = clock
        self._threshold = threshold
        self._window_s = window_s
        self._events: deque[float] = deque()
        self._tripped = False

    @property
    def tripped(self) -> bool:
        """True once the breaker has opened; a poisoned session never recovers."""
        return self._tripped

    def record(self) -> None:
        """Record one throttle; raise ``ThrottledOut("breaker")`` on the one that opens it.

        The window is the half-open interval of the last ``window_s`` seconds: an event exactly
        ``window_s`` old no longer counts.
        """
        now = self._clock.monotonic()
        self._events.append(now)
        while self._events and now - self._events[0] >= self._window_s:
            self._events.popleft()
        if len(self._events) >= self._threshold:
            self._tripped = True
            raise ThrottledOut("breaker")

    def check(self) -> None:
        """Raise ``ThrottledOut("breaker")`` when the breaker is open."""
        if self._tripped:
            raise ThrottledOut("breaker")
