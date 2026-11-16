"""run.jsonl: scrubbing, concurrent writes and interruption safety (FND-06, D-14).

A process killed mid-append is simulated by writing a fragment with
``Path.write_bytes``. Token-shaped strings are built at runtime.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from recover_assess.core import log
from recover_assess.core.errors import OutputError
from tests.fakes.clock import FakeClock

LINE_ONE = b'{"event":"site_state","state":"pending"}\n'
LINE_TWO = b'{"event":"site_state","state":"resolved"}\n'
FRAGMENT = b'{"event":"site_state","sta'


def state_event(site: str = "site-1") -> log.SiteStateEvent:
    return log.SiteStateEvent(level="INFO", site=site, state="collecting")


def test_read_ignores_an_unterminated_tail_and_reports_it(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    path.write_bytes(LINE_ONE + LINE_TWO + FRAGMENT)

    contents = log.read_run_log(path)

    assert [event["state"] for event in contents.events] == ["pending", "resolved"]
    assert contents.partial_tail is True


def test_read_of_a_complete_file_reports_no_partial_tail(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    path.write_bytes(LINE_ONE + LINE_TWO)

    contents = log.read_run_log(path)

    assert len(contents.events) == 2
    assert contents.partial_tail is False


def test_opening_a_log_truncates_the_fragment_and_the_next_emit_is_clean(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    path = tmp_path / "run.jsonl"
    path.write_bytes(LINE_ONE + LINE_TWO + FRAGMENT)

    with log.RunLog(path, fake_clock) as run_log:
        assert run_log.repaired_bytes == len(FRAGMENT)
        assert path.read_bytes() == LINE_ONE + LINE_TWO
        run_log.emit(state_event())

    data = path.read_bytes()
    assert data.endswith(b"\n")
    lines = data.split(b"\n")[:-1]
    assert len(lines) == 3
    assert all(isinstance(json.loads(line), dict) for line in lines)


def test_a_file_holding_only_a_fragment_becomes_empty(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    path = tmp_path / "run.jsonl"
    path.write_bytes(FRAGMENT)

    with log.RunLog(path, fake_clock) as run_log:
        assert run_log.repaired_bytes == len(FRAGMENT)
        assert path.stat().st_size == 0


def test_a_missing_or_empty_file_needs_no_repair(tmp_path: Path, fake_clock: FakeClock) -> None:
    missing = tmp_path / "missing.jsonl"
    empty = tmp_path / "empty.jsonl"
    empty.write_bytes(b"")

    with log.RunLog(missing, fake_clock) as first, log.RunLog(empty, fake_clock) as second:
        assert first.repaired_bytes == 0
        assert second.repaired_bytes == 0


def test_a_terminated_file_is_left_untouched(tmp_path: Path, fake_clock: FakeClock) -> None:
    path = tmp_path / "run.jsonl"
    path.write_bytes(LINE_ONE)

    with log.RunLog(path, fake_clock) as run_log:
        assert run_log.repaired_bytes == 0

    assert path.read_bytes() == LINE_ONE


def test_a_corrupt_terminated_middle_line_is_an_error_not_an_interruption(
    tmp_path: Path,
) -> None:
    path = tmp_path / "run.jsonl"
    path.write_bytes(LINE_ONE + b"[1, 2]\n" + LINE_TWO)

    with pytest.raises(OutputError, match=r"run_log_corrupt_line: line 2") as excinfo:
        log.read_run_log(path)

    assert "[1, 2]" not in str(excinfo.value)


def test_a_terminated_line_that_is_not_json_is_corruption(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    path.write_bytes(LINE_ONE + b"not json at all\n")

    with pytest.raises(OutputError, match=r"run_log_corrupt_line: line 2"):
        log.read_run_log(path)


def test_a_fragment_after_a_large_prefix_is_removed_exactly(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    path = tmp_path / "run.jsonl"
    prefix = LINE_ONE * (200 * 1024 // len(LINE_ONE) + 1)
    fragment = b'{"event":"' + b"x" * (70 * 1024)
    path.write_bytes(prefix + fragment)

    with log.RunLog(path, fake_clock) as run_log:
        assert run_log.repaired_bytes == len(fragment)

    assert len(prefix) > 200 * 1024
    assert path.read_bytes() == prefix


def test_fifty_concurrent_emits_never_interleave(tmp_path: Path, fake_clock: FakeClock) -> None:
    path = tmp_path / "run.jsonl"

    with log.RunLog(path, fake_clock) as run_log, ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda n: run_log.emit(state_event(f"site-{n}")), range(50)))

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 50
    parsed = [json.loads(line) for line in lines]
    assert all(isinstance(item, dict) for item in parsed)
    assert {item["site"] for item in parsed} == {f"site-{n}" for n in range(50)}


def test_a_log_needs_an_existing_parent_directory(tmp_path: Path, fake_clock: FakeClock) -> None:
    with pytest.raises(OutputError, match="run_log_parent_missing"):
        log.RunLog(tmp_path / "nope" / "run.jsonl", fake_clock)


def test_lines_follow_emission_order_with_clock_timestamps(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    path = tmp_path / "run.jsonl"

    with log.RunLog(path, fake_clock) as run_log:
        run_log.emit(state_event("first"))
        fake_clock.advance(5)
        run_log.emit(state_event("second"))

    events = log.read_run_log(path).events
    assert [event["site"] for event in events] == ["first", "second"]
    assert [event["ts"] for event in events] == ["2026-11-15T00:00:00Z", "2026-11-15T00:00:05Z"]


def test_scrub_redacts_tokens_signed_urls_and_download_urls() -> None:
    bearer = "Bearer " + "t" * 30
    jwt = "ey" + "J" + "h" * 12 + "." + "p" * 12 + "." + "s" * 12
    text = " ".join(
        [
            bearer,
            jwt,
            "https://example.com/f?sig=" + "q" * 8,
            "x?tempauth=" + "q" * 8,
            "api-key=" + "q" * 8,
            '{"@microsoft.graph.downloadUrl":"https://example.com/a","name":"f"}',
        ]
    )

    scrubbed = log.scrub_text(text)

    for secret in ("t" * 30, "h" * 12, "q" * 8, "downloadUrl", "https://example.com/a"):
        assert secret not in scrubbed
    assert "[REDACTED]" in scrubbed


def test_scrub_keeps_a_serialised_line_valid_json() -> None:
    detail = '{"@microsoft.graph.downloadUrl":"https://example.com/a"} Bearer ' + "t" * 30
    event = log.WarningEvent(level="WARNING", site="s", code="truncated", detail=detail)

    line = log.scrub_text(event.model_dump_json())

    assert json.loads(line)["code"] == "truncated"
    assert "downloadUrl" not in line
    assert "t" * 30 not in line
