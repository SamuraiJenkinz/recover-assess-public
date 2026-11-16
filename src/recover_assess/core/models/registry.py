"""Registry of published contract models and deterministic schema rendering (D-07).

Schemas are generated from the pydantic models, never written by hand. Rendering is
deterministic: ``indent=2``, ``ensure_ascii=False``, LF line endings, exactly one trailing
newline, and property order equal to the model field order.

This module imports models only; it never imports ``core.output``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel

from recover_assess.core.models.fact_sheet import FactSheet

__all__ = ["PUBLISHED", "SCHEMA_DIALECT", "build_schema", "render_schema", "schema_path"]

PUBLISHED: Final[dict[str, type[BaseModel]]] = {"fact_sheet": FactSheet}
"""Published schema name to the model it is generated from."""

SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"


def build_schema(name: str) -> dict[str, Any]:
    """Return the serialization-mode JSON schema for ``name``, with ``$schema`` as first key."""
    schema = PUBLISHED[name].model_json_schema(mode="serialization")
    return {"$schema": SCHEMA_DIALECT, **schema}


def render_schema(name: str) -> str:
    """Render the schema for ``name`` as byte-stable text ending in one newline."""
    return json.dumps(build_schema(name), indent=2, ensure_ascii=False) + "\n"


def schema_path(root: Path, name: str) -> Path:
    """Return where the checked-in schema for ``name`` lives under ``root``."""
    return root / "schemas" / f"{name}.schema.json"
