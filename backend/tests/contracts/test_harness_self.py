import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.contract_mutation_witnesses import (
    WitnessError,
    _check_record_matches_registry_entry,
)
from tests.contracts import transforms
from tests.contracts.loader import ContractRecordError, collect_all, load_parser_file
from tests.contracts.mutation_registry import MUTATION_REGISTRY
from tests.contracts.schema import ExpectedField

# ---------------------------------------------------------------------------
# Transform unit tests -- hand-computed expectations, never derived by
# running a parser.
# ---------------------------------------------------------------------------


def test_ascii_recase_upper() -> None:
    assert transforms.ascii_recase("Austin, tx", "upper") == "AUSTIN, TX"


def test_ascii_recase_lower() -> None:
    assert transforms.ascii_recase("AUSTIN, TX", "lower") == "austin, tx"


def test_ascii_recase_mixed_alternates_by_letter_ordinal_only() -> None:
    # Letters only advance the alternation counter; "," and " " do not.
    # Letter sequence: A(0->upper) u(1->lower) s(2->upper) t(3->lower)
    # i(4->upper) n(5->lower) t(6->upper) x(7->lower).
    assert transforms.ascii_recase("Austin, tx", "mixed") == "AuStIn, Tx"


def test_ascii_recase_leaves_non_ascii_letters_untouched() -> None:
    assert transforms.ascii_recase("Austin, Wİ", "upper") == "AUSTIN, Wİ"


def test_ascii_recase_rejects_unknown_mode() -> None:
    with pytest.raises(ContractRecordError):
        transforms.ascii_recase("x", "sideways")


def test_insert_codepoint_at_position() -> None:
    assert transforms.insert_codepoint("Toronto, TX", " ", 11) == "Toronto, TX "


def test_insert_codepoint_rejects_multi_codepoint_string() -> None:
    with pytest.raises(ContractRecordError):
        transforms.insert_codepoint("abc", "xy", 1)


def test_insert_codepoint_rejects_out_of_range_position() -> None:
    with pytest.raises(ContractRecordError):
        transforms.insert_codepoint("abc", "x", 99)


def test_append_codepoints() -> None:
    assert transforms.append_codepoints("Remote, U.S", ".") == "Remote, U.S."


def test_remove_boundary() -> None:
    assert transforms.remove_boundary("up to $150,000", 2, 3) == "upto $150,000"


def test_remove_boundary_rejects_invalid_span() -> None:
    with pytest.raises(ContractRecordError):
        transforms.remove_boundary("abc", 2, 1)


def test_nfkc_fullwidth_substitute_round_trips_via_nfkc() -> None:
    import unicodedata

    result = transforms.nfkc_fullwidth_substitute("TX", 0, 2)
    assert result != "TX"
    assert unicodedata.normalize("NFKC", result) == "TX"


def test_apply_transform_none_requires_no_parameters() -> None:
    assert transforms.apply_transform("abc", "none", {}) == "abc"
    with pytest.raises(ContractRecordError):
        transforms.apply_transform("abc", "none", {"x": 1})


def test_apply_transform_rejects_unrecognized_name() -> None:
    with pytest.raises(ContractRecordError):
        transforms.apply_transform("abc", "not_a_real_transform", {})


def test_apply_transform_rejects_bool_posing_as_int_parameter() -> None:
    with pytest.raises(ContractRecordError):
        transforms.apply_transform("abc", "insert_codepoint", {"codepoint": "x", "position": True})


def test_apply_transform_rejects_float_posing_as_int_parameter() -> None:
    with pytest.raises(ContractRecordError):
        transforms.apply_transform("abc", "insert_codepoint", {"codepoint": "x", "position": 1.0})


# ---------------------------------------------------------------------------
# Schema invariant tests.
# ---------------------------------------------------------------------------


def test_expected_field_rejects_value_without_unavailable_provenance() -> None:
    with pytest.raises(ContractRecordError):
        ExpectedField(value=None, provenance="parsed_description")


def test_expected_field_rejects_unavailable_with_a_value() -> None:
    with pytest.raises(ContractRecordError):
        ExpectedField(value="TX", provenance="unavailable")


def test_expected_field_rejects_unrecognized_provenance() -> None:
    with pytest.raises(ContractRecordError):
        ExpectedField(value="TX", provenance="made_up_provenance")


def test_expected_field_accepts_a_valid_pair() -> None:
    ExpectedField(value="TX", provenance="parsed_description")
    ExpectedField(value=None, provenance="unavailable")


