"""Provisional v1.0 fact-sheet contract (D-05, D-06).

The shape may be refined in place, with the schema and goldens regenerated in the same
commit, until the Phase 6 freeze. After the freeze, adding a key is a minor version and
renaming or removing one is a major version. No field has a default (D-05): a collector
that omits a key fails validation instead of shipping a hole.

Unknown is never zero. Every section carries a status; when that status is one of
``UNKNOWN_STATUSES`` (could not look) every measurement the section governs is null or an
empty list, and model validation rejects a fact sheet that puts a number there. Downstream
scoring can therefore always tell "nothing there" from "could not look".
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, model_validator

from recover_assess.core.models.common import (
    UNKNOWN_STATUSES,
    ColumnType,
    Contract,
    ContributorsMode,
    ErrorCodeStr,
    ExposureStatus,
    LastActivitySource,
    NonNegInt,
    OwnersSource,
    PathMode,
    PatternKind,
    SectionState,
    Share,
    SiteKind,
    TruncatedReason,
    UtcDatetime,
    round3,
)

__all__ = [
    "AgeBuckets",
    "CategoryShares",
    "CollectLimits",
    "Column",
    "Contributor",
    "Coverage",
    "Depth",
    "ExposureTotal",
    "ExtensionShare",
    "FactSheet",
    "FolderPattern",
    "GraphStats",
    "InputRecord",
    "LargestFile",
    "Library",
    "LibraryExposure",
    "ListInfo",
    "Owner",
    "Ownership",
    "Privacy",
    "SampleCandidate",
    "Sections",
    "SiteInfo",
    "Subsite",
    "WarningEntry",
]

Seconds = Annotated[float, Field(ge=0), AfterValidator(round3)]
PositiveInt = Annotated[int, Field(ge=1)]


def _is_unknown(state: SectionState) -> bool:
    return state.status in UNKNOWN_STATUSES


class Privacy(Contract):
    """How paths and contributor identities were recorded."""

    path_mode: PathMode
    contributors: ContributorsMode


class CollectLimits(Contract):
    """The caps and sample sizes this run was collected under."""

    max_items_per_library: PositiveInt
    fill_rate_sample: PositiveInt
    permission_checks_per_library: PositiveInt
    max_file_mb: PositiveInt
    sample_size: NonNegInt


class Sections(Contract):
    """Per-section collection status; the source of truth for "measured" versus "unknown"."""

    site: SectionState
    libraries: SectionState
    lists: SectionState
    exposure: SectionState
    ownership: SectionState
    sample_candidates: SectionState
    sam: SectionState


class InputRecord(Contract):
    """The input row this fact sheet was collected for."""

    raw: str
    normalized: str | None
    label: str | None
    business_unit: str | None
    owner_hint: str | None
    priority: str | None
    extra: dict[str, str]


class Subsite(Contract):
    title: str | None
    url: str


class SiteInfo(Contract):
    id: str
    url: str
    title: str | None
    created: UtcDatetime | None
    last_modified: UtcDatetime | None
    kind: SiteKind | None
    subsites: list[Subsite]


class Depth(Contract):
    """Folder depth: deepest level and the 50th and 90th percentiles."""

    max: NonNegInt
    p50: NonNegInt
    p90: NonNegInt


class CategoryShares(Contract):
    """Share of files per content category; each share is 0..1."""

    word: Share
    pdf: Share
    excel: Share
    powerpoint: Share
    email: Share
    image: Share
    text: Share
    archive: Share
    other: Share


class ExtensionShare(Contract):
    ext: str
    share: Share


class AgeBuckets(Contract):
    """Share of files by age of last modification."""

    lt_1y: Share
    y1_3: Share
    gt_3y: Share


class LargestFile(Contract):
    path: str
    bytes: NonNegInt


class Coverage(Contract):
    """How much of the library the enumeration actually counted."""

    counted_items: NonNegInt | None
    counted_bytes: NonNegInt | None
    root_bytes: NonNegInt | None
    ratio: Share | None


class Column(Contract):
    name: str
    display_name: str | None
    type: ColumnType
    required: bool
    custom: bool
    choices: list[str]
    term_set_id: str | None
    fill_rate: Share | None


class FolderPattern(Contract):
    """A naming pattern recognised at one folder depth."""

    depth: Annotated[int, Field(ge=1, le=4)]
    kind: PatternKind
    share: Share
    distinct: NonNegInt
    examples: Annotated[list[str], Field(max_length=10)]


class _ExposureCounts(Contract):
    """A status plus the eight exposure counts.

    A count is null whenever the status is one of ``UNKNOWN_STATUSES``: a permission check
    that was not run, was forbidden, failed or could not be determined never reads as zero.
    """

    status: ExposureStatus
    checked: NonNegInt | None
    items_with_anyone_link: NonNegInt | None
    items_with_org_link: NonNegInt | None
    items_with_people_link: NonNegInt | None
    items_with_direct_grants: NonNegInt | None
    items_with_guest_or_external: NonNegInt | None
    items_with_eeeu: NonNegInt | None
    items_differing_from_root: NonNegInt | None

    def _counts(self) -> list[int | None]:
        return [
            self.checked,
            self.items_with_anyone_link,
            self.items_with_org_link,
            self.items_with_people_link,
            self.items_with_direct_grants,
            self.items_with_guest_or_external,
            self.items_with_eeeu,
            self.items_differing_from_root,
        ]

    def has_any_count(self) -> bool:
        return any(count is not None for count in self._counts())

    @model_validator(mode="after")
    def _unknown_status_has_no_counts(self) -> Self:
        if self.status in UNKNOWN_STATUSES and self.has_any_count():
            msg = "exposure: a status that means 'could not look' requires every count to be null"
            raise ValueError(msg)
        return self


class LibraryExposure(_ExposureCounts):
    unique_permissions_method: Literal["compare_to_root"] | None


class ExposureTotal(_ExposureCounts):
    caller_is_owner: bool | None

    @model_validator(mode="after")
    def _unknown_status_has_no_caller_flag(self) -> Self:
        if self.status in UNKNOWN_STATUSES and self.caller_is_owner is not None:
            msg = (
                "exposure_total: a status that means 'could not look' requires caller_is_owner null"
            )
            raise ValueError(msg)
        return self


class Library(Contract):
    """One document library (or pages library) and the evidence collected from it."""

    id: str
    drive_id: str | None
    name: str
    kind: Literal["library", "pages"]
    files: NonNegInt | None
    folders: NonNegInt | None
    bytes: NonNegInt | None
    truncated: bool | None
    truncated_reason: TruncatedReason | None
    coverage: Coverage | None
    path_unresolved: NonNegInt | None
    depth: Depth | None
    categories: CategoryShares | None
    top_extensions: list[ExtensionShare]
    age: AgeBuckets | None
    created_by_year: dict[str, NonNegInt]
    last_activity: UtcDatetime | None
    last_activity_sources: list[LastActivitySource]
    largest_files: list[LargestFile]
    duplicate_rate: Share | None
    hash_coverage: Share | None
    columns: list[Column]
    mean_fill_rate: Share | None
    fill_rate_method: Literal["first_n"] | None
    fill_rate_sample: NonNegInt | None
    content_types: list[str]
    default_content_types_only: bool | None
    folder_patterns: list[FolderPattern]
    exposure: LibraryExposure

    @model_validator(mode="after")
    def _truncated_iff_reason(self) -> Self:
        if (self.truncated is True) != (self.truncated_reason is not None):
            msg = "library: truncated must be true if and only if truncated_reason is set"
            raise ValueError(msg)
        return self


class ListInfo(Contract):
    id: str
    name: str
    kind: Literal["list"]
    items: NonNegInt | None
    truncated: bool | None
    columns: list[Column]
    mean_fill_rate: Share | None
    fill_rate_method: Literal["first_n"] | None
    fill_rate_sample: NonNegInt | None
    last_activity: UtcDatetime | None


class Owner(Contract):
    id: str
    display_name: str | None
    mail: str | None


class Contributor(Contract):
    id: str
    files_modified_365d: NonNegInt
    last: date | None


class Ownership(Contract):
    owners: list[Owner]
    owners_source: OwnersSource
    active_contributors_90d: NonNegInt | None
    top_contributors: list[Contributor]
    owner_hint_matched: bool | None


class SampleCandidate(Contract):
    drive_id: str
    item_id: str
    path: str
    ext: str
    bytes: NonNegInt
    modified: date


class GraphStats(Contract):
    """Counters for the Graph traffic of one run, in the order of the spec example."""

    requests: NonNegInt
    batches: NonNegInt
    throttled: NonNegInt
    retries: NonNegInt
    seconds: Seconds


class WarningEntry(Contract):
    """One non-fatal condition. Named to avoid shadowing the builtin ``Warning``."""

    code: ErrorCodeStr
    detail: str | None


class FactSheet(Contract):
    """The fact sheet for one site: the contract every later stage reads.

    Provisional until the Phase 6 freeze (D-06). Unknown is never zero: when a section's
    status is in ``UNKNOWN_STATUSES`` (not_run, unavailable, forbidden, failed, unknown) the
    data it governs is null or an empty list. A measured zero is only ever recorded under a
    status that says the section was measured.
    """

    schema_version: Literal["1.0"]
    tool_version: str
    run_id: str
    collected_at: UtcDatetime
    status: Literal["complete", "partial", "failed"]
    privacy: Privacy
    collect_limits: CollectLimits
    sections: Sections
    input: InputRecord
    site: SiteInfo | None
    libraries: list[Library]
    lists: list[ListInfo]
    exposure_total: ExposureTotal
    ownership: Ownership
    sample_candidates: list[SampleCandidate]
    sam: dict[str, str] | None
    graph_stats: GraphStats
    warnings: list[WarningEntry]

    @model_validator(mode="after")
    def _unknown_is_never_zero(self) -> Self:
        sections = self.sections
        self._check_site(sections.site)
        if _is_unknown(sections.libraries) and self.libraries:
            msg = "sections.libraries: not measured, so libraries must be empty"
            raise ValueError(msg)
        if _is_unknown(sections.lists) and self.lists:
            msg = "sections.lists: not measured, so lists must be empty"
            raise ValueError(msg)
        self._check_exposure(sections.exposure)
        self._check_ownership(sections.ownership)
        if _is_unknown(sections.sample_candidates) and self.sample_candidates:
            msg = "sections.sample_candidates: not measured, so sample_candidates must be empty"
            raise ValueError(msg)
        if _is_unknown(sections.sam) and self.sam is not None:
            msg = "sections.sam: not measured, so sam must be null"
            raise ValueError(msg)
        return self

    def _check_site(self, state: SectionState) -> None:
        if _is_unknown(state) and self.site is not None:
            msg = "sections.site: not measured, so site must be null"
            raise ValueError(msg)
        if self.site is None and not _is_unknown(state):
            msg = "sections.site: site is null but the section status says it was measured"
            raise ValueError(msg)

    def _check_exposure(self, state: SectionState) -> None:
        if not _is_unknown(state):
            return
        total = self.exposure_total
        if total.has_any_count() or total.caller_is_owner is not None:
            msg = "sections.exposure: not measured, so exposure_total must hold no numbers"
            raise ValueError(msg)
        if any(lib.exposure.status not in UNKNOWN_STATUSES for lib in self.libraries):
            msg = "sections.exposure: not measured, so no library may report measured exposure"
            raise ValueError(msg)

    def _check_ownership(self, state: SectionState) -> None:
        if not _is_unknown(state):
            return
        ownership = self.ownership
        if (
            ownership.active_contributors_90d is not None
            or ownership.owner_hint_matched is not None
            or ownership.owners
            or ownership.top_contributors
        ):
            msg = "sections.ownership: not measured, so ownership must be null or empty"
            raise ValueError(msg)
