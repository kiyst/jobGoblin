import json
from pathlib import Path
from typing import Any

import pytest

from tests.contracts import transforms
from tests.contracts.loader import ContractRecordError, collect_all, load_parser_file
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
    # Keep the transform/target/boundary tokens consistent with the
    # copied record's own real fields (required since record_id must
    # match them); only the variant token needs to change for a
    # distinct, validly-shaped record_id.
    duplicate["record_id"] = duplicate["record_id"].replace("--variant-base", "--variant-second")
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
