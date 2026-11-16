"""Exception tree and the stable error-code vocabulary.

This is a leaf module: it imports only the standard library, so every other
module (the Graph client, the collectors, the CLI) can depend on it.

No exception message can carry a URL, a query string or a token. The
constructors accept only an identifier-shaped ``reason`` and, optionally, a
path *template* such as ``/sites/{site-id}``; the message is built from those
two values and nothing else.
"""

from __future__ import annotations

import re
from typing import Final

__all__ = [
    "ERROR_CODES",
    "ERROR_CODE_PATTERN",
    "ConfigError",
    "GraphError",
    "GraphHttpError",
    "GraphPolicyError",
    "GraphTransportError",
    "OutputError",
    "RecoverAssessError",
    "ThrottledOut",
    "UrlNotAllowedError",
    "WriteAttemptError",
    "is_error_code",
]

_REASON: Final = re.compile(r"[A-Za-z0-9_]+")
_FORBIDDEN_TEMPLATE_PARTS: Final = ("?", "#", "://")
_THROTTLE_REASONS: Final = frozenset({"retries_exhausted", "budget", "breaker"})

ERROR_CODES: Final[frozenset[str]] = frozenset(
    {
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
    }
)

# Anchored with \A and \Z so a trailing newline or space never matches.
ERROR_CODE_PATTERN: Final[str] = (
    r"\A(?:" + "|".join(sorted(ERROR_CODES)) + r"|graph_error_[1-5][0-9]{2})\Z"
)
_ERROR_CODE_RE: Final = re.compile(ERROR_CODE_PATTERN)


def is_error_code(value: str) -> bool:
    """Return True when ``value`` is one of the 11 spec codes or ``graph_error_NNN``."""
    return _ERROR_CODE_RE.fullmatch(value) is not None


class RecoverAssessError(Exception):
    """Base class for every error this tool raises on purpose."""


class ConfigError(RecoverAssessError):
    """Configuration is missing, malformed or contains a forbidden key."""


class OutputError(RecoverAssessError):
    """A run folder or output file could not be written safely."""


class GraphError(RecoverAssessError):
    """Base class for Graph client failures.

    ``reason`` must be identifier-shaped and ``template``, when given, must be a
    path template (leading ``/``, no query, fragment, scheme or whitespace), so
    the message can never carry a URL, query string or token.
    """

    def __init__(self, reason: str, *, template: str | None = None) -> None:
        if not _REASON.fullmatch(reason):
            msg = "reason must be an identifier-shaped code (letters, digits, underscore)"
            raise ValueError(msg)
        if template is not None and (
            not template.startswith("/")
            or any(part in template for part in _FORBIDDEN_TEMPLATE_PARTS)
            or any(char.isspace() for char in template)
        ):
            msg = "template must start with '/' and contain no query, fragment, scheme or space"
            raise ValueError(msg)
        super().__init__(reason)
        self._reason = reason
        self._template = template

    @property
    def reason(self) -> str:
        """The identifier-shaped reason code."""
        return self._reason

    @property
    def template(self) -> str | None:
        """The path template of the refused or failed request, if known."""
        return self._template

    def __str__(self) -> str:
        text = f"{type(self).__name__}: {self._reason}"
        if self._template is not None:
            text += f" [{self._template}]"
        return text


class GraphPolicyError(GraphError):
    """A request was refused by the client's own read-only policy."""


class WriteAttemptError(GraphPolicyError):
    """The single documented GRPH-01 type for every refused request.

    It is raised for any request the read-only policy or the request hook
    refuses: a verb other than GET, a ``$batch`` carrying a non-GET, or (through
    the narrower subclass) a URL that is not allowed.
    """


class UrlNotAllowedError(WriteAttemptError):
    """A refusal narrowed to a URL, host, prefix, path, query or redirect.

    Subclassing ``WriteAttemptError`` means ``except WriteAttemptError`` catches
    every refusal, while a test that needs precision can assert this class.
    """


class GraphHttpError(GraphError):
    """Graph answered with an HTTP error status."""

    def __init__(self, status: int, *, template: str | None = None) -> None:
        if not 100 <= status <= 599:
            msg = "status must be an HTTP status between 100 and 599"
            raise ValueError(msg)
        super().__init__(f"http_{status}", template=template)
        self._status = status

    @property
    def status(self) -> int:
        """The HTTP status code."""
        return self._status

    @property
    def code(self) -> str:
        """The stable error code, ``graph_error_NNN``."""
        return f"graph_error_{self._status}"


class GraphTransportError(GraphError):
    """The request failed before an HTTP status arrived (connect, TLS, timeout)."""

    def __init__(self, exc_type_name: str, *, timeout: bool, template: str | None = None) -> None:
        super().__init__(exc_type_name, template=template)
        self._is_timeout = timeout

    @property
    def is_timeout(self) -> bool:
        """True when the underlying failure was a timeout."""
        return self._is_timeout


class ThrottledOut(GraphError):
    """Throttling was not survivable. One type, three reasons.

    ``retries_exhausted``: the retry limit was reached. ``budget``: the time
    budget ran out. ``breaker``: the throttle circuit breaker opened.
    """

    def __init__(self, reason: str, *, template: str | None = None) -> None:
        if reason not in _THROTTLE_REASONS:
            msg = "reason must be one of: " + ", ".join(sorted(_THROTTLE_REASONS))
            raise ValueError(msg)
        super().__init__(reason, template=template)

    @property
    def code(self) -> str:
        """The stable error code, always ``throttled_out``."""
        return "throttled_out"