# ---------------------------------------------------------------------------
# Fail-closed loader tests -- one fault-injection case per validation
# category named in the binding Slice 2 proposal and its clarifications.
# ---------------------------------------------------------------------------

_VALID_LOCATION_RECORD: dict[str, Any] = {
    "record_id": "location-x--transform-none--target-location--boundary-whole_field--variant-base",
    "kind": "base",
    "parser": "location",
    "guard_ref": "location/g01-alias-trailing-period",
    "is_primary_witness": True,
    "historical_defect_ref": "88cdb2f/071d8dc finding 1",
    "target": {
        "input_field": "location",
        "semantic_form": "country_declaration",
        "boundary": "whole_field",
    },
    "original_input": {"location": "Remote, U.S."},
    "transform": {"name": "none", "parameters": {}},
    "expected_transformed_input": {"location": "Remote, U.S."},
    "expected_output": {
        "city": {"value": None, "provenance": "unavailable"},
        "state": {"value": None, "provenance": "unavailable"},
        "country": {"value": "United States", "provenance": "parsed_description"},
        "postal_code": {"value": None, "provenance": "unavailable"},
    },
    "rationale": "test fixture",
}


def _write_location_file(tmp_path: Path, records: list[dict[str, Any]]) -> Path:
    path = tmp_path / "location.json"
    path.write_text(json.dumps({"parser": "location", "records": records}), encoding="utf-8")
    return path


def test_loader_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "location.json"
    path.write_text('{"parser": "location", "records": [], "parser": "location"}', encoding="utf-8")
    with pytest.raises(ContractRecordError, match="duplicate JSON key"):
        load_parser_file(path, "location")


def test_loader_rejects_unknown_key(tmp_path: Path) -> None:
    record = dict(_VALID_LOCATION_RECORD, unknown_extra_field="x")
    with pytest.raises(ContractRecordError, match="unknown key"):
        load_parser_file(_write_location_file(tmp_path, [record]), "location")


def test_loader_rejects_missing_key(tmp_path: Path) -> None:
    record = dict(_VALID_LOCATION_RECORD)
    del record["rationale"]
    with pytest.raises(ContractRecordError, match="missing required key"):
        load_parser_file(_write_location_file(tmp_path, [record]), "location")


def test_loader_rejects_empty_records_array(tmp_path: Path) -> None:
    with pytest.raises(ContractRecordError, match="must not be empty"):
        load_parser_file(_write_location_file(tmp_path, []), "location")


_RECORDS_DIR = Path(__file__).resolve().parent / "records"


def test_loader_rejects_dangling_base_record_id(tmp_path: Path) -> None:
    generated = dict(_VALID_LOCATION_RECORD)
    generated["record_id"] = (
        "location-x--transform-none--target-location--boundary-whole_field--variant-2"
    )
    generated["kind"] = "generated"
    generated["is_primary_witness"] = False
    del generated["historical_defect_ref"]
    generated["base_record_id"] = (
        "does-not-exist--transform-none--target-location--boundary-whole_field--variant-base"
    )
    path = _write_location_file(tmp_path, [_VALID_LOCATION_RECORD, generated])
    with pytest.raises(ContractRecordError, match="does not resolve"):
        collect_all(
            {
                "location": path,
                "salary": _RECORDS_DIR / "salary.json",
                "experience": _RECORDS_DIR / "experience.json",
            }
        )


def test_loader_rejects_bool_posing_as_int_type(tmp_path: Path) -> None:
    record = dict(_VALID_LOCATION_RECORD)
    record["transform"] = {
        "name": "insert_codepoint",
        "parameters": {"codepoint": "x", "position": True},
    }
    with pytest.raises(ContractRecordError, match="bool"):
        load_parser_file(_write_location_file(tmp_path, [record]), "location")


def test_loader_rejects_invalid_provenance_value_combination(tmp_path: Path) -> None:
    record = json.loads(json.dumps(_VALID_LOCATION_RECORD))
    record["expected_output"]["country"] = {"value": None, "provenance": "parsed_description"}
    with pytest.raises(ContractRecordError):
        load_parser_file(_write_location_file(tmp_path, [record]), "location")


def test_loader_rejects_invalid_target_input_field(tmp_path: Path) -> None:
    record = json.loads(json.dumps(_VALID_LOCATION_RECORD))
    record["target"]["input_field"] = "not_a_real_field"
    with pytest.raises(ContractRecordError, match="input_field"):
        load_parser_file(_write_location_file(tmp_path, [record]), "location")


