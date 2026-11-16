"""Injectable clock.

Anything that waits or reads the time takes a ``Clock`` so tests can fake it.
This is the only module allowed to sleep (it is exempt from the ruff TID251
ban on ``time.sleep`` and ``asyncio.sleep``).
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Final, Protocol, runtime_checkable

__all__ = ["SYSTEM_CLOCK", "Clock", "SystemClock"]


@runtime_checkable
class Clock(Protocol):
    """Time source and sleeper."""

    def monotonic(self) -> float:
        """Seconds from a monotonic clock."""
        ...

    def utcnow(self) -> datetime:
        """The current time as a timezone-aware UTC datetime."""
        ...

    async def sleep(self, seconds: float) -> None:
        """Wait without blocking the event loop."""
        ...

    def sleep_sync(self, seconds: float) -> None:
        """Wait, blocking the calling thread."""
        ...


class SystemClock:
    """The real clock."""

    def monotonic(self) -> float:
        return time.monotonic()

    def utcnow(self) -> datetime:
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    def sleep_sync(self, seconds: float) -> None:
        time.sleep(seconds)


SYSTEM_CLOCK: Final = SystemClock()
