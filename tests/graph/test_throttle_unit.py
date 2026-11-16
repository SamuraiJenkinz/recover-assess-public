"""Throttling primitives (GRPH-05): Retry-After parsing, full jitter, shared gate, breaker."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest

from recover_assess.core.errors import ThrottledOut
from recover_assess.core.throttle import (
    BACKOFF_BASE_S,
    BACKOFF_CAP_S,
    BREAKER_THRESHOLD,
    BREAKER_WINDOW_S,
    MAX_RETRIES_DEFAULT,
    REQUEST_BUDGET_S,
    RETRYABLE_STATUSES,
    SiteBreaker,
    ThrottleGate,
    full_jitter_delay,
    parse_retry_after,
)
from tests.fakes.clock import FakeClock

NOW = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)


def test_the_fixed_spec_numbers() -> None:
    assert frozenset({429, 503}) == RETRYABLE_STATUSES
    assert (BACKOFF_BASE_S, BACKOFF_CAP_S) == (1.0, 60.0)
    assert (MAX_RETRIES_DEFAULT, REQUEST_BUDGET_S) == (6, 300.0)
    assert (BREAKER_THRESHOLD, BREAKER_WINDOW_S) == (20, 60.0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5", 5.0),
        ("0", 0.0),
        ("1.5", 1.5),
        (".5", 0.5),
        (" 7 ", 7.0),
        ("-3", 0.0),
        ("-0.5", 0.0),
    ],
)
def test_retry_after_seconds_forms(value: str, expected: float) -> None:
    assert parse_retry_after(value, now=NOW) == expected


def test_retry_after_http_date_is_relative_to_now() -> None:
    future = format_datetime(NOW + timedelta(seconds=30), usegmt=True)
    assert parse_retry_after(future, now=NOW) == 30.0


def test_retry_after_past_http_date_is_zero() -> None:
    past = format_datetime(NOW - timedelta(hours=1), usegmt=True)
    assert parse_retry_after(past, now=NOW) == 0.0


@pytest.mark.parametrize("value", ["soon", "", "   ", "nan", "inf", "-inf", "1e3", "9" * 400, None])
def test_unusable_retry_after_counts_as_absent(value: str | None) -> None:
    assert parse_retry_after(value, now=NOW) is None


@pytest.mark.parametrize("attempt", range(1, 11))
def test_jitter_stays_inside_the_exponential_ceiling(attempt: int) -> None:
    rng = random.Random(attempt)  # noqa: S311 - seeded, non-cryptographic test rng
    ceiling = min(60.0, 2.0 ** (attempt - 1))
    for _ in range(200):
        assert 0.0 <= full_jitter_delay(attempt, rng) <= ceiling


def test_the_same_seed_gives_the_same_jitter_sequence() -> None:
    first = random.Random(42)  # noqa: S311 - seeded, non-cryptographic test rng
    second = random.Random(42)  # noqa: S311 - seeded, non-cryptographic test rng
    one = [full_jitter_delay(n, first) for n in range(1, 8)]
    two = [full_jitter_delay(n, second) for n in range(1, 8)]
    assert one == two


def test_jitter_below_attempt_one_is_a_value_error() -> None:
    with pytest.raises(ValueError, match="attempt must be at least 1"):
        full_jitter_delay(0, random.Random(1))  # noqa: S311 - seeded, non-cryptographic test rng


def test_jitter_with_a_huge_attempt_number_does_not_overflow() -> None:
    value = full_jitter_delay(5000, random.Random(1))  # noqa: S311 - seeded test rng
    assert 0.0 <= value <= 60.0


async def test_gate_never_moves_backwards_and_waits_the_remaining_time(
    fake_clock: FakeClock,
) -> None:
    gate = ThrottleGate(fake_clock)
    start = fake_clock.monotonic()
    gate.trip(5)
    gate.trip(2)
    assert gate.resume_at == start + 5
    fake_clock.advance(1)
    await gate.wait()
    assert fake_clock.sleeps == [4.0]
    assert fake_clock.monotonic() == start + 5


async def test_gate_returns_at_once_when_resume_time_has_passed(fake_clock: FakeClock) -> None:
    gate = ThrottleGate(fake_clock)
    gate.trip(3)
    fake_clock.advance(10)
    await gate.wait()
    assert fake_clock.sleeps == []


def test_gate_clamps_a_negative_delay(fake_clock: FakeClock) -> None:
    gate = ThrottleGate(fake_clock)
    before = gate.resume_at
    gate.trip(-9)
    assert gate.resume_at == before


def test_breaker_does_not_trip_on_nineteen_in_the_window(fake_clock: FakeClock) -> None:
    breaker = SiteBreaker(fake_clock)
    for _ in range(19):
        breaker.record()
        fake_clock.advance(1)
    assert breaker.tripped is False
    breaker.check()


def test_breaker_trips_on_the_twentieth(fake_clock: FakeClock) -> None:
    breaker = SiteBreaker(fake_clock)
    for _ in range(19):
        breaker.record()
        fake_clock.advance(1)
    with pytest.raises(ThrottledOut) as info:
        breaker.record()
    assert info.value.reason == "breaker"
    assert breaker.tripped is True


def test_breaker_window_is_half_open_at_exactly_sixty_seconds(fake_clock: FakeClock) -> None:
    breaker = SiteBreaker(fake_clock)
    breaker.record()
    for _ in range(18):
        fake_clock.advance(1)
        breaker.record()
    fake_clock.advance(42)  # the first record is now exactly 60.0 s old
    breaker.record()
    assert breaker.tripped is False


def test_breaker_trips_when_the_twentieth_is_just_inside_the_window(
    fake_clock: FakeClock,
) -> None:
    breaker = SiteBreaker(fake_clock)
    breaker.record()
    for _ in range(18):
        fake_clock.advance(1)
        breaker.record()
    fake_clock.advance(40.9)
    with pytest.raises(ThrottledOut):
        breaker.record()


def test_a_tripped_breaker_stays_open(fake_clock: FakeClock) -> None:
    breaker = SiteBreaker(fake_clock, threshold=2)
    breaker.record()
    with pytest.raises(ThrottledOut):
        breaker.record()
    fake_clock.advance(10_000)
    with pytest.raises(ThrottledOut) as info:
        breaker.check()
    assert info.value.reason == "breaker"
    assert info.value.code == "throttled_out"
