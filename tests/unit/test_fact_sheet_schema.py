"""Fact-sheet contract (FND-04, FND-05, D-05, D-06): models, registry, generator and drift.

Every FactSheet in this module is built through ``_envelope_fact_sheet``, which starts from
the all-not-run fixture (the shape Phase 2 starts from) so no test constructs a sheet that is
missing a required v1.0 field. Values are synthetic: the run id is a plain label and no
email-, token- or tenant-host-shaped literal appears outside the contoso-style fixtures.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError

from recover_assess.core.models import fact_sheet as fact_sheet_module
from recover_assess.core.models.common import Contract, Share
from recover_assess.core.models.fact_sheet import FactSheet, GraphStats, WarningEntry
from recover_assess.core.models.registry import (
    PUBLISHED,
    SCHEMA_DIALECT,
    build_schema,
    render_schema,
    schema_path,
)
from tests.support.repo_scan import scan_text

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "scripts" / "gen_schemas.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "fact_sheet"
EXAMPLE_COMPLETE = FIXTURES / "example_complete.json"
EXAMPLE_NOT_RUN = FIXTURES / "example_not_run.json"

TOP_LEVEL_KEYS = (
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
ENVELOPE_KEYS = TOP_LEVEL_KEYS


def _load_fixture(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def _envelope_fact_sheet(**overrides: Any) -> FactSheet:
    """Build a FactSheet from the all-not-run fixture; ``overrides`` replace top-level keys."""
    values = _load_fixture(EXAMPLE_NOT_RUN)
    values.update(overrides)
    return FactSheet.model_validate(values)


def _envelope_document(**overrides: Any) -> dict[str, Any]:
    return _envelope_fact_sheet(**overrides).model_dump(mode="json")


class TestEnvelopeModel:
    def test_full_envelope_validates(self) -> None:
        sheet = _envelope_fact_sheet(status="complete")
        assert sheet.schema_version == "1.0"
        assert sheet.status == "complete"

    @pytest.mark.parametrize("missing", ENVELOPE_KEYS)
    def test_missing_envelope_key_fails_loudly(self, missing: str) -> None:
        document = _envelope_document()
        del document[missing]
        with pytest.raises(ValidationError):
            FactSheet.model_validate(document)

    def test_unknown_extra_key_is_rejected(self) -> None:
        document = _envelope_document()
        document["surprise"] = 1
        with pytest.raises(ValidationError):
            FactSheet.model_validate(document)

    def test_instances_are_frozen(self) -> None:
        sheet = _envelope_fact_sheet()
        with pytest.raises(ValidationError):
            sheet.run_id = "other"  # type: ignore[misc]

    def test_published_models_carry_no_field_defaults(self) -> None:
        models = [
            value
            for value in vars(fact_sheet_module).values()
            if isinstance(value, type) and issubclass(value, Contract) and value is not Contract
        ]
        assert len(models) >= 20
        for model in models:
            for name, field in model.model_fields.items():
                assert field.is_required(), f"{model.__name__}.{name} has a default"

    def test_schema_version_is_pinned_to_1_0(self) -> None:
        with pytest.raises(ValidationError):
            _envelope_fact_sheet(schema_version="2.0")

    def test_status_is_a_closed_set(self) -> None:
        with pytest.raises(ValidationError):
            _envelope_fact_sheet(status="done")


class TestCollectedAt:
    def test_offset_input_is_converted_to_utc_with_trailing_z(self) -> None:
        local = datetime(2026, 1, 2, 13, 4, 5, tzinfo=timezone(timedelta(hours=10)))
        document = _envelope_document(collected_at=local)
        assert document["collected_at"] == "2026-01-02T03:04:05Z"

    def test_utc_input_keeps_trailing_z(self) -> None:
        document = _envelope_document()
        assert document["collected_at"] == "2026-01-02T03:04:05Z"

    def test_naive_datetime_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _envelope_fact_sheet(collected_at=datetime(2026, 1, 2, 3, 4, 5))  # noqa: DTZ001


class TestWarningEntry:
    @pytest.mark.parametrize("code", ["graph_error_404", "throttled_out", "not_found"])
    def test_known_codes_validate(self, code: str) -> None:
        assert WarningEntry(code=code, detail=None).code == code

    @pytest.mark.parametrize("code", ["bogus_code", "graph_error_99", "throttled_out\n", ""])
    def test_unknown_codes_are_rejected(self, code: str) -> None:
        with pytest.raises(ValidationError):
            WarningEntry(code=code, detail=None)

    def test_detail_is_nullable_but_required(self) -> None:
        assert WarningEntry(code="timeout", detail="slow library").detail == "slow library"
        with pytest.raises(ValidationError):
            WarningEntry.model_validate({"code": "timeout"})


class TestGraphStats:
    def test_seconds_is_rounded_to_three_places(self) -> None:
        stats = GraphStats(requests=1, batches=0, throttled=0, retries=0, seconds=12.3456)
        assert stats.model_dump(mode="json")["seconds"] == 12.346

    def test_dump_key_order_matches_the_spec_example(self) -> None:
        stats = GraphStats(requests=1, batches=2, throttled=3, retries=4, seconds=0.5)
        assert list(stats.model_dump(mode="json")) == [
            "requests",
            "batches",
            "throttled",
            "retries",
            "seconds",
        ]

    def test_negative_counters_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GraphStats(requests=-1, batches=0, throttled=0, retries=0, seconds=0.0)
        with pytest.raises(ValidationError):
            GraphStats(requests=0, batches=0, throttled=0, retries=0, seconds=-0.1)


class TestShare:
    def test_share_rounds_to_four_places(self) -> None:
        assert TypeAdapter(Share).validate_python(0.123456) == 0.1235

    @pytest.mark.parametrize("value", [1.2, -0.1])
    def test_share_outside_unit_interval_is_rejected(self, value: float) -> None:
        with pytest.raises(ValidationError):
            TypeAdapter(Share).validate_python(value)


class TestRegistry:
    def test_fact_sheet_is_published(self) -> None:
        assert PUBLISHED["fact_sheet"] is FactSheet

    def test_first_key_is_the_dialect(self) -> None:
        schema = build_schema("fact_sheet")
        assert next(iter(schema)) == "$schema"
        assert schema["$schema"] == SCHEMA_DIALECT

    def test_schema_path_layout(self, tmp_path: Path) -> None:
        expected = tmp_path / "schemas" / "fact_sheet.schema.json"
        assert schema_path(tmp_path, "fact_sheet") == expected

    def test_rendering_twice_is_byte_identical(self) -> None:
        first = render_schema("fact_sheet")
        second = render_schema("fact_sheet")
        assert first == second
        assert first.endswith("}\n")
        assert not first.endswith("\n\n")
        assert "\r" not in first

    def test_property_order_follows_model_field_order(self) -> None:
        schema = build_schema("fact_sheet")
        assert list(schema["properties"]) == list(ENVELOPE_KEYS)
        assert list(schema["$defs"]["GraphStats"]["properties"]) == [
            "requests",
            "batches",
            "throttled",
            "retries",
            "seconds",
        ]


def _objects_with_properties(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if "properties" in node:
            found.append(node)
        for value in node.values():
            found.extend(_objects_with_properties(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_objects_with_properties(value))
    return found


class TestSchemaStructure:
    def test_every_object_requires_all_properties_and_forbids_extras(self) -> None:
        objects = _objects_with_properties(build_schema("fact_sheet"))
        assert len(objects) >= 20
        for obj in objects:
            assert obj["additionalProperties"] is False
            assert list(obj["required"]) == list(obj["properties"])

    def test_generated_schema_is_a_valid_schema(self) -> None:
        Draft202012Validator.check_schema(build_schema("fact_sheet"))


class TestDrift:
    def _checked_in_text(self) -> str:
        return schema_path(REPO_ROOT, "fact_sheet").read_text(encoding="utf-8")

    def test_checked_in_schema_equals_generated_as_parsed_json(self) -> None:
        assert json.loads(self._checked_in_text()) == build_schema("fact_sheet")

    def test_crlf_only_difference_is_not_drift(self) -> None:
        crlf = self._checked_in_text().replace("\n", "\r\n")
        assert crlf != self._checked_in_text()
        assert json.loads(crlf) == build_schema("fact_sheet")

    def test_a_single_changed_value_is_drift(self) -> None:
        mutated = copy.deepcopy(json.loads(self._checked_in_text()))
        mutated["$defs"]["GraphStats"]["properties"]["requests"]["type"] = "string"
        assert mutated != build_schema("fact_sheet")

    def test_a_single_removed_key_is_drift(self) -> None:
        mutated = copy.deepcopy(json.loads(self._checked_in_text()))
        del mutated["title"]
        assert mutated != build_schema("fact_sheet")


def _run_generator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GENERATOR), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


class TestGeneratorCheck:
    def test_check_passes_on_the_committed_tree(self) -> None:
        result = _run_generator("--check")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OK fact_sheet" in result.stdout
        assert "DRIFT" not in result.stdout

    def test_check_reports_drift_for_a_mutated_schema(self, tmp_path: Path) -> None:
        mutated = build_schema("fact_sheet")
        mutated["$defs"]["GraphStats"]["properties"]["requests"]["type"] = "string"
        target = schema_path(tmp_path, "fact_sheet")
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps(mutated, indent=2) + "\n", encoding="utf-8")
        result = _run_generator("--check", "--root", str(tmp_path))
        assert result.returncode == 1
        assert "DRIFT fact_sheet" in result.stdout

    def test_check_reports_drift_for_a_missing_schema(self, tmp_path: Path) -> None:
        result = _run_generator("--check", "--root", str(tmp_path))
        assert result.returncode == 1
        assert "DRIFT fact_sheet" in result.stdout

    def test_check_never_writes(self, tmp_path: Path) -> None:
        _run_generator("--check", "--root", str(tmp_path))
        assert not schema_path(tmp_path, "fact_sheet").exists()

    def test_generation_writes_lf_text_that_passes_check(self, tmp_path: Path) -> None:
        written = _run_generator("--root", str(tmp_path))
        assert written.returncode == 0, written.stdout + written.stderr
        raw = schema_path(tmp_path, "fact_sheet").read_bytes()
        assert b"\r" not in raw
        assert raw.decode("utf-8") == render_schema("fact_sheet")
        assert _run_generator("--check", "--root", str(tmp_path)).returncode == 0


class TestSchemaValidatesDocuments:
    def _validator(self) -> Draft202012Validator:
        return Draft202012Validator(build_schema("fact_sheet"))

    def test_zero_stats_document_validates(self) -> None:
        sheet = _envelope_fact_sheet(
            graph_stats=GraphStats(requests=0, batches=0, throttled=0, retries=0, seconds=0.0),
            warnings=[],
        )
        assert list(self._validator().iter_errors(sheet.model_dump(mode="json"))) == []

    @pytest.mark.parametrize("missing", ENVELOPE_KEYS)
    def test_removing_any_top_level_key_fails_validation(self, missing: str) -> None:
        document = _envelope_document()
        del document[missing]
        assert not self._validator().is_valid(document)

    def test_extra_top_level_key_fails_validation(self) -> None:
        document = _envelope_document()
        document["surprise"] = 1
        assert not self._validator().is_valid(document)

    def test_warning_code_pattern_is_enforced_by_the_schema(self) -> None:
        good = _envelope_document(warnings=[WarningEntry(code="graph_error_404", detail=None)])
        assert self._validator().is_valid(good)
        bad = copy.deepcopy(good)
        bad["warnings"][0]["code"] = "bogus_code"
        assert not self._validator().is_valid(bad)


class TestFnd05Vocabulary:
    def _defs(self) -> dict[str, Any]:
        defs: dict[str, Any] = build_schema("fact_sheet")["$defs"]
        return defs

    def test_top_level_properties_include_privacy_limits_and_sections(self) -> None:
        properties = build_schema("fact_sheet")["properties"]
        assert {"privacy", "collect_limits", "sections"} <= set(properties)

    def test_library_carries_coverage_and_truncation_evidence(self) -> None:
        properties = self._defs()["Library"]["properties"]
        for key in (
            "coverage",
            "truncated_reason",
            "path_unresolved",
            "hash_coverage",
            "last_activity_sources",
        ):
            assert key in properties

    def test_ownership_names_its_owner_source(self) -> None:
        assert "owners_source" in self._defs()["Ownership"]["properties"]

    def test_section_state_has_status_and_reason(self) -> None:
        assert list(self._defs()["SectionState"]["properties"]) == ["status", "reason"]

    def test_section_status_vocabulary_in_the_schema(self) -> None:
        status = self._defs()["SectionState"]["properties"]["status"]
        assert set(status["enum"]) == {
            "ok",
            "partial",
            "truncated",
            "not_run",
            "unavailable",
            "forbidden",
            "failed",
        }

    def test_exposure_status_vocabulary_in_the_schema(self) -> None:
        status = self._defs()["LibraryExposure"]["properties"]["status"]
        assert set(status["enum"]) == {
            "ok",
            "partial_caller_scoped",
            "unknown",
            "forbidden",
            "not_run",
            "failed",
        }

    def test_fact_sheet_description_states_unknown_is_never_zero(self) -> None:
        description = build_schema("fact_sheet")["description"]
        assert "Unknown is never zero" in description
        assert "Phase 6" in description


class TestFixtures:
    def test_complete_example_validates_against_the_model(self) -> None:
        sheet = FactSheet.model_validate_json(EXAMPLE_COMPLETE.read_text(encoding="utf-8"))
        assert sheet.sections.libraries.status == "ok"
        assert len(sheet.libraries) == 1
        assert len(sheet.lists) == 1

    def test_complete_example_validates_against_the_schema(self) -> None:
        validator = Draft202012Validator(build_schema("fact_sheet"))
        assert list(validator.iter_errors(_load_fixture(EXAMPLE_COMPLETE))) == []

    def test_complete_example_round_trips_exactly(self) -> None:
        text = EXAMPLE_COMPLETE.read_text(encoding="utf-8")
        parsed = FactSheet.model_validate_json(text)
        assert parsed.model_dump(mode="json") == json.loads(text)
        assert (
            json.dumps(parsed.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n" == text
        )

    def test_not_run_example_validates_against_model_and_schema(self) -> None:
        document = _load_fixture(EXAMPLE_NOT_RUN)
        sheet = FactSheet.model_validate(document)
        assert sheet.site is None
        assert sheet.sam is None
        assert sheet.libraries == []
        assert sheet.lists == []
        assert sheet.exposure_total.checked is None
        assert {state.status for state in vars_of_sections(sheet)} == {"not_run"}
        assert Draft202012Validator(build_schema("fact_sheet")).is_valid(document)

    @pytest.mark.parametrize("missing", TOP_LEVEL_KEYS)
    def test_not_run_example_loses_validity_when_any_key_is_removed(self, missing: str) -> None:
        document = _load_fixture(EXAMPLE_NOT_RUN)
        del document[missing]
        assert not Draft202012Validator(build_schema("fact_sheet")).is_valid(document)

    @pytest.mark.parametrize("path", [EXAMPLE_COMPLETE, EXAMPLE_NOT_RUN], ids=lambda p: p.name)
    def test_fixture_text_passes_the_client_data_scan(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        assert scan_text(text, path=path.name) == []

    @pytest.mark.parametrize("path", [EXAMPLE_COMPLETE, EXAMPLE_NOT_RUN], ids=lambda p: p.name)
    def test_fixtures_are_lf_with_one_trailing_newline(self, path: Path) -> None:
        raw = path.read_bytes()
        assert b"\r" not in raw
        assert raw.endswith(b"}\n")
        assert not raw.endswith(b"\n\n")

    def test_envelope_helper_builds_on_the_not_run_fixture(self) -> None:
        assert _envelope_fact_sheet().model_dump(mode="json") == _load_fixture(EXAMPLE_NOT_RUN)


def vars_of_sections(sheet: FactSheet) -> list[Any]:
    return [getattr(sheet.sections, name) for name in type(sheet.sections).model_fields]


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_schemas_under_test", GENERATOR)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestGeneratorUsesTheAtomicWriter:
    def test_generate_writes_through_atomic_write_text(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        generator = _load_generator()
        calls: list[tuple[Path, str]] = []

        def record(path: Path, text: str) -> None:
            calls.append((path, text))

        monkeypatch.setattr(generator, "atomic_write_text", record)
        assert generator.generate(tmp_path) == 0
        assert [path for path, _ in calls] == [schema_path(tmp_path, name) for name in PUBLISHED]
        assert [text for _, text in calls] == [render_schema(name) for name in PUBLISHED]

    def test_generated_file_leaves_no_temp_files_behind(self, tmp_path: Path) -> None:
        assert _run_generator("--root", str(tmp_path)).returncode == 0
        leftovers = [p.name for p in (tmp_path / "schemas").iterdir() if ".tmp-" in p.name]
        assert leftovers == []
