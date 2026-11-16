"""Hostile-URL corpus and hypothesis properties for the read-only URL policy (GRPH-01, GRPH-02).

Fixtures are synthetic: contoso host names, repeated-digit GUIDs, and the userinfo-form
hostile URL is assembled at runtime by explicit concatenation (the FND-07 scan convention),
so no word character, at sign and dotted domain ever sit together in source.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recover_assess.core import graph_policy
from recover_assess.core.errors import UrlNotAllowedError, WriteAttemptError
from recover_assess.core.graph_policy import (
    PLUS_PATH_MAX_SEGMENTS,
    ReadOnlyPolicy,
    load_allowlist,
)
from tests.fakes.fake_graph import SYNTHETIC_SITE_ID

POLICY = ReadOnlyPolicy(load_allowlist())
BASE = "https://graph.microsoft.com/v1.0"
HOST = "graph.microsoft.com"
SITE = SYNTHETIC_SITE_ID
LIST_ID = "cccccccc-dddd-eeee-ffff-000000000000"
GROUP_ID = "22222222-3333-4444-5555-666666666666"
DRIVE = "b!abc_DEF-123"
ITEM = "01ABCDEFGHIJKLMNOP"
USERINFO_FORM = "https://" + HOST + "@" + "evil.example/v1.0/sites/x"

ALL_TEMPLATE_IDS = {entry.id for entry in load_allowlist().entries}


# ---------------------------------------------------------------- accepted URLs


@pytest.mark.parametrize(
    ("url", "template_id"),
    [
        pytest.param(f"{BASE}/sites/{SITE}?$select=id,displayName", "site_by_id", id="site-select"),
        pytest.param(
            f"{BASE}/sites/contoso.sharepoint.com:/sites/team-a",
            "site_by_path",
            id="site-by-path-two-segments",
        ),
        pytest.param(f"{BASE}/drives/{DRIVE}/root/delta?token=abc", "drive_delta", id="delta"),
        pytest.param(
            f"{BASE}/sites/{SITE}/lists/{LIST_ID}/items?$expand=fields($select=Title)&$top=200",
            "list_items",
            id="items-expand-top",
        ),
        pytest.param(f"{BASE}/groups/{GROUP_ID}/owners?$skiptoken=X", "group_owners", id="owners"),
        pytest.param(
            f"{BASE}/drives/{DRIVE}/items/{ITEM}/permissions", "item_permissions", id="perm"
        ),
        pytest.param(
            f"{BASE}/sites/contoso.sharepoint.com:/" + "/".join(["p"] * PLUS_PATH_MAX_SEGMENTS),
            "site_by_path",
            id="site-by-path-eight-segments",
        ),
    ],
)
def test_valid_urls_are_accepted(url: str, template_id: str) -> None:
    assert POLICY.check("GET", url).id == template_id
    assert POLICY.check_absolute_url(url).id == template_id


def test_permuting_query_keys_gives_the_same_template() -> None:
    forward = f"{BASE}/sites/{SITE}/lists/{LIST_ID}/items?$select=id&$top=5&$expand=fields"
    permuted = f"{BASE}/sites/{SITE}/lists/{LIST_ID}/items?$expand=fields&$select=id&$top=5"

    assert POLICY.check("GET", forward) == POLICY.check("GET", permuted)


# ---------------------------------------------------------------- hostile corpus

HOSTILE: dict[str, str] = {
    "http-scheme": f"http://{HOST}/v1.0/sites/x",
    "userinfo-host": USERINFO_FORM,
    "foreign-host": "https://evil.example/v1.0/sites/x",
    "port-8443": f"https://{HOST}:8443/v1.0/sites/x",
    "port-443": f"https://{HOST}:443/v1.0/sites/x",
    "trailing-dot-host": f"https://{HOST}./v1.0/sites/x",
    "upper-case-host": "https://GRAPH.microsoft.com/v1.0/sites/x",
    "suffix-host": f"https://{HOST}.evil.example/v1.0/sites/x",
    "host-as-path": f"https://evil.example/{HOST}/v1.0/sites/x",
    "beta-prefix": f"https://{HOST}/beta/sites/x",
    "v1-0x-prefix": f"https://{HOST}/v1.0x/sites/x",
    "bare-prefix": f"https://{HOST}/v1.0",
    "dot-dot-segment": f"{BASE}/sites/../sites/x",
    "dot-segment": f"{BASE}/sites/./x",
    "encoded-slash-upper": f"{BASE}/sites/a%2Fb",
    "encoded-slash-lower": f"{BASE}/sites/a%2fb",
    "encoded-backslash": f"{BASE}/sites/a%5cb",
    "encoded-nul": f"{BASE}/sites/a%00b",
    "double-slash": f"{BASE}//sites/x",
    "double-slash-inside": f"{BASE}/sites//x",
    "content-suffix": f"{BASE}/drives/{DRIVE}/items/{ITEM}/content",
    "permissions-dot-dot-content": f"{BASE}/drives/{DRIVE}/items/{ITEM}/permissions/../content",
    "value-segment": f"{BASE}/drives/{DRIVE}/items/{ITEM}/$value",
    "value-segment-upper": f"{BASE}/drives/{DRIVE}/items/{ITEM}/$VALUE",
    "select-download-url": f"{BASE}/sites/x?$select=@microsoft.graph.downloadUrl",
    "select-download-url-upper": f"{BASE}/sites/x?$select=DOWNLOADURL",
    "unknown-query-key": f"{BASE}/sites/x?$search=a",
    "duplicate-query-key": f"{BASE}/sites/x?$select=id&$select=name",
    "backslash": f"{BASE}/sites/x\\y",
    "fragment": f"{BASE}/sites/x#frag",
    "encoded-dot-dot": f"{BASE}/sites/%2e%2e/x",
    "extra-after-delta": f"{BASE}/drives/{DRIVE}/root/delta/extra",
    "colon-dot-dot-beta": f"{BASE}/sites/contoso.sharepoint.com:/../beta",
    "ftp-scheme": f"ftp://{HOST}/v1.0/sites/x",
    "embedded-newline": f"{BASE}/sites/x\n/lists",
    "embedded-tab": f"{BASE}/sites/x\t",
    "embedded-space": f"{BASE}/sites/x y",
    "trailing-slash": f"{BASE}/sites/{SITE}/",
    "site-path-nine-segments": f"{BASE}/sites/contoso.sharepoint.com:/"
    + "/".join(["p"] * (PLUS_PATH_MAX_SEGMENTS + 1)),
    "site-path-colon-suffix": f"{BASE}/sites/contoso.sharepoint.com:/sites/team-a:",
    "site-path-content-segment": f"{BASE}/sites/contoso.sharepoint.com:/sites/Content",
    "site-path-colon-without-path": f"{BASE}/sites/contoso.sharepoint.com:",
    "empty-url": "",
    "no-scheme": f"{HOST}/v1.0/sites/x",
    "protocol-relative": f"//{HOST}/v1.0/sites/x",
    "extends-items": f"{BASE}/sites/{SITE}/lists/{LIST_ID}/items/extra",
    "abuts-lists": f"{BASE}/sites/{SITE}/listsX",
    "lists-case": f"{BASE}/sites/{SITE}/Lists",
    "empty-segment-query-only": f"{BASE}/?$select=id",
    "id-with-colon": f"{BASE}/sites/a:b",
    "unknown-resource": f"{BASE}/me/drive",
    "batch-sub-path": f"{BASE}/$batch/extra",
    "malformed-ipv6": "https://[graph.microsoft.com/v1.0/sites/x",
}


def test_the_hostile_corpus_has_at_least_23_cases() -> None:
    assert len(HOSTILE) >= 23


@pytest.mark.parametrize("url", list(HOSTILE.values()), ids=list(HOSTILE))
def test_hostile_urls_are_rejected(url: str) -> None:
    with pytest.raises(UrlNotAllowedError) as excinfo:
        POLICY.check("GET", url)

    assert isinstance(excinfo.value, WriteAttemptError)
    assert url not in str(excinfo.value) or url == ""


@pytest.mark.parametrize("url", list(HOSTILE.values()), ids=list(HOSTILE))
def test_hostile_urls_are_rejected_by_the_absolute_url_check_too(url: str) -> None:
    with pytest.raises(UrlNotAllowedError):
        POLICY.check_absolute_url(url)


def test_exception_reasons_are_identifier_shaped_and_never_hold_the_url() -> None:
    for url in HOSTILE.values():
        if not url:
            continue
        with pytest.raises(UrlNotAllowedError) as excinfo:
            POLICY.check("GET", url)
        text = str(excinfo.value)
        assert "evil.example" not in text
        assert "://" not in text


# ---------------------------------------------------------------- relative mode


@pytest.mark.parametrize("url", ["/sites/x", "sites/x"])
def test_relative_urls_with_and_without_a_leading_slash_match(url: str) -> None:
    assert POLICY.check_relative_url(url).id == "site_by_id"


@pytest.mark.parametrize(
    "url",
    [
        "/v1.0/sites/x",
        "v1.0/sites/x",
        f"{BASE}/sites/x",
        "//evil.example/sites/x",
        "",
        "/sites/x#frag",
        "/sites/x/content",
        "/sites/x?$select=downloadUrl",
        "/sites/x\\y",
    ],
    ids=[
        "leading-v1-with-slash",
        "leading-v1",
        "absolute",
        "protocol-relative",
        "empty",
        "fragment",
        "content",
        "download-url",
        "backslash",
    ],
)
def test_relative_mode_rejects_prefixed_absolute_and_hostile_urls(url: str) -> None:
    with pytest.raises(UrlNotAllowedError):
        POLICY.check_relative_url(url)


# ---------------------------------------------------------------- canonical segments


def test_canonical_segments_returns_decoded_segments_and_query_pairs() -> None:
    segments, query = graph_policy.canonical_segments(
        f"{BASE}/sites/a%20b/lists?$top=5&$select=id", absolute=True
    )

    assert list(segments) == ["sites", "a b", "lists"]
    assert list(query) == [("$top", "5"), ("$select", "id")]


def test_canonical_segments_relative_adds_the_missing_leading_slash() -> None:
    segments, query = graph_policy.canonical_segments("sites/x", absolute=False)

    assert list(segments) == ["sites", "x"]
    assert list(query) == []


def test_the_denied_segments_are_content_and_value() -> None:
    assert frozenset({"content", "$value"}) == graph_policy.DENIED_SEGMENTS


# ---------------------------------------------------------------- hypothesis

ID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-!,=~"
ids = st.text(alphabet=ID_ALPHABET, min_size=1, max_size=24).filter(
    lambda text: text.casefold() not in {"content", "$value"}
)


def _path_safe(text: str) -> str:
    return "".join(char if char.isalnum() or char in "_-" else "x" for char in text)


PATH_BUILDERS: dict[str, Callable[[str, str], str]] = {
    "site_by_id": lambda a, _b: f"/sites/{a}",
    # A site path segment has a narrower alphabet than an ID segment (no "!,=~").
    "site_by_path": lambda a, _b: f"/sites/contoso.sharepoint.com:/sites/{_path_safe(a)}",
    "subsites": lambda a, _b: f"/sites/{a}/sites",
    "lists": lambda a, _b: f"/sites/{a}/lists",
    "list_drive": lambda a, b: f"/sites/{a}/lists/{b}/drive",
    "columns": lambda a, b: f"/sites/{a}/lists/{b}/columns",
    "content_types": lambda a, b: f"/sites/{a}/lists/{b}/contentTypes",
    "list_items": lambda a, b: f"/sites/{a}/lists/{b}/items",
    "drive_delta": lambda a, _b: f"/drives/{a}/root/delta",
    "item_permissions": lambda a, b: f"/drives/{a}/items/{b}/permissions",
    "site_drive": lambda a, _b: f"/sites/{a}/drive",
    "group_owners": lambda a, _b: f"/groups/{a}/owners",
}
QUERIES = ["", "?$select=id,displayName", "?$top=200&$skiptoken=abc", "?$expand=fields"]


def _split(url: str) -> tuple[str, str]:
    path, sep, query = url.partition("?")
    return path, sep + query


MUTATIONS: dict[str, Callable[[str], str]] = {
    "dot-segment": lambda u: u.replace("/v1.0/", "/v1.0/../v1.0/", 1),
    "single-dot-segment": lambda u: u.replace("/v1.0/", "/v1.0/./", 1),
    "encoded-slash-upper": lambda u: _split(u)[0] + "%2F" + _split(u)[1],
    "encoded-slash-lower": lambda u: _split(u)[0] + "%2f" + _split(u)[1],
    "host-case-flip": lambda u: u.replace(HOST, "Graph.Microsoft.com", 1),
    "port-8443": lambda u: u.replace(HOST, HOST + ":8443", 1),
    "port-443": lambda u: u.replace(HOST, HOST + ":443", 1),
    "fragment": lambda u: u + "#frag",
    "scheme-downgrade": lambda u: u.replace("https://", "http://", 1),
    "content-append": lambda u: _split(u)[0] + "/content" + _split(u)[1],
    "value-append": lambda u: _split(u)[0] + "/$value" + _split(u)[1],
    "download-url-select": lambda u: u + ("&" if "?" in u else "?") + "$select=downloadUrl",
    "doubled-slash": lambda u: u.replace("/v1.0/", "/v1.0//", 1),
    "backslash": lambda u: _split(u)[0] + "\\" + _split(u)[1],
    "beta-prefix": lambda u: u.replace("/v1.0/", "/beta/", 1),
}


@given(
    template_id=st.sampled_from(sorted(PATH_BUILDERS)),
    first=ids,
    second=ids,
    query=st.sampled_from(QUERIES),
    mutation=st.sampled_from(sorted(MUTATIONS)),
)
def test_mutations_of_a_valid_url_are_never_accepted(
    template_id: str, first: str, second: str, query: str, mutation: str
) -> None:
    valid = BASE + PATH_BUILDERS[template_id](first, second) + query
    assert POLICY.check("GET", valid).id == template_id

    mutated = MUTATIONS[mutation](valid)

    assert mutated != valid
    with pytest.raises(WriteAttemptError):
        POLICY.check("GET", mutated)


@given(
    text=st.one_of(
        st.text(max_size=120),
        st.builds(lambda tail: BASE + "/" + tail, st.text(max_size=120)),
        st.builds(lambda tail: "https://" + HOST + tail, st.text(max_size=120)),
    )
)
def test_an_accepted_url_always_lies_under_the_v1_prefix_and_matches_a_known_template(
    text: str,
) -> None:
    try:
        matched = POLICY.check("GET", text)
    except WriteAttemptError:
        return

    assert text.startswith("https://graph.microsoft.com/v1.0/")
    assert urlsplit(text).netloc == HOST
    assert matched.id in ALL_TEMPLATE_IDS
    assert matched.id != "batch"
