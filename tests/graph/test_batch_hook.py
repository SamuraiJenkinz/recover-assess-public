"""The request hook re-validates every serialised ``$batch`` body on its own (T-01-33).

Every request here goes through the raw ``httpx2`` client built by ``make_http_client`` (never
through ``ReadOnlyPolicy.check``), and the MockTransport handler records what reaches it, so
"refused" means ``fake_graph.requests`` stayed empty.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx2
import pytest

from recover_assess.core.errors import UrlNotAllowedError, WriteAttemptError
from recover_assess.core.graph import make_http_client
from recover_assess.core.graph_policy import MatchedTemplate, ReadOnlyPolicy, load_allowlist
from tests.conftest import MakeGraphClient
from tests.fakes.fake_graph import SYNTHETIC_SITE_ID, FakeGraph

BATCH_URL = "https://graph.microsoft.com/v1.0/$batch"
BATCH_ROUTE = r"/v1\.0/\$batch"
SITE_SUB_URL = f"/sites/{SYNTHETIC_SITE_ID}"
LISTS_SUB_URL = f"sites/{SYNTHETIC_SITE_ID}/lists"


def log_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sub(request_id: str, url: str, method: str = "GET") -> dict[str, Any]:
    return {"id": request_id, "method": method, "url": url}


VALID_BODY: dict[str, Any] = {"requests": [sub("1", SITE_SUB_URL), sub("2", LISTS_SUB_URL)]}


@pytest.fixture
async def raw_client(fake_graph: FakeGraph) -> AsyncIterator[httpx2.AsyncClient]:
    client = make_http_client(
        connect_timeout_s=30.0, read_timeout_s=120.0, transport=fake_graph.transport()
    )
    yield client
    await client.aclose()


async def test_a_valid_get_only_batch_reaches_the_transport_once(
    raw_client: httpx2.AsyncClient, fake_graph: FakeGraph
) -> None:
    fake_graph.json_route("POST", BATCH_ROUTE, {"responses": []})

    await raw_client.request("POST", BATCH_URL, json=VALID_BODY)

    assert len(fake_graph.requests) == 1
    assert fake_graph.requests[0].method == "POST"
    assert fake_graph.requests[0].body == VALID_BODY


REFUSED_SHAPES: dict[str, Any] = {
    "delete": {"requests": [sub("1", SITE_SUB_URL, "DELETE")]},
    "post-lower": {"requests": [sub("1", SITE_SUB_URL, "post")]},
    "patch-mixed": {"requests": [sub("1", SITE_SUB_URL, "Patch")]},
    "body-key": {"requests": [{**sub("1", SITE_SUB_URL), "body": {"a": 1}}]},
    "depends-on-key": {"requests": [{**sub("1", SITE_SUB_URL), "dependsOn": ["2"]}]},
    "headers-key": {"requests": [{**sub("1", SITE_SUB_URL), "headers": {"X-Test": "1"}}]},
    "nested-batch": {"requests": [sub("1", "/$batch")]},
    "twenty-one": {"requests": [sub(str(n), SITE_SUB_URL) for n in range(1, 22)]},
    "empty-list": {"requests": []},
    "missing-requests": {},
    "ids-differ-by-case": {"requests": [sub("a", SITE_SUB_URL), sub("A", SITE_SUB_URL)]},
}


@pytest.mark.parametrize("body", list(REFUSED_SHAPES.values()), ids=list(REFUSED_SHAPES))
async def test_the_hook_refuses_an_unsafe_batch_shape_before_any_transport(
    body: dict[str, Any], raw_client: httpx2.AsyncClient, fake_graph: FakeGraph
) -> None:
    with pytest.raises(WriteAttemptError) as excinfo:
        await raw_client.request("POST", BATCH_URL, json=body)

    assert excinfo.type is WriteAttemptError
    assert fake_graph.requests == []


REFUSED_URLS: dict[str, str] = {
    "absolute": "https://graph.microsoft.com/v1.0/sites/x",
    "leading-v1": "/v1.0/sites/x",
    "content": "/sites/x/lists/y/items/z/content",
}


@pytest.mark.parametrize("url", list(REFUSED_URLS.values()), ids=list(REFUSED_URLS))
async def test_the_hook_refuses_an_unsafe_sub_url_before_any_transport(
    url: str, raw_client: httpx2.AsyncClient, fake_graph: FakeGraph
) -> None:
    with pytest.raises(UrlNotAllowedError) as excinfo:
        await raw_client.request("POST", BATCH_URL, json={"requests": [sub("1", url)]})

    assert isinstance(excinfo.value, WriteAttemptError)
    assert fake_graph.requests == []


async def test_the_hook_refuses_a_duplicate_key_that_hides_a_write_in_a_sub_request(
    raw_client: httpx2.AsyncClient, fake_graph: FakeGraph
) -> None:
    text = '{"requests": [{"id": "1", "method": "GET", "method": "DELETE", "url": "/sites/x"}]}'

    with pytest.raises(WriteAttemptError) as excinfo:
        await raw_client.request(
            "POST", BATCH_URL, content=text, headers={"Content-Type": "application/json"}
        )

    assert excinfo.value.reason == "batch_body_unreadable"
    assert fake_graph.requests == []


UNREADABLE: dict[str, tuple[bytes, str]] = {
    "not-json": (b"not json", "application/json"),
    "top-level-array": (b'[{"id": "1", "method": "GET", "url": "/sites/x"}]', "application/json"),
    "empty": (b"", "application/json"),
    "wrong-content-type": (json.dumps(VALID_BODY).encode(), "text/plain"),
    "content-type-prefix-only": (json.dumps(VALID_BODY).encode(), "application/jsonx"),
    "invalid-utf8": (b'{"requests": "\xff"}', "application/json"),
}


@pytest.mark.parametrize("case", list(UNREADABLE), ids=list(UNREADABLE))
async def test_the_hook_refuses_an_unreadable_batch_body(
    case: str, raw_client: httpx2.AsyncClient, fake_graph: FakeGraph
) -> None:
    content, content_type = UNREADABLE[case]

    with pytest.raises(WriteAttemptError) as excinfo:
        await raw_client.request(
            "POST", BATCH_URL, content=content, headers={"Content-Type": content_type}
        )

    assert excinfo.value.reason == "batch_body_unreadable"
    assert fake_graph.requests == []


async def test_a_content_type_with_parameters_and_odd_case_is_accepted(
    raw_client: httpx2.AsyncClient, fake_graph: FakeGraph
) -> None:
    fake_graph.json_route("POST", BATCH_ROUTE, {"responses": []})

    await raw_client.request(
        "POST",
        BATCH_URL,
        content=json.dumps(VALID_BODY),
        headers={"Content-Type": "Application/JSON; charset=utf-8"},
    )

    assert len(fake_graph.requests) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://graph.microsoft.com/v1.0/$BATCH",
        "https://graph.microsoft.com/v1.0/$batch/extra",
        "https://graph.microsoft.com/v1.0/sites/x",
    ],
    ids=["upper-case", "extra-segment", "other-path"],
)
async def test_post_to_any_other_path_is_still_a_refused_write(
    url: str, raw_client: httpx2.AsyncClient, fake_graph: FakeGraph
) -> None:
    with pytest.raises(WriteAttemptError) as excinfo:
        await raw_client.request("POST", url, json=VALID_BODY)

    assert excinfo.value.reason == "method_not_allowed"
    assert fake_graph.requests == []


async def test_a_query_on_the_batch_url_is_refused(
    raw_client: httpx2.AsyncClient, fake_graph: FakeGraph
) -> None:
    with pytest.raises(WriteAttemptError):
        await raw_client.request("POST", BATCH_URL + "?$select=id", json=VALID_BODY)

    assert fake_graph.requests == []


async def test_the_other_write_verbs_to_the_batch_url_are_refused(
    raw_client: httpx2.AsyncClient, fake_graph: FakeGraph
) -> None:
    for method in ("PUT", "PATCH", "DELETE"):
        with pytest.raises(WriteAttemptError):
            await raw_client.request(method, BATCH_URL, json=VALID_BODY)

    assert fake_graph.requests == []


class AcceptEverythingPolicy(ReadOnlyPolicy):
    """A test double standing in for a buggy or permissive injected policy."""

    def check(
        self,
        method: str,
        url: str,
        *,
        batch_body: Any = None,
    ) -> MatchedTemplate:
        return MatchedTemplate(id="batch", template="/$batch")


async def test_the_hook_does_not_depend_on_the_injected_policy(
    make_graph_client: MakeGraphClient, fake_graph: FakeGraph
) -> None:
    permissive = AcceptEverythingPolicy(load_allowlist())
    client = await make_graph_client(policy=permissive)
    body = {"requests": [sub("1", "/sites/x", "DELETE")]}

    async with client.open_session("site-1") as session:
        with pytest.raises(WriteAttemptError):
            await client._send(session, "POST", BATCH_URL, json_body=body)

    assert fake_graph.requests == []


async def test_a_valid_batch_through_the_permissive_client_is_still_sent(
    make_graph_client: MakeGraphClient, fake_graph: FakeGraph
) -> None:
    fake_graph.json_route("POST", BATCH_ROUTE, {"responses": []})
    client = await make_graph_client(policy=AcceptEverythingPolicy(load_allowlist()))

    async with client.open_session("site-1") as session:
        await client._send(session, "POST", BATCH_URL, json_body=VALID_BODY)

    assert [r.method for r in fake_graph.requests] == ["POST"]


async def test_the_packaged_policy_is_one_cached_instance() -> None:
    from recover_assess.core.graph import packaged_policy

    assert packaged_policy() is packaged_policy()


async def test_a_refused_batch_leaves_no_trace_in_the_run_log(
    make_graph_client: MakeGraphClient, run_log_path: Path
) -> None:
    client = await make_graph_client(policy=AcceptEverythingPolicy(load_allowlist()))

    async with client.open_session("site-1") as session:
        with pytest.raises(WriteAttemptError):
            await client._send(
                session, "POST", BATCH_URL, json_body={"requests": [sub("1", "/me", "DELETE")]}
            )

    # The request line is written only after a response or a transport error.
    assert log_text(run_log_path) == ""
