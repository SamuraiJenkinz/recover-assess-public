"""The single module allowed to talk to Microsoft 365 (GRPH-01).

Read-only by construction, with two independent guards:

1. :class:`~recover_assess.core.graph_policy.ReadOnlyPolicy` runs first in
   :meth:`GraphClient._send`, before the token is fetched or anything is sent.
2. :func:`guard_request` is installed as an ``httpx2`` request hook, so it also
   stops a request made directly on the raw client, before any transport runs.

The factory :func:`make_http_client` passes ``transport=`` only when a test
supplies one: ``httpx2`` disables ``HTTPS_PROXY``/``NO_PROXY`` whenever a
transport is passed, so production must not wrap or replace it. HTTP/2 stays off,
redirects are never followed automatically, and TLS verification is never turned
off (the OS trust store is the ``httpx2`` default).

Every URL the server supplies (a next link or a redirect location) is validated by the
policy before it is requested, so the bearer token never travels to a rejected URL.
Response bodies lose their ``@microsoft.graph.*`` annotations (pre-authenticated download
URLs) at this boundary.

Exceptions raised here never carry a URL: transport errors are re-raised with
``from None`` and a class-name reason, because ``httpx2`` messages include URLs.
"""

from __future__ import annotations

import asyncio
import functools
import json
import random
import re
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import aclosing, asynccontextmanager
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING, Any, Final, Self
from urllib.parse import quote, urlencode, urljoin

import httpx2
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception_type

from recover_assess import __version__
from recover_assess.core.clock import SYSTEM_CLOCK, Clock
from recover_assess.core.errors import (
    GraphError,
    GraphHttpError,
    GraphTransportError,
    ThrottledOut,
    UrlNotAllowedError,
    WriteAttemptError,
)
from recover_assess.core.graph_policy import (
    API_PREFIX,
    GRAPH_HOST,
    MatchedTemplate,
    ReadOnlyPolicy,
    load_allowlist,
)
from recover_assess.core.log import RequestEvent, RetryEvent, RunLog
from recover_assess.core.models.fact_sheet import GraphStats
from recover_assess.core.throttle import (
    MAX_RETRIES_DEFAULT,
    REQUEST_BUDGET_S,
    RETRYABLE_STATUSES,
    SiteBreaker,
    ThrottleGate,
    full_jitter_delay,
    parse_retry_after,
)

if TYPE_CHECKING:
    from recover_assess.core.config import Settings

__all__ = [
    "GRAPH_BASE_URL",
    "MAX_BATCH_SIZE",
    "MAX_REDIRECT_HOPS",
    "BatchItem",
    "BatchResult",
    "GraphClient",
    "GraphSession",
    "Page",
    "PagedResult",
    "TokenSource",
    "build_user_agent",
    "guard_request",
    "make_http_client",
    "packaged_policy",
    "strip_annotations",
]

GRAPH_BASE_URL: Final = "https://" + GRAPH_HOST + API_PREFIX
_BATCH_PATH: Final = API_PREFIX + "/$batch"
_BATCH_TEMPLATE: Final = "/$batch"
TokenSource = Callable[[], Awaitable[str]]
MAX_REDIRECT_HOPS: Final = 3
MAX_BATCH_SIZE: Final = 20
_MAX_COMPANY_LENGTH: Final = 64
_REDIRECT_STATUSES: Final[frozenset[int]] = frozenset({301, 302, 303, 307, 308})
_ANNOTATION_PREFIX: Final = "@microsoft.graph."
_REQUEST_ID: Final = re.compile(r"[A-Za-z0-9-]{1,64}")


def _safe_request_id(*candidates: str | None) -> str | None:
    """The first candidate that looks like a request id, else ``None``.

    The ``request-id`` header is server-supplied text that goes into a run-log line, so only a
    GUID-shaped value (letters, digits and hyphens, at most 64) is kept. Anything else, such as
    a URL or a token, is dropped rather than logged.
    """
    for candidate in candidates:
        if candidate:
            return candidate if _REQUEST_ID.fullmatch(candidate) else None
    return None


def strip_annotations(obj: Any) -> Any:
    """Return a copy of ``obj`` with every ``@microsoft.graph.*`` key removed at every level.

    Those keys carry pre-authenticated download URLs, so they must never reach a caller, a
    log or a fixture. The ``@odata.*`` paging and count keys are kept.
    """
    if isinstance(obj, dict):
        return {
            key: strip_annotations(value)
            for key, value in obj.items()
            if not (isinstance(key, str) and key.startswith(_ANNOTATION_PREFIX))
        }
    if isinstance(obj, list):
        return [strip_annotations(item) for item in obj]
    return obj