def test_loader_rejects_invalid_transform_argument(tmp_path: Path) -> None:
    record = json.loads(json.dumps(_VALID_LOCATION_RECORD))
    record["transform"] = {
        "name": "insert_codepoint",
        "parameters": {"codepoint": "x", "position": 999},
    }
    with pytest.raises(ContractRecordError):
        load_parser_file(_write_location_file(tmp_path, [record]), "location")


def test_loader_rejects_transformed_input_mismatch(tmp_path: Path) -> None:
    record = json.loads(json.dumps(_VALID_LOCATION_RECORD))
    record["expected_transformed_input"] = {"location": "Remote, U.S. (wrong)"}
    with pytest.raises(ContractRecordError, match="mismatch"):
        load_parser_file(_write_location_file(tmp_path, [record]), "location")


def test_loader_rejects_duplicate_record_id_within_a_file(tmp_path: Path) -> None:
    with pytest.raises(ContractRecordError, match="duplicate record_id"):
        load_parser_file(
            _write_location_file(tmp_path, [_VALID_LOCATION_RECORD, _VALID_LOCATION_RECORD]),
            "location",
        )


def test_loader_rejects_a_guard_that_belongs_to_a_different_parser(tmp_path: Path) -> None:
    record = dict(_VALID_LOCATION_RECORD)
    record["guard_ref"] = "salary/g01-covered-whitespace-class"
    with pytest.raises(ContractRecordError, match="belongs to parser"):
        load_parser_file(_write_location_file(tmp_path, [record]), "location")


def test_loader_rejects_any_record_referencing_a_superseded_guard(tmp_path: Path) -> None:
    record = dict(_VALID_LOCATION_RECORD)
    record["record_id"] = (
        "experience-x--transform-none--target-title--boundary-attribution_frame--variant-base"
    )
    record["parser"] = "experience"
    record["guard_ref"] = "experience/g07-reversed-label-anchor"
    record["target"] = {
        "input_field": "title",
        "semantic_form": "bare_phrase",
        "boundary": "attribution_frame",
    }
    record["original_input"] = {"title": "x", "description": None}
    record["expected_transformed_input"] = {"title": "x", "description": None}
    record["expected_output"] = {
        "minimum": {"value": None, "provenance": "unavailable"},
        "maximum": {"value": None, "provenance": "unavailable"},
    }
    path = tmp_path / "experience.json"
    path.write_text(json.dumps({"parser": "experience", "records": [record]}), encoding="utf-8")
    with pytest.raises(ContractRecordError, match="superseded"):
        load_parser_file(path, "experience")


def test_loader_rejects_zero_primary_witnesses_for_an_active_guard(tmp_path: Path) -> None:
    record = dict(_VALID_LOCATION_RECORD)
    record["is_primary_witness"] = False
    path = _write_location_file(tmp_path, [record])
    with pytest.raises(ContractRecordError, match="zero designated primary witnesses"):
        collect_all(
            {
                "location": path,
                "salary": _RECORDS_DIR / "salary.json",
                "experience": _RECORDS_DIR / "experience.json",
            }
        )


def test_loader_rejects_more_than_one_primary_witness_for_the_same_guard(tmp_path: Path) -> None:
    # Start from the real, fully-covering location.json (all 8 guards each
    # with exactly one primary witness) and add one extra primary witness
    # for an already-covered guard, isolating the multi-witness check from
    # the zero-witness check.
    real = json.loads((_RECORDS_DIR / "location.json").read_text(encoding="utf-8"))
    duplicate = dict(real["records"][0])
    # A base record's record_id must keep "--variant-base" (enforced by
    # the loader) -- vary the slug prefix instead for a distinct,
    # validly-shaped record_id, keeping transform/target/boundary
    # tokens consistent with the copied record's own real fields.
    duplicate["record_id"] = duplicate["record_id"].replace(
        "location-alias-trailing-period", "location-alias-trailing-period-duplicate"
    )
    real["records"].append(duplicate)
    path = tmp_path / "location.json"
    path.write_text(json.dumps(real), encoding="utf-8")
    with pytest.raises(ContractRecordError, match="more than one designated primary witness"):
        collect_all(
            {
                "location": path,
                "salary": _RECORDS_DIR / "salary.json",
                "experience": _RECORDS_DIR / "experience.json",
            }
        )


