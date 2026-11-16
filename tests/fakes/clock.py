"""Fake clock: time only moves when a test or a sleeper moves it."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

__all__ = ["FakeClock", "ManualClock", "settle"]

_EPOCH_MONOTONIC = 1000.0


class FakeClock:
    """Advance-on-sleep fake of ``core.clock.Clock``.

    ``sleep`` adds the requested seconds to the clock, records them and yields
    once. It is not a discrete-event scheduler, so concurrent sleepers advance
    time additively; assert gate and breaker state, not interleaved wake order.
    """

    def __init__(self) -> None:
        self.t = _EPOCH_MONOTONIC
        self.sleeps: list[float] = []
        self.now = datetime(2026, 11, 15, tzinfo=UTC)

    def monotonic(self) -> float:
        return self.t

    def utcnow(self) -> datetime:
        return self.now + timedelta(seconds=self.t - _EPOCH_MONOTONIC)

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds
        await asyncio.sleep(0)

    def sleep_sync(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds

    def advance(self, seconds: float) -> None:
        """Move the clock forward without recording a sleep."""
        self.t += seconds


class ManualClock(FakeClock):
    """A fake whose sleepers really wait until the test moves time with :meth:`tick`.

    Needed to observe two tasks at once, which advance-on-sleep cannot show.
    """

    def __init__(self) -> None:
        super().__init__()
        self._waiters: list[tuple[float, asyncio.Future[None]]] = []

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        waiter: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._waiters.append((self.t + seconds, waiter))
        await waiter

    def tick(self, seconds: float) -> None:
        """Move time forward and wake every sleeper whose time has come."""
        self.t += seconds
        due = [entry for entry in self._waiters if entry[0] <= self.t]
        self._waiters = [entry for entry in self._waiters if entry[0] > self.t]
        for _, waiter in due:
            waiter.set_result(None)


async def settle(rounds: int = 50) -> None:
    """Let every ready task run until it blocks again."""
    for _ in range(rounds):
        await asyncio.sleep(0)
