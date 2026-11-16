"""The env typo scan: pydantic-settings silently ignores a mistyped top-level group (T-01-12)."""

from __future__ import annotations

from pathlib import Path

import pytest

from recover_assess.core.config import CONFIG_ENV_VAR, ENV_PREFIX, load_settings, unknown_env_vars
from recover_assess.core.errors import ConfigError


@pytest.fixture(autouse=True)
def _empty_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_mistyped_top_level_group_is_flagged_with_a_hint() -> None:
    name = ENV_PREFIX + "COLECT__SAMPLE_SIZE"

    assert unknown_env_vars({name: "1"}) == [(name, "collect")]


def test_mistyped_nested_key_is_flagged_with_a_hint() -> None:
    name = ENV_PREFIX + "COLLECT__SAMPEL_SIZE"

    assert unknown_env_vars({name: "1"}) == [(name, "sample_size")]


def test_extra_part_after_a_leaf_is_flagged_without_a_hint() -> None:
    name = ENV_PREFIX + "AUTH__MODE__X"

    assert unknown_env_vars({name: "1"}) == [(name, None)]


def test_unrelated_and_single_underscore_names_are_ignored() -> None:
    environ = {"PATH": "x", CONFIG_ENV_VAR: "y", "RECOVER_ASSESSMENT": "z", "HOME": "h"}

    assert unknown_env_vars(environ) == []


def test_valid_names_are_not_flagged_in_any_case() -> None:
    environ = {
        ENV_PREFIX + "COLLECT__SAMPLE_SIZE": "1",
        "recover_assess__http__max_retries": "2",
        ENV_PREFIX + "COLLECT": '{"sample_size": 3}',
    }

    assert unknown_env_vars(environ) == []


def test_a_name_with_no_close_match_has_no_hint() -> None:
    name = ENV_PREFIX + "ZZZZZZ__QQQQ"

    assert unknown_env_vars({name: "1"}) == [(name, None)]


def test_the_original_spelling_is_reported() -> None:
    name = "recover_assess__colect__sample_size"

    assert unknown_env_vars({name: "1"}) == [(name, "collect")]


def test_several_offenders_are_all_reported() -> None:
    first = ENV_PREFIX + "COLECT__SAMPLE_SIZE"
    second = ENV_PREFIX + "HTTP__MAX_RETRYS"

    found = dict(unknown_env_vars({first: "1", second: "1"}))

    assert found == {first: "collect", second: "max_retries"}


def test_load_settings_raises_for_a_mistyped_top_level_group() -> None:
    name = ENV_PREFIX + "COLECT__SAMPLE_SIZE"

    with pytest.raises(ConfigError, match=r"COLECT__SAMPLE_SIZE.*collect"):
        load_settings(environ={name: "1"})


def test_load_settings_raises_for_a_mistyped_nested_key() -> None:
    name = ENV_PREFIX + "COLLECT__SAMPEL_SIZE"

    with pytest.raises(ConfigError, match=r"COLLECT__SAMPEL_SIZE.*sample_size"):
        load_settings(environ={name: "1"})


def test_load_settings_names_every_offender() -> None:
    first = ENV_PREFIX + "COLECT__SAMPLE_SIZE"
    second = ENV_PREFIX + "AUTH__MODE__X"

    with pytest.raises(ConfigError) as caught:
        load_settings(environ={first: "1", second: "1"})

    assert first in str(caught.value)
    assert second in str(caught.value)


def test_the_scan_never_echoes_a_value() -> None:
    canary = "can" + "ary-" + "typo-value"
    name = ENV_PREFIX + "COLECT__SAMPLE_SIZE"

    with pytest.raises(ConfigError) as caught:
        load_settings(environ={name: canary})

    assert canary not in str(caught.value)


def test_a_mistyped_variable_in_the_real_process_environment_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_PREFIX + "COLECT__SAMPLE_SIZE", "1")

    with pytest.raises(ConfigError, match="COLECT"):
        load_settings()