def test_record_id_target_token_must_match_the_records_own_input_field(tmp_path: Path) -> None:
    """A record's record_id embeds the target input field as one of its
    five tokens (Slice 2 binding decision 5); a Slice 2 hardening fix
    (found by adversarial review) requires that embedded token to
    actually match the record's real `target.input_field`, closing a
    gap where record_id was previously decorative rather than a
    trustworthy description of what the record exercises. One provable
    side effect: since no two parsers share an input-field name, a
    valid record from one parser can never collide, by record_id, with
    a valid record from a different parser -- collect_all's cross-file
    global-uniqueness map remains as defense in depth for a future
    parser that might reuse a field name, but cannot be exercised by
    any record valid under today's three parsers."""
    record = json.loads(json.dumps(_VALID_LOCATION_RECORD))
    record["record_id"] = record["record_id"].replace("target-location", "target-compensation_text")
    with pytest.raises(ContractRecordError, match="target.input_field is 'location'"):
        load_parser_file(_write_location_file(tmp_path, [record]), "location")


# ---------------------------------------------------------------------------
# Correction round (Sol re-review): genuinely parser/field-discriminated
# expected-output typing.
# ---------------------------------------------------------------------------


def test_loader_rejects_int_value_for_a_location_string_field(tmp_path: Path) -> None:
    record = json.loads(json.dumps(_VALID_LOCATION_RECORD))
    record["expected_output"]["country"] = {"value": 12345, "provenance": "parsed_description"}
    with pytest.raises(ContractRecordError, match="must be a str or null"):
        load_parser_file(_write_location_file(tmp_path, [record]), "location")


def test_loader_rejects_str_value_for_a_salary_integer_field(tmp_path: Path) -> None:
    records_dir = Path(__file__).resolve().parent / "records"
    record = json.loads((records_dir / "salary.json").read_text(encoding="utf-8"))["records"][0]
    record = json.loads(json.dumps(record))
    record["expected_output"]["minimum"] = {"value": "120000", "provenance": "parsed_description"}
    path = tmp_path / "salary.json"
    path.write_text(json.dumps({"parser": "salary", "records": [record]}), encoding="utf-8")
    with pytest.raises(ContractRecordError, match="must be a int or null"):
        load_parser_file(path, "salary")


def test_loader_rejects_int_value_for_a_salary_string_field(tmp_path: Path) -> None:
    records_dir = Path(__file__).resolve().parent / "records"
    record = json.loads((records_dir / "salary.json").read_text(encoding="utf-8"))["records"][0]
    record = json.loads(json.dumps(record))
    record["expected_output"]["currency"] = {"value": 1, "provenance": "parsed_description"}
    path = tmp_path / "salary.json"
    path.write_text(json.dumps({"parser": "salary", "records": [record]}), encoding="utf-8")
    with pytest.raises(ContractRecordError, match="must be a str or null"):
        load_parser_file(path, "salary")


def test_loader_rejects_str_value_for_an_experience_integer_field(tmp_path: Path) -> None:
    records_dir = Path(__file__).resolve().parent / "records"
    record = json.loads((records_dir / "experience.json").read_text(encoding="utf-8"))["records"][0]
    record = json.loads(json.dumps(record))
    record["expected_output"]["minimum"] = {"value": "5", "provenance": "parsed_description"}
    path = tmp_path / "experience.json"
    path.write_text(json.dumps({"parser": "experience", "records": [record]}), encoding="utf-8")
    with pytest.raises(ContractRecordError, match="must be a int or null"):
        load_parser_file(path, "experience")


def test_loader_still_rejects_bool_for_a_numeric_field_despite_field_discrimination(
    tmp_path: Path,
) -> None:
    """bool is a subclass of int in Python -- confirms the field-specific
    int check does not accidentally let a bool slip through now that the
    generic str|int check has been replaced with per-field typing."""
    records_dir = Path(__file__).resolve().parent / "records"
    record = json.loads((records_dir / "salary.json").read_text(encoding="utf-8"))["records"][0]
    record = json.loads(json.dumps(record))
    record["expected_output"]["minimum"] = {"value": True, "provenance": "parsed_description"}
    path = tmp_path / "salary.json"
    path.write_text(json.dumps({"parser": "salary", "records": [record]}), encoding="utf-8")
    with pytest.raises(ContractRecordError, match="bool is never a valid expected value"):
        load_parser_file(path, "salary")


