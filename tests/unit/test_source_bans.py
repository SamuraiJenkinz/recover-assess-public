"""AST bans for what import-linter cannot see (T-01-09).

- network libraries are imported only where the architecture allows
- no write-verb attribute call (post, put, patch, delete) anywhere in src
- no dynamic import (importlib.import_module, __import__)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "recover_assess"

NETWORK_ROOTS = frozenset({"httpx2", "httpx", "requests", "aiohttp", "urllib3", "socket"})
WRITE_VERBS = frozenset({"post", "put", "patch", "delete"})
GRAPH_MODULE = "core/graph.py"
PROVIDERS_PREFIX = "core/providers/"


def _import_roots(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name.split(".")[0] for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        return [node.module.split(".")[0]]
    return []


def _network_import_allowed(relative_path: str, root: str) -> bool:
    if root != "httpx2":
        return False
    return relative_path == GRAPH_MODULE or relative_path.startswith(PROVIDERS_PREFIX)


def find_offenders(relative_path: str, source_text: str) -> list[str]:
    """Return one description per banned construct in ``source_text``.

    ``relative_path`` is the module path under src/recover_assess, with forward slashes.
    """
    relative_path = relative_path.replace("\\", "/")
    offenders: list[str] = []
    for node in ast.walk(ast.parse(source_text)):
        if isinstance(node, ast.Import | ast.ImportFrom):
            for root in _import_roots(node):
                if root in NETWORK_ROOTS and not _network_import_allowed(relative_path, root):
                    offenders.append(f"{relative_path}:{node.lineno}: imports {root}")
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr in WRITE_VERBS:
                    offenders.append(f"{relative_path}:{node.lineno}: calls .{func.attr}(...)")
                is_importlib = isinstance(func.value, ast.Name) and func.value.id == "importlib"
                if func.attr == "import_module" and is_importlib:
                    offenders.append(f"{relative_path}:{node.lineno}: importlib.import_module")
            elif isinstance(func, ast.Name) and func.id in {"__import__", "import_module"}:
                offenders.append(f"{relative_path}:{node.lineno}: dynamic import {func.id}")
    return offenders


@pytest.mark.parametrize(
    ("path", "source"),
    [
        ("core/collect/x.py", "import httpx2\n"),
        ("core/collect/x.py", "from httpx2 import AsyncClient\n"),
        ("core/score/x.py", "import requests\n"),
        ("core/graph.py", "import requests\n"),
        ("core/providers/azure.py", "import aiohttp\n"),
        ("core/clock.py", "import socket\n"),
        ("core/collect/x.py", "client.post('/x')\n"),
        ("core/collect/x.py", "await self._http.delete(url)\n"),
        ("core/collect/x.py", "client.put(url)\n"),
        ("core/collect/x.py", "client.patch(url)\n"),
        ("core/collect/x.py", 'import importlib\nimportlib.import_module("httpx2")\n'),
        ("core/collect/x.py", '__import__("httpx2")\n'),
    ],
)
def test_checker_flags_banned_constructs(path: str, source: str) -> None:
    assert find_offenders(path, source)


@pytest.mark.parametrize(
    ("path", "source"),
    [
        ("core/graph.py", "import httpx2\n"),
        ("core/providers/azure.py", "from httpx2 import Client\n"),
        ("core/collect/x.py", "import json\nclient.get('/x')\nclient.request('GET', '/x')\n"),
        ("core/collect/x.py", "from . import sibling\n"),
    ],
)
def test_checker_allows_permitted_constructs(path: str, source: str) -> None:
    assert find_offenders(path, source) == []


def test_whole_tree_has_no_offenders() -> None:
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC).as_posix()
        offenders.extend(find_offenders(relative, path.read_text(encoding="utf-8")))
    assert offenders == []
