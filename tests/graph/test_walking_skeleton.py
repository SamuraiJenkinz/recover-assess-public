"""Walking skeleton: one allow-listed GET travels policy, client, hook and transport.

Every request goes through ``httpx2.MockTransport`` via the client factory; no test
touches the network.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx2
import pytest

from recover_assess.core.errors import (
    GraphHttpError,
    GraphTransportError,
    UrlNotAllowedError,
    WriteAttemptError,
)
from recover_assess.core.graph import GRAPH_BASE_URL, GraphSession, make_http_client
from tests.conftest import MakeGraphClient
from tests.fakes.clock import FakeClock
from tests.fakes.fake_graph import SYNTHETIC_SITE_ID, FakeGraph

SITE_PATH = f"/sites/{SYNTHETIC_SITE_ID}"
SITE_REGEX = r"/v1\.0/sites/[^/]+"
REQUEST_ID = "11111111-2222-3333-4444-555555555555"
REQUIRED_FIELDS = {
    "ts",
    "level",
    "event",
    "site",
    "method",
    "template",
    "status",
    "duration_ms",
    "retry",
    "request_id",
}


def log_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in log_text(path).splitlines()]


async def test_one_get_writes_one_typed_line(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
    run_log_path: Path,
    canary_token: str,
) -> None:
    body = {"id": SYNTHETIC_SITE_ID, "displayName": "Contoso Team"}
    fake_graph.json_route("GET", SITE_REGEX, body, headers={"request-id": REQUEST_ID})
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        result = await session.get(SITE_PATH)

    assert result == body
    lines = read_lines(run_log_path)
    assert len(lines) == 1
    line = lines[0]
    assert set(line) >= REQUIRED_FIELDS
    assert line["event"] == "request"
    assert line["level"] == "INFO"
    assert line["site"] == "site-1"
    assert line["method"] == "GET"
    assert line["template"] == "/sites/{site-id}"
    assert line["status"] == 200
    assert line["retry"] == 0
    assert line["request_id"] == REQUEST_ID
    assert line["duration_ms"] == 0.0
    assert line["ts"] == "2026-11-15T00:00:00Z"
    assert canary_token not in log_text(run_log_path)
    assert [r.authorization for r in fake_graph.requests] == [f"Bearer {canary_token}"]


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "delete"])
async def test_non_get_verbs_never_reach_the_transport(
    method: str,
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
) -> None:
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(WriteAttemptError) as excinfo:
            await client._send(session, method, GRAPH_BASE_URL + SITE_PATH)

    assert excinfo.type is WriteAttemptError
    assert fake_graph.requests == []
    assert log_text(run_log_path) == ""


async def test_path_off_the_allow_list_is_refused_and_not_logged(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
) -> None:
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(UrlNotAllowedError):
            await session.get("/me/drive")
        with pytest.raises(WriteAttemptError):
            await session.get("/me/drive")

    assert fake_graph.requests == []
    assert log_text(run_log_path) == ""


async def test_not_found_raises_graph_http_error_and_is_logged(
    make_graph_client: MakeGraphClient,
    run_log_path: Path,
) -> None:
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(GraphHttpError) as excinfo:
            await session.get(SITE_PATH)

    assert excinfo.value.code == "graph_error_404"
    lines = read_lines(run_log_path)
    assert len(lines) == 1
    assert lines[0]["status"] == 404


async def test_query_parameters_are_encoded_and_recorded(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.json_route("GET", SITE_REGEX, {"id": SYNTHETIC_SITE_ID})
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        await session.get(SITE_PATH, {"$select": "id,displayName"})

    assert fake_graph.requests[0].query == [("$select", "id,displayName")]


async def test_make_http_client_keeps_env_proxies_unless_a_transport_is_given(
    monkeypatch: pytest.MonkeyPatch,
    fake_graph: FakeGraph,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    production = make_http_client(connect_timeout_s=30.0, read_timeout_s=120.0)
    injected = make_http_client(
        connect_timeout_s=30.0, read_timeout_s=120.0, transport=fake_graph.transport()
    )
    try:
        assert production._mounts
        assert not injected._mounts
        assert production.follow_redirects is False
        assert injected.follow_redirects is False
        assert production.timeout.connect == 30.0
        assert production.timeout.read == 120.0
    finally:
        await production.aclose()
        await injected.aclose()


SITE_URL = GRAPH_BASE_URL + SITE_PATH


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "delete"])
async def test_raw_client_write_verbs_are_refused_by_the_request_hook(
    method: str,
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
) -> None:
    client = await make_graph_client()

    with pytest.raises(WriteAttemptError) as excinfo:
        await client._http.request(method, SITE_URL)

    assert excinfo.type is WriteAttemptError
    assert fake_graph.requests == []
    assert log_text(run_log_path) == ""


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/v1.0/sites/x",
        "http://graph.microsoft.com/v1.0/sites/x",
        "https://graph.microsoft.com:8443/v1.0/sites/x",
    ],
)
async def test_raw_client_foreign_hosts_are_refused_by_the_request_hook(
    url: str,
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
) -> None:
    client = await make_graph_client()

    with pytest.raises(UrlNotAllowedError) as excinfo:
        await client._http.request("GET", url)

    assert excinfo.type is UrlNotAllowedError
    assert fake_graph.requests == []
    assert log_text(run_log_path) == ""


async def test_raw_client_get_outside_the_v1_prefix_is_refused(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    client = await make_graph_client()

    with pytest.raises(WriteAttemptError):
        await client._http.request("GET", "https://graph.microsoft.com/beta/sites/x")

    assert fake_graph.requests == []


async def test_ten_gets_and_one_delete_reach_the_transport_as_ten_gets(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.json_route("GET", SITE_REGEX, {"id": SYNTHETIC_SITE_ID})
    client = await make_graph_client()

    outcomes = await asyncio.gather(
        *[client._http.request("GET", SITE_URL) for _ in range(10)],
        client._http.request("DELETE", SITE_URL),
        return_exceptions=True,
    )

    assert [r.method for r in fake_graph.requests] == ["GET"] * 10
    assert sum(isinstance(o, WriteAttemptError) for o in outcomes) == 1


async def test_connect_error_becomes_a_url_free_transport_error_with_one_line(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
) -> None:
    def refuse(_request: httpx2.Request) -> httpx2.Response:
        message = "connect failed " + GRAPH_BASE_URL + "/sites/x?" + "sig=" + "q" * 8
        raise httpx2.ConnectError(message)

    fake_graph.route("GET", SITE_REGEX, refuse)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(GraphTransportError) as excinfo:
            await session.get(SITE_PATH)

    text = str(excinfo.value)
    assert "https://" not in text
    assert "sig=" not in text
    assert excinfo.value.is_timeout is False
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True
    lines = read_lines(run_log_path)
    assert len(lines) == 1
    assert lines[0]["status"] is None


async def test_read_timeout_is_flagged_as_a_timeout(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
) -> None:
    def time_out(_request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out")

    fake_graph.route("GET", SITE_REGEX, time_out)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(GraphTransportError) as excinfo:
            await session.get(SITE_PATH)

    assert excinfo.value.is_timeout is True
    assert len(read_lines(run_log_path)) == 1


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"client-request-id": REQUEST_ID}, REQUEST_ID),
        (
            {"request-id": REQUEST_ID, "client-request-id": "66666666-7777-8888-9999-000000000000"},
            REQUEST_ID,
        ),
        ({}, None),
    ],
)
async def test_request_id_falls_back_to_client_request_id_then_null(
    headers: dict[str, str],
    expected: str | None,
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
) -> None:
    fake_graph.json_route("GET", SITE_REGEX, {"id": SYNTHETIC_SITE_ID}, headers=headers)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        await session.get(SITE_PATH)

    assert read_lines(run_log_path)[0]["request_id"] == expected


async def test_session_exposes_no_write_methods(make_graph_client: MakeGraphClient) -> None:
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        assert isinstance(session, GraphSession)
        for name in ("post", "put", "patch", "delete"):
            assert not hasattr(session, name)
