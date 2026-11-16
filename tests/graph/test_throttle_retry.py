"""Client-level throttling (GRPH-05): Retry-After, jitter, budget, shared gate and breaker.

Every test runs on a fake clock, so nothing sleeps for real.
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import timedelta
from email.utils import format_datetime
from pathlib import Path

import pytest

from recover_assess.core.errors import GraphHttpError, ThrottledOut
from recover_assess.core.throttle import full_jitter_delay
from tests.conftest import MakeGraphClient
from tests.fakes.clock import FakeClock, ManualClock, settle
from tests.fakes.fake_graph import FakeGraph

PATH_A = "/sites/site-a"
REGEX_A = r"/v1\.0/sites/site-a"
PATH_B = "/sites/site-b"
REGEX_B = r"/v1\.0/sites/site-b"
BODY = {"id": "site-a", "displayName": "Contoso Team"}


def log_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in log_text(path).splitlines()]


def lines_of(path: Path, event: str) -> list[dict[str, object]]:
    return [line for line in read_lines(path) if line["event"] == event]


async def test_retry_after_seconds_is_honoured_then_the_body_is_returned(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
    run_log_path: Path,
    canary_token: str,
) -> None:
    fake_graph.throttle(REGEX_A, times=1, retry_after="5")
    fake_graph.json_route("GET", REGEX_A, BODY)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        result = await session.get(PATH_A)

    assert result == BODY
    assert fake_clock.sleeps == [5.0]
    requests = lines_of(run_log_path, "request")
    assert [(line["retry"], line["status"]) for line in requests] == [(0, 429), (1, 200)]
    retries = lines_of(run_log_path, "retry")
    assert len(retries) == 1
    assert retries[0]["attempt"] == 1
    assert retries[0]["delay_s"] == 5.0
    assert retries[0]["status"] == 429
    assert retries[0]["template"] == "/sites/{site-id}"
    assert canary_token not in log_text(run_log_path)


async def test_a_retry_after_http_date_is_measured_on_the_injected_clock(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
) -> None:
    when = format_datetime(fake_clock.utcnow() + timedelta(seconds=20), usegmt=True)
    fake_graph.throttle(REGEX_A, times=1, retry_after=when)
    fake_graph.json_route("GET", REGEX_A, BODY)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        await session.get(PATH_A)

    assert fake_clock.sleeps == [20.0]


async def test_503_without_retry_after_uses_seeded_full_jitter(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
) -> None:
    fake_graph.throttle(REGEX_A, times=2, status=503)
    fake_graph.json_route("GET", REGEX_A, BODY)
    client = await make_graph_client(rng=random.Random(7))  # noqa: S311 - seeded test rng
    expected_rng = random.Random(7)  # noqa: S311 - seeded test rng
    expected = [full_jitter_delay(1, expected_rng), full_jitter_delay(2, expected_rng)]

    async with client.open_session("site-1") as session:
        result = await session.get(PATH_A)

    assert result == BODY
    assert fake_clock.sleeps == expected
    assert len(fake_graph.requests) == 3


async def test_an_unparseable_retry_after_falls_back_to_jitter(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
) -> None:
    fake_graph.throttle(REGEX_A, times=1, retry_after="soon")
    fake_graph.json_route("GET", REGEX_A, BODY)
    client = await make_graph_client(rng=random.Random(3))  # noqa: S311 - seeded test rng

    async with client.open_session("site-1") as session:
        await session.get(PATH_A)

    assert fake_clock.sleeps == [full_jitter_delay(1, random.Random(3))]  # noqa: S311 - seeded


async def test_the_seventh_consecutive_throttle_exhausts_the_retries(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
    run_log_path: Path,
) -> None:
    fake_graph.throttle(REGEX_A, times=50, retry_after="1")
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(ThrottledOut) as info:
            await session.get(PATH_A)

    assert info.value.reason == "retries_exhausted"
    assert info.value.code == "throttled_out"
    assert len(fake_graph.requests) == 7
    assert len(fake_clock.sleeps) == 6
    assert [line["retry"] for line in lines_of(run_log_path, "request")] == list(range(7))
    assert len(lines_of(run_log_path, "retry")) == 6


async def test_six_throttles_then_success_is_still_within_the_retry_limit(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
) -> None:
    fake_graph.throttle(REGEX_A, times=6, retry_after="1")
    fake_graph.json_route("GET", REGEX_A, BODY)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        assert await session.get(PATH_A) == BODY

    assert len(fake_graph.requests) == 7
    assert len(fake_clock.sleeps) == 6


async def test_max_retries_zero_never_retries(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
) -> None:
    fake_graph.throttle(REGEX_A, times=5, retry_after="1")
    client = await make_graph_client(max_retries=0)

    async with client.open_session("site-1") as session:
        with pytest.raises(ThrottledOut) as info:
            await session.get(PATH_A)

    assert info.value.reason == "retries_exhausted"
    assert len(fake_graph.requests) == 1
    assert fake_clock.sleeps == []


async def test_a_wait_that_would_pass_the_budget_fails_at_once_without_sleeping(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
) -> None:
    fake_graph.throttle(REGEX_A, times=50, retry_after="100")
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(ThrottledOut) as info:
            await session.get(PATH_A)

    assert info.value.reason == "budget"
    assert fake_clock.sleeps == [100.0, 100.0, 100.0]
    assert len(fake_graph.requests) == 4


async def test_a_wait_that_reaches_exactly_the_budget_is_allowed(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
) -> None:
    fake_graph.throttle(REGEX_A, times=3, retry_after="100")
    fake_graph.json_route("GET", REGEX_A, BODY)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        assert await session.get(PATH_A) == BODY

    assert fake_clock.sleeps == [100.0, 100.0, 100.0]
    assert fake_clock.monotonic() - 1000.0 == 300.0


async def test_a_hostile_retry_after_is_refused_at_once(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
) -> None:
    fake_graph.throttle(REGEX_A, times=5, retry_after="86400")
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(ThrottledOut) as info:
            await session.get(PATH_A)

    assert info.value.reason == "budget"
    assert fake_clock.sleeps == []
    assert len(fake_graph.requests) == 1


@pytest.mark.parametrize("status", [400, 403, 404, 500, 502, 504])
async def test_other_statuses_are_sent_once_and_never_retried(
    status: int,
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
    run_log_path: Path,
) -> None:
    fake_graph.json_route("GET", REGEX_A, {"error": {"code": "x"}}, status=status)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(GraphHttpError) as info:
            await session.get(PATH_A)

    assert info.value.status == status
    assert len(fake_graph.requests) == 1
    assert fake_clock.sleeps == []
    assert lines_of(run_log_path, "retry") == []
    assert session.counters.retries == 0


async def test_a_throttle_on_one_site_holds_the_next_send_on_another_site(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    clock = ManualClock()
    fake_graph.clock = clock
    fake_graph.throttle(REGEX_A, times=1, retry_after="10")
    fake_graph.json_route("GET", REGEX_A, BODY)
    fake_graph.json_route("GET", REGEX_B, {"id": "site-b"})
    client = await make_graph_client(clock=clock)
    start = clock.monotonic()

    async with client.open_session("a") as session_a, client.open_session("b") as session_b:
        task_a = asyncio.create_task(session_a.get(PATH_A))
        await settle()
        assert [r.path for r in fake_graph.requests] == ["/v1.0" + PATH_A]
        throttled_at = fake_graph.request_times[0]

        task_b = asyncio.create_task(session_b.get(PATH_B))
        await settle()
        # B is held by the shared gate: it has not sent anything yet.
        assert [r.path for r in fake_graph.requests] == ["/v1.0" + PATH_A]
        assert not task_b.done()

        clock.tick(10)
        await settle()
        assert await task_a == BODY
        assert await task_b == {"id": "site-b"}

        b_index = next(i for i, r in enumerate(fake_graph.requests) if r.path.endswith("site-b"))
        assert fake_graph.request_times[b_index] >= throttled_at + 10
        assert clock.monotonic() == start + 10
        assert session_b.counters.throttled == 0
        assert session_b.counters.requests == 1
        assert session_a.counters.throttled == 1


async def test_the_breaker_fails_a_site_without_touching_other_sites(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
) -> None:
    fake_graph.throttle(REGEX_A, times=1000, retry_after="1")
    fake_graph.json_route("GET", REGEX_B, {"id": "site-b"})
    client = await make_graph_client()

    async with client.open_session("a") as session_a, client.open_session("b") as session_b:
        reasons: list[str] = []
        for _ in range(3):
            with pytest.raises(ThrottledOut) as info:
                await session_a.get(PATH_A)
            reasons.append(info.value.reason)
        assert reasons == ["retries_exhausted", "retries_exhausted", "breaker"]
        assert session_a.counters.throttled == 20
        assert session_a.counters.requests == 20
        assert session_a.breaker.tripped is True

        sent = len(fake_graph.requests)
        with pytest.raises(ThrottledOut) as poisoned:
            await session_a.get(PATH_A)
        assert poisoned.value.reason == "breaker"
        assert len(fake_graph.requests) == sent

        assert await session_b.get(PATH_B) == {"id": "site-b"}
        assert session_b.breaker.tripped is False


async def test_session_counters_tally_sends_throttles_and_retries(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.throttle(REGEX_A, times=1, status=429, retry_after="0")
    fake_graph.throttle(REGEX_A, times=1, status=503, retry_after="0")
    fake_graph.json_route("GET", REGEX_A, BODY)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        assert session.counters.requests == 0
        await session.get(PATH_A)

    assert session.counters.requests == 3
    assert session.counters.throttled == 2
    assert session.counters.retries == 2
    assert session.counters.batches == 0


async def test_a_negative_retry_limit_is_refused(make_graph_client: MakeGraphClient) -> None:
    with pytest.raises(ValueError, match="max_retries must not be negative"):
        await make_graph_client(max_retries=-1)
