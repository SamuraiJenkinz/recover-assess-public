"""Concurrency limits (GRPH-06): 2 sites at once and 4 requests in flight per site.

The fake server yields several times inside every request, so concurrent tasks really
interleave and a peak counter can only reach its limit if the client allows it.
"""

from __future__ import annotations

import asyncio

import httpx2
import pytest

from recover_assess.core.config import load_settings
from recover_assess.core.graph import GraphClient
from recover_assess.core.log import RunLog
from tests.conftest import MakeGraphClient
from tests.fakes.clock import FakeClock, ManualClock, settle
from tests.fakes.fake_graph import FakeGraph

SITE_REGEX = r"/v1\.0/sites/site-[a-z0-9]+"


def serve_sites(fake_graph: FakeGraph) -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"path": request.url.path})

    fake_graph.route("GET", SITE_REGEX, respond)


class SessionPeak:
    """Counts the sessions that are open at the same moment."""

    def __init__(self) -> None:
        self.current = 0
        self.peak = 0

    def enter(self) -> None:
        self.current += 1
        self.peak = max(self.peak, self.current)

    def leave(self) -> None:
        self.current -= 1


async def drive_site(
    client: GraphClient, peak: SessionPeak, name: str, gets: int
) -> list[dict[str, object]]:
    async with client.open_session(name) as session:
        peak.enter()
        try:
            fetched: list[dict[str, object]] = await asyncio.gather(
                *(session.get(f"/sites/{name}") for _ in range(gets))
            )
            return fetched
        finally:
            peak.leave()


async def test_five_sessions_of_ten_gets_peak_at_two_sites_and_four_in_flight(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    serve_sites(fake_graph)
    client = await make_graph_client()
    peak = SessionPeak()

    results = await asyncio.gather(
        *(drive_site(client, peak, f"site-{name}", 10) for name in "abcde")
    )

    assert peak.peak == 2
    assert max(fake_graph.peak_in_flight.values()) == 4
    assert set(fake_graph.peak_in_flight) == {f"site-{name}" for name in "abcde"}
    assert all(value <= 4 for value in fake_graph.peak_in_flight.values())
    assert sum(len(batch) for batch in results) == 50
    assert len(fake_graph.requests) == 50
    assert all(count == 0 for count in fake_graph.current_in_flight.values())


async def test_a_lower_per_site_limit_is_respected(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    serve_sites(fake_graph)
    client = await make_graph_client(max_in_flight_per_site=1)

    await drive_site(client, SessionPeak(), "site-a", 8)

    assert fake_graph.peak_in_flight == {"site-a": 1}
    assert len(fake_graph.requests) == 8


async def test_one_site_slot_means_sessions_never_overlap(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    serve_sites(fake_graph)
    client = await make_graph_client(max_sites=1)
    peak = SessionPeak()

    await asyncio.gather(*(drive_site(client, peak, f"site-{name}", 3) for name in "abc"))

    assert peak.peak == 1
    assert len(fake_graph.requests) == 9


async def test_a_third_session_waits_until_a_site_slot_is_released(
    make_graph_client: MakeGraphClient,
) -> None:
    client = await make_graph_client()
    third_entered = asyncio.Event()
    release = asyncio.Event()

    async def hold() -> None:
        async with client.open_session("held"):
            await release.wait()

    async def third() -> None:
        async with client.open_session("third"):
            third_entered.set()

    holders = [asyncio.create_task(hold()), asyncio.create_task(hold())]
    await settle()
    waiting = asyncio.create_task(third())
    await settle()
    assert not third_entered.is_set()

    release.set()
    await asyncio.gather(*holders, waiting)
    assert third_entered.is_set()


class _BodyFailedError(Exception):
    """Raised inside a session body to prove the site slot is released."""


async def test_the_site_slot_is_released_when_a_session_body_raises(
    make_graph_client: MakeGraphClient,
) -> None:
    client = await make_graph_client(max_sites=1)

    async def failing_session() -> None:
        async with client.open_session("first"):
            raise _BodyFailedError

    with pytest.raises(_BodyFailedError):
        await failing_session()

    async with asyncio.timeout(5), client.open_session("second") as session:
        assert session.site_key == "second"


async def test_a_request_sleeping_on_a_429_backoff_does_not_hold_its_slot(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    clock = ManualClock()
    fake_graph.clock = clock
    fake_graph.throttle(r"/v1\.0/sites/site-a", times=1, retry_after="5")
    serve_sites(fake_graph)
    client = await make_graph_client(clock=clock, max_in_flight_per_site=1)

    async with client.open_session("one-site") as session:
        task_a = asyncio.create_task(session.get("/sites/site-a"))
        task_b = asyncio.create_task(session.get("/sites/site-b"))
        await settle()

        # With a single slot, B can only have been sent if A gave its slot back to sleep.
        assert task_b.done()
        assert not task_a.done()
        assert any(request.path.endswith("site-b") for request in fake_graph.requests)

        clock.tick(5)
        await settle()
        assert (await task_a)["path"] == "/v1.0/sites/site-a"


@pytest.mark.parametrize(
    ("field", "value"),
    [("max_sites", 0), ("max_in_flight_per_site", 0), ("max_in_flight_per_site", -1)],
)
async def test_limits_below_one_are_refused(
    make_graph_client: MakeGraphClient, field: str, value: int
) -> None:
    with pytest.raises(ValueError, match=field):
        await make_graph_client(**{field: value})


async def test_from_settings_maps_the_concurrency_limits(
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
    run_log: RunLog,
    canary_token: str,
) -> None:
    serve_sites(fake_graph)
    settings = load_settings(
        environ={},
        cli_overrides={"http": {"max_in_flight_per_site": 3, "max_concurrent_sites": 1}},
    )

    async def token() -> str:
        return canary_token

    async with GraphClient.from_settings(
        settings,
        token=token,
        run_log=run_log,
        clock=fake_clock,
        transport=fake_graph.transport(),
    ) as client:
        peak = SessionPeak()
        await asyncio.gather(*(drive_site(client, peak, f"site-{name}", 10) for name in "ab"))

    assert peak.peak == 1
    assert max(fake_graph.peak_in_flight.values()) == 3
