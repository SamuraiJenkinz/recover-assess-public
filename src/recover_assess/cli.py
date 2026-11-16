"""Typer entry point for recover-assess.

Tracebacks never show local variables: they can hold bearer tokens, which would
break the "no tokens in logs" promise.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer

from recover_assess import __version__
from recover_assess.core.config import CONFIG_ENV_VAR, load_settings
from recover_assess.core.errors import ConfigError

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    no_args_is_help=True,
    add_completion=False,
    help="Read-only SharePoint recovery assessment.",
)


config_app = typer.Typer(
    pretty_exceptions_show_locals=False,
    no_args_is_help=True,
    help="Inspect configuration.",
)
app.add_typer(config_app, name="config")


class PathMode(StrEnum):
    """How paths and folder names appear in outputs."""

    FULL = "full"
    TOKENS = "tokens"
    HASHED = "hashed"


def _print_version_and_exit(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_print_version_and_exit,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """Read-only SharePoint recovery assessment."""


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo(__version__)


@config_app.command("show")
def config_show(
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            envvar=CONFIG_ENV_VAR,
            help="Config file (default ./recover-assess.yaml when present).",
        ),
    ] = None,
    max_items: Annotated[
        int | None,
        typer.Option("--max-items", help="Overrides collect.max_items_per_library."),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Overrides output.dir."),
    ] = None,
    path_mode: Annotated[
        PathMode | None,
        typer.Option("--path-mode", help="Overrides output.path_mode."),
    ] = None,
) -> None:
    """Print the effective configuration as JSON.

    Only the NAME of a secret-bearing environment variable is shown, never its value.
    """
    # Forward only flags the operator actually gave: None would override YAML.
    overrides: dict[str, Any] = {}
    if max_items is not None:
        overrides["collect"] = {"max_items_per_library": max_items}
    output: dict[str, Any] = {}
    if out is not None:
        output["dir"] = out
    if path_mode is not None:
        output["path_mode"] = path_mode.value
    if output:
        overrides["output"] = output
    try:
        settings = load_settings(config_path=config, cli_overrides=overrides)
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(settings.model_dump(mode="json"), indent=2))
