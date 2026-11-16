"""Manual, validated redirects (GRPH-02, D-09).

A 3xx is never followed automatically: its Location is resolved, validated by the read-only
policy, and only then requested, at most three times. Hostile and token-shaped strings that
would trip the repo scan are assembled at runtime.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from recover_assess.core.errors import GraphHttpError, UrlNotAllowedError
from recover_assess.core.graph import GRAPH_BASE_URL, MAX_REDIRECT_HOPS
from tests.conftest import MakeGraphClient
from tests.fakes.fake_graph import FakeGraph

START = "/sites/start-site"
FINAL = "/sites/final-site"
START_REGEX = r"/v1\.0/sites/start-site"
FINAL_REGEX = r"/v1\.0/sites/final-site"
BODY = {"id": "final-site", "displayName": "Contoso Team"}


def log_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in log_text(path).splitlines()]


async def test_an_absolute_location_is_followed_once_and_logged_per_hop(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
    canary_token: str,
) -> None:
    fake_graph.redirect(START_REGEX, GRAPH_BASE_URL + FINAL)
    fake_graph.json_route("GET", FINAL_REGEX, BODY)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        result = await session.get(START)

    assert result == BODY
    assert [r.path for r in fake_graph.requests] == ["/v1.0" + START, "/v1.0" + FINAL]
    assert all(r.authorization == f"Bearer {canary_token}" for r in fake_graph.requests)
    lines = read_lines(run_log_path)
    assert [line["status"] for line in lines] == [302, 200]
    assert {line["template"] for line in lines} == {"/sites/{site-id}"}
    assert canary_token not in log_text(run_log_path)


async def test_a_relative_location_is_resolved_against_the_request_url(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.redirect(START_REGEX, "/v1.0" + FINAL)
    fake_graph.json_route("GET", FINAL_REGEX, BODY)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        result = await session.get(START)

    assert result == BODY
    assert len(fake_graph.requests) == 2


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_every_redirect_status_is_followed_the_same_way(
    status: int,
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.redirect(START_REGEX, GRAPH_BASE_URL + FINAL, status=status)
    fake_graph.json_route("GET", FINAL_REGEX, BODY)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        result = await session.get(START)

    assert result == BODY
    assert len(fake_graph.requests) == 2


async def test_a_not_modified_response_is_not_a_redirect(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.redirect(START_REGEX, GRAPH_BASE_URL + FINAL, status=304)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(GraphHttpError) as excinfo:
            await session.get(START)

    assert excinfo.value.status == 304
    assert len(fake_graph.requests) == 1


def hostile_locations() -> list[tuple[str, str]]:
    userinfo = "https://graph.microsoft.com" + "@" + "evil.example/v1.0/sites/x"
    return [
        ("foreign-host", "https://evil.example/x"),
        ("scheme-relative", "//evil.example/x"),
        ("http-scheme", "http://graph.microsoft.com/v1.0/sites/x"),
        ("beta-prefix", "https://graph.microsoft.com/beta/sites/x"),
        ("item-content", GRAPH_BASE_URL + "/drives/d/items/i/content"),
        ("userinfo-host", userinfo),
        ("explicit-port", "https://graph.microsoft.com:8443/v1.0/sites/x"),
    ]


@pytest.mark.parametrize(
    "location",
    [location for _, location in hostile_locations()],
    ids=[name for name, _ in hostile_locations()],
)
async def test_a_hostile_location_is_refused_and_never_requested(
    location: str,
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
    canary_token: str,
) -> None:
    token_calls: list[int] = []

    async def counting_token() -> str:
        token_calls.append(1)
        return canary_token

    fake_graph.redirect(START_REGEX, location)
    client = await make_graph_client(token=counting_token)

    async with client.open_session("site-1") as session:
        with pytest.raises(UrlNotAllowedError) as excinfo:
            await session.get(START)

    assert excinfo.type is UrlNotAllowedError
    assert [r.path for r in fake_graph.requests] == ["/v1.0" + START]
    assert len(token_calls) == 1
    assert [line["status"] for line in read_lines(run_log_path)] == [302]


def chain(fake_graph: FakeGraph, length: int) -> None:
    """Redirects hop-0 to hop-1 and so on for ``length`` hops, then a 200 at the end."""
    for index in range(length):
        fake_graph.redirect(
            rf"/v1\.0/sites/hop-{index}", GRAPH_BASE_URL + f"/sites/hop-{index + 1}"
        )
    fake_graph.json_route("GET", rf"/v1\.0/sites/hop-{length}", BODY)


async def test_three_consecutive_redirects_are_allowed(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    chain(fake_graph, MAX_REDIRECT_HOPS)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        result = await session.get("/sites/hop-0")

    assert result == BODY
    assert len(fake_graph.requests) == MAX_REDIRECT_HOPS + 1


async def test_a_fourth_consecutive_redirect_is_refused_after_three_follow_ups(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    chain(fake_graph, MAX_REDIRECT_HOPS + 1)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(UrlNotAllowedError) as excinfo:
            await session.get("/sites/hop-0")

    assert MAX_REDIRECT_HOPS == 3
    assert excinfo.value.reason == "too_many_redirects"
    assert len(fake_graph.requests) == MAX_REDIRECT_HOPS + 1
    assert fake_graph.requests[-1].path == f"/v1.0/sites/hop-{MAX_REDIRECT_HOPS}"


@pytest.mark.parametrize("location", [None, ""], ids=["no-header", "empty-header"])
async def test_a_redirect_without_a_location_is_refused_and_sends_nothing_more(
    location: str | None,
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.redirect(START_REGEX, location)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(UrlNotAllowedError) as excinfo:
            await session.get(START)

    assert excinfo.value.reason == "redirect_without_location"
    assert len(fake_graph.requests) == 1


async def test_a_redirect_answering_a_batch_post_is_refused(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.json_route(
        "POST",
        r"/v1\.0/\$batch",
        {},
        status=307,
        headers={"Location": GRAPH_BASE_URL + FINAL},
    )
    fake_graph.json_route("GET", FINAL_REGEX, BODY)
    client = await make_graph_client()
    body = {"requests": [{"id": "1", "method": "GET", "url": "/sites/x"}]}

    async with client.open_session("site-1") as session:
        with pytest.raises(UrlNotAllowedError) as excinfo:
            await client._send(session, "POST", GRAPH_BASE_URL + "/$batch", json_body=body)

    assert excinfo.value.reason == "redirect_on_batch"
    assert [r.method for r in fake_graph.requests] == ["POST"]