class _Throttled(Exception):
    """A 429 or 503 answered one attempt. Carries only the status, header text and template."""

    def __init__(self, status: int, retry_after: str | None, template: str) -> None:
        super().__init__(status)
        self.status = status
        self.retry_after = retry_after
        self.template = template


@dataclass
class _SessionCounters:
    """Per-site tallies behind :meth:`GraphSession.graph_stats`.

    ``requests`` counts every HTTP attempt sent (retries, redirect hops and each ``$batch``
    POST), ``batches`` the ``$batch`` POSTs, ``throttled`` the 429/503 responses plus throttled
    sub-responses, and ``retries`` the re-sent single requests plus re-queued sub-requests.
    """

    requests: int = 0
    batches: int = 0
    throttled: int = 0
    retries: int = 0


@dataclass(frozen=True)
class Page:
    """One page of a collection response, annotations already stripped."""

    items: list[dict[str, Any]]
    next_link: str | None
    delta_link: str | None


@dataclass(frozen=True)
class PagedResult:
    """The outcome of :meth:`GraphSession.get_all`: at most ``cap`` items."""

    items: list[dict[str, Any]]
    truncated: bool
    cap: int
    pages: int


@dataclass(frozen=True)
class BatchItem:
    """One independent GET to send inside a ``$batch``: a path under v1.0 and its query."""

    path: str
    params: Mapping[str, str] | None = None


@dataclass(frozen=True)
class BatchResult:
    """The outcome of one :class:`BatchItem`, in the position of its input.

    ``error_code`` is ``None`` on success, ``graph_error_<status>`` for a failed
    sub-request, ``throttled_out`` when it was still throttled after the retry limit, and
    ``batch_response_missing`` when the server returned nothing for its id.
    """

    index: int
    template: str
    status: int
    body: dict[str, Any] | None
    error_code: str | None
    truncated: bool = False


def build_user_agent(company: str | None, version: str) -> str:
    """The ``User-Agent`` value: ``NONISV|<company>|recover-assess/<version>`` or the bare app.

    The decorated form lets a tenant admin attribute the traffic (it affects throttling
    priority only). A blank company counts as absent; a ``|``, a non-printable character or
    more than 64 characters is refused so the header can never be split or injected into.
    """
    app = "recover-assess/" + version
    if company is None or not company.strip():
        return app
    if "|" in company or not company.isprintable() or len(company) > _MAX_COMPANY_LENGTH:
        msg = (
            "user_agent_company must be printable text without '|' and at most "
            f"{_MAX_COMPANY_LENGTH} characters"
        )
        raise ValueError(msg)
    return "NONISV|" + company + "|" + app


@functools.cache
def packaged_policy() -> ReadOnlyPolicy:
    """The read-only policy built from the packaged allow-list (D-08), one per process.

    The request hook always uses this, never the policy injected into a client, so its
    ``$batch`` body check holds even when the injected policy is wrong or permissive.
    """
    return ReadOnlyPolicy(load_allowlist())


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """JSON object hook: a repeated key could hide a write from a last-wins parser."""
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("duplicate_key")
        seen[key] = value
    return seen


async def _guard_batch_body(request: httpx2.Request) -> None:
    """Re-validate the serialised ``$batch`` body the transport would send."""
    if request.url.query:
        raise UrlNotAllowedError("query_not_allowed")
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise WriteAttemptError("batch_body_unreadable")
    try:
        parsed = json.loads(await request.aread(), object_pairs_hook=_reject_duplicate_keys)
    except Exception:
        # Fail closed: a body that cannot be read or parsed is never sent.
        raise WriteAttemptError("batch_body_unreadable") from None
    if not isinstance(parsed, dict):
        raise WriteAttemptError("batch_body_unreadable")
    packaged_policy().check_batch_body(parsed)


async def guard_request(request: httpx2.Request) -> None:
    """Second, independent guard: runs as a request hook before any transport.

    It allows GET under ``/v1.0/`` on ``graph.microsoft.com`` and POST only to the path
    exactly ``/v1.0/$batch``, and only after it has parsed the serialised body bytes and
    checked every sub-request against the packaged allow-list. Every other request is refused.
    """
    url = request.url
    if url.scheme != "https" or url.host != GRAPH_HOST or url.port not in {None, 443}:
        raise UrlNotAllowedError("host_not_allowed")
    if url.userinfo:
        raise UrlNotAllowedError("host_not_allowed")
    if not url.path.startswith(API_PREFIX + "/"):
        raise WriteAttemptError("method_not_allowed")
    if request.method == "GET":
        return
    if request.method == "POST" and url.path == _BATCH_PATH:
        await _guard_batch_body(request)
        return
    raise WriteAttemptError("method_not_allowed")


