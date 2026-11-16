"""Pure read-only request policy for the Graph client (GRPH-01).

This module is deliberately free of any HTTP library: it uses the standard
library, pydantic and yaml only, so it can be unit-tested and property-tested
without an event loop and so the import contract "only ``core/graph.py`` imports
httpx2" stays literally true.

:meth:`ReadOnlyPolicy.check` is the first guard. It admits GET on an allow-listed
absolute URL and POST only to ``/v1.0/$batch`` with a body whose sub-requests are all
allow-listed GETs; every other verb is refused. URLs are canonicalised first (host, prefix,
dot segments, encoded separators, query keys) and then matched, as decoded segments, against
the packaged allow-list of anchored, per-segment templates (D-08, D-09). Reasons on every
refusal are identifier-shaped codes; a URL is never put in an exception.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Any, Final, Literal, Self
from urllib.parse import parse_qsl, unquote, urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from recover_assess.core.errors import UrlNotAllowedError, WriteAttemptError

__all__ = [
    "ALLOWED_QUERY_KEYS",
    "API_PREFIX",
    "DENIED_SEGMENTS",
    "GRAPH_HOST",
    "ID_SEGMENT",
    "MAX_BATCH_REQUESTS",
    "PLUS_PATH_MAX_SEGMENTS",
    "Allowlist",
    "AllowlistEntry",
    "MatchedTemplate",
    "ReadOnlyPolicy",
    "canonical_segments",
    "load_allowlist",
]

GRAPH_HOST: Final = "graph.microsoft.com"
API_PREFIX: Final = "/v1.0"
ALLOWED_QUERY_KEYS: Final[frozenset[str]] = frozenset(
    {"$select", "$expand", "$top", "$filter", "$skiptoken", "token"}
)
# One path segment of a real site, drive or item id (RESEARCH A2: confirmed by the Phase 2 smoke).
ID_SEGMENT: Final = re.compile(r"[A-Za-z0-9!_.,=~-]+")

# Template placeholders. "{name}" is one ID-shaped segment; "{hostname}:" is a dotted host
# name followed by a colon; "{+path}" is the single multi-segment placeholder (site_by_path).
_PLACEHOLDER: Final = re.compile(r"\{[A-Za-z][A-Za-z0-9-]*\}")
_HOST_PLACEHOLDER: Final = "{hostname}:"
_PLUS_PLACEHOLDER: Final = "{+path}"
_HOSTNAME_SEGMENT: Final = re.compile(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+:")
# Conservative character class for a server-relative site path segment (RESEARCH A8).
_PATH_SEGMENT: Final = re.compile(r"[A-Za-z0-9 _.~-]+")
PLUS_PATH_MAX_SEGMENTS: Final = 8
# Path segments that name file content or a pre-authenticated download (D-09). Denied even as
# a site path segment: fail closed (flagged assumption A14).
DENIED_SEGMENTS: Final[frozenset[str]] = frozenset({"content", "$value"})
BATCH_TEMPLATE: Final = "/$batch"
MAX_BATCH_REQUESTS: Final = 20
_BATCH_SUB_REQUEST_KEYS: Final[frozenset[str]] = frozenset({"id", "method", "url"})


class AllowlistEntry(BaseModel):
    """One allow-listed endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    method: Literal["GET", "POST"]
    template: str
    learn_url: str

    @field_validator("template")
    @classmethod
    def _template_shape(cls, value: str) -> str:
        if not value.startswith("/"):
            msg = "template must start with '/'"
            raise ValueError(msg)
        if "*" in value:
            msg = "template must not contain a wildcard"
            raise ValueError(msg)
        _compile_template(value)
        return value

    @model_validator(mode="after")
    def _post_only_for_batch(self) -> Self:
        if self.method == "POST" and self.template != BATCH_TEMPLATE:
            msg = "only the /$batch template may use POST"
            raise ValueError(msg)
        return self

    @field_validator("learn_url")
    @classmethod
    def _learn_url_shape(cls, value: str) -> str:
        if not value.startswith("https://learn.microsoft.com/"):
            msg = "learn_url must be a https://learn.microsoft.com/ page"
            raise ValueError(msg)
        return value


def _compile_template(template: str) -> tuple[str, ...]:
    """Split a template into segments, rejecting any unsupported placeholder syntax."""
    segments = tuple(template.split("/")[1:])
    for index, segment in enumerate(segments):
        if segment == _PLUS_PLACEHOLDER:
            if index != len(segments) - 1:
                msg = "{+path} may only be the last template segment"
                raise ValueError(msg)
        elif "{" in segment or "}" in segment:
            if segment != _HOST_PLACEHOLDER and _PLACEHOLDER.fullmatch(segment) is None:
                msg = "unsupported placeholder in template"
                raise ValueError(msg)
        elif segment == "":
            msg = "template must not contain an empty segment"
            raise ValueError(msg)
    return segments


