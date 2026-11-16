"""Canary log capture across every client path (GRPH-07, ROADMAP success criterion 4).

Every canary is built at runtime by concatenation so no token-shaped or signed-URL-shaped
literal exists in this file (the FND-07 repo scan). Each test writes to its own run.jsonl and
then asserts that none of the canaries reached it, that every request line has exactly the
twelve contract keys, that each template belongs to the allow-list and that the reusable audit
finds nothing. Exceptions raised to the caller are checked for the same canaries.
"""

from __future__ import annotations

import json
import re
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx2
import pytest

from recover_assess.core.errors import (
    GraphHttpError,
    GraphTransportError,
    UrlNotAllowedError,
    WriteAttemptError,
)
from recover_assess.core.graph import GRAPH_BASE_URL, BatchItem
from recover_assess.core.graph_policy import load_allowlist
from tests.conftest import MakeGraphClient
from tests.fakes.fake_graph import FakeGraph
from tests.support.log_audit import AuditFinding, audit_run_log

SESSION_KEY = "site-1"
REQUEST_KEYS = {
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
    "via_batch",
    "batch_size",
}
TEMPLATES = {entry.template for entry in load_allowlist().entries}
SELECT = {"$select": "id,displayName"}


@dataclass(frozen=True)
class Canaries:
    """Every value that must never reach run.jsonl or an exception message."""

    token: str
    sentinel: str
    download_url: str
    title: str
    site_id: str
    drive_id: str
    item_id: str

    @property
    def values(self) -> list[str]:
        """The raw strings to search for, including the pieces of the signed URL."""
        return [
            self.token,
            self.sentinel,
            self.download_url,
            "tempauth=",
            "sig=",
            self.title,
            self.site_id,
            self.drive_id,
            self.item_id,
        ]

    def body(self, **extra: Any) -> dict[str, Any]:
        """A fake response body carrying every canary a real body could."""
        return {
            "id": self.site_id,
            "displayName": self.title,
            "note": self.sentinel,
            "@microsoft.graph.downloadUrl": self.download_url,
            "child": {"@microsoft.graph.downloadUrl": self.download_url, "name": self.sentinel},
            **extra,
        }


@pytest.fixture
def canaries(canary_token: str) -> Canaries:
    return Canaries(
        token=canary_token,
        sentinel="body-" + "sentinel-" + "k" * 12,
        download_url="https://contoso-my.sharepoint.com/dl/file"
        + "?tempauth="
        + "t" * 14
        + "&sig="
        + "q" * 14,
        title="Canary Title " + "Z" * 8,
        site_id="sitecanary" + "7" * 10,
        drive_id="b!drivecanary" + "8" * 10,
        item_id="itemcanary" + "9" * 10,
    )


def site_regex(site_id: str, tail: str = "") -> str:
    return r"/v1\.0/sites/" + re.escape(site_id) + tail


def read_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def assert_log_clean(path: Path, canaries: Canaries) -> list[dict[str, Any]]:
    """Assert the contract for one run.jsonl and return its parsed lines."""
    text = path.read_text(encoding="utf-8")
    for value in canaries.values:
        assert value not in text
    assert "downloadurl" not in text.casefold()
    assert "Bearer" not in text
    assert "?" not in text
    assert "https://" not in text
    assert "evil" not in text
    lines = read_lines(path)
    for line in lines:
        if line["event"] == "request":
            assert set(line) == REQUEST_KEYS
            assert line["template"] in TEMPLATES
            assert line["site"] == SESSION_KEY
        elif line["event"] == "retry":
            assert line["template"] in TEMPLATES
            assert line["site"] == SESSION_KEY
    assert audit_run_log(path) == []
    return lines


def assert_exception_clean(exc: BaseException, canaries: Canaries) -> None:
    """Assert an exception carries no URL, query string or canary, in text or traceback."""
    text = str(exc)
    for value in canaries.values:
        assert value not in text
    assert "https://" not in text
    assert "?" not in text
    assert "evil" not in text
    assert exc.__context__ is None or exc.__suppress_context__
    assert exc.__cause__ is None
    rendered = "".join(traceback.format_exception(exc))
    for value in canaries.values:
        assert value not in rendered


def request_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [line for line in lines if line["event"] == "request"]