def make_http_client(
    *,
    connect_timeout_s: float,
    read_timeout_s: float,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> httpx2.AsyncClient:
    """Build the one ``httpx2`` client, with the request hook installed.

    ``transport`` is passed through only when it is not ``None`` (a test double).
    """
    extra: dict[str, Any] = {}
    if transport is not None:
        extra["transport"] = transport
    return httpx2.AsyncClient(
        timeout=httpx2.Timeout(
            connect=connect_timeout_s,
            read=read_timeout_s,
            write=read_timeout_s,
            pool=connect_timeout_s,
        ),
        follow_redirects=False,
        event_hooks={"request": [guard_request]},
        **extra,
    )


class GraphClient:
    """One per run. Owns the HTTP client, the policy, the token source and the run log.

    Invariant (handed to Phase 3): build exactly one ``GraphClient`` per run and open every
    site's session from it. The :class:`~recover_assess.core.throttle.ThrottleGate` and the
    site semaphore are client-wide, so the limit of ``max_sites`` sites at once and the
    tenant-wide throttle coordination hold only when every session comes from that one client.
    A second client would bypass the shared gate and double the site limit.
    """

    def __init__(
        self,
        *,
        token: TokenSource,
        run_log: RunLog,
        clock: Clock = SYSTEM_CLOCK,
        policy: ReadOnlyPolicy | None = None,
        transport: httpx2.AsyncBaseTransport | None = None,
        connect_timeout_s: float = 30.0,
        read_timeout_s: float = 120.0,
        user_agent: str | None = None,
        max_retries: int = MAX_RETRIES_DEFAULT,
        request_budget_s: float = REQUEST_BUDGET_S,
        rng: random.Random | None = None,
        max_sites: int = 2,
        max_in_flight_per_site: int = 4,
    ) -> None:
        if max_retries < 0:
            msg = "max_retries must not be negative"
            raise ValueError(msg)
        if max_sites < 1:
            msg = "max_sites must be at least 1"
            raise ValueError(msg)
        if max_in_flight_per_site < 1:
            msg = "max_in_flight_per_site must be at least 1"
            raise ValueError(msg)
        self._max_in_flight_per_site = max_in_flight_per_site
        # Held for the whole life of a session; acquired in open_session.
        self._site_slots = asyncio.Semaphore(max_sites)
        self._token = token
        self._run_log = run_log
        self._clock = clock
        self._max_retries = max_retries
        self._request_budget_s = request_budget_s
        self._rng = rng if rng is not None else random.Random()  # noqa: S311 - backoff jitter
        # One gate per client: tenant-wide throttling coordination holds only while a run
        # opens every site's session from this one client.
        self._gate = ThrottleGate(clock)
        self._policy = policy if policy is not None else packaged_policy()
        self._user_agent = user_agent if user_agent is not None else f"recover-assess/{__version__}"
        self._http = make_http_client(
            connect_timeout_s=connect_timeout_s,
            read_timeout_s=read_timeout_s,
            transport=transport,
        )

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        token: TokenSource,
        run_log: RunLog,
        clock: Clock = SYSTEM_CLOCK,
        transport: httpx2.AsyncBaseTransport | None = None,
        rng: random.Random | None = None,
    ) -> Self:
        """Build the run's one client from the operator's ``http`` settings."""
        http = settings.http
        return cls(
            token=token,
            run_log=run_log,
            clock=clock,
            transport=transport,
            rng=rng,
            connect_timeout_s=http.connect_timeout_s,
            read_timeout_s=http.read_timeout_s,
            max_retries=http.max_retries,
            max_sites=http.max_concurrent_sites,
            max_in_flight_per_site=http.max_in_flight_per_site,
            user_agent=build_user_agent(http.user_agent_company, __version__),
        )

    @property
    def policy(self) -> ReadOnlyPolicy:
        """The read-only policy this client enforces."""
        return self._policy

    @property
    def clock(self) -> Clock:
        """The injected clock every wait and timestamp comes from."""
        return self._clock

    @property
    def gate(self) -> ThrottleGate:
        """The throttle gate shared by every session of this client."""
        return self._gate

    @property
    def max_retries(self) -> int:
        """How many times a throttled request, or a batch's throttled items, is re-sent."""
        return self._max_retries

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying ``httpx2`` client."""
        await self._http.aclose()

    @asynccontextmanager
    async def open_session(self, site_key: str) -> AsyncIterator[GraphSession]:
        """Yield a session whose request lines carry ``site_key`` (an opaque label).

        The site slot is held for the whole session and released on exit, including on an
        exception, so at most ``max_sites`` sessions of this client are open at once.
        """
        async with self._site_slots:
            yield GraphSession(self, site_key, self._max_in_flight_per_site)

    def _log_request(
        self,
        session: GraphSession,
        method: str,
        matched: MatchedTemplate,
        *,
        status: int | None,
        request_id: str | None,
        started: float,
        retry: int,
        batch_size: int | None = None,
    ) -> None:
        self._run_log.emit(
            RequestEvent(
                level="INFO",
                site=session.site_key,
                method="POST" if method.upper() == "POST" else "GET",
                template=matched.template,
                status=status,
                duration_ms=max(0.0, (self._clock.monotonic() - started) * 1000.0),
                retry=retry,
                request_id=request_id,
                batch_size=batch_size,
            )
        )

    def _log_sub_response(
        self,
        session: GraphSession,
        *,
        template: str,
        status: int,
        request_id: str | None,
        started: float,
        retry: int,
    ) -> None:
        """One run-log line per ``$batch`` sub-response (``via_batch`` true)."""
        self._run_log.emit(
            RequestEvent(
                level="INFO",
                site=session.site_key,
                method="GET",
                template=template,
                status=status,
                duration_ms=max(0.0, (self._clock.monotonic() - started) * 1000.0),
                retry=retry,
                request_id=request_id,
                via_batch=True,
            )
        )

    async def _hop(
        self,
        session: GraphSession,
        method: str,
        url: str,
        matched: MatchedTemplate,
        headers: Mapping[str, str],
        json_body: Any,
        retry: int,
    ) -> httpx2.Response:
        """Send one request, count it and write its run-log line.

        The session's in-flight slot is held only around the transport call, never during the
        gate wait or a backoff sleep, so a sleeping request does not block its siblings.
        """
        started = self._clock.monotonic()
        session.counters.requests += 1
        is_batch = method.upper() == "POST"
        if is_batch:
            session.counters.batches += 1
        batch_size = len(json_body["requests"]) if is_batch and json_body is not None else None
        try:
            async with session.in_flight:
                response = await self._http.request(method, url, headers=headers, json=json_body)
        except httpx2.TimeoutException as exc:
            self._log_request(
                session,
                method,
                matched,
                status=None,
                request_id=None,
                started=started,
                retry=retry,
                batch_size=batch_size,
            )
            raise GraphTransportError(
                type(exc).__name__, timeout=True, template=matched.template
            ) from None
        except httpx2.TransportError as exc:
            self._log_request(
                session,
                method,
                matched,
                status=None,
                request_id=None,
                started=started,
                retry=retry,
                batch_size=batch_size,
            )
            raise GraphTransportError(
                type(exc).__name__, timeout=False, template=matched.template
            ) from None
        request_id = _safe_request_id(
            response.headers.get("request-id"), response.headers.get("client-request-id")
        )
        self._log_request(
            session,
            method,
            matched,
            status=response.status_code,
            request_id=request_id,
            started=started,
            retry=retry,
            batch_size=batch_size,
        )
        return response

    async def _attempt(
        self,
        session: GraphSession,
        method: str,
        url: str,
        json_body: Any,
        attempt_number: int,
    ) -> httpx2.Response:
        """One attempt: breaker, shared gate, policy, token, send, redirects, throttle check.

        A 3xx on a GET is followed by hand inside the attempt: its ``Location`` is resolved
        against the request URL and passed through the policy before the follow-up GET, at most
        ``MAX_REDIRECT_HOPS`` times. A 3xx answering a POST is refused. A 429 or 503 raises the
        internal ``_Throttled`` so the retry loop can wait and try again.
        """
        session.breaker.check()
        await self._gate.wait()
        current = url
        matched = self._policy.check(method, current, batch_body=json_body)
        token = await self._token()
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "User-Agent": self._user_agent,
        }
        retry = attempt_number - 1
        hops = 0
        while True:
            response = await self._hop(
                session,
                method,
                current,
                matched,
                headers,
                json_body if hops == 0 else None,
                retry,
            )
            if response.status_code in RETRYABLE_STATUSES:
                session.counters.throttled += 1
                try:
                    session.breaker.record()
                except ThrottledOut:
                    raise ThrottledOut("breaker", template=matched.template) from None
                raise _Throttled(
                    response.status_code, response.headers.get("retry-after"), matched.template
                )
            if response.status_code not in _REDIRECT_STATUSES:
                return response
            if method.upper() != "GET":
                raise UrlNotAllowedError("redirect_on_batch", template=matched.template)
            location = response.headers.get("location")
            if not location:
                raise UrlNotAllowedError("redirect_without_location", template=matched.template)
            if hops >= MAX_REDIRECT_HOPS:
                raise UrlNotAllowedError("too_many_redirects", template=matched.template)
            current = urljoin(current, location)
            # Validate before the follow-up GET: no token travels to a rejected URL.
            matched = self._policy.check("GET", current)
            hops += 1

    def _stop(self, retry_state: RetryCallState) -> bool:
        """tenacity ``stop``: one initial send plus ``max_retries`` retries."""
        return retry_state.attempt_number > self._max_retries

    def _wait_for(
        self, session: GraphSession, started: float, retry_state: RetryCallState
    ) -> float:
        """tenacity ``wait``: pick the delay, enforce the budget, trip the gate, log the retry.

        Uses the injected clock and rng only; tenacity's wall-clock stop and global-random
        jitter helpers are deliberately not used (they cannot be faked in tests).
        """
        if self._stop(retry_state):
            # tenacity asks for the delay before it checks stop; with no retry left nothing is
            # scheduled, so there is no gate trip, no counter and no retry line.
            return 0.0
        outcome = retry_state.outcome
        exc = outcome.exception() if outcome is not None else None
        if not isinstance(exc, _Throttled):
            msg = "the retry loop waits only after a throttle"
            raise TypeError(msg)
        header_delay = parse_retry_after(exc.retry_after, now=self._clock.utcnow())
        delay = (
            header_delay
            if header_delay is not None
            else full_jitter_delay(retry_state.attempt_number, self._rng)
        )
        if self._clock.monotonic() - started + delay > self._request_budget_s:
            raise ThrottledOut("budget", template=exc.template)
        self._gate.trip(delay)
        session.counters.retries += 1
        self._run_log.emit(
            RetryEvent(
                level="WARNING",
                site=session.site_key,
                template=exc.template,
                attempt=retry_state.attempt_number,
                delay_s=delay,
                status=exc.status,
            )
        )
        return delay

    async def _requeue_wait(
        self,
        session: GraphSession,
        *,
        started: float,
        round_number: int,
        status: int,
        retry_afters: Sequence[str | None],
        count: int,
    ) -> None:
        """Wait before re-sending the throttled items of one ``$batch`` response.

        The delay is the longest parsed sub ``Retry-After``, else seeded full jitter. The same
        time budget as a single request applies (``ThrottledOut("budget")`` before sleeping);
        the shared gate is tripped, the re-queued items are counted as retries and one retry
        line is written. ``round_number`` is 1 for the first re-queue.
        """
        now = self._clock.utcnow()
        parsed = [
            delay
            for text in retry_afters
            if (delay := parse_retry_after(text, now=now)) is not None
        ]
        delay = max(parsed) if parsed else full_jitter_delay(round_number, self._rng)
        if self._clock.monotonic() - started + delay > self._request_budget_s:
            raise ThrottledOut("budget", template=_BATCH_TEMPLATE)
        self._gate.trip(delay)
        session.counters.retries += count
        self._run_log.emit(
            RetryEvent(
                level="WARNING",
                site=session.site_key,
                template=_BATCH_TEMPLATE,
                attempt=round_number,
                delay_s=delay,
                status=status,
            )
        )
        await self._gate.wait()

    async def _send(
        self,
        session: GraphSession,
        method: str,
        url: str,
        *,
        json_body: Any = None,
    ) -> httpx2.Response:
        """Send with retries: only 429 and 503 are retried, every other status returns once.

        Waits ``Retry-After`` (else full-jitter backoff) on the injected clock, at most
        ``max_retries`` times and within the per-request budget. Exhaustion raises
        ``ThrottledOut("retries_exhausted")``; a budget overrun raises ``ThrottledOut("budget")``
        without sleeping; the per-site breaker raises ``ThrottledOut("breaker")``.
        """
        started = self._clock.monotonic()
        retrying = AsyncRetrying(
            sleep=self._clock.sleep,
            stop=self._stop,
            wait=functools.partial(self._wait_for, session, started),
            retry=retry_if_exception_type(_Throttled),
            reraise=True,
        )
        try:
            async for attempt in retrying:
                with attempt:
                    return await self._attempt(
                        session, method, url, json_body, attempt.retry_state.attempt_number
                    )
        except _Throttled as exc:
            raise ThrottledOut("retries_exhausted", template=exc.template) from None
        msg = "the retry loop ended without a result"
        raise RuntimeError(msg)


class GraphSession:
    """Read-only handle for one site. Exposes ``get`` and paging, nothing that writes."""

    def __init__(self, client: GraphClient, site_key: str, max_in_flight: int = 4) -> None:
        self._client = client
        self._site_key = site_key
        self._in_flight = asyncio.Semaphore(max_in_flight)
        self._breaker = SiteBreaker(client.clock)
        self._counters = _SessionCounters()
        self._opened_at = client.clock.monotonic()

    @property
    def breaker(self) -> SiteBreaker:
        """This site's throttle breaker; once open, every later call fails without sending."""
        return self._breaker

    @property
    def counters(self) -> _SessionCounters:
        """Requests, batches, throttles and retries so far."""
        return self._counters

    @property
    def in_flight(self) -> asyncio.Semaphore:
        """This session's in-flight slots (``max_in_flight_per_site`` of them)."""
        return self._in_flight

    @property
    def opened_at(self) -> float:
        """Monotonic time at which the session was opened."""
        return self._opened_at

    @property
    def site_key(self) -> str:
        """The opaque label carried on every request line."""
        return self._site_key

    @staticmethod
    def _relative(path: str, params: Mapping[str, str] | None) -> str:
        """``path`` plus its urlencoded query: the form of a ``$batch`` sub-request url."""
        if params:
            return path + "?" + urlencode(params, quote_via=quote, safe="$,()'")
        return path

    @staticmethod
    def _url(path: str, params: Mapping[str, str] | None) -> str:
        return GRAPH_BASE_URL + GraphSession._relative(path, params)

    def graph_stats(self) -> GraphStats:
        """The fact-sheet counters for this session.

        ``seconds`` is the session's wall time on the injected clock, rounded to 3 places. It is
        never taken from an ``httpx2`` response's own elapsed time.
        """
        return GraphStats(
            requests=self._counters.requests,
            batches=self._counters.batches,
            throttled=self._counters.throttled,
            retries=self._counters.retries,
            seconds=round(self._client.clock.monotonic() - self._opened_at, 3),
        )

    async def _fetch_object(self, url: str) -> dict[str, Any]:
        """GET ``url`` and return its JSON object with download annotations stripped."""
        response = await self._client._send(self, "GET", url)
        if not 200 <= response.status_code < 300:
            matched = self._client.policy.check("GET", url)
            raise GraphHttpError(response.status_code, template=matched.template)
        if not response.content:
            return {}
        try:
            data = json.loads(response.content)
        except ValueError:
            matched = self._client.policy.check("GET", url)
            raise GraphError("response_not_json", template=matched.template) from None
        if not isinstance(data, dict):
            matched = self._client.policy.check("GET", url)
            raise GraphError("response_not_object", template=matched.template)
        stripped: dict[str, Any] = strip_annotations(data)
        return stripped

    async def get(self, path: str, params: Mapping[str, str] | None = None) -> dict[str, Any]:
        """GET ``path`` under the v1.0 base and return the JSON object."""
        return await self._fetch_object(self._url(path, params))

    async def iter_pages(
        self, path: str, params: Mapping[str, str] | None = None
    ) -> AsyncGenerator[Page, None]:
        """Yield each page of a collection, following the next link to the end.

        The next URL is the server's link used verbatim (a skip token is never built by hand).
        It is validated against the read-only policy as soon as the page arrives and again
        before it is requested, so a hostile or empty link raises
        :class:`~recover_assess.core.errors.UrlNotAllowedError` and no token travels to it.
        The delta link is exposed on the last page and never followed.
        """
        url: str | None = self._url(path, params)
        while url is not None:
            data = await self._fetch_object(url)
            value = data.get("value")
            if not isinstance(value, list):
                matched = self._client.policy.check("GET", url)
                raise GraphError("response_missing_value", template=matched.template)
            next_link = data.get("@odata.nextLink")
            if next_link is not None:
                if not isinstance(next_link, str):
                    raise UrlNotAllowedError("next_link_invalid")
                self._client.policy.check("GET", next_link)
            delta_link = data.get("@odata.deltaLink")
            yield Page(
                items=[item for item in value if isinstance(item, dict)],
                next_link=next_link,
                delta_link=delta_link if isinstance(delta_link, str) else None,
            )
            url = next_link

    async def get_all(
        self, path: str, params: Mapping[str, str] | None = None, *, cap: int
    ) -> PagedResult:
        """Collect pages until the end or until ``cap`` items, marking truncation.

        ``cap`` counts items, not pages. ``truncated`` is true exactly when items were dropped
        or a next link remained once the cap was reached; no page is requested after that.
        """
        if cap < 1:
            msg = "cap must be at least 1"
            raise ValueError(msg)
        items: list[dict[str, Any]] = []
        pages = 0
        truncated = False
        async with aclosing(self.iter_pages(path, params)) as stream:
            async for page in stream:
                pages += 1
                items.extend(page.items)
                if len(items) >= cap:
                    truncated = len(items) > cap or page.next_link is not None
                    break
        return PagedResult(items=items[:cap], truncated=truncated, cap=cap, pages=pages)

    async def batch(
        self,
        items: Sequence[BatchItem],
        *,
        chunk_size: int = MAX_BATCH_SIZE,
        max_items_per_result: int = 50_000,
    ) -> list[BatchResult]:
        """Send independent GETs as ``POST /$batch`` groups and return one result per item.

        Results come back in input order. Every sub-response is judged on its own status (an
        outer 200 says nothing about the sub-requests): a sub 403 or 404 becomes a result with
        ``error_code`` ``graph_error_<status>`` and never raises. Throttled sub-requests (429 or
        503) are re-sent, and only those, after the longest sub ``Retry-After`` (else full
        jitter), inside the same retry and time limits as a single request; any still throttled
        at the limit end as ``throttled_out``. A sub-response with a next link is completed with
        validated paged GETs, capped at ``max_items_per_result`` (``truncated`` is then true).

        Every url is checked against the allow-list before anything is sent, and the whole body
        is checked again by the policy and by the transport hook.
        """
        if not 1 <= chunk_size <= MAX_BATCH_SIZE:
            msg = f"chunk_size must be between 1 and {MAX_BATCH_SIZE}"
            raise ValueError(msg)
        if max_items_per_result < 1:
            msg = "max_items_per_result must be at least 1"
            raise ValueError(msg)
        urls = [self._relative(item.path, item.params) for item in items]
        templates = [self._client.policy.check_relative_url(url).template for url in urls]
        results: list[BatchResult | None] = [None] * len(urls)
        for start in range(0, len(urls), chunk_size):
            indices = list(range(start, min(start + chunk_size, len(urls))))
            await self._run_chunk(indices, urls, templates, results, max_items_per_result)
        done = [result for result in results if result is not None]
        if len(done) != len(urls):
            msg = "every batch item must end with a result"
            raise RuntimeError(msg)
        return done

    async def _run_chunk(
        self,
        indices: list[int],
        urls: list[str],
        templates: list[str],
        results: list[BatchResult | None],
        cap: int,
    ) -> None:
        """Send one chunk, re-sending only its throttled items until done or out of retries."""
        client = self._client
        started = client.clock.monotonic()
        pending = indices
        rounds = 0
        while True:
            throttled = await self._post_batch(pending, urls, templates, results, cap, rounds)
            if not throttled:
                return
            if rounds >= client.max_retries:
                for index, status, _ in throttled:
                    results[index] = BatchResult(
                        index=index,
                        template=templates[index],
                        status=status,
                        body=None,
                        error_code="throttled_out",
                    )
                return
            rounds += 1
            await client._requeue_wait(
                self,
                started=started,
                round_number=rounds,
                status=throttled[0][1],
                retry_afters=[text for _, _, text in throttled],
                count=len(throttled),
            )
            pending = [index for index, _, _ in throttled]

    async def _post_batch(
        self,
        pending: list[int],
        urls: list[str],
        templates: list[str],
        results: list[BatchResult | None],
        cap: int,
        round_number: int,
    ) -> list[tuple[int, int, str | None]]:
        """POST one ``$batch``, fill ``results`` for every finished item, return the throttled."""
        client = self._client
        body = {
            "requests": [
                {"id": str(number), "method": "GET", "url": urls[index]}
                for number, index in enumerate(pending, 1)
            ]
        }
        sent = client.clock.monotonic()
        response = await client._send(self, "POST", GRAPH_BASE_URL + "/$batch", json_body=body)
        if not 200 <= response.status_code < 300:
            raise GraphHttpError(response.status_code, template=_BATCH_TEMPLATE)
        try:
            payload = json.loads(response.content)
        except ValueError:
            raise GraphError("response_not_json", template=_BATCH_TEMPLATE) from None
        responses = payload.get("responses") if isinstance(payload, dict) else None
        if not isinstance(responses, list):
            raise GraphError("batch_response_invalid", template=_BATCH_TEMPLATE)
        # Correlate by id only, case-insensitively: the server may answer in any order.
        by_id: dict[str, dict[str, Any]] = {}
        for sub in responses:
            if isinstance(sub, dict) and isinstance(sub.get("id"), str):
                by_id.setdefault(sub["id"].casefold(), sub)
        throttled: list[tuple[int, int, str | None]] = []
        for number, index in enumerate(pending, 1):
            template = templates[index]
            sub = by_id.get(str(number))
            status = sub.get("status") if sub is not None else None
            if sub is None or not isinstance(status, int) or isinstance(status, bool):
                results[index] = BatchResult(
                    index=index,
                    template=template,
                    status=0,
                    body=None,
                    error_code="batch_response_missing",
                )
                continue
            raw_headers = sub.get("headers")
            headers = (
                {str(key).casefold(): str(value) for key, value in raw_headers.items()}
                if isinstance(raw_headers, dict)
                else {}
            )
            client._log_sub_response(
                self,
                template=template,
                status=status,
                request_id=_safe_request_id(
                    headers.get("request-id"), headers.get("client-request-id")
                ),
                started=sent,
                retry=round_number,
            )
            if status in RETRYABLE_STATUSES:
                self._counters.throttled += 1
                try:
                    self._breaker.record()
                except ThrottledOut:
                    raise ThrottledOut("breaker", template=template) from None
                throttled.append((index, status, headers.get("retry-after")))
            elif 200 <= status < 300:
                raw_body = sub.get("body")
                sub_body: dict[str, Any] = (
                    strip_annotations(raw_body) if isinstance(raw_body, dict) else {}
                )
                merged, truncated = await self._complete_sub_pages(sub_body, cap)
                results[index] = BatchResult(
                    index=index,
                    template=template,
                    status=status,
                    body=merged,
                    error_code=None,
                    truncated=truncated,
                )
            else:
                results[index] = BatchResult(
                    index=index,
                    template=template,
                    status=status,
                    body=None,
                    error_code=f"graph_error_{status}",
                )
        return throttled

    async def _complete_sub_pages(
        self, body: dict[str, Any], cap: int
    ) -> tuple[dict[str, Any], bool]:
        """Finish a sub-result that carries a next link with validated paged GETs.

        The link is validated against the policy as soon as it arrives and before each request,
        so a hostile link raises :class:`~recover_assess.core.errors.UrlNotAllowedError` and no
        token travels to it. The merged body drops the link; items beyond ``cap`` are dropped
        and the second element is true.
        """
        policy = self._client.policy
        value = body.get("value")
        link = body.get("@odata.nextLink")
        if link is None:
            if isinstance(value, list) and len(value) > cap:
                return {**body, "value": value[:cap]}, True
            return body, False
        if not isinstance(link, str):
            raise UrlNotAllowedError("next_link_invalid")
        policy.check("GET", link)
        if not isinstance(value, list):
            raise GraphError("response_missing_value")
        items = [item for item in value if isinstance(item, dict)]
        merged = {key: val for key, val in body.items() if key != "@odata.nextLink"}
        truncated = False
        next_url: str | None = link
        while next_url is not None:
            if len(items) >= cap:
                truncated = True
                break
            data = await self._fetch_object(next_url)
            page = data.get("value")
            if not isinstance(page, list):
                raise GraphError(
                    "response_missing_value", template=policy.check("GET", next_url).template
                )
            items.extend(item for item in page if isinstance(item, dict))
            following = data.get("@odata.nextLink")
            if following is not None:
                if not isinstance(following, str):
                    raise UrlNotAllowedError("next_link_invalid")
                policy.check("GET", following)
            next_url = following
        if len(items) > cap:
            items = items[:cap]
            truncated = True
        merged["value"] = items
        return merged, truncated
