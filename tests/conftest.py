"""Shared fixtures: fake clock and Graph server, run log, canary token, client factory."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from hypothesis import settings

from recover_assess.core.graph import GraphClient
from recover_assess.core.log import RunLog
from tests.fakes.clock import FakeClock
from tests.fakes.fake_graph import FakeGraph

settings.register_profile("ci", deadline=None, derandomize=True, max_examples=200)
settings.register_profile("dev", deadline=None, max_examples=100)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def fake_graph(fake_clock: FakeClock) -> FakeGraph:
    return FakeGraph(clock=fake_clock)


@pytest.fixture
def run_log_path(tmp_path: Path) -> Path:
    logs = tmp_path / "logs"
    logs.mkdir()
    return logs / "run.jsonl"


@pytest.fixture
def run_log(run_log_path: Path, fake_clock: FakeClock) -> Iterator[RunLog]:
    log = RunLog(run_log_path, fake_clock)
    yield log
    log.close()


@pytest.fixture
def canary_token() -> str:
    """A JWT-shaped token built at runtime, so no token-shaped literal exists in source."""
    return "ey" + "J" + "h" * 20 + "." + "p" * 24 + "." + "s" * 24


MakeGraphClient = Callable[..., Awaitable[GraphClient]]


@pytest.fixture
async def make_graph_client(
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
    run_log: RunLog,
    canary_token: str,
) -> AsyncIterator[MakeGraphClient]:
    """Async factory for a GraphClient on the fake transport; every client is closed at teardown."""
    clients: list[GraphClient] = []

    async def token() -> str:
        return canary_token

    async def make(**overrides: Any) -> GraphClient:
        kwargs: dict[str, Any] = {
            "token": token,
            "run_log": run_log,
            "clock": fake_clock,
            "transport": fake_graph.transport(),
        }
        kwargs.update(overrides)
        client = GraphClient(**kwargs)
        clients.append(client)
        return client

    yield make
    for client in clients:
        await client.aclose()
