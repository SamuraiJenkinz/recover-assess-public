"""``GraphSession.batch`` (GRPH-04): chunking, correlation, per-sub status, re-queue, paging.

Every test runs on a fake clock, so nothing sleeps for real. All data is synthetic.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import httpx2
import pytest

from recover_assess.core.errors import GraphHttpError, ThrottledOut, UrlNotAllowedError
from recover_assess.core.graph import MAX_BATCH_SIZE, BatchItem
from recover_assess.core.throttle import full_jitter_delay
from tests.conftest import MakeGraphClient
from tests.fakes.clock import FakeClock
from tests.fakes.fake_graph import FakeGraph

LISTS_REGEX = r"/v1\.0/sites/site-\d+/lists"
BATCH_ROUTE = r"/v1\.0/\$batch"


def make_items(count: int) -> list[BatchItem]:
    return [BatchItem(f"/sites/site-{number}/lists") for number in range(1, count + 1)]


def serve_lists(fake_graph: FakeGraph) -> None:
    """Every ``/sites/site-N/lists`` answers with its own path, so a result names its item."""

    def respond(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"path": request.url.path})

    fake_graph.route("GET", LISTS_REGEX, respond)


def post_sizes(fake_graph: FakeGraph) -> list[int]:
    return [len(post) for post in fake_graph.batch_posts]


def log_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in log_text(path).splitlines()]


@pytest.mark.parametrize(
    ("count", "expected"),
    [(19, [19]), (20, [20]), (21, [20, 1]), (45, [20, 20, 5])],
)
async def test_items_are_sent_in_groups_of_at_most_twenty(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    count: int,
    expected: list[int],
) -> None:
    serve_lists(fake_graph)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        results = await session.batch(make_items(count))

    assert post_sizes(fake_graph) == expected
    assert [request.method for request in fake_graph.requests] == ["POST"] * len(expected)
    assert [result.index for result in results] == list(range(count))
    assert {result.status for result in results} == {200}


async def test_each_sub_request_carries_only_id_method_and_a_relative_url(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    serve_lists(fake_graph)
    client = await make_graph_client()
    items = [
        BatchItem("/sites/site-1/lists", {"$select": "id,displayName"}),
        BatchItem("/sites/site-2/lists"),
        BatchItem("/sites/site-3/lists"),
    ]

    async with client.open_session("site-1") as session:
        await session.batch(items)

    assert len(fake_graph.batch_posts) == 1
    subs = fake_graph.batch_posts[0]
    assert all(set(sub) == {"id", "method", "url"} for sub in subs)
    assert all(sub["method"] == "GET" for sub in subs)
    assert [sub["id"] for sub in subs] == ["1", "2", "3"]
    assert subs[0]["url"] == "/sites/site-1/lists?$select=id,displayName"
    assert not any("v1.0" in sub["url"] for sub in subs)
    assert not any(sub["url"].startswith("http") for sub in subs)
    assert fake_graph.requests[0].path == "/v1.0/$batch"


async def test_ids_restart_at_one_in_every_post(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    serve_lists(fake_graph)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        await session.batch(make_items(25))

    assert [sub["id"] for sub in fake_graph.batch_posts[0]] == [str(n) for n in range(1, 21)]
    assert [sub["id"] for sub in fake_graph.batch_posts[1]] == ["1", "2", "3", "4", "5"]


async def test_an_empty_batch_returns_nothing_and_sends_nothing(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        results = await session.batch([])

    assert results == []
    assert fake_graph.requests == []
    assert session.counters.requests == 0


async def test_one_item_makes_one_post_with_one_sub_request(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    serve_lists(fake_graph)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        results = await session.batch(make_items(1))

    assert post_sizes(fake_graph) == [1]
    assert len(results) == 1
    assert results[0].body == {"path": "/v1.0/sites/site-1/lists"}
    assert results[0].template == "/sites/{site-id}/lists"
    assert results[0].error_code is None


@pytest.mark.parametrize("chunk_size", [0, MAX_BATCH_SIZE + 1, -3])
async def test_an_invalid_chunk_size_is_refused_before_any_request(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    chunk_size: int,
) -> None:
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(ValueError, match="chunk_size"):
            await session.batch(make_items(3), chunk_size=chunk_size)

    assert fake_graph.requests == []


async def test_a_smaller_chunk_size_splits_the_batch(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    serve_lists(fake_graph)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        results = await session.batch(make_items(12), chunk_size=5)

    assert post_sizes(fake_graph) == [5, 5, 2]
    assert len(results) == 12


async def test_results_come_back_in_input_order_although_the_server_shuffles(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    serve_lists(fake_graph)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        results = await session.batch(make_items(15))

    sent_order = [str(n) for n in range(1, 16)]
    assert fake_graph.batch_response_ids[0] != sent_order
    assert sorted(fake_graph.batch_response_ids[0]) == sorted(sent_order)
    assert [result.body for result in results] == [
        {"path": f"/v1.0/sites/site-{n}/lists"} for n in range(1, 16)
    ]
    assert [result.index for result in results] == list(range(15))


async def test_a_sub_403_and_a_sub_404_are_results_not_exceptions(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.json_route(
        "GET", r"/v1\.0/sites/site-2/lists", {"error": {"code": "accessDenied"}}, status=403
    )
    fake_graph.json_route(
        "GET", r"/v1\.0/sites/site-3/lists", {"error": {"code": "itemNotFound"}}, status=404
    )
    fake_graph.json_route("GET", r"/v1\.0/sites/site-1/lists", {"value": []})
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        results = await session.batch(make_items(3))

    assert [(r.status, r.error_code, r.body) for r in results] == [
        (200, None, {"value": []}),
        (403, "graph_error_403", None),
        (404, "graph_error_404", None),
    ]
    assert len(fake_graph.requests) == 1


async def test_an_outer_200_does_not_hide_a_failed_sub_request(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.json_route("GET", r"/v1\.0/sites/site-1/lists", {"value": []}, status=500)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        results = await session.batch(make_items(1))

    assert results[0].status == 500
    assert results[0].error_code == "graph_error_500"


async def test_a_non_throttling_outer_failure_raises_with_the_batch_template(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.json_route("POST", BATCH_ROUTE, {"error": {"code": "boom"}}, status=500)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(GraphHttpError) as excinfo:
            await session.batch(make_items(2))

    assert excinfo.value.template == "/$batch"
    assert len(fake_graph.requests) == 1


async def test_an_id_the_server_does_not_answer_becomes_a_missing_result(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.json_route(
        "POST", BATCH_ROUTE, {"responses": [{"id": "1", "status": 200, "body": {"value": []}}]}
    )
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        results = await session.batch(make_items(2))

    assert [(r.index, r.status, r.error_code) for r in results] == [
        (0, 200, None),
        (1, 0, "batch_response_missing"),
    ]


async def test_only_the_throttled_sub_requests_are_re_sent_after_the_longest_retry_after(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
) -> None:
    serve_lists(fake_graph)
    fake_graph.sub_throttle(r"/v1\.0/sites/site-3/lists", times=1, retry_after="2")
    fake_graph.sub_throttle(r"/v1\.0/sites/site-7/lists", times=1, retry_after="5")
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        results = await session.batch(make_items(10))

    assert post_sizes(fake_graph) == [10, 2]
    second = fake_graph.batch_posts[1]
    assert [sub["id"] for sub in second] == ["1", "2"]
    assert [sub["url"] for sub in second] == ["/sites/site-3/lists", "/sites/site-7/lists"]
    assert fake_clock.sleeps == [5.0]
    assert fake_graph.request_times[1] - fake_graph.request_times[0] >= 5
    assert [result.status for result in results] == [200] * 10
    assert [result.body for result in results] == [
        {"path": f"/v1.0/sites/site-{n}/lists"} for n in range(1, 11)
    ]
    assert session.counters.retries == 2
    assert session.counters.throttled == 2
    # No completed item was asked for twice: 10 first-round urls plus the 2 re-sent ones.
    all_urls = [sub["url"] for post in fake_graph.batch_posts for sub in post]
    assert len(all_urls) == 12
    assert len(set(all_urls)) == 10


async def test_a_503_sub_response_is_re_queued_like_a_429(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    serve_lists(fake_graph)
    fake_graph.sub_throttle(r"/v1\.0/sites/site-2/lists", times=1, status=503)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        results = await session.batch(make_items(3))

    assert post_sizes(fake_graph) == [3, 1]
    assert [result.status for result in results] == [200, 200, 200]


async def test_a_requeue_without_retry_after_uses_seeded_full_jitter(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
) -> None:
    serve_lists(fake_graph)
    fake_graph.sub_throttle(r"/v1\.0/sites/site-2/lists", times=2)
    client = await make_graph_client(rng=random.Random(5))  # noqa: S311 - seeded test rng
    expected_rng = random.Random(5)  # noqa: S311 - seeded test rng
    expected = [full_jitter_delay(1, expected_rng), full_jitter_delay(2, expected_rng)]

    async with client.open_session("site-1") as session:
        results = await session.batch(make_items(3))

    # The gate sleeps resume_at minus now, so allow for float rounding on the clock value.
    assert fake_clock.sleeps == pytest.approx(expected)
    assert [result.status for result in results] == [200, 200, 200]


@pytest.mark.parametrize("status", [429, 503])
async def test_a_sub_request_throttled_every_round_ends_as_throttled_out(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    status: int,
) -> None:
    serve_lists(fake_graph)
    fake_graph.sub_throttle(
        r"/v1\.0/sites/site-2/lists", times=1000, status=status, retry_after="1"
    )
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        results = await session.batch(make_items(3))

    assert [(r.status, r.error_code) for r in results] == [
        (200, None),
        (status, "throttled_out"),
        (200, None),
    ]
    assert results[1].body is None
    # One first POST plus max_retries (6) re-queue rounds, each with only the stuck item.
    assert post_sizes(fake_graph) == [3, 1, 1, 1, 1, 1, 1]
    assert session.counters.retries == 6


async def test_a_requeue_that_would_pass_the_budget_raises_before_sleeping(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
) -> None:
    serve_lists(fake_graph)
    fake_graph.sub_throttle(r"/v1\.0/sites/site-1/lists", times=1, retry_after="400")
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(ThrottledOut) as excinfo:
            await session.batch(make_items(2))

    assert excinfo.value.reason == "budget"
    assert fake_clock.sleeps == []
    assert post_sizes(fake_graph) == [2]


async def test_twenty_throttled_sub_responses_open_the_breaker(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    serve_lists(fake_graph)
    fake_graph.sub_throttle(LISTS_REGEX, times=1000, retry_after="1")
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(ThrottledOut) as excinfo:
            await session.batch(make_items(20))

    assert excinfo.value.reason == "breaker"
    assert session.breaker.tripped


async def test_a_throttled_whole_batch_is_retried_by_the_outer_loop(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    fake_clock: FakeClock,
) -> None:
    serve_lists(fake_graph)
    fake_graph.throttle(BATCH_ROUTE, times=1, retry_after="3")
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        results = await session.batch(make_items(4))

    assert [result.status for result in results] == [200] * 4
    assert fake_clock.sleeps == [3.0]
    assert [request.method for request in fake_graph.requests] == ["POST", "POST"]


async def test_a_sub_response_with_a_next_link_is_completed_by_paged_gets(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    pages = [{"id": f"list-{n}"} for n in range(1, 6)]
    fake_graph.paged(r"/v1\.0/sites/site-1/lists", pages, page_size=2)
    fake_graph.json_route("GET", r"/v1\.0/sites/site-2/lists", {"value": [{"id": "only"}]})
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        results = await session.batch(make_items(2))

    paged, plain = results
    assert paged.body is not None
    assert paged.body["value"] == pages
    assert "@odata.nextLink" not in paged.body
    assert paged.truncated is False
    assert plain.body == {"value": [{"id": "only"}]}
    assert [request.method for request in fake_graph.requests] == ["POST", "GET", "GET"]
    assert all(request.authorization for request in fake_graph.requests)


async def test_the_item_cap_drops_the_excess_and_marks_truncated(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    pages = [{"id": f"list-{n}"} for n in range(1, 6)]
    fake_graph.paged(r"/v1\.0/sites/site-1/lists", pages, page_size=2)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        results = await session.batch(make_items(1), max_items_per_result=3)

    assert results[0].truncated is True
    assert results[0].body is not None
    assert results[0].body["value"] == pages[:3]
    assert [request.method for request in fake_graph.requests] == ["POST", "GET"]


async def test_a_single_page_over_the_cap_is_truncated_too(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.json_route(
        "GET", r"/v1\.0/sites/site-1/lists", {"value": [{"id": str(n)} for n in range(6)]}
    )
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        results = await session.batch(make_items(1), max_items_per_result=4)

    assert results[0].truncated is True
    assert results[0].body is not None
    assert len(results[0].body["value"]) == 4


async def test_a_hostile_next_link_in_a_sub_body_is_refused_and_never_requested(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.json_route(
        "GET",
        r"/v1\.0/sites/site-1/lists",
        {"value": [], "@odata.nextLink": "https://graph.evil.example/v1.0/sites/site-9/lists"},
    )
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(UrlNotAllowedError):
            await session.batch(make_items(1))

    assert [request.method for request in fake_graph.requests] == ["POST"]


@pytest.mark.parametrize("path", ["/me/messages", "/sites/site-1/lists/../drive", "/v1.0/sites/x"])
async def test_a_path_outside_the_allow_list_raises_before_any_post(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    path: str,
) -> None:
    serve_lists(fake_graph)
    client = await make_graph_client()

    async with client.open_session("site-1") as session:
        with pytest.raises(UrlNotAllowedError):
            await session.batch([*make_items(2), BatchItem(path)])

    assert fake_graph.requests == []
    assert session.counters.requests == 0


async def test_the_run_log_has_one_line_per_post_and_one_per_sub_response(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
    canary_token: str,
) -> None:
    fake_graph.json_route("GET", r"/v1\.0/sites/site-9/lists", {}, status=403)
    serve_lists(fake_graph)
    client = await make_graph_client()
    items = [*make_items(2), BatchItem("/sites/site-9/lists")]

    async with client.open_session("site-1") as session:
        await session.batch(items)

    text = log_text(run_log_path)
    lines = [line for line in read_lines(run_log_path) if line["event"] == "request"]
    outer = [line for line in lines if not line["via_batch"]]
    subs = [line for line in lines if line["via_batch"]]
    assert len(outer) == 1
    assert (outer[0]["template"], outer[0]["batch_size"], outer[0]["method"]) == (
        "/$batch",
        3,
        "POST",
    )
    assert len(subs) == 3
    assert {line["template"] for line in subs} == {"/sites/{site-id}/lists"}
    assert sorted(line["status"] for line in subs) == [200, 200, 403]
    assert canary_token not in text
    assert "Bearer" not in text
