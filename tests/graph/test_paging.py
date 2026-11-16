"""Paging to the end, the item cap, hostile next links and annotation stripping (GRPH-02, GRPH-03).

Every request goes through ``httpx2.MockTransport`` via the client factory; no test touches
the network. Hostile links that would trip the repo scan are assembled at runtime.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from recover_assess.core.errors import GraphError, UrlNotAllowedError
from recover_assess.core.graph import GRAPH_BASE_URL, Page, PagedResult, strip_annotations
from tests.conftest import MakeGraphClient
from tests.fakes.fake_graph import SYNTHETIC_SITE_ID, FakeGraph

LISTS_PATH = f"/sites/{SYNTHETIC_SITE_ID}/lists"
LISTS_REGEX = r"/v1\.0/sites/[^/]+/lists"
HOST = "https://graph.microsoft.com"


def make_items(count: int) -> list[dict[str, Any]]:
    return [{"id": f"item-{index}"} for index in range(count)]


def read_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def test_iter_pages_follows_next_links_to_the_end(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.paged(LISTS_REGEX, make_items(7), page_size=3)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        pages = [page async for page in session.iter_pages(LISTS_PATH)]

    assert [len(page.items) for page in pages] == [3, 3, 1]
    assert [r.method for r in fake_graph.requests] == ["GET"] * 3
    assert pages[0].next_link is not None
    assert pages[1].next_link is not None
    assert pages[2].next_link is None
    assert fake_graph.requests[1].url == pages[0].next_link
    assert fake_graph.requests[2].url == pages[1].next_link
    assert all(isinstance(page, Page) for page in pages)


@pytest.mark.parametrize(
    ("cap", "total", "page_size", "expected_items", "truncated", "pages"),
    [
        (10, 7, 3, 7, False, 3),
        (7, 7, 3, 7, False, 3),
        (6, 7, 3, 6, True, 2),
        (3, 3, 3, 3, False, 1),
        (12, 7, 3, 7, False, 3),
        (2, 7, 3, 2, True, 1),
    ],
    ids=["cap-above", "cap-equal", "cap-below", "one-page-exact", "cap-well-above", "cap-in-page"],
)
async def test_get_all_marks_truncation_at_the_cap(
    cap: int,
    total: int,
    page_size: int,
    expected_items: int,
    truncated: bool,
    pages: int,
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.paged(LISTS_REGEX, make_items(total), page_size=page_size)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        result = await session.get_all(LISTS_PATH, cap=cap)

    assert isinstance(result, PagedResult)
    assert len(result.items) == expected_items
    assert result.items == make_items(total)[:expected_items]
    assert result.truncated is truncated
    assert result.cap == cap
    assert result.pages == pages
    assert len(fake_graph.requests) == pages


async def test_cap_equal_to_the_item_count_with_a_remaining_next_link_is_truncated(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.paged(LISTS_REGEX, make_items(6), page_size=3)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        result = await session.get_all(LISTS_PATH, cap=3)

    assert len(result.items) == 3
    assert result.truncated is True
    assert result.pages == 1
    assert len(fake_graph.requests) == 1


async def test_more_available_than_the_cap_drops_the_excess_and_stops_requesting(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.paged(LISTS_REGEX, make_items(8), page_size=4)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        result = await session.get_all(LISTS_PATH, cap=3)

    assert result.items == make_items(8)[:3]
    assert result.truncated is True
    assert len(fake_graph.requests) == 1


@pytest.mark.parametrize("cap", [0, -1])
async def test_get_all_rejects_a_cap_below_one_before_any_request(
    cap: int,
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(ValueError, match="cap must be at least 1"):
            await session.get_all(LISTS_PATH, cap=cap)

    assert fake_graph.requests == []


def hostile_links() -> list[tuple[str, str]]:
    userinfo = HOST + "@" + "evil.example/v1.0/sites"
    return [
        ("foreign-host", "https://evil.example/v1.0/sites"),
        ("http-scheme", "http://graph.microsoft.com/v1.0/sites/x/lists"),
        ("beta-prefix", HOST + "/beta/sites/x/lists"),
        ("item-content", HOST + "/v1.0/drives/d/items/i/content"),
        ("userinfo-host", userinfo),
        ("explicit-port", "https://graph.microsoft.com:8443/v1.0/sites/x/lists"),
        ("empty-string", ""),
    ]


@pytest.mark.parametrize(
    "hostile_link",
    [link for _, link in hostile_links()],
    ids=[name for name, _ in hostile_links()],
)
async def test_a_hostile_next_link_is_refused_and_never_requested(
    hostile_link: str,
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
    canary_token: str,
) -> None:
    token_calls: list[int] = []

    async def counting_token() -> str:
        token_calls.append(1)
        return canary_token

    fake_graph.paged(
        LISTS_REGEX,
        make_items(7),
        page_size=3,
        hostile_next_link_on_page=2,
        hostile_link=hostile_link,
    )
    client = await make_graph_client(token=counting_token)

    async with client.open_session("site-1") as session:
        with pytest.raises(UrlNotAllowedError) as excinfo:
            _ = [page async for page in session.iter_pages(LISTS_PATH)]

    assert excinfo.type is UrlNotAllowedError
    assert len(fake_graph.requests) == 2
    assert all(r.url.startswith(GRAPH_BASE_URL + "/sites/") for r in fake_graph.requests)
    assert all("evil" not in r.url and "8443" not in r.url for r in fake_graph.requests)
    assert len(token_calls) == 2
    assert len(read_lines(run_log_path)) == 2


async def test_a_hostile_first_page_link_stops_get_all_even_at_the_cap(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.paged(
        LISTS_REGEX,
        make_items(3),
        page_size=3,
        hostile_next_link_on_page=1,
        hostile_link="https://evil.example/v1.0/sites",
    )
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(UrlNotAllowedError):
            await session.get_all(LISTS_PATH, cap=3)

    assert len(fake_graph.requests) == 1


async def test_a_non_string_next_link_is_refused(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.json_route("GET", LISTS_REGEX, {"value": [], "@odata.nextLink": 123})
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(UrlNotAllowedError):
            _ = [page async for page in session.iter_pages(LISTS_PATH)]

    assert len(fake_graph.requests) == 1


@pytest.mark.parametrize("body", [{"value": []}, {"value": [], "@odata.nextLink": None}])
async def test_an_absent_or_null_next_link_ends_paging(
    body: dict[str, Any],
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.json_route("GET", LISTS_REGEX, body)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        pages = [page async for page in session.iter_pages(LISTS_PATH)]

    assert len(pages) == 1
    assert pages[0].next_link is None
    assert len(fake_graph.requests) == 1


async def test_the_delta_link_is_exposed_on_the_last_page_and_not_followed(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    delta = GRAPH_BASE_URL + "/drives/d/root/delta?token=abc"
    fake_graph.json_route("GET", LISTS_REGEX, {"value": [{"id": "a"}], "@odata.deltaLink": delta})
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        pages = [page async for page in session.iter_pages(LISTS_PATH)]

    assert pages[0].delta_link == delta
    assert pages[0].next_link is None
    assert len(fake_graph.requests) == 1


async def test_a_page_without_a_value_array_is_a_graph_error(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.json_route("GET", LISTS_REGEX, {"id": "not-a-collection"})
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(GraphError) as excinfo:
            _ = [page async for page in session.iter_pages(LISTS_PATH)]

    assert excinfo.value.reason == "response_missing_value"
    assert excinfo.value.template == "/sites/{site-id}/lists"


async def test_download_annotations_never_reach_the_caller(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    download = "https://contoso.example/dl/" + "z" * 8
    key = "@microsoft.graph." + "downloadUrl"
    body = {
        key: download,
        "@odata.count": 2,
        "value": [
            {"id": "a", key: download, "file": {key: download, "name": "n"}},
            {"id": "b", "items": [{key: download, "id": "c"}]},
        ],
    }
    fake_graph.json_route("GET", LISTS_REGEX, body)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        got = await session.get(LISTS_PATH)
        pages = [page async for page in session.iter_pages(LISTS_PATH)]

    for result in (got, [page.items for page in pages]):
        text = json.dumps(result)
        assert "@microsoft.graph." not in text
        assert download not in text
    assert got["@odata.count"] == 2
    assert got["value"][0] == {"id": "a", "file": {"name": "n"}}
    assert pages[0].items[1] == {"id": "b", "items": [{"id": "c"}]}


async def test_odata_paging_keys_survive_annotation_stripping(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    link = GRAPH_BASE_URL + "/sites/x/lists?$skiptoken=2"
    fake_graph.json_route("GET", LISTS_REGEX, {"value": [], "@odata.nextLink": link})
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        got = await session.get(LISTS_PATH)

    assert got["@odata.nextLink"] == link


def test_strip_annotations_copies_and_leaves_the_input_untouched() -> None:
    key = "@microsoft.graph." + "downloadUrl"
    original = {"a": [{key: "x", "b": 1}], key: "y", "n": None}

    stripped = strip_annotations(original)

    assert stripped == {"a": [{"b": 1}], "n": None}
    assert original == {"a": [{key: "x", "b": 1}], key: "y", "n": None}
    assert strip_annotations(5) == 5
    assert strip_annotations("text") == "text"