async def test_a_single_get_logs_only_a_template_and_the_opaque_site_key(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
    canaries: Canaries,
) -> None:
    fake_graph.json_route("GET", site_regex(canaries.site_id), canaries.body())
    client = await make_graph_client()

    async with client.open_session(SESSION_KEY) as session:
        result = await session.get(f"/sites/{canaries.site_id}", SELECT)

    assert "@microsoft.graph.downloadUrl" not in result
    assert "@microsoft.graph.downloadUrl" not in result["child"]
    lines = assert_log_clean(run_log_path, canaries)
    assert [(line["method"], line["status"]) for line in request_lines(lines)] == [("GET", 200)]


async def test_a_capped_paged_get_logs_one_templated_line_per_page(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
    canaries: Canaries,
) -> None:
    items = [canaries.body(index=number) for number in range(40)]
    fake_graph.paged(site_regex(canaries.site_id, "/lists"), items, page_size=10)
    client = await make_graph_client()

    async with client.open_session(SESSION_KEY) as session:
        result = await session.get_all(f"/sites/{canaries.site_id}/lists", SELECT, cap=25)

    assert result.truncated is True
    assert len(result.items) == 25
    assert all("@microsoft.graph.downloadUrl" not in item for item in result.items)
    lines = assert_log_clean(run_log_path, canaries)
    assert len(request_lines(lines)) == 3
    assert {line["template"] for line in lines} == {"/sites/{site-id}/lists"}


async def test_a_followed_redirect_logs_a_clean_line_per_hop(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
    canaries: Canaries,
) -> None:
    fake_graph.redirect(site_regex("start-site"), GRAPH_BASE_URL + "/sites/final-site")
    fake_graph.json_route("GET", site_regex("final-site"), canaries.body())
    client = await make_graph_client()

    async with client.open_session(SESSION_KEY) as session:
        await session.get("/sites/start-site", SELECT)

    lines = assert_log_clean(run_log_path, canaries)
    assert [line["status"] for line in request_lines(lines)] == [302, 200]


async def test_a_hostile_redirect_is_refused_with_clean_log_and_message(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
    canaries: Canaries,
) -> None:
    hostile = "https://evil.example/steal" + "?sig=" + "z" * 10 + "&tempauth=" + "y" * 10
    fake_graph.redirect(site_regex("start-site"), hostile)
    client = await make_graph_client()

    async with client.open_session(SESSION_KEY) as session:
        with pytest.raises(UrlNotAllowedError) as info:
            await session.get("/sites/start-site")

    assert_exception_clean(info.value, canaries)
    assert [request.path for request in fake_graph.requests] == ["/v1.0/sites/start-site"]
    lines = assert_log_clean(run_log_path, canaries)
    assert [line["status"] for line in request_lines(lines)] == [302]


async def test_a_hostile_next_link_is_refused_with_clean_log_and_message(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
    canaries: Canaries,
) -> None:
    hostile = "https://evil.example/next" + "?sig=" + "z" * 10
    fake_graph.paged(
        site_regex(canaries.site_id, "/lists"),
        [canaries.body(index=number) for number in range(30)],
        page_size=10,
        hostile_next_link_on_page=1,
        hostile_link=hostile,
    )
    client = await make_graph_client()

    async with client.open_session(SESSION_KEY) as session:
        with pytest.raises(UrlNotAllowedError) as info:
            await session.get_all(f"/sites/{canaries.site_id}/lists", cap=100)

    assert_exception_clean(info.value, canaries)
    assert len(fake_graph.requests) == 1
    lines = assert_log_clean(run_log_path, canaries)
    assert len(request_lines(lines)) == 1


async def test_a_throttled_then_successful_get_logs_a_clean_retry(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
    canaries: Canaries,
) -> None:
    fake_graph.throttle(site_regex(canaries.site_id), times=1, retry_after="1")
    fake_graph.json_route("GET", site_regex(canaries.site_id), canaries.body())
    client = await make_graph_client()

    async with client.open_session(SESSION_KEY) as session:
        await session.get(f"/sites/{canaries.site_id}", SELECT)

    lines = assert_log_clean(run_log_path, canaries)
    assert [(line["retry"], line["status"]) for line in request_lines(lines)] == [
        (0, 429),
        (1, 200),
    ]
    assert len([line for line in lines if line["event"] == "retry"]) == 1