class Allowlist(BaseModel):
    """The packaged allow-list document."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    entries: list[AllowlistEntry]

    @model_validator(mode="after")
    def _unique(self) -> Allowlist:
        ids = [entry.id for entry in self.entries]
        templates = [entry.template for entry in self.entries]
        if len(set(ids)) != len(ids):
            msg = "allow-list ids must be unique"
            raise ValueError(msg)
        if len(set(templates)) != len(templates):
            msg = "allow-list templates must be unique"
            raise ValueError(msg)
        return self


def load_allowlist() -> Allowlist:
    """Load and validate the allow-list packaged next to this module."""
    text = (
        resources.files("recover_assess.core")
        .joinpath("graph_allowlist.yaml")
        .read_text(encoding="utf-8")
    )
    data: Any = yaml.safe_load(text)
    return Allowlist.model_validate(data)


@dataclass(frozen=True)
class MatchedTemplate:
    """The allow-list entry a request matched."""

    id: str
    template: str


def _refuse(reason: str) -> UrlNotAllowedError:
    return UrlNotAllowedError(reason)


CanonicalUrl = tuple[tuple[str, ...], tuple[tuple[str, str], ...]]


def _has_control(text: str, *, allow_space: bool) -> bool:
    floor = 0x20 if allow_space else 0x21
    return any(ord(char) < floor or ord(char) == 0x7F for char in text)


def canonical_segments(url: str, *, absolute: bool) -> CanonicalUrl:
    """Canonicalise ``url`` and return its decoded path segments and query pairs.

    ``absolute=True`` is the form a request is sent in: scheme ``https``, host exactly
    ``graph.microsoft.com``, path under ``/v1.0/``. ``absolute=False`` is the form of a
    ``$batch`` sub-request url: no scheme or host, no ``v1.0`` prefix, and a missing
    leading ``/`` is added. Everything is decided on decoded segments, never on raw text.
    Every refusal is a :class:`UrlNotAllowedError` with an identifier-shaped reason.
    """
    if _has_control(url, allow_space=False) or "\\" in url or "#" in url:
        raise _refuse("segment_not_allowed")
    try:
        parts = urlsplit(url)
    except ValueError:
        raise _refuse("host_not_allowed") from None
    if absolute:
        if not url.startswith("https://") or parts.scheme != "https" or parts.netloc != GRAPH_HOST:
            raise _refuse("host_not_allowed")
        if not parts.path.startswith(API_PREFIX + "/"):
            raise _refuse("prefix_not_allowed")
        raw_path = parts.path[len(API_PREFIX) :]
    else:
        if parts.scheme or parts.netloc:
            raise _refuse("host_not_allowed")
        raw_path = parts.path if parts.path.startswith("/") else "/" + parts.path
    lowered = raw_path.lower()
    if "%2f" in lowered or "%5c" in lowered or "%00" in lowered:
        raise _refuse("segment_not_allowed")
    segments: list[str] = []
    for raw in raw_path.split("/")[1:]:
        segment = unquote(raw)
        if (
            segment in {"", ".", ".."}
            or "/" in segment
            or "\\" in segment
            or _has_control(segment, allow_space=True)
        ):
            raise _refuse("segment_not_allowed")
        if not segments and not absolute and segment.casefold() == API_PREFIX[1:]:
            raise _refuse("prefix_not_allowed")
        if segment.casefold() in DENIED_SEGMENTS:
            raise _refuse("content_not_allowed")
        segments.append(segment)
    pairs = tuple(parse_qsl(parts.query, keep_blank_values=True))
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise _refuse("query_not_allowed")
    for key, value in pairs:
        if key not in ALLOWED_QUERY_KEYS or "downloadurl" in value.casefold():
            raise _refuse("query_not_allowed")
    return tuple(segments), pairs


def _matches(expected: tuple[str, ...], segments: list[str]) -> bool:
    """Whole-path match of decoded segments against one compiled template."""
    if expected and expected[-1] == _PLUS_PLACEHOLDER:
        fixed = expected[:-1]
        rest = segments[len(fixed) :]
        if not 1 <= len(rest) <= PLUS_PATH_MAX_SEGMENTS or len(segments) < len(fixed):
            return False
        if any(_PATH_SEGMENT.fullmatch(part) is None for part in rest):
            return False
        segments = segments[: len(fixed)]
        expected = fixed
    if len(expected) != len(segments):
        return False
    for pattern, actual in zip(expected, segments, strict=True):
        if pattern == _HOST_PLACEHOLDER:
            if _HOSTNAME_SEGMENT.fullmatch(actual) is None:
                return False
        elif _PLACEHOLDER.fullmatch(pattern):
            if ID_SEGMENT.fullmatch(actual) is None:
                return False
        elif pattern != actual:
            return False
    return True


class ReadOnlyPolicy:
    """The first of the two independent read-only guards."""

    def __init__(self, allowlist: Allowlist) -> None:
        self._entries = tuple(
            (entry, _compile_template(entry.template)) for entry in allowlist.entries
        )

    def _match(self, segments: tuple[str, ...]) -> MatchedTemplate:
        for entry, compiled in self._entries:
            if _matches(compiled, list(segments)):
                return MatchedTemplate(id=entry.id, template=entry.template)
        raise _refuse("template_not_allowed")

    def check_absolute_url(self, url: str) -> MatchedTemplate:
        """Match an absolute v1.0 URL against the allow-list, or raise."""
        segments, _ = canonical_segments(url, absolute=True)
        return self._match(segments)

    def check_relative_url(self, url: str) -> MatchedTemplate:
        """Match a ``$batch`` sub-request url (relative, no ``/v1.0`` prefix), or raise."""
        segments, _ = canonical_segments(url, absolute=False)
        return self._match(segments)

    def check_batch_body(self, body: Mapping[str, Any]) -> list[MatchedTemplate]:
        """Validate a ``$batch`` body and return one matched template per sub-request.

        The body must hold only ``requests``: 1 to 20 mappings that each carry only ``id``,
        ``method`` and ``url``. Methods must be GET (any letter case), ids non-empty strings
        unique case-insensitively, and urls relative, un-prefixed and allow-listed. A
        ``body``, ``dependsOn`` or ``headers`` key, a nested ``$batch`` or any other shape is
        refused with :class:`WriteAttemptError` (a bad url with its ``UrlNotAllowedError``
        subclass).
        """
        if not isinstance(body, Mapping):
            raise WriteAttemptError("batch_body_unreadable")
        if set(body) - {"requests"}:
            raise WriteAttemptError("batch_field_not_allowed")
        requests = body.get("requests")
        if not isinstance(requests, list):
            raise WriteAttemptError("batch_requests_invalid")
        if not 1 <= len(requests) <= MAX_BATCH_REQUESTS:
            raise WriteAttemptError("batch_size_invalid")
        seen: set[str] = set()
        matched: list[MatchedTemplate] = []
        for item in requests:
            if not isinstance(item, Mapping):
                raise WriteAttemptError("batch_requests_invalid")
            if set(item) - _BATCH_SUB_REQUEST_KEYS:
                raise WriteAttemptError("batch_field_not_allowed")
            request_id, method, url = item.get("id"), item.get("method"), item.get("url")
            if not isinstance(request_id, str) or not request_id:
                raise WriteAttemptError("batch_id_invalid")
            if request_id.casefold() in seen:
                raise WriteAttemptError("batch_id_duplicate")
            seen.add(request_id.casefold())
            if not isinstance(method, str) or not method.isascii() or method.upper() != "GET":
                raise WriteAttemptError("batch_method_not_allowed")
            if not isinstance(url, str):
                raise WriteAttemptError("batch_requests_invalid")
            template = self.check_relative_url(url)
            if template.template == BATCH_TEMPLATE:
                raise WriteAttemptError("batch_nested_not_allowed")
            matched.append(template)
        return matched

    def check(
        self,
        method: str,
        url: str,
        *,
        batch_body: Mapping[str, Any] | None = None,
    ) -> MatchedTemplate:
        """Return the matched template, or raise before anything is sent.

        GET is allowed on any allow-listed absolute URL except the ``$batch`` URL. POST is
        allowed only to exactly ``https://graph.microsoft.com/v1.0/$batch`` and only with a
        ``batch_body`` that :meth:`check_batch_body` accepts. Every other verb, in any letter
        case, is refused as ``method_not_allowed``.
        """
        verb = method.upper() if method.isascii() else ""
        if verb == "GET":
            matched = self.check_absolute_url(url)
            if matched.template == BATCH_TEMPLATE:
                raise WriteAttemptError("method_not_allowed")
            return matched
        if verb == "POST":
            matched = self.check_absolute_url(url)
            if matched.template != BATCH_TEMPLATE:
                raise WriteAttemptError("method_not_allowed")
            if batch_body is None:
                raise WriteAttemptError("batch_body_missing")
            self.check_batch_body(batch_body)
            return matched
        raise WriteAttemptError("method_not_allowed")
