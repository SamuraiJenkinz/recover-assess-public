"""Layered settings (FND-03): precedence, deep merge, strict keys, secrets and the allow-list.

Environments are passed to ``load_settings`` as plain mappings, so no test touches the real
process environment except the one that proves the default. Every test runs in an empty
working directory so a developer's own ``recover-assess.yaml`` can never leak in. Canary
values are built at runtime by concatenation.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import BaseModel

from recover_assess.core import config
from recover_assess.core.config import (
    CONFIG_ENV_VAR,
    ENV_PREFIX,
    Settings,
    load_settings,
    resolve_config_path,
)
from recover_assess.core.errors import ConfigError

SECRET_HINT_MESSAGE = r"app_certificate.*managed_identity|managed_identity.*app_certificate"


@pytest.fixture(autouse=True)
def _empty_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def write_yaml(tmp_path: Path, text: str, name: str = "cfg.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def env(**pairs: str) -> dict[str, str]:
    """Build an environment mapping; keys are given without the prefix, ``__`` kept as is."""
    return {ENV_PREFIX + key: value for key, value in pairs.items()}


def test_defaults_only() -> None:
    settings = load_settings(environ={})

    assert settings.collect.max_items_per_library == 50000
    assert settings.collect.sample_size == 15
    assert settings.collect.skip_lists == [
        "Site Assets",
        "Style Library",
        "Form Templates",
        "Preservation Hold Library",
    ]
    assert settings.http.max_in_flight_per_site == 4
    assert settings.http.max_concurrent_sites == 2
    assert settings.http.max_retries == 6
    assert settings.output.path_mode == "full"
    assert settings.auth.mode == "delegated"
    assert settings.tenant.default_hostname is None


def test_yaml_overrides_default(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, "collect:\n  sample_size: 20\n")

    settings = load_settings(config_path=path, environ={})

    assert settings.collect.sample_size == 20


def test_env_overrides_yaml(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, "collect:\n  sample_size: 20\n")

    settings = load_settings(config_path=path, environ=env(COLLECT__SAMPLE_SIZE="30"))

    assert settings.collect.sample_size == 30


def test_cli_overrides_env_and_the_group_is_deep_merged(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, "collect:\n  sample_size: 20\n  max_items_per_library: 1234\n")

    settings = load_settings(
        config_path=path,
        cli_overrides={"collect": {"sample_size": 40}},
        environ=env(COLLECT__SAMPLE_SIZE="30"),
    )

    assert settings.collect.sample_size == 40
    assert settings.collect.max_items_per_library == 1234


def test_lower_case_env_names_work() -> None:
    settings = load_settings(environ={"recover_assess__collect__sample_size": "7"})

    assert settings.collect.sample_size == 7


def test_list_values_accept_json_in_env() -> None:
    settings = load_settings(environ=env(COLLECT__SKIP_LISTS='["A","B"]'))

    assert settings.collect.skip_lists == ["A", "B"]


def test_process_environment_is_the_default_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_PREFIX + "COLLECT__SAMPLE_SIZE", "11")

    assert load_settings().collect.sample_size == 11


def test_unknown_yaml_key_at_top_level_is_a_config_error(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, "colect:\n  sample_size: 1\n")

    with pytest.raises(ConfigError, match=r"colect.*collect"):
        load_settings(config_path=path, environ={})


def test_unknown_yaml_key_nested_is_a_config_error(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, "collect:\n  sampel_size: 1\n")

    with pytest.raises(ConfigError, match=r"collect\.sampel_size.*sample_size"):
        load_settings(config_path=path, environ={})


@pytest.mark.parametrize("key", ["client_secret", "clientSecret"])
def test_client_secret_in_yaml_is_rejected_with_a_pointer(tmp_path: Path, key: str) -> None:
    path = write_yaml(tmp_path, f"auth:\n  {key}: not-a-real-value\n")

    with pytest.raises(ConfigError, match=SECRET_HINT_MESSAGE):
        load_settings(config_path=path, environ={})


def test_client_secret_in_env_is_rejected_with_a_pointer() -> None:
    with pytest.raises(ConfigError, match=SECRET_HINT_MESSAGE):
        load_settings(environ=env(AUTH__CLIENT_SECRET="not-a-real-value"))


def test_client_secret_value_is_never_echoed(tmp_path: Path) -> None:
    canary = "sec" + "ret-" + "canary-" + "value"
    path = write_yaml(tmp_path, f"auth:\n  client_secret: {canary}\n")

    with pytest.raises(ConfigError) as from_yaml:
        load_settings(config_path=path, environ={})
    with pytest.raises(ConfigError) as from_env:
        load_settings(environ=env(AUTH__CLIENT_SECRET=canary))

    assert canary not in str(from_yaml.value)
    assert canary not in str(from_env.value)


def test_allowlist_in_yaml_is_rejected(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, 'graph:\n  allowlist: ["/anything"]\n')

    with pytest.raises(ConfigError, match="graph"):
        load_settings(config_path=path, environ={})


def test_allowlist_in_env_is_rejected() -> None:
    with pytest.raises(ConfigError, match="GRAPH__ALLOWLIST"):
        load_settings(environ=env(GRAPH__ALLOWLIST='["/anything"]'))


def _field_names(model: type[BaseModel]) -> Iterator[str]:
    for name, field in model.model_fields.items():
        yield name
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            yield from _field_names(annotation)


def test_no_settings_field_is_an_allow_list() -> None:
    """D-08: the Graph allow-list is not configurable through any operator channel."""
    names = list(_field_names(Settings))

    assert "collect" in names  # the walk really descended
    assert [name for name in names if "allow" in name.casefold()] == []


def test_unquoted_yaml_no_is_rejected_for_a_string_field(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, "tenant:\n  default_hostname: no\n")

    with pytest.raises(ConfigError, match=r"tenant\.default_hostname"):
        load_settings(config_path=path, environ={})


def test_quoted_yaml_no_is_accepted_for_a_string_field(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, 'tenant:\n  default_hostname: "no"\n')

    assert load_settings(config_path=path, environ={}).tenant.default_hostname == "no"


def test_explicit_missing_config_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        resolve_config_path(tmp_path / "missing.yaml", {})


def test_env_named_missing_config_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        resolve_config_path(None, {CONFIG_ENV_VAR: str(tmp_path / "missing.yaml")})


def test_env_named_config_file_is_honoured(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, "collect:\n  sample_size: 3\n", name="from-env.yaml")

    assert resolve_config_path(None, {CONFIG_ENV_VAR: str(path)}) == path
    assert load_settings(environ={CONFIG_ENV_VAR: str(path)}).collect.sample_size == 3


def test_explicit_path_wins_over_the_env_path(tmp_path: Path) -> None:
    explicit = write_yaml(tmp_path, "collect:\n  sample_size: 1\n", name="explicit.yaml")
    other = write_yaml(tmp_path, "collect:\n  sample_size: 2\n", name="other.yaml")

    assert resolve_config_path(explicit, {CONFIG_ENV_VAR: str(other)}) == explicit


def test_default_file_in_the_working_directory_is_used_only_when_present(
    tmp_path: Path,
) -> None:
    assert resolve_config_path(None, {}) is None

    write_yaml(tmp_path, "collect:\n  sample_size: 9\n", name="recover-assess.yaml")

    found = resolve_config_path(None, {})
    assert found is not None
    assert found.name == "recover-assess.yaml"
    assert load_settings(environ={}).collect.sample_size == 9


def test_a_bad_value_is_never_echoed(tmp_path: Path) -> None:
    canary = "can" + "ary-" + "do-not-echo"
    path = write_yaml(tmp_path, f"collect:\n  sample_size: {canary}\n")

    with pytest.raises(ConfigError) as caught:
        load_settings(config_path=path, environ={})

    assert "collect.sample_size" in str(caught.value)
    assert canary not in str(caught.value)


def test_a_bad_env_value_is_never_echoed() -> None:
    canary = "can" + "ary-" + "env-value"

    with pytest.raises(ConfigError) as caught:
        load_settings(environ=env(COLLECT__SAMPLE_SIZE=canary))

    assert "collect.sample_size" in str(caught.value)
    assert canary not in str(caught.value)


def test_yaml_syntax_error_does_not_echo_the_file_content(tmp_path: Path) -> None:
    canary = "can" + "ary-" + "yaml-content"
    path = write_yaml(tmp_path, f"collect: [{canary}\n  - : :\n")

    with pytest.raises(ConfigError) as caught:
        load_settings(config_path=path, environ={})

    assert canary not in str(caught.value)


def test_yaml_is_parsed_with_safe_load_only(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, "collect: !!python/object/apply:os.getcwd []\n")

    with pytest.raises(ConfigError):
        load_settings(config_path=path, environ={})


def test_empty_env_string_for_an_int_field_is_a_config_error() -> None:
    """FA-2: an empty env value is a value, not an absent one."""
    with pytest.raises(ConfigError, match=r"collect\.sample_size"):
        load_settings(environ=env(COLLECT__SAMPLE_SIZE=""))


def test_cli_override_equal_to_the_default_still_beats_yaml(tmp_path: Path) -> None:
    """FA-2: an explicitly given flag overrides YAML even when it equals the default."""
    path = write_yaml(tmp_path, "collect:\n  max_items_per_library: 99\n")

    settings = load_settings(
        config_path=path,
        cli_overrides={"collect": {"max_items_per_library": 50000}},
        environ={},
    )

    assert settings.collect.max_items_per_library == 50000


def test_yaml_null_for_a_non_nullable_key_is_a_config_error(tmp_path: Path) -> None:
    """FA-2: null is only legal where the field is nullable."""
    path = write_yaml(tmp_path, "collect:\n  sample_size: null\n")

    with pytest.raises(ConfigError, match=r"collect\.sample_size"):
        load_settings(config_path=path, environ={})


def test_nullable_keys_accept_yaml_null(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, "auth:\n  certificate_path: null\n")

    assert load_settings(config_path=path, environ={}).auth.certificate_path is None


def test_out_of_range_values_are_rejected() -> None:
    with pytest.raises(ConfigError, match=r"http\.max_retries"):
        load_settings(environ=env(HTTP__MAX_RETRIES="11"))


@pytest.mark.parametrize("value", ["7", "10"])
def test_max_retries_cannot_exceed_six(value: str) -> None:
    # T-01-24 / GRPH-05: at most 6 retries, whatever the operator config says.
    with pytest.raises(ConfigError, match=r"http\.max_retries"):
        load_settings(environ=env(HTTP__MAX_RETRIES=value))


def test_max_retries_accepts_six() -> None:
    assert load_settings(environ=env(HTTP__MAX_RETRIES="6")).http.max_retries == 6


def test_the_yaml_path_does_not_leak_between_loads(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, "collect:\n  sample_size: 20\n")

    assert load_settings(config_path=path, environ={}).collect.sample_size == 20
    # A later load without a path must not see the earlier file.
    assert load_settings(environ={}).collect.sample_size == 15
    # ... and a failed load must not leave state behind either.
    bad = write_yaml(tmp_path, "nope: 1\n", name="bad.yaml")
    with pytest.raises(ConfigError):
        load_settings(config_path=bad, environ={})
    assert load_settings(environ={}).collect.sample_size == 15


def test_module_constants_have_the_documented_values() -> None:
    assert ENV_PREFIX == "RECOVER_ASSESS__"
    assert CONFIG_ENV_VAR == "RECOVER_ASSESS_CONFIG"
    assert config.DEFAULT_CONFIG_NAME == "recover-assess.yaml"
