"""Full provisional v1.0 fact-sheet contract: vocabulary and the unknown-vs-zero invariant.

FND-04 (every key required, null where allowed) and FND-05 (status, coverage and unknown
vocabulary; unknown evidence is never recorded as a measured zero). Every FactSheet here is a
complete document built by the helpers below; an envelope-only sheet is never constructed.
Values are synthetic: contoso hosts, repeated-digit GUIDs, no real names or tokens.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from recover_assess.core.models.common import (
    UNKNOWN_STATUSES,
    SectionState,
    Share,
)
from recover_assess.core.models.fact_sheet import (
    FactSheet,
    Library,
    LibraryExposure,
)

SECTION_NAMES = (
    "site",
    "libraries",
    "lists",
    "exposure",
    "ownership",
    "sample_candidates",
    "sam",
)
FACT_SHEET_ORDER = (
    "schema_version",
    "tool_version",
    "run_id",
    "collected_at",
    "status",
    "privacy",
    "collect_limits",
    "sections",
    "input",
    "site",
    "libraries",
    "lists",
    "exposure_total",
    "ownership",
    "sample_candidates",
    "sam",
    "graph_stats",
    "warnings",
)
COUNT_FIELDS = (
    "checked",
    "items_with_anyone_link",
    "items_with_org_link",
    "items_with_people_link",
    "items_with_direct_grants",
    "items_with_guest_or_external",
    "items_with_eeeu",
    "items_differing_from_root",
)


def _counts(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "checked": 25,
        "items_with_anyone_link": 0,
        "items_with_org_link": 2,
        "items_with_people_link": 3,
        "items_with_direct_grants": 1,
        "items_with_guest_or_external": 0,
        "items_with_eeeu": 0,
        "items_differing_from_root": 4,
    }
    values.update(overrides)
    return values


def _null_counts() -> dict[str, Any]:
    return dict.fromkeys(COUNT_FIELDS)


def _library_exposure(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "status": "ok",
        **_counts(),
        "unique_permissions_method": "compare_to_root",
    }
    values.update(overrides)
    return values


def _column(name: str, column_type: str) -> dict[str, Any]:
    return {
        "name": name,
        "display_name": name,
        "type": column_type,
        "required": False,
        "custom": True,
        "choices": [],
        "term_set_id": None,
        "fill_rate": 0.75,
    }


def _library(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "id": "22222222-2222-2222-2222-222222222222",
        "drive_id": "33333333-3333-3333-3333-333333333333",
        "name": "Shared Documents",
        "kind": "library",
        "files": 120,
        "folders": 14,
        "bytes": 52428800,
        "truncated": False,
        "truncated_reason": None,
        "coverage": {
            "counted_items": 134,
            "counted_bytes": 52428800,
            "root_bytes": 52428800,
            "ratio": 1.0,
        },
        "path_unresolved": 0,
        "depth": {"max": 4, "p50": 2, "p90": 3},
        "categories": {
            "word": 0.4,
            "pdf": 0.2,
            "excel": 0.15,
            "powerpoint": 0.1,
            "email": 0.05,
            "image": 0.04,
            "text": 0.03,
            "archive": 0.01,
            "other": 0.02,
        },
        "top_extensions": [{"ext": "docx", "share": 0.4}],
        "age": {"lt_1y": 0.5, "y1_3": 0.3, "gt_3y": 0.2},
        "created_by_year": {"2023": 40, "2024": 80},
        "last_activity": "2026-01-02T03:04:05Z",
        "last_activity_sources": ["file"],
        "largest_files": [{"path": "Reports/Summary.docx", "bytes": 2097152}],
        "duplicate_rate": 0.0125,
        "hash_coverage": 0.9,
        "columns": [_column("Region", "choice"), _column("Reviewer", "personOrGroup")],
        "mean_fill_rate": 0.75,
        "fill_rate_method": "first_n",
        "fill_rate_sample": 100,
        "content_types": ["Document"],
        "default_content_types_only": True,
        "folder_patterns": [
            {"depth": 1, "kind": "year", "share": 0.5, "distinct": 3, "examples": ["2023", "2024"]}
        ],
        "exposure": _library_exposure(),
    }
    values.update(overrides)
    return values


def _ok_section() -> dict[str, Any]:
    return {"status": "ok", "reason": None}


def _full_document() -> dict[str, Any]:
    """A complete, internally consistent fact sheet in which every section was measured."""
    return {
        "schema_version": "1.0",
        "tool_version": "0.1.0",
        "run_id": "run-demo",
        "collected_at": "2026-01-02T03:04:05Z",
        "status": "complete",
        "privacy": {"path_mode": "full", "contributors": "email"},
        "collect_limits": {
            "max_items_per_library": 50000,
            "fill_rate_sample": 500,
            "permission_checks_per_library": 200,
            "max_file_mb": 10,
            "sample_size": 15,
        },
        "sections": dict.fromkeys(SECTION_NAMES, _ok_section()),
        "input": {
            "raw": "https://contoso.sharepoint.com/sites/example",
            "normalized": "https://contoso.sharepoint.com/sites/example",
            "label": "Contoso Team Site",
            "business_unit": "Operations",
            "owner_hint": None,
            "priority": None,
            "extra": {},
        },
        "site": {
            "id": "11111111-1111-1111-1111-111111111111",
            "url": "https://contoso.sharepoint.com/sites/example",
            "title": "Contoso Team Site",
            "created": "2024-03-04T05:06:07Z",
            "last_modified": "2026-01-01T00:00:00Z",
            "kind": "group",
            "subsites": [],
        },
        "libraries": [_library()],
        "lists": [
            {
                "id": "44444444-4444-4444-4444-444444444444",
                "name": "Change Log",
                "kind": "list",
                "items": 42,
                "truncated": False,
                "columns": [_column("Owner", "personOrGroup")],
                "mean_fill_rate": 0.8,
                "fill_rate_method": "first_n",
                "fill_rate_sample": 42,
                "last_activity": "2025-12-31T00:00:00Z",
            }
        ],
        "exposure_total": {
            "status": "ok",
            **_counts(checked=25),
            "caller_is_owner": False,
        },
        "ownership": {
            "owners": [
                {
                    "id": "55555555-5555-5555-5555-555555555555",
                    "display_name": None,
                    "mail": "owner@example.com",
                }
            ],
            "owners_source": "group_owners",
            "active_contributors_90d": 3,
            "top_contributors": [
                {"id": "contributor@example.com", "files_modified_365d": 12, "last": "2025-12-30"}
            ],
            "owner_hint_matched": None,
        },
        "sample_candidates": [
            {
                "drive_id": "33333333-3333-3333-3333-333333333333",
                "item_id": "66666666-6666-6666-6666-666666666666",
                "path": "Reports/Summary.docx",
                "ext": "docx",
                "bytes": 2097152,
                "modified": "2025-12-30",
            }
        ],
        "sam": {"slug": "example"},
        "graph_stats": {
            "requests": 40,
            "batches": 2,
            "throttled": 0,
            "retries": 0,
            "seconds": 3.5,
        },
        "warnings": [],
    }


def _not_run_document() -> dict[str, Any]:
    """Every section not run: site null, empty lists, null measurements, sam null."""
    document = _full_document()
    not_run = {"status": "not_run", "reason": None}
    document["status"] = "partial"
    document["sections"] = dict.fromkeys(SECTION_NAMES, not_run)
    document["input"] = {
        "raw": "https://contoso.sharepoint.com/sites/example",
        "normalized": None,
        "label": None,
        "business_unit": None,
        "owner_hint": None,
        "priority": None,
        "extra": {},
    }
    document["site"] = None
    document["libraries"] = []
    document["lists"] = []
    document["exposure_total"] = {
        "status": "not_run",
        **_null_counts(),
        "caller_is_owner": None,
    }
    document["ownership"] = {
        "owners": [],
        "owners_source": "unavailable",
        "active_contributors_90d": None,
        "top_contributors": [],
        "owner_hint_matched": None,
    }
    document["sample_candidates"] = []
    document["sam"] = None
    document["graph_stats"] = {
        "requests": 0,
        "batches": 0,
        "throttled": 0,
        "retries": 0,
        "seconds": 0.0,
    }
    return document


def _sheet(document: dict[str, Any]) -> FactSheet:
    return FactSheet.model_validate(document)


def _rejects(document: dict[str, Any], *, naming: str) -> None:
    with pytest.raises(ValidationError) as caught:
        _sheet(document)
    assert naming in str(caught.value)


class TestBaselines:
    def test_full_document_validates(self) -> None:
        sheet = _sheet(_full_document())
        assert sheet.sections.libraries.status == "ok"
        assert len(sheet.libraries) == 1

    def test_not_run_document_validates(self) -> None:
        sheet = _sheet(_not_run_document())
        assert sheet.site is None
        assert sheet.sam is None
        assert sheet.libraries == []

    def test_field_order_matches_the_contract(self) -> None:
        assert tuple(FactSheet.model_fields) == FACT_SHEET_ORDER

    def test_full_document_round_trips_through_the_model(self) -> None:
        document = _full_document()
        assert _sheet(document).model_dump(mode="json") == document

    def test_no_published_model_field_has_a_default(self) -> None:
        seen: set[type] = set()

        def walk(model: type[Any]) -> None:
            if model in seen:
                return
            seen.add(model)
            for name, field in model.model_fields.items():
                assert field.is_required(), f"{model.__name__}.{name} has a default"

        for model in (FactSheet, Library, LibraryExposure, SectionState):
            walk(model)

    @pytest.mark.parametrize("missing", FACT_SHEET_ORDER)
    def test_missing_top_level_key_is_rejected(self, missing: str) -> None:
        document = _full_document()
        del document[missing]
        with pytest.raises(ValidationError):
            _sheet(document)


class TestSectionState:
    @pytest.mark.parametrize("reason", [None, "throttled_out", "graph_error_403"])
    def test_reason_accepts_codes_and_null(self, reason: str | None) -> None:
        assert SectionState(status="failed", reason=reason).reason == reason

    @pytest.mark.parametrize("reason", ["oops", "graph_error_99", ""])
    def test_reason_rejects_free_text(self, reason: str) -> None:
        with pytest.raises(ValidationError):
            SectionState(status="failed", reason=reason)

    def test_status_vocabulary_is_closed(self) -> None:
        with pytest.raises(ValidationError):
            SectionState.model_validate({"status": "done", "reason": None})
        for status in (
            "ok",
            "partial",
            "truncated",
            "not_run",
            "unavailable",
            "forbidden",
            "failed",
        ):
            assert SectionState(status=status, reason=None).status == status

    def test_unknown_statuses_are_the_could_not_look_values(self) -> None:
        assert (
            frozenset({"not_run", "unavailable", "forbidden", "failed", "unknown"})
            == UNKNOWN_STATUSES
        )

    def test_exposure_status_vocabulary(self) -> None:
        exposure = _library_exposure(status="partial_caller_scoped")
        assert LibraryExposure.model_validate(exposure).status == "partial_caller_scoped"
        with pytest.raises(ValidationError):
            LibraryExposure.model_validate(_library_exposure(status="unavailable"))


class TestSiteSection:
    def test_not_run_with_a_site_object_is_rejected(self) -> None:
        document = _full_document()
        document["sections"]["site"] = {"status": "not_run", "reason": None}
        _rejects(document, naming="sections.site")

    def test_site_null_with_ok_status_is_rejected(self) -> None:
        document = _full_document()
        document["site"] = None
        _rejects(document, naming="sections.site")

    @pytest.mark.parametrize("status", ["partial", "truncated"])
    def test_partial_statuses_keep_the_site_object(self, status: str) -> None:
        document = _full_document()
        document["sections"]["site"] = {"status": status, "reason": None}
        assert _sheet(document).site is not None


class TestLibrariesAndListsSections:
    def test_forbidden_with_libraries_is_rejected(self) -> None:
        document = _full_document()
        document["sections"]["libraries"] = {"status": "forbidden", "reason": "graph_error_403"}
        _rejects(document, naming="sections.libraries")

    def test_forbidden_with_empty_libraries_is_accepted(self) -> None:
        document = _full_document()
        document["sections"]["libraries"] = {"status": "forbidden", "reason": "graph_error_403"}
        document["libraries"] = []
        assert _sheet(document).libraries == []

    @pytest.mark.parametrize("status", ["not_run", "unavailable", "failed"])
    def test_every_unknown_status_forbids_libraries(self, status: str) -> None:
        document = _full_document()
        document["sections"]["libraries"] = {"status": status, "reason": None}
        _rejects(document, naming="sections.libraries")

    def test_unknown_lists_section_forbids_lists(self) -> None:
        document = _full_document()
        document["sections"]["lists"] = {"status": "failed", "reason": "timeout"}
        _rejects(document, naming="sections.lists")

    def test_ok_with_an_empty_list_is_a_measured_none(self) -> None:
        document = _full_document()
        document["lists"] = []
        assert _sheet(document).lists == []


class TestExposure:
    def test_forbidden_with_checked_zero_is_rejected(self) -> None:
        document = _full_document()
        document["exposure_total"] = {
            "status": "forbidden",
            **_null_counts(),
            "caller_is_owner": None,
        }
        document["exposure_total"]["checked"] = 0
        _rejects(document, naming="exposure")

    def test_forbidden_with_all_counts_null_is_accepted(self) -> None:
        document = _full_document()
        document["sections"]["exposure"] = {"status": "forbidden", "reason": "graph_error_403"}
        document["exposure_total"] = {
            "status": "forbidden",
            **_null_counts(),
            "caller_is_owner": None,
        }
        document["libraries"][0]["exposure"] = _library_exposure(
            status="forbidden", **_null_counts(), unique_permissions_method=None
        )
        assert _sheet(document).exposure_total.checked is None

    def test_ok_with_checked_zero_is_a_measured_zero(self) -> None:
        document = _full_document()
        document["exposure_total"] = {
            "status": "ok",
            **_counts(
                checked=0,
                items_with_org_link=0,
                items_with_people_link=0,
                items_with_direct_grants=0,
                items_differing_from_root=0,
            ),
            "caller_is_owner": True,
        }
        assert _sheet(document).exposure_total.checked == 0

    def test_unknown_with_checked_zero_is_rejected(self) -> None:
        document = _full_document()
        document["exposure_total"] = {
            "status": "unknown",
            **_null_counts(),
            "caller_is_owner": None,
        }
        document["exposure_total"]["checked"] = 0
        _rejects(document, naming="exposure")

    def test_unknown_with_all_counts_null_is_accepted(self) -> None:
        document = _full_document()
        document["exposure_total"] = {
            "status": "unknown",
            **_null_counts(),
            "caller_is_owner": None,
        }
        assert _sheet(document).exposure_total.status == "unknown"

    def test_library_exposure_unknown_with_eeeu_zero_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LibraryExposure.model_validate(
                _library_exposure(status="unknown", **{**_null_counts(), "items_with_eeeu": 0})
            )

    @pytest.mark.parametrize("status", ["not_run", "forbidden", "failed", "unknown"])
    def test_library_exposure_unknown_statuses_require_null_counts(self, status: str) -> None:
        nulls = LibraryExposure.model_validate(
            _library_exposure(status=status, **_null_counts(), unique_permissions_method=None)
        )
        assert nulls.checked is None
        with pytest.raises(ValidationError):
            LibraryExposure.model_validate(
                _library_exposure(status=status, items_with_anyone_link=3)
            )

    def test_library_exposure_not_run_with_anyone_link_is_rejected(self) -> None:
        document = _full_document()
        document["libraries"][0]["exposure"] = _library_exposure(status="not_run", **_null_counts())
        document["libraries"][0]["exposure"]["items_with_anyone_link"] = 3
        _rejects(document, naming="exposure")

    def test_unknown_exposure_section_forbids_numeric_totals(self) -> None:
        document = _full_document()
        document["sections"]["exposure"] = {"status": "not_run", "reason": None}
        _rejects(document, naming="sections.exposure")

    def test_unknown_exposure_section_forbids_measured_library_exposure(self) -> None:
        document = _full_document()
        document["sections"]["exposure"] = {"status": "not_run", "reason": None}
        document["exposure_total"] = {
            "status": "not_run",
            **_null_counts(),
            "caller_is_owner": None,
        }
        _rejects(document, naming="sections.exposure")

    def test_unknown_exposure_section_forbids_caller_is_owner(self) -> None:
        document = _not_run_document()
        document["exposure_total"]["status"] = "ok"
        document["exposure_total"]["caller_is_owner"] = False
        _rejects(document, naming="sections.exposure")


class TestOwnership:
    def test_unavailable_with_contributors_zero_is_rejected(self) -> None:
        document = _full_document()
        document["sections"]["ownership"] = {
            "status": "unavailable",
            "reason": "owners_unavailable",
        }
        document["ownership"] = {
            "owners": [],
            "owners_source": "unavailable",
            "active_contributors_90d": 0,
            "top_contributors": [],
            "owner_hint_matched": None,
        }
        _rejects(document, naming="sections.ownership")

    def test_unavailable_with_null_and_empty_values_is_accepted(self) -> None:
        document = _full_document()
        document["sections"]["ownership"] = {
            "status": "unavailable",
            "reason": "owners_unavailable",
        }
        document["ownership"] = {
            "owners": [],
            "owners_source": "unavailable",
            "active_contributors_90d": None,
            "top_contributors": [],
            "owner_hint_matched": None,
        }
        assert _sheet(document).ownership.active_contributors_90d is None

    def test_unavailable_with_owners_listed_is_rejected(self) -> None:
        document = _full_document()
        document["sections"]["ownership"] = {"status": "unavailable", "reason": None}
        document["ownership"]["active_contributors_90d"] = None
        document["ownership"]["owner_hint_matched"] = None
        document["ownership"]["top_contributors"] = []
        _rejects(document, naming="sections.ownership")

    def test_unavailable_with_owner_hint_matched_is_rejected(self) -> None:
        document = _not_run_document()
        document["ownership"]["owner_hint_matched"] = False
        _rejects(document, naming="sections.ownership")


class TestSampleCandidatesAndSam:
    def test_not_run_with_candidates_is_rejected(self) -> None:
        document = _full_document()
        document["sections"]["sample_candidates"] = {"status": "not_run", "reason": None}
        _rejects(document, naming="sections.sample_candidates")

    def test_not_run_with_empty_sam_object_is_rejected(self) -> None:
        document = _not_run_document()
        document["sam"] = {}
        _rejects(document, naming="sections.sam")

    def test_not_run_with_null_sam_is_accepted(self) -> None:
        assert _sheet(_not_run_document()).sam is None


class TestTruncation:
    def test_truncated_true_without_reason_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Library.model_validate(_library(truncated=True, truncated_reason=None))

    def test_reason_without_truncated_true_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Library.model_validate(_library(truncated=False, truncated_reason="cap"))

    def test_reason_with_unknown_truncated_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Library.model_validate(_library(truncated=None, truncated_reason="cap"))

    @pytest.mark.parametrize("reason", ["cap", "time", "throttle", "resync"])
    def test_truncated_true_with_reason_is_accepted(self, reason: str) -> None:
        library = Library.model_validate(_library(truncated=True, truncated_reason=reason))
        assert library.truncated_reason == reason

    def test_unknown_reason_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Library.model_validate(_library(truncated=True, truncated_reason="because"))

    def test_untruncated_library_validates(self) -> None:
        assert Library.model_validate(_library()).truncated is False


class TestScalarTypes:
    def test_share_rounds_to_four_places(self) -> None:
        assert TypeAdapter(Share).validate_python(0.123456) == 0.1235

    def test_library_shares_are_rounded(self) -> None:
        library = Library.model_validate(_library(duplicate_rate=0.123456))
        assert library.duplicate_rate == 0.1235

    def test_share_above_one_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Library.model_validate(_library(duplicate_rate=1.2))

    def test_offset_datetime_serialises_in_utc_with_z(self) -> None:
        document = _full_document()
        local = datetime(2026, 1, 2, 13, 4, 5, tzinfo=timezone(timedelta(hours=10)))
        document["collected_at"] = local
        dumped = _sheet(document).model_dump(mode="json")
        assert dumped["collected_at"] == "2026-01-02T03:04:05Z"
        assert datetime.fromisoformat(dumped["collected_at"]) == datetime(
            2026, 1, 2, 3, 4, 5, tzinfo=UTC
        )

    def test_folder_pattern_depth_is_bounded(self) -> None:
        pattern = {"depth": 5, "kind": "year", "share": 0.5, "distinct": 3, "examples": []}
        with pytest.raises(ValidationError):
            Library.model_validate(_library(folder_patterns=[pattern]))

    def test_folder_pattern_examples_are_capped_at_ten(self) -> None:
        pattern = {
            "depth": 1,
            "kind": "categorical",
            "share": 0.5,
            "distinct": 11,
            "examples": [str(n) for n in range(11)],
        }
        with pytest.raises(ValidationError):
            Library.model_validate(_library(folder_patterns=[pattern]))

    def test_collect_limits_must_be_positive(self) -> None:
        document = _full_document()
        document["collect_limits"]["max_items_per_library"] = 0
        with pytest.raises(ValidationError):
            _sheet(document)


class TestErrorMessages:
    def test_message_names_the_section_but_never_the_value(self) -> None:
        document = _full_document()
        document["sections"]["libraries"] = {"status": "forbidden", "reason": None}
        document["libraries"][0]["files"] = 7391
        with pytest.raises(ValidationError) as caught:
            _sheet(document)
        text = str(caught.value)
        assert "sections.libraries" in text
        assert "7391" not in text

    def test_exposure_message_never_echoes_the_count(self) -> None:
        with pytest.raises(ValidationError) as caught:
            LibraryExposure.model_validate(
                _library_exposure(
                    status="not_run", **{**_null_counts(), "items_with_anyone_link": 7391}
                )
            )
        assert "7391" not in str(caught.value)

    def test_validation_errors_hide_submitted_input(self) -> None:
        document = copy.deepcopy(_full_document())
        document["input"]["raw"] = 12345
        with pytest.raises(ValidationError) as caught:
            _sheet(document)
        assert "12345" not in str(caught.value)
