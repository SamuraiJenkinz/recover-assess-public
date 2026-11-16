"""Transport and proxy regression guard, and the request hook on the raw client.

``httpx2`` ignores ``HTTPS_PROXY``/``NO_PROXY`` when a transport is passed, so production
must never pass one. These tests turn a regression of that into a red build.
"""

from __future__ import annotations

import pytest

from recover_assess.core.errors import UrlNotAllowedError, WriteAttemptError
from recover_assess.core.graph import GRAPH_BASE_URL, make_http_client
from tests.conftest import MakeGraphClient
from tests.fakes.fake_graph import SYNTHETIC_SITE_ID, FakeGraph

PROXY = "http://proxy.example:8080"


def clear_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)


async def test_production_client_keeps_the_environment_proxy_mounts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_proxy_env(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", PROXY)
    client = make_http_client(connect_timeout_s=30.0, read_timeout_s=120.0)
    try:
        assert client._mounts
        assert client.follow_redirects is False
    finally:
        await client.aclose()


async def test_no_proxy_is_honoured_for_the_graph_host(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_proxy_env(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", PROXY)
    monkeypatch.setenv("NO_PROXY", "graph.microsoft.com")
    client = make_http_client(connect_timeout_s=30.0, read_timeout_s=120.0)
    try:
        assert any(transport is None for transport in client._mounts.values())
    finally:
        await client.aclose()


async def test_an_injected_transport_has_no_proxy_mounts(
    monkeypatch: pytest.MonkeyPatch,
    fake_graph: FakeGraph,
) -> None:
    clear_proxy_env(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", PROXY)
    client = make_http_client(
        connect_timeout_s=30.0, read_timeout_s=120.0, transport=fake_graph.transport()
    )
    try:
        assert not client._mounts
        assert client.follow_redirects is False
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    ("url", "error"),
    [
        ("https://evil.example/v1.0/sites/x", UrlNotAllowedError),
        ("https://graph.microsoft.com:8443/v1.0/sites/x", UrlNotAllowedError),
    ],
    ids=["foreign-host", "explicit-port"],
)
async def test_the_request_hook_refuses_foreign_hosts_before_the_transport(
    url: str,
    error: type[Exception],
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    client = await make_graph_client()

    with pytest.raises(error):
        await client._http.request("GET", url)

    assert fake_graph.requests == []


async def test_the_request_hook_refuses_a_post_to_a_site_path(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    client = await make_graph_client()

    with pytest.raises(WriteAttemptError):
        await client._http.request("POST", f"{GRAPH_BASE_URL}/sites/{SYNTHETIC_SITE_ID}")

    assert fake_graph.requests == []


async def test_the_raw_client_does_not_follow_a_redirect_on_its_own(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
) -> None:
    fake_graph.redirect(r"/v1\.0/sites/start-site", GRAPH_BASE_URL + "/sites/final-site")
    client = await make_graph_client()

    response = await client._http.request("GET", GRAPH_BASE_URL + "/sites/start-site")

    assert response.status_code == 302
    assert len(fake_graph.requests) == 1
