"""Layered, typo-proof configuration (FND-03).

Precedence, each layer overriding the last: built-in defaults, the YAML file, the
``RECOVER_ASSESS__*`` environment, then explicit CLI overrides. Nested groups are
deep-merged, so overriding ``collect.sample_size`` keeps the YAML value of
``collect.max_items_per_library``.

Every failure is a ``ConfigError``. No message ever carries a submitted value, because a
value may be a secret; only key paths and variable names appear. There is deliberately no
allow-list key anywhere in the models (D-08): the Graph allow-list is not configurable.

This is a leaf module: standard library, pydantic, pydantic-settings, yaml and
``core.errors`` only.
"""

from __future__ import annotations

import difflib
import os
from collections.abc import Mapping
from contextvars import ContextVar
from pathlib import Path
from typing import Annotated, Any, Final, Literal, NamedTuple

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError, model_validator
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)
from pydantic_settings.exceptions import SettingsError

from recover_assess.core.errors import ConfigError

__all__ = [
    "CONFIG_ENV_VAR",
    "DEFAULT_CONFIG_NAME",
    "ENV_PREFIX",
    "AuthSettings",
    "CollectSettings",
    "HttpSettings",
    "OutputSettings",
    "Settings",
    "TenantSettings",
    "load_settings",
    "resolve_config_path",
    "unknown_env_vars",
]

ENV_PREFIX: Final = "RECOVER_ASSESS__"
CONFIG_ENV_VAR: Final = "RECOVER_ASSESS_CONFIG"
DEFAULT_CONFIG_NAME: Final = "recover-assess.yaml"
_DELIMITER: Final = "__"

UNSUPPORTED_CREDENTIAL_MESSAGE: Final = (
    "client secrets are not supported; use auth.mode app_certificate (certificate_path) "
    "or managed_identity"
)

_Count = Annotated[int, Field(ge=1)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _is_client_secret_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    return key.casefold().replace("_", "").replace("-", "") == "clientsecret"


class TenantSettings(_StrictModel):
    """Which tenant and default SharePoint host to talk to."""

    id: StrictStr | None = None
    default_hostname: StrictStr | None = None


class AuthSettings(_StrictModel):
    """How the tool signs in. There is no client-secret mode (rejected below)."""

    mode: Literal["delegated", "app_certificate", "managed_identity"] = "delegated"
    client_id: StrictStr | None = None
    certificate_path: Path | None = None
    certificate_thumbprint: StrictStr | None = None
    # The NAME of the environment variable that holds the certificate password. The
    # variable itself is never read by configuration code, so it can never be printed.
    certificate_password_env: StrictStr | None = None
    managed_identity_client_id: StrictStr | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_client_secret(cls, data: object) -> object:
        if isinstance(data, dict) and any(_is_client_secret_key(key) for key in data):
            raise ValueError(UNSUPPORTED_CREDENTIAL_MESSAGE)
        return data


class CollectSettings(_StrictModel):
    """Collector limits and the SAM export join."""

    max_rows: _Count = 500
    max_items_per_library: _Count = 50000
    fill_rate_sample: _Count = 500
    permission_checks_per_library: _Count = 200
    sample_size: Annotated[int, Field(ge=0)] = 15
    max_file_mb: _Count = 10
    owners_via_groups: bool = False
    skip_lists: list[StrictStr] = Field(
        default_factory=lambda: [
            "Site Assets",
            "Style Library",
            "Form Templates",
            "Preservation Hold Library",
        ]
    )
    sam_url_column: StrictStr = "Site URL"
    sam_keep_columns: list[StrictStr] = Field(default_factory=list)


class HttpSettings(_StrictModel):
    """Transport limits for the Graph client."""

    max_in_flight_per_site: _Count = 4
    # The config twin of the spec's --concurrency flag (wired by Phase 3).
    max_concurrent_sites: _Count = 2
    connect_timeout_s: Annotated[float, Field(gt=0)] = 30.0
    read_timeout_s: Annotated[float, Field(gt=0)] = 120.0
    max_retries: Annotated[int, Field(ge=0, le=10)] = 6
    site_wall_clock_minutes: _Count = 30
    # Decorates the User-Agent so a tenant admin can attribute the traffic.
    user_agent_company: StrictStr | None = None


class OutputSettings(_StrictModel):
    """Where run folders go and how identifying values appear in them."""

    dir: Path = Path("out")
    path_mode: Literal["full", "tokens", "hashed"] = "full"
    contributors: Literal["email", "hashed"] = "email"


class _LoadContext(NamedTuple):
    yaml_path: Path | None
    environ: Mapping[str, str]


# Set by load_settings for the duration of one build. A ContextVar, not a class
# attribute: global mutable state would break parallel tests.
_CONTEXT: ContextVar[_LoadContext | None] = ContextVar("recover_assess_config_load", default=None)


class _MappingEnvSource(EnvSettingsSource):
    """Reads the mapping given to ``load_settings`` instead of always reading ``os.environ``."""

    def _load_env_vars(self) -> Mapping[str, str | None]:
        context = _CONTEXT.get()
        source: Mapping[str, str] = os.environ if context is None else context.environ
        # case_sensitive is False for Settings: names are matched in lower case.
        return {name.casefold(): value for name, value in source.items()}


class Settings(BaseSettings):
    """The effective configuration. ``extra="forbid"`` makes unknown YAML keys an error."""

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_nested_delimiter=_DELIMITER,
        extra="forbid",
        case_sensitive=False,
    )

    tenant: TenantSettings = Field(default_factory=TenantSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    collect: CollectSettings = Field(default_factory=CollectSettings)
    http: HttpSettings = Field(default_factory=HttpSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """First item wins: CLI (init) over env over YAML over the model defaults."""
        del env_settings, dotenv_settings, file_secret_settings
        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            _MappingEnvSource(settings_cls),
        ]
        context = _CONTEXT.get()
        if context is not None and context.yaml_path is not None:
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=context.yaml_path))
        return tuple(sources)


