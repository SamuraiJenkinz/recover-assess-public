"""A fake Graph server on ``httpx2.MockTransport`` that records every request.

Synthetic data only: host names are contoso, every GUID group is one repeated hex
digit (the FND-07 scan convention).
"""

from __future__ import annotations

import asyncio
import inspect
import json
import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl

import httpx2

from recover_assess.core.clock import Clock

__all__ = ["SYNTHETIC_SITE_ID", "FakeGraph", "RecordedRequest", "Responder"]

SYNTHETIC_SITE_ID = (
    "contoso.sharepoint.com,"
    "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee,"
    "11111111-2222-3333-4444-555555555555"
)

Responder = Callable[[httpx2.Request], httpx2.Response | Awaitable[httpx2.Response]]


@dataclass(frozen=True)
class RecordedRequest:
    """One request the transport handler saw."""

    method: str
    url: str
    path: str
    query: list[tuple[str, str]]
    authorization: str | None
    body: Any


class _ThrottleRule:
    """The next ``remaining`` requests matching ``pattern`` get a throttling status."""

    def __init__(
        self, pattern: re.Pattern[str], remaining: int, status: int, retry_after: str | None
    ) -> None:
        self.pattern = pattern
        self.remaining = remaining
        self.status = status
        self.retry_after = retry_after


_SITE_OR_DRIVE = re.compile(r"/v1\.0/(?:sites|drives)/([^/]+)")
_BATCH_PATH = "/v1.0/$batch"
_YIELDS_IN_HANDLER = 5


