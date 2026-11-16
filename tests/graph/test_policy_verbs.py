"""Verb matrix and ``$batch`` body validation of the read-only policy (GRPH-01, T-01-20).

Verb and batch-shape refusals assert the exact class WriteAttemptError; URL refusals assert
UrlNotAllowedError, which is also a WriteAttemptError, so the subclassing loses no precision.
"""

from __future__ import annotations

from typing import Any

import pytest

from recover_assess.core import graph_policy
from recover_assess.core.errors import UrlNotAllowedError, WriteAttemptError
from recover_assess.core.graph_policy import (
    MatchedTemplate,
    ReadOnlyPolicy,
    load_allowlist,
)
from tests.fakes.fake_graph import SYNTHETIC_SITE_ID

POLICY = ReadOnlyPolicy(load_allowlist())
MAX_BATCH_REQUESTS = 20  # the Graph $batch limit, pinned here independently of the code
BASE = "https://graph.microsoft.com/v1.0"
SITE_URL = f"{BASE}/sites/{SYNTHETIC_SITE_ID}"
BATCH_URL = f"{BASE}/$batch"
BATCH_MATCH = MatchedTemplate(id="batch", template="/$batch")


def sub(request_id: str, url: str, method: str = "GET") -> dict[str, Any]:
    return {"id": request_id, "method": method, "url": url}


VALID_BODY: dict[str, Any] = {
    "requests": [sub("1", "/sites/x"), sub("2", "sites/x/lists")],
}


# ---------------------------------------------------------------- the verb matrix


def test_get_on_an_allowed_url_returns_the_template() -> None:
    assert POLICY.check("GET", SITE_URL) == MatchedTemplate(
        id="site_by_id", template="/sites/{site-id}"
    )


@pytest.mark.parametrize(
    "method",
    ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT", "MERGE", "get ", ""],
    ids=[
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
        "connect",
        "merge",
        "get-trailing-space",
        "empty",
    ],
)
def test_every_verb_but_get_is_refused_on_an_allowed_get_url(method: str) -> None:
    with pytest.raises(WriteAttemptError) as excinfo:
        POLICY.check(method, SITE_URL)

    assert excinfo.type is WriteAttemptError
    assert excinfo.value.reason == "method_not_allowed"


def test_post_to_the_batch_url_with_a_valid_body_returns_the_batch_template() -> None:
    assert POLICY.check("POST", BATCH_URL, batch_body=VALID_BODY) == BATCH_MATCH


def test_get_to_the_batch_url_is_refused() -> None:
    with pytest.raises(WriteAttemptError) as excinfo:
        POLICY.check("GET", BATCH_URL)

    assert excinfo.type is WriteAttemptError


def test_post_to_the_batch_url_without_a_body_is_refused() -> None:
    with pytest.raises(WriteAttemptError) as excinfo:
        POLICY.check("POST", BATCH_URL, batch_body=None)

    assert excinfo.type is WriteAttemptError


@pytest.mark.parametrize(
    "url",
    [f"{BASE}/$BATCH", f"{BASE}/$batch/extra", f"{BASE}/$batch/", f"{BASE}/$batch#x"],
    ids=["upper-case", "extra-segment", "trailing-slash", "fragment"],
)
def test_post_to_a_url_that_is_not_exactly_the_batch_url_is_refused(url: str) -> None:
    with pytest.raises(UrlNotAllowedError):
        POLICY.check("POST", url, batch_body=VALID_BODY)


def test_post_with_a_valid_body_to_a_non_batch_url_is_refused() -> None:
    with pytest.raises(WriteAttemptError) as excinfo:
        POLICY.check("POST", SITE_URL, batch_body=VALID_BODY)

    assert excinfo.type is WriteAttemptError


def test_a_valid_body_returns_one_template_per_sub_request_in_order() -> None:
    assert POLICY.check_batch_body(VALID_BODY) == [
        MatchedTemplate(id="site_by_id", template="/sites/{site-id}"),
        MatchedTemplate(id="lists", template="/sites/{site-id}/lists"),
    ]


def test_a_lower_case_get_method_is_accepted_because_the_comparison_is_case_insensitive() -> None:
    body = {"requests": [sub("1", "/sites/x", method="get")]}

    assert [m.id for m in POLICY.check_batch_body(body)] == ["site_by_id"]


def test_exactly_the_maximum_number_of_sub_requests_is_accepted() -> None:
    body = {"requests": [sub(str(n), "/sites/x") for n in range(1, MAX_BATCH_REQUESTS + 1)]}

    assert len(POLICY.check_batch_body(body)) == 20


