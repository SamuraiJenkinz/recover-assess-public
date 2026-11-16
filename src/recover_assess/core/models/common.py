"""Contract base model and shared scalar types for every published model.

Published models carry no field defaults, forbid extra keys and are frozen (D-05): a
collector that forgets a key fails validation instead of silently shipping a hole. The
JSON schema is generated in serialization mode with every property required, so a document
missing any key fails the generated schema as well.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Final, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

from recover_assess.core.errors import ERROR_CODE_PATTERN

__all__ = [
    "UNKNOWN_STATUSES",
    "ColumnType",
    "Contract",
    "ContributorsMode",
    "ErrorCodeStr",
    "ExposureStatus",
    "LastActivitySource",
    "NonNegInt",
    "OwnersSource",
    "PathMode",
    "PatternKind",
    "SectionState",
    "SectionStatus",
    "Share",
    "SiteKind",
    "TruncatedReason",
    "UtcDatetime",
    "round3",
    "round4",
]


class Contract(BaseModel):
    """Base class for published models: strict extras, frozen, every key required in the schema.

    ``regex_engine="python-re"`` is needed because the error-code pattern is anchored with
    ``\\A`` and ``\\Z``, which the default Rust engine does not accept.
    ``hide_input_in_errors`` keeps submitted values out of validation error text.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_serialization_defaults_required=True,
        regex_engine="python-re",
        hide_input_in_errors=True,
    )


def round4(value: float) -> float:
    """Round to four decimal places (the precision of every published share)."""
    return round(value, 4)


def round3(value: float) -> float:
    """Round to three decimal places (the precision of published durations)."""
    return round(value, 3)


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


Share = Annotated[float, Field(ge=0, le=1), AfterValidator(round4)]
"""A ratio in the closed interval 0..1, rounded to four decimal places."""

UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]
"""A timezone-aware datetime converted to UTC; it serialises with a trailing ``Z``."""

NonNegInt = Annotated[int, Field(ge=0)]
"""An integer that is zero or greater."""

ErrorCodeStr = Annotated[str, StringConstraints(pattern=ERROR_CODE_PATTERN)]
"""A stable error code from ``core.errors`` (also enforced by the generated schema)."""

# Vocabulary (research proposal A12; provisional until the Phase 6 freeze, D-06).
SectionStatus = Literal[
    "ok", "partial", "truncated", "not_run", "unavailable", "forbidden", "failed"
]
"""Outcome of one collection section. ``ok`` is the only value that means it was fully measured."""

ExposureStatus = Literal["ok", "partial_caller_scoped", "unknown", "forbidden", "not_run", "failed"]
"""Outcome of a permission-exposure check. ``unknown`` is a check whose outcome could not be
determined (COL-09): distinct from ``forbidden`` and from a measured zero."""

UNKNOWN_STATUSES: Final[frozenset[str]] = frozenset(
    {"not_run", "unavailable", "forbidden", "failed", "unknown"}
)
"""The "could not look" values of both status vocabularies (``unavailable`` occurs only in
``SectionStatus`` and ``unknown`` only in ``ExposureStatus``). Under any of them every
measurement the section governs is null or an empty list, never zero."""

TruncatedReason = Literal["cap", "time", "throttle", "resync"]
PathMode = Literal["full", "tokens", "hashed"]
ContributorsMode = Literal["email", "hashed"]
ColumnType = Literal[
    "text",
    "choice",
    "dateTime",
    "number",
    "boolean",
    "personOrGroup",
    "lookup",
    "term",
    "calculated",
    "other",
]
PatternKind = Literal[
    "year", "fiscal_year", "quarter", "month", "date", "numeric_id", "categorical"
]
LastActivitySource = Literal["file", "list", "page", "drive"]
OwnersSource = Literal["group_owners", "unavailable"]
SiteKind = Literal["group", "communication", "other"]


class SectionState(Contract):
    """Status of one collection section and, when it is not ``ok``, the reason code."""

    status: SectionStatus
    reason: ErrorCodeStr | None