# ---------------------------------------------------------------------------
# Correction round (Sol re-review): record traceability.
# ---------------------------------------------------------------------------


def test_loader_rejects_record_id_whose_parser_prefix_does_not_match_parser(
    tmp_path: Path,
) -> None:
    record = json.loads(json.dumps(_VALID_LOCATION_RECORD))
    record["record_id"] = record["record_id"].replace("location-x", "salary-x")
    with pytest.raises(ContractRecordError, match="does not start with the required"):
        load_parser_file(_write_location_file(tmp_path, [record]), "location")


def test_loader_rejects_base_record_with_non_none_transform(tmp_path: Path) -> None:
    record = json.loads(json.dumps(_VALID_LOCATION_RECORD))
    record["record_id"] = record["record_id"].replace("transform-none", "transform-ascii_recase")
    record["transform"] = {"name": "ascii_recase", "parameters": {"mode": "upper"}}
    record["expected_transformed_input"] = {"location": "REMOTE, U.S."}
    with pytest.raises(ContractRecordError, match="a base record must use transform 'none'"):
        load_parser_file(_write_location_file(tmp_path, [record]), "location")


def test_loader_rejects_base_record_with_non_base_variant(tmp_path: Path) -> None:
    record = json.loads(json.dumps(_VALID_LOCATION_RECORD))
    record["record_id"] = record["record_id"].replace("variant-base", "variant-first")
    with pytest.raises(
        ContractRecordError, match="a base record's record_id must use variant 'base'"
    ):
        load_parser_file(_write_location_file(tmp_path, [record]), "location")


def test_loader_rejects_generated_record_masquerading_with_variant_base(tmp_path: Path) -> None:
    generated = json.loads(json.dumps(_VALID_LOCATION_RECORD))
    generated["kind"] = "generated"
    generated["is_primary_witness"] = False
    del generated["historical_defect_ref"]
    generated["base_record_id"] = _VALID_LOCATION_RECORD["record_id"]
    # record_id still ends in "--variant-base", which is reserved for
    # actual base records.
    with pytest.raises(ContractRecordError, match="must not use variant 'base'"):
        load_parser_file(
            _write_location_file(tmp_path, [_VALID_LOCATION_RECORD, generated]), "location"
        )


def test_loader_rejects_base_record_whose_historical_defect_ref_disagrees_with_the_guard_inventory(
    tmp_path: Path,
) -> None:
    record = json.loads(json.dumps(_VALID_LOCATION_RECORD))
    record["historical_defect_ref"] = "this does not match the taxonomy entry"
    with pytest.raises(ContractRecordError, match="does not match guard inventory entry"):
        load_parser_file(_write_location_file(tmp_path, [record]), "location")


_RECORDS_DIR_FOR_TRACEABILITY = Path(__file__).resolve().parent / "records"


def _real_location_base_record() -> dict[str, Any]:
    data = json.loads((_RECORDS_DIR_FOR_TRACEABILITY / "location.json").read_text(encoding="utf-8"))
    return dict(data["records"][0])  # location/g01's real, committed base record


def _valid_generated_from(base: dict[str, Any], *, variant: str) -> dict[str, Any]:
    generated: dict[str, Any] = json.loads(json.dumps(base))
    generated["record_id"] = generated["record_id"].replace(
        "--variant-base", f"--variant-{variant}"
    )
    generated["kind"] = "generated"
    generated["is_primary_witness"] = False
    del generated["historical_defect_ref"]
    generated["base_record_id"] = base["record_id"]
    return generated


def test_loader_rejects_generated_record_whose_base_is_itself_generated(tmp_path: Path) -> None:
    base = _real_location_base_record()
    first_generated = _valid_generated_from(base, variant="second")
    second_generated = _valid_generated_from(base, variant="third")
    second_generated["base_record_id"] = first_generated["record_id"]
    path = _write_location_file(tmp_path, [base, first_generated, second_generated])
    with pytest.raises(ContractRecordError, match="not a base record"):
        collect_all(
            {
                "location": path,
                "salary": _RECORDS_DIR_FOR_TRACEABILITY / "salary.json",
                "experience": _RECORDS_DIR_FOR_TRACEABILITY / "experience.json",
            }
        )