class FakeGraph:
    """Routes keyed by method and a path regex; unmatched requests get a 404.

    When ``clock`` is set, the clock value at each handled request is appended to
    ``request_times`` (parallel to ``requests``).

    ``POST /v1.0/$batch`` is answered by a built-in handler unless a test registered its own
    route: it asserts at most 20 unique ids, dispatches each sub-request to the GET routes and
    answers the sub-responses in a seeded shuffled order. ``sub_throttle`` throttles
    sub-requests only. ``current_in_flight`` and ``peak_in_flight`` count concurrently handled
    requests per site or drive id (the segment after ``/sites/`` or ``/drives/``).
    """

    def __init__(self, clock: Clock | None = None, *, shuffle_seed: int = 1) -> None:
        self.clock = clock
        self.requests: list[RecordedRequest] = []
        self.request_times: list[float] = []
        self.batch_posts: list[list[dict[str, Any]]] = []
        self.batch_response_ids: list[list[str]] = []
        self.current_in_flight: dict[str, int] = {}
        self.peak_in_flight: dict[str, int] = {}
        self._routes: list[tuple[str, re.Pattern[str], Responder]] = []
        self._throttles: list[_ThrottleRule] = []
        self._sub_throttles: list[_ThrottleRule] = []
        self._shuffle = random.Random(shuffle_seed)  # noqa: S311 - deterministic test shuffle

    def route(self, method: str, path_regex: str, responder: Responder) -> None:
        """Answer ``method`` requests whose URL path fully matches ``path_regex``."""
        self._routes.append((method.upper(), re.compile(path_regex), responder))

    def json_route(
        self,
        method: str,
        path_regex: str,
        body: Any,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Answer matching requests with a fixed JSON body."""

        def respond(_request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(status, json=body, headers=headers)

        self.route(method, path_regex, respond)

    def paged(
        self,
        path_regex: str,
        items: list[dict[str, Any]],
        *,
        page_size: int,
        hostile_next_link_on_page: int | None = None,
        hostile_link: str = "",
    ) -> None:
        """Serve ``items`` as pages of ``page_size`` with absolute next links.

        Page ``n`` is requested with ``$skiptoken=n`` (the first request has none). Each next
        link is the same path with the following page number. On page
        ``hostile_next_link_on_page`` the next link is ``hostile_link`` instead, even when
        that page would otherwise be the last.
        """

        def respond(request: httpx2.Request) -> httpx2.Response:
            query = dict(parse_qsl(request.url.query.decode("ascii")))
            page = int(query.get("$skiptoken", "1"))
            start = (page - 1) * page_size
            body: dict[str, Any] = {"value": items[start : start + page_size]}
            if hostile_next_link_on_page == page:
                body["@odata.nextLink"] = hostile_link
            elif start + page_size < len(items):
                raw_path = request.url.raw_path.split(b"?", 1)[0].decode("ascii")
                body["@odata.nextLink"] = (
                    "https://graph.microsoft.com" + raw_path + "?$skiptoken=" + str(page + 1)
                )
            return httpx2.Response(200, json=body)

        self.route("GET", path_regex, respond)

    def redirect(
        self,
        path_regex: str,
        location: str | None,
        *,
        status: int = 302,
    ) -> None:
        """Answer GETs on ``path_regex`` with a 3xx; ``location=None`` sends no header."""
        headers = {} if location is None else {"Location": location}
        self.json_route("GET", path_regex, {}, status=status, headers=headers)

    def throttle(
        self,
        path_regex: str,
        *,
        times: int,
        status: int = 429,
        retry_after: str | None = None,
    ) -> None:
        """Answer the next ``times`` requests on ``path_regex`` with ``status``.

        An optional ``Retry-After`` header is sent; normal routing resumes afterwards. Rules
        are consumed in the order they were added.
        """
        self._throttles.append(_ThrottleRule(re.compile(path_regex), times, status, retry_after))

    def sub_throttle(
        self,
        path_regex: str,
        *,
        times: int,
        status: int = 429,
        retry_after: str | None = None,
    ) -> None:
        """Answer the next ``times`` ``$batch`` sub-requests on ``path_regex`` with ``status``.

        Only sub-requests are affected; the outer POST still answers 200.
        """
        self._sub_throttles.append(
            _ThrottleRule(re.compile(path_regex), times, status, retry_after)
        )

    def transport(self) -> httpx2.MockTransport:
        """A transport to inject through ``make_http_client(transport=...)``."""
        return httpx2.MockTransport(self._handle)

    async def _handle(self, request: httpx2.Request) -> httpx2.Response:
        site = _SITE_OR_DRIVE.match(request.url.path)
        key = site.group(1) if site else None
        if key is not None:
            current = self.current_in_flight.get(key, 0) + 1
            self.current_in_flight[key] = current
            self.peak_in_flight[key] = max(self.peak_in_flight.get(key, 0), current)
        try:
            return await self._respond(request)
        finally:
            if key is not None:
                self.current_in_flight[key] -= 1

    async def _respond(self, request: httpx2.Request) -> httpx2.Response:
        content = request.content
        self.requests.append(
            RecordedRequest(
                method=request.method,
                url=str(request.url),
                path=request.url.path,
                query=parse_qsl(request.url.query.decode("ascii"), keep_blank_values=True),
                authorization=request.headers.get("authorization"),
                body=json.loads(content) if content else None,
            )
        )
        if self.clock is not None:
            self.request_times.append(self.clock.monotonic())
        for _ in range(_YIELDS_IN_HANDLER):
            await asyncio.sleep(0)
        for rule in self._throttles:
            if rule.remaining > 0 and rule.pattern.fullmatch(request.url.path):
                rule.remaining -= 1
                headers = {} if rule.retry_after is None else {"Retry-After": rule.retry_after}
                return httpx2.Response(
                    rule.status, json={"error": {"code": "throttled"}}, headers=headers
                )
        return await self._dispatch(request)

    async def _dispatch(self, request: httpx2.Request) -> httpx2.Response:
        for method, pattern, responder in self._routes:
            if method == request.method and pattern.fullmatch(request.url.path):
                result = responder(request)
                if inspect.isawaitable(result):
                    return await result
                return result
        if request.method == "POST" and request.url.path == _BATCH_PATH:
            return await self._batch(request)
        return httpx2.Response(404, json={"error": {"code": "itemNotFound"}})

    async def _batch(self, request: httpx2.Request) -> httpx2.Response:
        subs: list[dict[str, Any]] = json.loads(request.content)["requests"]
        assert len(subs) <= 20, "a $batch holds at most 20 sub-requests"
        ids = [sub["id"] for sub in subs]
        assert len(set(ids)) == len(ids), "sub-request ids must be unique"
        self.batch_posts.append(subs)
        responses = [await self._sub_response(sub) for sub in subs]
        self._shuffle.shuffle(responses)
        self.batch_response_ids.append([response["id"] for response in responses])
        return httpx2.Response(200, json={"responses": responses})

    async def _sub_response(self, sub: dict[str, Any]) -> dict[str, Any]:
        raw = str(sub["url"])
        url = "https://graph.microsoft.com/v1.0" + (raw if raw.startswith("/") else "/" + raw)
        path = httpx2.URL(url).path
        for rule in self._sub_throttles:
            if rule.remaining > 0 and rule.pattern.fullmatch(path):
                rule.remaining -= 1
                headers = {} if rule.retry_after is None else {"Retry-After": rule.retry_after}
                return {
                    "id": sub["id"],
                    "status": rule.status,
                    "headers": headers,
                    "body": {"error": {"code": "throttled"}},
                }
        response = await self._dispatch(httpx2.Request("GET", url))
        return {
            "id": sub["id"],
            "status": response.status_code,
            "headers": dict(response.headers),
            "body": json.loads(response.content) if response.content else None,
        }