async def test_a_403_with_a_sentinel_body_surfaces_a_clean_error(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
    canaries: Canaries,
) -> None:
    error_body = {"error": {"code": "accessDenied", "message": canaries.sentinel + canaries.title}}
    fake_graph.json_route("GET", site_regex(canaries.site_id), error_body, status=403)
    client = await make_graph_client()

    async with client.open_session(SESSION_KEY) as session:
        with pytest.raises(GraphHttpError) as info:
            await session.get(f"/sites/{canaries.site_id}")

    assert info.value.status == 403
    assert_exception_clean(info.value, canaries)
    lines = assert_log_clean(run_log_path, canaries)
    assert [line["status"] for line in request_lines(lines)] == [403]


@pytest.mark.parametrize(
    "failure",
    [httpx2.ReadTimeout, httpx2.ConnectError],
    ids=["read_timeout", "connect_error"],
)
async def test_a_transport_error_with_a_url_in_its_message_surfaces_a_clean_error(
    failure: type[httpx2.TransportError],
    make_graph_client: MakeGraphClient,
    run_log_path: Path,
    canaries: Canaries,
) -> None:
    def refuse(request: httpx2.Request) -> httpx2.Response:
        message = f"{request.url} failed with {canaries.token} {canaries.download_url}"
        raise failure(message, request=request)

    client = await make_graph_client(transport=httpx2.MockTransport(refuse))

    async with client.open_session(SESSION_KEY) as session:
        with pytest.raises(GraphTransportError) as info:
            await session.get(f"/sites/{canaries.site_id}", SELECT)

    assert info.value.is_timeout is (failure is httpx2.ReadTimeout)
    assert_exception_clean(info.value, canaries)
    lines = assert_log_clean(run_log_path, canaries)
    assert [line["status"] for line in request_lines(lines)] == [None]


async def test_a_batch_with_a_throttled_and_a_failed_sub_response_logs_clean_lines(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
    canaries: Canaries,
) -> None:
    fake_graph.json_route("GET", site_regex(canaries.site_id), canaries.body())
    fake_graph.json_route("GET", site_regex(canaries.site_id, "/lists"), canaries.body())
    fake_graph.sub_throttle(site_regex(canaries.site_id, "/lists"), times=1, retry_after="1")
    fake_graph.json_route(
        "GET",
        r"/v1\.0/drives/"
        + re.escape(canaries.drive_id)
        + r"/items/"
        + re.escape(canaries.item_id)
        + "/permissions",
        {"error": {"code": "itemNotFound", "message": canaries.sentinel}},
        status=404,
    )
    client = await make_graph_client()

    async with client.open_session(SESSION_KEY) as session:
        results = await session.batch(
            [
                BatchItem(f"/sites/{canaries.site_id}", SELECT),
                BatchItem(f"/sites/{canaries.site_id}/lists", SELECT),
                BatchItem(f"/drives/{canaries.drive_id}/items/{canaries.item_id}/permissions"),
            ]
        )

    assert [result.status for result in results] == [200, 200, 404]
    assert [result.error_code for result in results] == [None, None, "graph_error_404"]
    assert results[0].body is not None
    assert "@microsoft.graph.downloadUrl" not in results[0].body
    lines = assert_log_clean(run_log_path, canaries)
    posts = [line for line in request_lines(lines) if line["method"] == "POST"]
    assert [line["template"] for line in posts] == ["/$batch", "/$batch"]
    assert [line["batch_size"] for line in posts] == [3, 1]
    subs = [line for line in request_lines(lines) if line["via_batch"]]
    assert [line["status"] for line in subs] == [200, 429, 404, 200]


async def test_a_delete_on_the_raw_client_is_refused_before_anything_is_logged_or_sent(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
    canaries: Canaries,
) -> None:
    client = await make_graph_client()

    with pytest.raises(WriteAttemptError) as info:
        await client._http.request("DELETE", f"{GRAPH_BASE_URL}/sites/{canaries.site_id}")

    assert_exception_clean(info.value, canaries)
    assert fake_graph.requests == []
    assert_log_clean(run_log_path, canaries)


@pytest.mark.parametrize(
    "hostile_id",
    ["https://evil.example/x" + "?sig=" + "z" * 8, "Bearer " + "x" * 24, "line\nbreak"],
    ids=["url", "bearer", "newline"],
)
async def test_a_hostile_request_id_header_never_reaches_the_log(
    hostile_id: str,
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
    canaries: Canaries,
) -> None:
    safe = "11111111-2222-3333-4444-555555555555"
    fake_graph.json_route(
        "GET", site_regex(canaries.site_id), canaries.body(), headers={"request-id": hostile_id}
    )
    fake_graph.json_route(
        "GET", site_regex("other-site"), canaries.body(), headers={"request-id": safe}
    )
    client = await make_graph_client()

    async with client.open_session(SESSION_KEY) as session:
        await session.get(f"/sites/{canaries.site_id}")
        await session.get("/sites/other-site")

    lines = assert_log_clean(run_log_path, canaries)
    assert [line["request_id"] for line in request_lines(lines)] == [None, safe]