def test_loader_rejects_generated_record_with_different_original_input_than_its_base(
    tmp_path: Path,
) -> None:
    base = _real_location_base_record()
    generated = _valid_generated_from(base, variant="second")
    generated["original_input"] = {"location": "Somewhere else entirely"}
    generated["expected_transformed_input"] = {"location": "Somewhere else entirely"}
    path = _write_location_file(tmp_path, [base, generated])
    with pytest.raises(
        ContractRecordError, match="does not match its base record's original_input"
    ):
        collect_all(
            {
                "location": path,
                "salary": _RECORDS_DIR_FOR_TRACEABILITY / "salary.json",
                "experience": _RECORDS_DIR_FOR_TRACEABILITY / "experience.json",
            }
        )


def test_loader_rejects_generated_record_with_different_target_than_its_base(
    tmp_path: Path,
) -> None:
    base = _real_location_base_record()
    generated = _valid_generated_from(base, variant="second")
    generated["target"] = {
        "input_field": "location",
        "semantic_form": "country_declaration",
        "boundary": "whole_field",
    }
    # Keep the record_id's own boundary token internally consistent with
    # this record's (differing) target, so the per-record consistency
    # check passes and the cross-record base/generated mismatch below is
    # what's actually isolated.
    generated["record_id"] = generated["record_id"].replace(
        "boundary-country_token", "boundary-whole_field"
    )
    path = _write_location_file(tmp_path, [base, generated])
    with pytest.raises(ContractRecordError, match="does not match its base record's target"):
        collect_all(
            {
                "location": path,
                "salary": _RECORDS_DIR_FOR_TRACEABILITY / "salary.json",
                "experience": _RECORDS_DIR_FOR_TRACEABILITY / "experience.json",
            }
        )


# ---------------------------------------------------------------------------
# Correction round (Sol re-review): contract_mutation_witnesses.py must
# load records through the fail-closed loader and verify, before running
# any witness, that the registry entry and the loaded record genuinely
# agree with each other.
# ---------------------------------------------------------------------------


def _real_location_g01_record():  # type: ignore[no-untyped-def]
    all_records = collect_all(
        {
            "location": _RECORDS_DIR_FOR_TRACEABILITY / "location.json",
            "salary": _RECORDS_DIR_FOR_TRACEABILITY / "salary.json",
            "experience": _RECORDS_DIR_FOR_TRACEABILITY / "experience.json",
        }
    )
    (record,) = [
        r for r in all_records["location"] if r.guard_ref == "location/g01-alias-trailing-period"
    ]
    return record


def test_witness_script_rejects_a_missing_record() -> None:
    entry = MUTATION_REGISTRY["location/g01-alias-trailing-period"]
    with pytest.raises(WitnessError, match="does not exist in the loaded"):
        _check_record_matches_registry_entry(entry, None)


def test_witness_script_rejects_a_non_primary_witness_record() -> None:
    entry = MUTATION_REGISTRY["location/g01-alias-trailing-period"]
    record = dataclasses.replace(_real_location_g01_record(), is_primary_witness=False)
    with pytest.raises(WitnessError, match="not marked as a designated primary witness"):
        _check_record_matches_registry_entry(entry, record)


def test_witness_script_rejects_a_guard_ref_mismatch() -> None:
    entry = MUTATION_REGISTRY["location/g01-alias-trailing-period"]
    record = dataclasses.replace(
        _real_location_g01_record(), guard_ref="location/g02-state-zip-provenance"
    )
    with pytest.raises(WitnessError, match="belongs to guard"):
        _check_record_matches_registry_entry(entry, record)


def test_witness_script_rejects_a_parser_mismatch() -> None:
    entry = MUTATION_REGISTRY["location/g01-alias-trailing-period"]
    record = dataclasses.replace(_real_location_g01_record(), parser="salary")
    with pytest.raises(WitnessError, match="does not match the registry entry's parser"):
        _check_record_matches_registry_entry(entry, record)


def test_witness_script_rejects_registry_input_disagreeing_with_record_input() -> None:
    entry = MUTATION_REGISTRY["location/g01-alias-trailing-period"]
    record = dataclasses.replace(
        _real_location_g01_record(),
        expected_transformed_input={"location": "a different string entirely"},
    )
    with pytest.raises(WitnessError, match="does not exactly equal"):
        _check_record_matches_registry_entry(entry, record)


def test_witness_script_accepts_the_real_matching_record() -> None:
    entry = MUTATION_REGISTRY["location/g01-alias-trailing-period"]
    record = _real_location_g01_record()
    assert _check_record_matches_registry_entry(entry, record) is record