def resolve_config_path(explicit: Path | None, environ: Mapping[str, str]) -> Path | None:
    """Pick the config file: ``--config``, else ``RECOVER_ASSESS_CONFIG``, else the default.

    A file that was named (explicitly or through the environment) but does not exist is an
    error. The default file in the working directory is used only when it is present.
    """
    named = explicit
    if named is None:
        from_env = environ.get(CONFIG_ENV_VAR)
        if from_env:
            named = Path(from_env)
    if named is not None:
        if not named.is_file():
            msg = f"config file not found: {named}"
            raise ConfigError(msg)
        return named
    default = Path.cwd() / DEFAULT_CONFIG_NAME
    return default if default.is_file() else None


def _model_children(model: type[BaseModel]) -> dict[str, type[BaseModel] | None]:
    """Map each field name to its nested model class, or None for a leaf."""
    children: dict[str, type[BaseModel] | None] = {}
    for name, field in model.model_fields.items():
        annotation = field.annotation
        is_model = isinstance(annotation, type) and issubclass(annotation, BaseModel)
        children[name] = annotation if is_model and isinstance(annotation, type) else None
    return children


def _closest(name: str, valid: list[str]) -> str | None:
    matches = difflib.get_close_matches(name.casefold(), valid, n=1)
    return matches[0] if matches else None


def unknown_env_vars(
    environ: Mapping[str, str],
    *,
    model: type[BaseModel] = Settings,
    prefix: str = ENV_PREFIX,
    delimiter: str = _DELIMITER,
) -> list[tuple[str, str | None]]:
    """Return ``(name, hint)`` for every prefixed variable that names no configuration key.

    pydantic-settings silently ignores a mistyped top-level group, so this scan is what makes
    ``RECOVER_ASSESS__COLECT__SAMPLE_SIZE`` an error. Matching is case-insensitive; ``name`` is
    reported as spelled in the environment. ``hint`` is the closest valid name at the level
    where the walk failed, or None.
    """
    folded_prefix = prefix.casefold()
    offenders: list[tuple[str, str | None]] = []
    for name in environ:
        if not name.casefold().startswith(folded_prefix):
            continue
        parts = name[len(prefix) :].casefold().split(delimiter)
        level: type[BaseModel] | None = model
        hint: str | None = None
        bad = False
        for index, part in enumerate(parts):
            if level is None:  # a leaf with leftover parts
                bad = True
                break
            children = _model_children(level)
            if part not in children:
                hint = _closest(part, list(children))
                bad = True
                break
            level = children[part]
            if level is None and index < len(parts) - 1:
                bad = True
                break
        if bad:
            offenders.append((name, hint))
    return offenders


def _format_validation_error(exc: ValidationError) -> str:
    """Render each problem as ``dotted.path: message`` without ever including the input."""
    lines: list[str] = []
    for error in exc.errors(include_input=False, include_url=False, include_context=False):
        location = ".".join(str(part) for part in error["loc"])
        if error["type"] == "extra_forbidden":
            valid = _valid_names_at(error["loc"][:-1])
            hint = _closest(str(error["loc"][-1]), valid)
            suffix = f" (did you mean '{hint}'?)" if hint else ""
            lines.append(f"{location}: unknown configuration key{suffix}")
        else:
            lines.append(f"{location}: {error['msg']}")
    return "invalid configuration: " + "; ".join(lines)


def _valid_names_at(location: tuple[int | str, ...]) -> list[str]:
    level: type[BaseModel] | None = Settings
    for part in location:
        if level is None:
            return []
        level = _model_children(level).get(str(part))
    return [] if level is None else list(level.model_fields)


def _yaml_error_message(path: Path, exc: yaml.YAMLError) -> str:
    mark = getattr(exc, "problem_mark", None)
    where = f" at line {mark.line + 1}" if mark is not None else ""
    return f"invalid YAML in {path}{where}"


def load_settings(
    config_path: Path | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    """Build the effective ``Settings`` or raise ``ConfigError``.

    ``environ`` defaults to ``os.environ``. ``cli_overrides`` holds only values the operator
    actually supplied (never None), nested by group: ``{"collect": {"sample_size": 40}}``.
    """
    env: Mapping[str, str] = os.environ if environ is None else environ

    for name in env:
        if name.casefold().startswith(ENV_PREFIX.casefold()):
            last = name[len(ENV_PREFIX) :].split(_DELIMITER)[-1]
            if _is_client_secret_key(last):
                msg = f"{name}: {UNSUPPORTED_CREDENTIAL_MESSAGE}"
                raise ConfigError(msg)

    offenders = unknown_env_vars(env)
    if offenders:
        parts = [f"{name} (did you mean '{hint}'?)" if hint else name for name, hint in offenders]
        msg = "unknown environment variable(s): " + ", ".join(parts)
        raise ConfigError(msg)

    path = resolve_config_path(config_path, env)
    token = _CONTEXT.set(_LoadContext(yaml_path=path, environ=env))
    try:
        try:
            return Settings(**dict(cli_overrides or {}))
        except ValidationError as exc:
            raise ConfigError(_format_validation_error(exc)) from None
        except yaml.YAMLError as exc:
            raise ConfigError(_yaml_error_message(path or Path(DEFAULT_CONFIG_NAME), exc)) from None
        except SettingsError as exc:
            raise ConfigError(f"invalid configuration source: {exc}") from None
    finally:
        _CONTEXT.reset(token)
