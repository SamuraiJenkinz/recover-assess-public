"""``graph_stats`` (GRPH-08) and construction from settings, with pinned counting rules."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx2
import pytest
from jsonschema import Draft202012Validator

from recover_assess import __version__
from recover_assess.core.config import load_settings
from recover_assess.core.graph import BatchItem, GraphClient, build_user_agent
from recover_assess.core.log import RunLog
from recover_assess.core.models.fact_sheet import GraphStats
from tests.conftest import MakeGraphClient
from tests.fakes.clock import FakeClock
from tests.fakes.fake_graph import FakeGraph

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "fact_sheet.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
GRAPH_STATS_VALIDATOR = Draft202012Validator(
    {"$ref": "#/$defs/GraphStats", "$defs": SCHEMA["$defs"]}
)
KEY_ORDER = ["requests", "batches", "throttled", "retries", "seconds"]
SITE_A = r"/v1\.0/sites/site-a"
SITE_B = r"/v1\.0/sites/site-b"


def counts(stats: GraphStats) -> tuple[int, int, int, int]:
    return (stats.requests, stats.batches, stats.throttled, stats.retries)


def serve_sites(fake_graph: FakeGraph) -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"path": request.url.path})

    fake_graph.route("GET", r"/v1\.0/sites/site-[a-z0-9]+", respond)
    fake_graph.route("GET", r"/v1\.0/sites/site-\d+/lists", respond)


async def test_one_successful_get_counts_one_request(
    make_graph_client: MakeGraphClient, fake_graph: FakeGraph
) -> None:
    serve_sites(fake_graph)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        await session.get("/sites/site-a")
        stats = session.graph_stats()

    assert counts(stats) == (1, 0, 0, 0)


async def test_a_retried_request_counts_one_request_per_attempt(
    make_graph_client: MakeGraphClient, fake_graph: FakeGraph
) -> None:
    fake_graph.throttle(SITE_A, times=1, retry_after="2")
    serve_sites(fake_graph)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        await session.get("/sites/site-a")
        stats = session.graph_stats()

    assert counts(stats) == (2, 0, 1, 1)
    assert len(fake_graph.requests) == 2


async def test_a_redirect_hop_counts_as_a_request(
    make_graph_client: MakeGraphClient, fake_graph: FakeGraph
) -> None:
    fake_graph.redirect(SITE_A, "https://graph.microsoft.com/v1.0/sites/site-b")
    serve_sites(fake_graph)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        await session.get("/sites/site-a")
        stats = session.graph_stats()

    assert counts(stats) == (2, 0, 0, 0)


async def test_a_batch_counts_one_request_and_one_batch_whatever_its_size(
    make_graph_client: MakeGraphClient, fake_graph: FakeGraph
) -> None:
    serve_sites(fake_graph)
    client = await make_graph_client()
    items = [BatchItem(f"/sites/site-{n}/lists") for n in (1, 2, 3)]

    async with client.open_session("site-1") as session:
        await session.batch(items)
        stats = session.graph_stats()

    assert counts(stats) == (1, 1, 0, 0)


async def test_a_requeued_sub_request_adds_one_request_one_batch_and_one_retry(
    make_graph_client: MakeGraphClient, fake_graph: FakeGraph
) -> None:
    serve_sites(fake_graph)
    fake_graph.sub_throttle(r"/v1\.0/sites/site-2/lists", times=1, retry_after="1")
    client = await make_graph_client()
    items = [BatchItem(f"/sites/site-{n}/lists") for n in (1, 2, 3)]

    async with client.open_session("site-1") as session:
        await session.batch(items)
        stats = session.graph_stats()

    assert counts(stats) == (2, 2, 1, 1)


async def test_a_throttled_whole_batch_counts_each_post(
    make_graph_client: MakeGraphClient, fake_graph: FakeGraph
) -> None:
    serve_sites(fake_graph)
    fake_graph.throttle(r"/v1\.0/\$batch", times=1, retry_after="1")
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        await session.batch([BatchItem("/sites/site-1/lists")])
        stats = session.graph_stats()

    assert counts(stats) == (2, 2, 1, 1)


async def test_an_idle_session_reports_zeros_and_validates(
    make_graph_client: MakeGraphClient,
) -> None:
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        stats = session.graph_stats()

    assert counts(stats) == (0, 0, 0, 0)
    assert stats.seconds == 0.0
    GRAPH_STATS_VALIDATOR.validate(stats.model_dump(mode="json"))


async def test_seconds_come_from_the_injected_clock_rounded_to_three_places(
    make_graph_client: MakeGraphClient, fake_clock: FakeClock
) -> None:
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        fake_clock.advance(12.3456)
        stats = session.graph_stats()

    assert stats.seconds == 12.346


async def test_stats_serialise_in_the_spec_order_and_validate_against_the_contract(
    make_graph_client: MakeGraphClient, fake_graph: FakeGraph
) -> None:
    serve_sites(fake_graph)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        await session.get("/sites/site-a")
        dumped = session.graph_stats().model_dump(mode="json")

    assert list(dumped) == KEY_ORDER
    assert list(json.loads(json.dumps(dumped))) == KEY_ORDER
    GRAPH_STATS_VALIDATOR.validate(dumped)


async def test_counters_are_per_session_and_sum_to_the_transport_total(
    make_graph_client: MakeGraphClient, fake_graph: FakeGraph
) -> None:
    serve_sites(fake_graph)
    fake_graph.throttle(SITE_B, times=2, retry_after="1")
    client = await make_graph_client()

    async def run(name: str, gets: int) -> GraphStats:
        async with client.open_session(name) as session:
            await asyncio.gather(*(session.get(f"/sites/{name}") for _ in range(gets)))
            return session.graph_stats()

    stats = await asyncio.gather(run("site-a", 3), run("site-b", 5), run("site-c", 7))

    assert stats[0].requests == 3
    assert stats[1].throttled == 2
    assert stats[0].throttled == 0
    assert sum(s.requests for s in stats) == len(fake_graph.requests)
    assert sum(s.requests for s in stats) == 3 + 5 + 7 + 2


@pytest.mark.parametrize(
    ("company", "expected"),
    [
        (None, f"recover-assess/{__version__}"),
        ("", f"recover-assess/{__version__}"),
        ("   ", f"recover-assess/{__version__}"),
        ("Contoso", f"NONISV|Contoso|recover-assess/{__version__}"),
        ("Contoso Ltd", f"NONISV|Contoso Ltd|recover-assess/{__version__}"),
    ],
)
def test_build_user_agent_forms(company: str | None, expected: str) -> None:
    assert build_user_agent(company, __version__) == expected


@pytest.mark.parametrize("company", ["Con|toso", "Con\ntoso", "Con\x00toso", "x" * 65, "tab\there"])
def test_build_user_agent_refuses_unsafe_company_names(company: str) -> None:
    with pytest.raises(ValueError, match="user_agent_company"):
        build_user_agent(company, __version__)


def test_a_company_of_exactly_64_characters_is_accepted() -> None:
    assert build_user_agent("c" * 64, "1.2.3") == "NONISV|" + "c" * 64 + "|recover-assess/1.2.3"


@pytest.mark.parametrize(
    ("company", "expected"),
    [
        ("Contoso", f"NONISV|Contoso|recover-assess/{__version__}"),
        (None, f"recover-assess/{__version__}"),
    ],
)
async def test_from_settings_sends_the_decorated_user_agent_on_every_request(
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
    run_log: RunLog,
    canary_token: str,
    company: str | None,
    expected: str,
) -> None:
    seen: list[str] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.headers["user-agent"])
        return httpx2.Response(200, json={})

    fake_graph.route("GET", r"/v1\.0/sites/site-[a-z]", respond)
    http: dict[str, Any] = {}
    if company is not None:
        http["user_agent_company"] = company
    settings = load_settings(environ={}, cli_overrides={"http": http} if http else None)

    async def token() -> str:
        return canary_token

    async with (
        GraphClient.from_settings(
            settings,
            token=token,
            run_log=run_log,
            clock=fake_clock,
            transport=fake_graph.transport(),
        ) as client,
        client.open_session("site-1") as session,
    ):
        await session.get("/sites/site-a")
        await session.get("/sites/site-b")

    assert seen == [expected, expected]
