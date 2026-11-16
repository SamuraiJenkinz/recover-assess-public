"""The packaged allow-list is pinned: any new endpoint is a reviewed code change (D-08)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from recover_assess.core.errors import UrlNotAllowedError
from recover_assess.core.graph_policy import (
    Allowlist,
    AllowlistEntry,
    ReadOnlyPolicy,
    load_allowlist,
)
from tests.fakes.fake_graph import SYNTHETIC_SITE_ID

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "recover_assess"

# The review gate: this mapping is hard-coded on purpose. Adding an endpoint means
# changing it here, in the YAML, and in the SUMMARY of the plan that adds it.
EXPECTED: dict[str, tuple[str, str]] = {
    "site_by_id": ("GET", "/sites/{site-id}"),
    "site_by_path": ("GET", "/sites/{hostname}:/{+path}"),
    "subsites": ("GET", "/sites/{site-id}/sites"),
    "lists": ("GET", "/sites/{site-id}/lists"),
    "list_drive": ("GET", "/sites/{site-id}/lists/{list-id}/drive"),
    "columns": ("GET", "/sites/{site-id}/lists/{list-id}/columns"),
    "content_types": ("GET", "/sites/{site-id}/lists/{list-id}/contentTypes"),
    "list_items": ("GET", "/sites/{site-id}/lists/{list-id}/items"),
    "drive_delta": ("GET", "/drives/{drive-id}/root/delta"),
    "item_permissions": ("GET", "/drives/{drive-id}/items/{item-id}/permissions"),
    "site_drive": ("GET", "/sites/{site-id}/drive"),
    "group_owners": ("GET", "/groups/{group-id}/owners"),
    "batch": ("POST", "/$batch"),
}

LIST_ID = "cccccccc-dddd-eeee-ffff-000000000000"
DRIVE_ID = "b!abc_DEF-123"
ITEM_ID = "01ABCDEFGHIJKLMNOP"
GROUP_ID = "22222222-3333-4444-5555-666666666666"
BASE = "https://graph.microsoft.com/v1.0"

SAMPLE_PATHS: dict[str, str] = {
    "site_by_id": f"/sites/{SYNTHETIC_SITE_ID}",
    "site_by_path": "/sites/contoso.sharepoint.com:/sites/team-a",
    "subsites": f"/sites/{SYNTHETIC_SITE_ID}/sites",
    "lists": f"/sites/{SYNTHETIC_SITE_ID}/lists",
    "list_drive": f"/sites/{SYNTHETIC_SITE_ID}/lists/{LIST_ID}/drive",
    "columns": f"/sites/{SYNTHETIC_SITE_ID}/lists/{LIST_ID}/columns",
    "content_types": f"/sites/{SYNTHETIC_SITE_ID}/lists/{LIST_ID}/contentTypes",
    "list_items": f"/sites/{SYNTHETIC_SITE_ID}/lists/{LIST_ID}/items",
    "drive_delta": f"/drives/{DRIVE_ID}/root/delta",
    "item_permissions": f"/drives/{DRIVE_ID}/items/{ITEM_ID}/permissions",
    "site_drive": f"/sites/{SYNTHETIC_SITE_ID}/drive",
    "group_owners": f"/groups/{GROUP_ID}/owners",
}


def test_the_packaged_allowlist_is_exactly_the_pinned_set() -> None:
    allowlist = load_allowlist()

    actual = {entry.id: (entry.method, entry.template) for entry in allowlist.entries}

    assert actual == EXPECTED
    assert len(allowlist.entries) == 13


def test_every_entry_cites_a_learn_page() -> None:
    for entry in load_allowlist().entries:
        assert entry.learn_url.startswith("https://learn.microsoft.com/"), entry.id
        if entry.id == "batch":
            assert entry.learn_url == "https://learn.microsoft.com/en-us/graph/json-batching"
        else:
            assert entry.learn_url.endswith("view=graph-rest-1.0"), entry.id


def _entry(**overrides: str) -> dict[str, str]:
    base = {
        "id": "x",
        "method": "GET",
        "template": "/sites/{site-id}",
        "learn_url": "https://learn.microsoft.com/en-us/graph/api/site-get?view=graph-rest-1.0",
    }
    base.update(overrides)
    return base


def _document(*entries: dict[str, str]) -> dict[str, object]:
    return {"version": 1, "entries": list(entries)}


@pytest.mark.parametrize(
    "document",
    [
        _document(_entry(), _entry(template="/sites/{site-id}/sites")),
        _document(_entry(), _entry(id="y")),
        _document(_entry(id="p", method="POST", template="/sites/{site-id}")),
        _document(_entry(template="/sites/*")),
        _document(_entry(template="/sites/{site-id}/*")),
        _document(_entry(learn_url="https://evil.example/en-us/graph/api/site-get")),
        _document(_entry(learn_url="http://learn.microsoft.com/en-us/graph/api/site-get")),
        _document(_entry(template="/sites/{+path}/lists")),
    ],
    ids=[
        "duplicate-id",
        "duplicate-template",
        "post-other-than-batch",
        "wildcard-segment",
        "wildcard-tail",
        "learn-url-foreign-host",
        "learn-url-http",
        "plus-path-not-last",
    ],
)
def test_the_loader_rejects_a_malformed_document(document: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Allowlist.model_validate(document)


def test_a_post_entry_for_the_batch_template_is_accepted() -> None:
    entry = AllowlistEntry.model_validate(
        _entry(
            id="batch",
            method="POST",
            template="/$batch",
            learn_url="https://learn.microsoft.com/en-us/graph/json-batching",
        )
    )

    assert entry.method == "POST"


@pytest.mark.parametrize("entry_id", sorted(SAMPLE_PATHS))
def test_each_sample_url_matches_its_entry_and_no_other(entry_id: str) -> None:
    allowlist = load_allowlist()
    url = BASE + SAMPLE_PATHS[entry_id]

    assert ReadOnlyPolicy(allowlist).check("GET", url).id == entry_id
    for other in allowlist.entries:
        if other.id in {entry_id, "batch"}:
            continue
        alone = ReadOnlyPolicy(Allowlist(version=1, entries=[other]))
        with pytest.raises(UrlNotAllowedError):
            alone.check("GET", url)


def test_the_decision_does_not_depend_on_declaration_order() -> None:
    allowlist = load_allowlist()
    reversed_policy = ReadOnlyPolicy(
        Allowlist(version=1, entries=list(reversed(allowlist.entries)))
    )
    forward_policy = ReadOnlyPolicy(allowlist)

    for entry_id, path in SAMPLE_PATHS.items():
        assert forward_policy.check("GET", BASE + path).id == entry_id
        assert reversed_policy.check("GET", BASE + path).id == entry_id


def test_no_allowlist_file_exists_under_config() -> None:
    config_dir = REPO_ROOT / "config"

    offenders = [p.name for p in config_dir.rglob("*") if "allowlist" in p.name.lower()]

    assert offenders == []


def test_no_operator_setting_names_the_allowlist() -> None:
    for relative in ("src/recover_assess/core/config.py", "recover-assess.example.yaml"):
        text = (REPO_ROOT / relative).read_text(encoding="utf-8").lower()
        assert "allowlist" not in text, relative
        assert "allow_list" not in text, relative


def test_the_policy_is_only_constructed_from_the_packaged_allowlist() -> None:
    constructions = [
        (path.relative_to(SRC).as_posix(), line)
        for path in SRC.rglob("*.py")
        for line in path.read_text(encoding="utf-8").splitlines()
        if "ReadOnlyPolicy(" in line
    ]

    assert {path for path, _ in constructions} == {"core/graph.py"}
    assert all("ReadOnlyPolicy(load_allowlist())" in line for _, line in constructions)
    assert len(constructions) == 1


def test_the_policy_exposes_no_method_that_adds_or_replaces_templates() -> None:
    public = [name for name in dir(ReadOnlyPolicy) if not name.startswith("_")]

    forbidden = [name for name in public if name.startswith(("add", "register", "extend", "set"))]

    assert forbidden == []
