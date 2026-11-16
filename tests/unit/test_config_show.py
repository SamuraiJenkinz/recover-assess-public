"""`recover-assess config show` and the neutral example configuration (FND-03)."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import BaseModel
from typer.testing import CliRunner

from recover_assess import __version__
from recover_assess.cli import app
from recover_assess.core.config import Settings, load_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = REPO_ROOT / "recover-assess.example.yaml"

runner = CliRunner()


def _field_names(model: type[BaseModel]) -> Iterator[str]:
    for name, field in model.model_fields.items():
        yield name
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            yield from _field_names(annotation)


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty cwd and no inherited RECOVER_ASSESS settings."""
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.upper().startswith("RECOVER_ASSESS"):
            monkeypatch.delenv(name)


def test_config_show_prints_the_defaults_as_json() -> None:
    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0
    shown = json.loads(result.stdout)
    assert shown["collect"]["max_items_per_library"] == 50000
    assert shown["output"]["path_mode"] == "full"


def test_max_items_flag_overrides_the_default() -> None:
    result = runner.invoke(app, ["config", "show", "--max-items", "10"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["collect"]["max_items_per_library"] == 10
    assert '"max_items_per_library": 10' in result.stdout


def test_out_and_path_mode_flags_map_to_output_settings() -> None:
    result = runner.invoke(app, ["config", "show", "--out", "elsewhere", "--path-mode", "tokens"])

    assert result.exit_code == 0
    output = json.loads(result.stdout)["output"]
    assert output["dir"] == "elsewhere"
    assert output["path_mode"] == "tokens"


def test_unset_flags_do_not_override_yaml(tmp_path: Path) -> None:
    path = tmp_path / "cfg.yaml"
    path.write_text("collect:\n  max_items_per_library: 77\n", encoding="utf-8")

    result = runner.invoke(app, ["config", "show", "--config", str(path)])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["collect"]["max_items_per_library"] == 77


def test_flag_beats_yaml_and_keeps_the_rest_of_the_group(tmp_path: Path) -> None:
    path = tmp_path / "cfg.yaml"
    path.write_text("collect:\n  max_items_per_library: 77\n  sample_size: 5\n", encoding="utf-8")

    result = runner.invoke(app, ["config", "show", "--config", str(path), "--max-items", "10"])

    collect = json.loads(result.stdout)["collect"]
    assert collect["max_items_per_library"] == 10
    assert collect["sample_size"] == 5


def test_invalid_config_exits_1_with_the_message_on_stderr(tmp_path: Path) -> None:
    path = tmp_path / "cfg.yaml"
    path.write_text("colect:\n  sample_size: 1\n", encoding="utf-8")

    result = runner.invoke(app, ["config", "show", "--config", str(path)])

    assert result.exit_code == 1
    assert "colect" in result.stderr
    assert result.stdout == ""


def test_missing_config_file_exits_1(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "show", "--config", str(tmp_path / "nope.yaml")])

    assert result.exit_code == 1
    assert "not found" in result.stderr
    assert result.stdout == ""


def test_config_path_can_come_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "cfg.yaml"
    path.write_text("collect:\n  sample_size: 3\n", encoding="utf-8")
    monkeypatch.setenv("RECOVER_ASSESS_CONFIG", str(path))

    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["collect"]["sample_size"] == 3


def test_the_password_variable_value_is_never_printed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canary = "pw" + "-canary-" + "value"
    path = tmp_path / "cfg.yaml"
    path.write_text("auth:\n  certificate_password_env: CERT_PW\n", encoding="utf-8")
    monkeypatch.setenv("CERT_PW", canary)

    result = runner.invoke(app, ["config", "show", "--config", str(path)])

    assert result.exit_code == 0
    assert "CERT_PW" in result.stdout
    assert canary not in result.stdout
    assert canary not in result.stderr


def test_example_config_loads_and_shows() -> None:
    settings = load_settings(EXAMPLE, environ={})
    assert settings.tenant.default_hostname == "contoso.sharepoint.com"

    result = runner.invoke(app, ["config", "show", "--config", str(EXAMPLE)])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["tenant"]["default_hostname"] == "contoso.sharepoint.com"


def test_example_config_uses_only_synthetic_identifiers() -> None:
    text = EXAMPLE.read_text(encoding="utf-8")

    assert "contoso.sharepoint.com" in text
    assert "00000000-0000-0000-0000-000000000000" in text
    assert "11111111-1111-1111-1111-111111111111" in text


def test_example_config_mentions_every_operator_key() -> None:
    text = EXAMPLE.read_text(encoding="utf-8")
    missing = [name for name in _field_names(Settings) if f"{name}:" not in text]

    assert missing == []


@pytest.mark.parametrize("args", [["--version"], ["version"]])
def test_version_still_prints(args: list[str]) -> None:
    result = runner.invoke(app, args)

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__ == "0.1.0"
