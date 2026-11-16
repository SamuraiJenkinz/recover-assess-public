"""Atomic writers: lock retry, interruption safety, concurrency (FND-06, D-14).

The deterministic cases inject ``replace``, ``sleep`` and ``rng``. The Windows-only
cases hold a real file handle open, which is what makes ``os.replace`` fail there.
"""

from __future__ import annotations

import json
import os
import random
import sys
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from recover_assess.core.errors import OutputError
from recover_assess.core.output import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    sweep_orphans,
)

ReplaceFn = Callable[[Path, Path], object]


def real_replace(source: Path, target: Path) -> None:
    source.replace(target)


def listing(directory: Path) -> list[str]:
    return sorted(entry.name for entry in directory.iterdir())


def flaky_replace(failures: int, calls: list[int]) -> ReplaceFn:
    """A replace that raises PermissionError ``failures`` times, then really replaces."""

    def replace(source: Path, target: Path) -> None:
        calls.append(1)
        if len(calls) <= failures:
            raise PermissionError("held by another process")
        real_replace(source, target)

    return replace


def always_denied(calls: list[int]) -> ReplaceFn:
    def replace(source: Path, target: Path) -> None:
        del source, target
        calls.append(1)
        raise PermissionError("held by another process")

    return replace


def test_text_is_written_as_exact_utf8_with_no_newline_translation(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"

    atomic_write_text(target, "line one\nline two\né\r\n")

    assert target.read_bytes() == "line one\nline two\né\r\n".encode()


def test_json_is_two_space_indented_unescaped_with_one_trailing_newline(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    payload = {"name": "café", "items": [1, 2]}

    atomic_write_json(target, payload)

    expected = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    assert target.read_bytes() == expected.encode("utf-8")
    assert target.read_bytes().endswith(b"}\n")


def test_three_denied_replaces_then_success_records_three_bounded_sleeps(tmp_path: Path) -> None:
    target = tmp_path / "out.bin"
    calls: list[int] = []
    sleeps: list[float] = []

    atomic_write_bytes(
        target,
        b"payload",
        replace=flaky_replace(3, calls),
        sleep=sleeps.append,
        rng=random.Random(7),  # noqa: S311 - deterministic test jitter
    )

    assert target.read_bytes() == b"payload"
    assert len(calls) == 4
    assert len(sleeps) == 3
    assert all(0.05 <= seconds <= 0.25 for seconds in sleeps)
    assert listing(tmp_path) == ["out.bin"]


def test_persistent_denial_raises_after_exactly_attempts_and_keeps_the_old_bytes(
    tmp_path: Path,
) -> None:
    target = tmp_path / "out.bin"
    target.write_bytes(b"previous")
    calls: list[int] = []
    sleeps: list[float] = []

    with pytest.raises(OutputError):
        atomic_write_bytes(
            target,
            b"new",
            replace=always_denied(calls),
            sleep=sleeps.append,
            attempts=4,
        )

    assert len(calls) == 4
    assert len(sleeps) == 3
    assert target.read_bytes() == b"previous"
    assert listing(tmp_path) == ["out.bin"]


def test_failed_fsync_leaves_the_previous_target_untouched_and_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "out.bin"
    target.write_bytes(b"previous")

    def broken_fsync(descriptor: int) -> None:
        del descriptor
        raise OSError("disk went away")

    monkeypatch.setattr(os, "fsync", broken_fsync)

    with pytest.raises(OutputError):
        atomic_write_bytes(target, b"new")

    assert target.read_bytes() == b"previous"
    assert listing(tmp_path) == ["out.bin"]


def test_failed_fsync_for_a_new_target_leaves_the_target_absent_and_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "out.bin"

    def broken_fsync(descriptor: int) -> None:
        del descriptor
        raise OSError("disk went away")

    monkeypatch.setattr(os, "fsync", broken_fsync)

    with pytest.raises(OutputError):
        atomic_write_bytes(target, b"new")

    assert listing(tmp_path) == []


def test_a_replace_that_fails_for_another_reason_leaves_the_previous_target_untouched(
    tmp_path: Path,
) -> None:
    target = tmp_path / "out.bin"
    target.write_bytes(b"previous")

    def broken_replace(source: Path, destination: Path) -> None:
        del source, destination
        raise OSError("cross-device link")

    with pytest.raises(OutputError):
        atomic_write_bytes(target, b"new", replace=broken_replace)

    assert target.read_bytes() == b"previous"
    assert listing(tmp_path) == ["out.bin"]


def test_writing_zero_bytes_creates_a_zero_byte_target(tmp_path: Path) -> None:
    target = tmp_path / "empty.bin"

    atomic_write_bytes(target, b"")

    assert target.exists()
    assert target.stat().st_size == 0
    assert listing(tmp_path) == ["empty.bin"]


def test_a_missing_parent_directory_raises_and_creates_nothing(tmp_path: Path) -> None:
    parent = tmp_path / "does-not-exist"
    target = parent / "out.bin"

    with pytest.raises(OutputError) as excinfo:
        atomic_write_bytes(target, b"data")

    assert not parent.exists()
    assert listing(tmp_path) == []
    assert str(tmp_path) not in str(excinfo.value)


def test_writing_identical_content_twice_leaves_identical_bytes_and_no_temp_file(
    tmp_path: Path,
) -> None:
    target = tmp_path / "out.json"

    atomic_write_json(target, {"a": 1})
    first = target.read_bytes()
    atomic_write_json(target, {"a": 1})

    assert target.read_bytes() == first
    assert listing(tmp_path) == ["out.json"]


def test_temp_names_are_dot_target_tmp_pid_counter_and_unique_per_call(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    temp_names: list[str] = []

    def spying_replace(source: Path, destination: Path) -> None:
        temp_names.append(source.name)
        real_replace(source, destination)

    atomic_write_bytes(target, b"one", replace=spying_replace)
    atomic_write_bytes(target, b"two", replace=spying_replace)

    prefix = f".out.json.tmp-{os.getpid()}-"
    assert len(temp_names) == 2
    assert all(name.startswith(prefix) for name in temp_names)
    counters = [name.removeprefix(prefix) for name in temp_names]
    assert all(counter.isdigit() for counter in counters)
    assert counters[0] != counters[1]


def test_four_threads_of_five_writes_leave_one_complete_payload_and_no_temp_files(
    tmp_path: Path,
) -> None:
    target = tmp_path / "shared.bin"
    payloads = {
        (worker, index): bytes([65 + worker]) * (1000 + index)
        for worker in range(4)
        for index in range(5)
    }

    def write_all(worker: int) -> None:
        for index in range(5):
            atomic_write_bytes(target, payloads[(worker, index)], attempts=50)

    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in [pool.submit(write_all, worker) for worker in range(4)]:
            future.result()

    assert target.read_bytes() in set(payloads.values())
    assert listing(tmp_path) == ["shared.bin"]


def test_sweep_orphans_removes_stale_temp_files_and_leaves_everything_else(
    tmp_path: Path,
) -> None:
    stale = [tmp_path / ".x.json.tmp-123-4", tmp_path / ".run.jsonl.tmp-9-0"]
    keep = [tmp_path / "x.json", tmp_path / "x.json.tmp-1-1", tmp_path / ".hidden"]
    for path in [*stale, *keep]:
        path.write_bytes(b"x")
    nested = tmp_path / "sub"
    nested.mkdir()
    (nested / ".y.json.tmp-1-1").write_bytes(b"x")

    removed = sweep_orphans(tmp_path)

    assert sorted(removed) == sorted(stale)
    assert listing(tmp_path) == sorted(["x.json", "x.json.tmp-1-1", ".hidden", "sub"])
    assert (nested / ".y.json.tmp-1-1").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="a held handle blocks replace on Windows only")
def test_windows_held_handle_exhausts_retries_with_output_error(tmp_path: Path) -> None:
    target = tmp_path / "held.bin"
    target.write_bytes(b"previous")
    sleeps: list[float] = []

    with target.open("rb") as handle:
        with pytest.raises(OutputError):
            atomic_write_bytes(target, b"new", sleep=sleeps.append, attempts=3)
        assert handle.read() == b"previous"

    assert len(sleeps) == 2
    assert target.read_bytes() == b"previous"
    assert listing(tmp_path) == ["held.bin"]


@pytest.mark.skipif(sys.platform != "win32", reason="a held handle blocks replace on Windows only")
def test_windows_releasing_the_handle_mid_retry_lets_the_write_succeed(tmp_path: Path) -> None:
    target = tmp_path / "held.bin"
    target.write_bytes(b"previous")
    release = threading.Event()
    released = threading.Event()
    handle = target.open("rb")

    def releaser() -> None:
        release.wait(timeout=10)
        handle.close()
        released.set()

    thread = threading.Thread(target=releaser)
    thread.start()

    def sleep_until_released(seconds: float) -> None:
        del seconds
        release.set()
        assert released.wait(timeout=10)

    try:
        atomic_write_bytes(target, b"new", sleep=sleep_until_released, attempts=5)
    finally:
        release.set()
        thread.join(timeout=10)
        handle.close()

    assert target.read_bytes() == b"new"
    assert listing(tmp_path) == ["held.bin"]