async def test_a_request_retried_twice_logs_retry_0_1_2_and_two_retry_lines(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
    canaries: Canaries,
) -> None:
    fake_graph.throttle(site_regex(canaries.site_id), times=2, retry_after="1")
    fake_graph.json_route("GET", site_regex(canaries.site_id), canaries.body())
    client = await make_graph_client()

    async with client.open_session(SESSION_KEY) as session:
        await session.get(f"/sites/{canaries.site_id}")

    lines = assert_log_clean(run_log_path, canaries)
    assert [line["retry"] for line in request_lines(lines)] == [0, 1, 2]
    assert len([line for line in lines if line["event"] == "retry"]) == 2


async def test_a_batch_of_three_logs_one_outer_line_and_three_via_batch_lines(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
    canaries: Canaries,
) -> None:
    fake_graph.json_route("GET", site_regex(canaries.site_id), canaries.body())
    client = await make_graph_client()

    async with client.open_session(SESSION_KEY) as session:
        await session.batch([BatchItem(f"/sites/{canaries.site_id}") for _ in range(3)])

    lines = assert_log_clean(run_log_path, canaries)
    outer = [line for line in request_lines(lines) if not line["via_batch"]]
    subs = [line for line in request_lines(lines) if line["via_batch"]]
    assert [(line["method"], line["template"], line["batch_size"]) for line in outer] == [
        ("POST", "/$batch", 3)
    ]
    assert len(subs) == 3
    assert {line["method"] for line in subs} == {"GET"}


async def test_a_followed_redirect_logs_exactly_one_line_per_hop(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
    canaries: Canaries,
) -> None:
    fake_graph.redirect(site_regex("start-site"), GRAPH_BASE_URL + "/sites/final-site")
    fake_graph.json_route("GET", site_regex("final-site"), canaries.body())
    client = await make_graph_client()

    async with client.open_session(SESSION_KEY) as session:
        await session.get("/sites/start-site")

    assert len(request_lines(assert_log_clean(run_log_path, canaries))) == 2
    assert len(fake_graph.requests) == 2


def test_the_audit_flags_a_delete_a_post_outside_batch_and_a_secret(
    tmp_path: Path, canary_token: str
) -> None:
    base = {
        "ts": "2026-11-15T00:00:00Z",
        "level": "INFO",
        "event": "request",
        "site": SESSION_KEY,
        "status": 200,
        "duration_ms": 1.0,
        "retry": 0,
        "request_id": None,
        "via_batch": False,
        "batch_size": None,
    }
    delete_line = {**base, "method": "DELETE", "template": "/sites/{site-id}"}
    post_line = {**base, "method": "POST", "template": "/sites/{site-id}"}
    leaky_line = {
        **base,
        "method": "GET",
        "template": "/sites/{site-id}",
        "request_id": canary_token,
    }
    path = tmp_path / "run.jsonl"
    path.write_text(
        "\n".join(json.dumps(line) for line in (delete_line, post_line, leaky_line)) + "\n",
        encoding="utf-8",
    )

    findings = audit_run_log(path)

    assert AuditFinding(1, "method_not_get_or_post") in findings
    assert AuditFinding(2, "post_outside_batch") in findings
    assert AuditFinding(3, "secret_pattern_jwt") in findings
    assert all(canary_token not in repr(finding) for finding in findings)


def test_the_audit_flags_an_unparseable_line_and_accepts_a_clean_batch_post(
    tmp_path: Path,
) -> None:
    clean_post = {
        "ts": "2026-11-15T00:00:00Z",
        "level": "INFO",
        "event": "request",
        "site": SESSION_KEY,
        "method": "POST",
        "template": "/$batch",
        "status": 200,
        "duration_ms": 1.0,
        "retry": 0,
        "request_id": None,
        "via_batch": False,
        "batch_size": 3,
    }
    path = tmp_path / "run.jsonl"
    path.write_text(json.dumps(clean_post) + "\nnot json\n", encoding="utf-8")

    assert audit_run_log(path) == [AuditFinding(2, "unparseable_line")]