def test_the_batch_limit_is_twenty() -> None:
    assert graph_policy.MAX_BATCH_REQUESTS == MAX_BATCH_REQUESTS


# ---------------------------------------------------------------- batch shape refusals

REFUSED_BODIES: dict[str, Any] = {
    "method-post": {"requests": [sub("1", "/sites/x", "POST")]},
    "method-post-lower": {"requests": [sub("1", "/sites/x", "post")]},
    "method-patch-mixed": {"requests": [sub("1", "/sites/x", "Patch")]},
    "method-delete": {"requests": [sub("1", "/sites/x", "DELETE")]},
    "method-get-trailing-space": {"requests": [sub("1", "/sites/x", "GET ")]},
    "method-not-a-string": {"requests": [{"id": "1", "method": None, "url": "/sites/x"}]},
    "method-missing": {"requests": [{"id": "1", "url": "/sites/x"}]},
    "body-key": {"requests": [{**sub("1", "/sites/x"), "body": {"a": 1}}]},
    "depends-on-key": {"requests": [{**sub("1", "/sites/x"), "dependsOn": ["2"]}]},
    "headers-key": {"requests": [{**sub("1", "/sites/x"), "headers": {"Authorization": "x"}}]},
    "nested-batch": {"requests": [sub("1", "/$batch")]},
    "nested-batch-no-slash": {"requests": [sub("1", "$batch")]},
    "twenty-one-requests": {
        "requests": [sub(str(n), "/sites/x") for n in range(1, MAX_BATCH_REQUESTS + 2)]
    },
    "zero-requests": {"requests": []},
    "requests-missing": {},
    "requests-not-a-list": {"requests": "x"},
    "request-not-a-mapping": {"requests": ["/sites/x"]},
    "extra-top-level-key": {"requests": [sub("1", "/sites/x")], "extra": 1},
    "id-missing": {"requests": [{"method": "GET", "url": "/sites/x"}]},
    "id-empty": {"requests": [sub("", "/sites/x")]},
    "id-not-a-string": {"requests": [{"id": 1, "method": "GET", "url": "/sites/x"}]},
    "ids-differ-only-by-case": {"requests": [sub("a", "/sites/x"), sub("A", "/sites/x")]},
    "ids-identical": {"requests": [sub("1", "/sites/x"), sub("1", "/sites/x")]},
}


@pytest.mark.parametrize("body", list(REFUSED_BODIES.values()), ids=list(REFUSED_BODIES))
def test_check_batch_body_refuses_unsafe_shapes_with_the_documented_type(
    body: dict[str, Any],
) -> None:
    with pytest.raises(WriteAttemptError) as excinfo:
        POLICY.check_batch_body(body)

    assert excinfo.type is WriteAttemptError


@pytest.mark.parametrize("body", list(REFUSED_BODIES.values()), ids=list(REFUSED_BODIES))
def test_check_refuses_the_same_bodies_on_a_post_to_the_batch_url(body: dict[str, Any]) -> None:
    with pytest.raises(WriteAttemptError) as excinfo:
        POLICY.check("POST", BATCH_URL, batch_body=body)

    assert excinfo.type is WriteAttemptError


def test_a_body_that_is_not_a_mapping_is_refused() -> None:
    with pytest.raises(WriteAttemptError) as excinfo:
        POLICY.check_batch_body(["requests"])  # type: ignore[arg-type]

    assert excinfo.type is WriteAttemptError


REFUSED_SUB_URLS: dict[str, str] = {
    "absolute": f"{BASE}/sites/x",
    "leading-v1": "/v1.0/sites/x",
    "leading-v1-no-slash": "v1.0/sites/x",
    "protocol-relative": "//evil.example/sites/x",
    "content": "/sites/x/lists/y/items/z/content",
    "not-allow-listed": "/me/drive",
    "download-url": "/sites/x?$select=downloadUrl",
    "dot-dot": "/sites/../me",
    "empty": "",
}


@pytest.mark.parametrize("url", list(REFUSED_SUB_URLS.values()), ids=list(REFUSED_SUB_URLS))
def test_check_batch_body_refuses_unsafe_sub_urls_with_url_not_allowed(url: str) -> None:
    with pytest.raises(UrlNotAllowedError) as excinfo:
        POLICY.check_batch_body({"requests": [sub("1", url)]})

    assert isinstance(excinfo.value, WriteAttemptError)
