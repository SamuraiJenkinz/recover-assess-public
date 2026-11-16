"""Foundation tests: version, error vocabulary, clock, lock content, README guidance."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import re
import tomllib
from datetime import UTC
from pathlib import Path
from types import ModuleType

import pytest
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[2]

ACCEPTED_CODES = [
    "not_found",
    "not_granted",
    "no_access",
    "ambiguous",
    "name_requires_delegated",
    "throttled_out",
    "timeout",
    "truncated",
    "has_subsites",
    "owners_unavailable",
    "sam_no_match",
    "graph_error_404",
    "graph_error_503",
]
REJECTED_CODES = [
    "graph_error_4041",
    "graph_error_099",
    "graph_error_abc",
    "NOT_FOUND",
    "",
    "not_found ",
]


def _errors() -> ModuleType:
    return importlib.import_module("recover_assess.core.errors")


def _load_verify_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "verify_sha256", ROOT / "scripts" / "verify_sha256.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- version and CLI -------------------------------------------------------------------


def test_version_option_prints_exactly_the_version() -> None:
    from recover_assess.cli import app

    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0"


def test_version_command_prints_the_same_string() -> None:
    from recover_assess.cli import app

    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0"


def test_no_arguments_prints_help_and_exits_two() -> None:
    from recover_assess.cli import app

    result = CliRunner().invoke(app, [])
    assert result.exit_code == 2
    assert "Usage" in result.output


def test_installed_metadata_matches_module_version() -> None:
    import recover_assess

    assert importlib.metadata.version("recover-assess") == "0.1.0"
    assert recover_assess.__version__ == "0.1.0"


def test_cli_never_shows_locals_in_tracebacks() -> None:
    from recover_assess.cli import app

    assert app.pretty_exceptions_show_locals is False


# -- error vocabulary ------------------------------------------------------------------


@pytest.mark.parametrize("code", ACCEPTED_CODES)
def test_is_error_code_accepts_spec_codes(code: str) -> None:
    assert _errors().is_error_code(code) is True


@pytest.mark.parametrize("code", REJECTED_CODES)
def test_is_error_code_rejects_everything_else(code: str) -> None:
    assert _errors().is_error_code(code) is False


def test_error_codes_are_the_eleven_spec_strings() -> None:
    assert len(_errors().ERROR_CODES) == 11
    assert re.fullmatch(_errors().ERROR_CODE_PATTERN, "graph_error_599")
    assert not re.fullmatch(_errors().ERROR_CODE_PATTERN, "graph_error_600")


def test_graph_error_rejects_a_url_as_reason() -> None:
    with pytest.raises(ValueError, match="identifier"):
        _errors().GraphError("https://evil.example/x")


def test_graph_error_rejects_a_template_that_could_carry_a_query() -> None:
    with pytest.raises(ValueError, match="template"):
        _errors().GraphError("bad", template="/sites?token=abc")
    with pytest.raises(ValueError, match="template"):
        _errors().GraphError("bad", template="sites/no-leading-slash")


def test_url_not_allowed_message_carries_no_url_or_token() -> None:
    err = _errors().UrlNotAllowedError("host_not_allowed", template="/sites/{site-id}")
    text = str(err)
    assert "https://" not in text
    assert "Bearer" not in text
    assert "host_not_allowed" in text
    assert "/sites/{site-id}" in text
    assert err.reason == "host_not_allowed"
    assert err.template == "/sites/{site-id}"


def test_graph_http_error_code_is_graph_error_status() -> None:
    err = _errors().GraphHttpError(404, template="/sites/{site-id}")
    assert err.code == "graph_error_404"
    assert err.status == 404
    assert _errors().is_error_code(err.code)


def test_graph_transport_error_records_timeout_and_class_name_only() -> None:
    err = _errors().GraphTransportError("ReadTimeout", timeout=True, template="/sites/{site-id}")
    assert err.is_timeout is True
    assert err.reason == "ReadTimeout"


def test_throttled_out_has_one_code_and_three_reasons() -> None:
    errors = _errors()
    err = errors.ThrottledOut("breaker")
    assert err.code == "throttled_out"
    assert err.reason == "breaker"
    for reason in ("retries_exhausted", "budget", "breaker"):
        assert errors.ThrottledOut(reason).code == "throttled_out"
    with pytest.raises(ValueError, match="reason"):
        errors.ThrottledOut("other")


def test_url_not_allowed_is_a_write_attempt_error() -> None:
    errors = _errors()
    assert issubclass(errors.UrlNotAllowedError, errors.WriteAttemptError)
    with pytest.raises(errors.WriteAttemptError):
        raise errors.UrlNotAllowedError("template_not_allowed")
    assert not isinstance(errors.WriteAttemptError("method_not_allowed"), errors.UrlNotAllowedError)


def test_exception_tree_roots() -> None:
    errors = _errors()
    for name in ("ConfigError", "OutputError", "GraphError"):
        assert issubclass(getattr(errors, name), errors.RecoverAssessError)
    for name in ("GraphPolicyError", "GraphHttpError", "GraphTransportError", "ThrottledOut"):
        assert issubclass(getattr(errors, name), errors.GraphError)
    assert issubclass(errors.WriteAttemptError, errors.GraphPolicyError)


# -- clock -----------------------------------------------------------------------------


def test_system_clock_utcnow_is_timezone_aware_utc() -> None:
    from recover_assess.core.clock import SYSTEM_CLOCK, Clock, SystemClock

    now = SystemClock().utcnow()
    assert now.tzinfo is UTC
    assert isinstance(SYSTEM_CLOCK, Clock)


def test_system_clock_monotonic_is_non_decreasing() -> None:
    from recover_assess.core.clock import SystemClock

    clock = SystemClock()
    first = clock.monotonic()
    second = clock.monotonic()
    assert second >= first


def test_system_clock_sleeps_do_not_raise_for_zero() -> None:
    from recover_assess.core.clock import SystemClock

    SystemClock().sleep_sync(0)


async def test_system_clock_async_sleep_zero() -> None:
    from recover_assess.core.clock import SystemClock

    await SystemClock().sleep(0)


# -- scripts/verify_sha256.py ----------------------------------------------------------


def test_verify_sha256_matches_name_form_and_bare_uppercase_sidecar(tmp_path: Path) -> None:
    script = _load_verify_script()
    archive = tmp_path / "a.zip"
    archive.write_bytes(b"hello archive")
    digest = hashlib.sha256(b"hello archive").hexdigest()

    named = tmp_path / "named.sha256"
    named.write_text(f"{digest}  a.zip\n", encoding="utf-8")
    bare = tmp_path / "bare.sha256"
    bare.write_text(digest.upper(), encoding="utf-8")

    assert script.main([str(archive), str(named)]) == 0
    assert script.main([str(archive), str(bare)]) == 0


def test_verify_sha256_mismatch_returns_one(tmp_path: Path) -> None:
    script = _load_verify_script()
    archive = tmp_path / "a.zip"
    archive.write_bytes(b"hello archive")
    sidecar = tmp_path / "wrong.sha256"
    sidecar.write_text("0" * 64, encoding="utf-8")
    assert script.main([str(archive), str(sidecar)]) == 1


def test_verify_sha256_rejects_a_malformed_sidecar(tmp_path: Path) -> None:
    script = _load_verify_script()
    sidecar = tmp_path / "bad.sha256"
    sidecar.write_text("not-a-digest  a.zip", encoding="utf-8")
    with pytest.raises(ValueError, match="64-character"):
        script.read_expected_digest(sidecar)


# -- lock, manifest and README content -------------------------------------------------


def test_lock_names_none_of_the_forbidden_packages() -> None:
    with (ROOT / "uv.lock").open("rb") as handle:
        names = {package["name"] for package in tomllib.load(handle)["package"]}
    assert names.isdisjoint({"httpx", "respx", "requests", "vcrpy", "pytest-httpx"})
    assert "httpx2" in names


def test_ruff_select_is_the_explicit_fifteen_rule_list() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        config = tomllib.load(handle)
    assert config["tool"]["ruff"]["lint"]["select"] == [
        "E",
        "F",
        "I",
        "B",
        "UP",
        "S",
        "SIM",
        "RUF",
        "ASYNC",
        "PTH",
        "TID",
        "DTZ",
        "T20",
        "PT",
        "C4",
    ]
    assert "extend-select" not in config["tool"]["ruff"]["lint"]


def test_pyproject_authors_carry_no_email_address() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        authors = tomllib.load(handle)["project"]["authors"]
    assert authors
    assert all("@" not in value for author in authors for value in author.values())


def test_readme_documents_the_trust_store_fix() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "UV_SYSTEM_CERTS" in text
    assert text.count("UV_SYSTEM_CERTS") >= 2
    assert "UV_PYTHON_DOWNLOADS=never" in text


@pytest.mark.parametrize(
    "forbidden",
    [
        "--allow-insecure-host",
        "UV_INSECURE_HOST",
        "--trusted-host",
        "verify=False",
        "PYTHONHTTPSVERIFY",
        "NODE_TLS_REJECT_UNAUTHORIZED",
    ],
)
def test_readme_never_suggests_weakening_tls(forbidden: str) -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert forbidden not in text
