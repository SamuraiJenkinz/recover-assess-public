"""Phase 1 acceptance: five sites through two slots, one throttled until its breaker opens.

This is ROADMAP success criteria 3 (throttling, concurrency limits and the breaker) and 4
(nothing secret in the run log) exercised together on a fake Graph with a fake clock, through
the public client surface only: ``open_session``, ``get``, ``get_all``, ``batch`` and
``graph_stats``. All data is synthetic.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx2
from jsonschema import Draft202012Validator

from recover_assess.core.errors import ThrottledOut
from recover_assess.core.graph import BatchItem, GraphClient
from recover_assess.core.models.fact_sheet import GraphStats
from tests.conftest import MakeGraphClient
from tests.fakes.fake_graph import FakeGraph
from tests.support.log_audit import audit_run_log

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "fact_sheet.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
GRAPH_STATS_VALIDATOR = Draft202012Validator(
    {"$ref": "#/$defs/GraphStats", "$defs": SCHEMA["$defs"]}
)

SITE_IDS = {f"site-{number}": f"accsite{number}" + "0" * 6 for number in range(1, 6)}
THROTTLED_KEY = "site-3"
GOOD_KEYS = [key for key in SITE_IDS if key != THROTTLED_KEY]
LIST_ID = "acclist" + "1" * 6
CONCURRENT_GETS = 8
ITEMS = 40
PAGE_SIZE = 10
CAP = 25
BREAKER_THROTTLES = 20
WALL_TIME_LIMIT_S = 10.0


@dataclass
class SiteOutcome:
    """What one site task observed, for assertions made after the gather."""

    key: str
    stats: GraphStats
    reasons: list[str]
    final_code: str | None = None
    poisoned_reason: str | None = None
    sends_before_poisoned_get: int = 0
    sends_after_poisoned_get: int = 0
    truncated: bool = False
    item_count: int = 0
    batch_statuses: list[int] | None = None


class SessionPeak:
    """Counts the sessions that are open at the same moment."""

    def __init__(self) -> None:
        self.current = 0
        self.peak = 0

    def enter(self) -> None:
        self.current += 1
        self.peak = max(self.peak, self.current)

    def leave(self) -> None:
        self.current -= 1


def site_regex(site_id: str, tail: str = "") -> str:
    return r"/v1\.0/sites/" + re.escape(site_id) + tail


def serve_good_site(fake_graph: FakeGraph, site_id: str) -> None:
    """Routes for one healthy site, plus one throttled sub-request in its batch."""

    def respond(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"path": request.url.path, "value": []})

    items = [{"id": f"item-{number}", "name": "synthetic"} for number in range(ITEMS)]
    fake_graph.paged(site_regex(site_id, "/lists"), items, page_size=PAGE_SIZE)
    fake_graph.route("GET", site_regex(site_id), respond)
    fake_graph.route(
        "GET",
        site_regex(
            site_id, r"/(?:sites|drive|lists/" + LIST_ID + r"/(?:columns|contentTypes|drive))"
        ),
        respond,
    )
    fake_graph.sub_throttle(site_regex(site_id, "/drive"), times=1, retry_after="1")


def sends_for(fake_graph: FakeGraph, site_id: str) -> int:
    return sum(1 for request in fake_graph.requests if f"/sites/{site_id}" in request.path)


async def run_good_site(
    client: GraphClient, peak: SessionPeak, key: str, site_id: str
) -> SiteOutcome:
    async with client.open_session(key) as session:
        peak.enter()
        try:
            await asyncio.gather(
                *(session.get(f"/sites/{site_id}") for _ in range(CONCURRENT_GETS))
            )
            paged = await session.get_all(f"/sites/{site_id}/lists", cap=CAP)
            results = await session.batch(
                [
                    BatchItem(f"/sites/{site_id}/sites"),
                    BatchItem(f"/sites/{site_id}/drive"),
                    BatchItem(f"/sites/{site_id}/lists/{LIST_ID}/columns"),
                    BatchItem(f"/sites/{site_id}/lists/{LIST_ID}/contentTypes"),
                    BatchItem(f"/sites/{site_id}/lists/{LIST_ID}/drive"),
                ]
            )
            return SiteOutcome(
                key=key,
                stats=session.graph_stats(),
                reasons=[],
                truncated=paged.truncated,
                item_count=len(paged.items),
                batch_statuses=[result.status for result in results],
            )
        finally:
            peak.leave()


async def run_throttled_site(
    client: GraphClient, fake_graph: FakeGraph, peak: SessionPeak, key: str, site_id: str
) -> SiteOutcome:
    reasons: list[str] = []
    final_code: str | None = None
    async with client.open_session(key) as session:
        peak.enter()
        try:
            for _ in range(5):
                try:
                    await session.get(f"/sites/{site_id}")
                except ThrottledOut as exc:
                    reasons.append(exc.reason)
                    final_code = exc.code
                    if exc.reason == "breaker":
                        break
            before = sends_for(fake_graph, site_id)
            poisoned_reason: str | None = None
            try:
                await session.get(f"/sites/{site_id}")
            except ThrottledOut as exc:
                poisoned_reason = exc.reason
            return SiteOutcome(
                key=key,
                stats=session.graph_stats(),
                reasons=reasons,
                final_code=final_code,
                poisoned_reason=poisoned_reason,
                sends_before_poisoned_get=before,
                sends_after_poisoned_get=sends_for(fake_graph, site_id),
            )
        finally:
            peak.leave()


async def test_five_sites_through_two_slots_with_one_breaker_and_a_clean_log(
    make_graph_client: MakeGraphClient,
    fake_graph: FakeGraph,
    run_log_path: Path,
    canary_token: str,
) -> None:
    for key in GOOD_KEYS:
        serve_good_site(fake_graph, SITE_IDS[key])
    throttled_id = SITE_IDS[THROTTLED_KEY]
    fake_graph.throttle(site_regex(throttled_id, ".*"), times=1_000, retry_after="1")
    client = await make_graph_client(max_sites=2, max_in_flight_per_site=4)
    peak = SessionPeak()

    started = time.perf_counter()
    gathered = await asyncio.gather(
        *(
            run_throttled_site(client, fake_graph, peak, key, site_id)
            if key == THROTTLED_KEY
            else run_good_site(client, peak, key, site_id)
            for key, site_id in SITE_IDS.items()
        ),
        return_exceptions=True,
    )
    wall_time = time.perf_counter() - started

    outcomes = {outcome.key: outcome for outcome in gathered if isinstance(outcome, SiteOutcome)}
    assert set(outcomes) == set(SITE_IDS), [g for g in gathered if isinstance(g, BaseException)]
    assert wall_time < WALL_TIME_LIMIT_S

    # The four healthy sites finished with the expected results despite the poisoned one.
    for key in GOOD_KEYS:
        good = outcomes[key]
        assert good.truncated is True
        assert good.item_count == CAP
        assert good.batch_statuses == [200] * 5
        assert (good.stats.requests, good.stats.batches) == (13, 2)
        assert (good.stats.throttled, good.stats.retries) == (1, 1)

    # The breaker is told apart from retry exhaustion by its reason, not its shared code.
    bad = outcomes[THROTTLED_KEY]
    assert bad.reasons == ["retries_exhausted", "retries_exhausted", "breaker"]
    assert bad.final_code == "throttled_out"
    assert bad.sends_before_poisoned_get == BREAKER_THROTTLES
    assert bad.poisoned_reason == "breaker"
    assert bad.sends_after_poisoned_get == BREAKER_THROTTLES
    assert (bad.stats.requests, bad.stats.throttled, bad.stats.retries) == (20, 20, 17)

    # Concurrency limits held, and the in-flight limit was really exercised.
    assert peak.peak <= 2
    assert max(fake_graph.peak_in_flight.values()) <= 4
    assert max(fake_graph.peak_in_flight[SITE_IDS[key]] for key in GOOD_KEYS) >= 2

    # A throttle on the poisoned site delayed sends to the other sites through the shared gate.
    first_throttled_send = min(
        time_at
        for request, time_at in zip(fake_graph.requests, fake_graph.request_times, strict=True)
        if throttled_id in request.path
    )
    assert any(
        time_at >= first_throttled_send + 1.0
        for request, time_at in zip(fake_graph.requests, fake_graph.request_times, strict=True)
        if throttled_id not in request.path and "/sites/" in request.path
    )

    # Every session's counters satisfy the fact-sheet contract.
    for outcome in outcomes.values():
        GRAPH_STATS_VALIDATOR.validate(outcome.stats.model_dump(mode="json"))
        assert outcome.stats.requests >= 1
    assert all(outcomes[key].stats.batches >= 1 for key in GOOD_KEYS)

    # The shared run log is clean.
    assert audit_run_log(run_log_path) == []
    assert canary_token not in read_text(run_log_path)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")
