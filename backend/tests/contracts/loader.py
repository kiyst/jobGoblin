"""Fail-closed JSON loader for the deterministic parser-contract harness
(Workflow v3.2 Slice 2). Rejects, with a specific `ContractRecordError`,
every one of the malformed-record categories named in the binding Slice
2 proposal and its clarifications: duplicate JSON keys and record IDs,
unknown/missing keys, empty collections, dangling references, invalid
types (including bool/float posing as int), invalid provenance/value
combinations, invalid targets/transform arguments, a transformed-input
mismatch, and collection cardinality (including designated-primary-
witness cardinality). Imports nothing from `app.normalization.*`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tests.contracts.schema import (
    BOUNDARIES,
    INPUT_FIELDS,
    OUTPUT_FIELD_TYPES,
    OUTPUT_FIELDS,
    PARSERS,
    SEMANTIC_FORMS,
    TRANSFORM_NAMES,
    TRANSFORM_PARAMETER_KEYS,
    CaseRecord,
    ContractRecordError,
    ExpectedField,
    Parser,
    Target,
    TransformSpec,
)
from tests.contracts.taxonomy import GUARD_INVENTORY, active_guards
from tests.contracts.transforms import apply_transform

_RECORD_ID_RE = re.compile(
    r"^(?P<base>[a-z0-9][a-z0-9_-]*)"
    r"--transform-(?P<transform>[a-z0-9_.]+)"
    r"--target-(?P<target>[a-z0-9_]+)"
    r"--boundary-(?P<boundary>[a-z0-9_]+)"
    r"--variant-(?P<variant>[a-z0-9_]+)$"
)

_RECORD_REQUIRED_KEYS = frozenset(
    {
        "record_id",
        "kind",
        "parser",
        "guard_ref",
        "target",
        "original_input",
        "transform",
        "expected_transformed_input",
        "expected_output",
        "rationale",
        "is_primary_witness",
    }
)
_TARGET_KEYS = frozenset({"input_field", "semantic_form", "boundary"})
_TRANSFORM_KEYS = frozenset({"name", "parameters"})
_EXPECTED_FIELD_KEYS = frozenset({"value", "provenance"})


def _no_duplicate_keys_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ContractRecordError(f"duplicate JSON key {key!r} in {pairs!r}")
        seen[key] = value
    return seen


def _parse_json_no_duplicates(text: str, *, context: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_no_duplicate_keys_hook)
    except json.JSONDecodeError as exc:
        raise ContractRecordError(f"{context}: invalid JSON: {exc}") from exc


def _require_dict(value: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractRecordError(f"{context}: expected an object, got {type(value).__name__}")
    return value


def _require_exact_keys(
    obj: dict[str, Any],
    required: frozenset[str],
    *,
    context: str,
    optional: frozenset[str] = frozenset(),
) -> None:
    actual = set(obj.keys())
    missing = required - actual
    unknown = actual - required - optional
    if missing:
        raise ContractRecordError(f"{context}: missing required key(s) {sorted(missing)}")
    if unknown:
        raise ContractRecordError(f"{context}: unknown key(s) {sorted(unknown)}")


def _require_str(obj: dict[str, Any], key: str, *, context: str) -> str:
    value = obj[key]
    if not isinstance(value, str) or not value:
        raise ContractRecordError(f"{context}: {key!r} must be a non-empty string, got {value!r}")
    return value


def _require_bool(obj: dict[str, Any], key: str, *, context: str) -> bool:
    value = obj[key]
    if not isinstance(value, bool):
        raise ContractRecordError(f"{context}: {key!r} must be a bool, got {type(value).__name__}")
    return value


def _load_target(obj: Any, parser: Parser, *, context: str) -> Target:
    target_obj = _require_dict(obj, context=f"{context}.target")
    _require_exact_keys(target_obj, _TARGET_KEYS, context=f"{context}.target")
    input_field = _require_str(target_obj, "input_field", context=f"{context}.target")
    semantic_form = _require_str(target_obj, "semantic_form", context=f"{context}.target")
    boundary = _require_str(target_obj, "boundary", context=f"{context}.target")
    if input_field not in INPUT_FIELDS[parser]:
        raise ContractRecordError(
            f"{context}.target.input_field: {input_field!r} is not valid for parser {parser!r} "
            f"(expected one of {sorted(INPUT_FIELDS[parser])})"
        )
    if semantic_form not in SEMANTIC_FORMS[parser]:
        raise ContractRecordError(
            f"{context}.target.semantic_form: {semantic_form!r} is not valid for parser "
            f"{parser!r} (expected one of {sorted(SEMANTIC_FORMS[parser])})"
        )
    if boundary not in BOUNDARIES[parser]:
        raise ContractRecordError(
            f"{context}.target.boundary: {boundary!r} is not valid for parser {parser!r} "
            f"(expected one of {sorted(BOUNDARIES[parser])})"
        )
    return Target(input_field=input_field, semantic_form=semantic_form, boundary=boundary)


def _load_transform(obj: Any, *, context: str) -> TransformSpec:
    transform_obj = _require_dict(obj, context=f"{context}.transform")
    _require_exact_keys(transform_obj, _TRANSFORM_KEYS, context=f"{context}.transform")
    name = transform_obj["name"]
    if not isinstance(name, str) or name not in TRANSFORM_NAMES:
        raise ContractRecordError(
            f"{context}.transform.name: {name!r} is not a recognized transform "
            f"(expected one of {sorted(TRANSFORM_NAMES)})"
        )
    parameters = transform_obj["parameters"]
    if not isinstance(parameters, dict):
        raise ContractRecordError(f"{context}.transform.parameters must be an object")
    _require_exact_keys(
        parameters,
        TRANSFORM_PARAMETER_KEYS[name],
        context=f"{context}.transform.parameters ({name})",
    )
    for key, value in parameters.items():
        if isinstance(value, bool):
            raise ContractRecordError(
                f"{context}.transform.parameters[{key!r}]: bool is never accepted as a "
                "transform parameter value"
            )
    return TransformSpec(name=name, parameters=dict(parameters))


def _require_input_dict(obj: Any, parser: Parser, *, context: str) -> dict[str, str | None]:
    input_obj = _require_dict(obj, context=context)
    _require_exact_keys(input_obj, INPUT_FIELDS[parser], context=context)
    result: dict[str, str | None] = {}
    for field, value in input_obj.items():
        if value is not None and not isinstance(value, str):
            raise ContractRecordError(
                f"{context}[{field!r}] must be a string or null, got {type(value).__name__}"
            )
        result[field] = value
    return result


def _load_expected_output(obj: Any, parser: Parser, *, context: str) -> dict[str, ExpectedField]:
    output_obj = _require_dict(obj, context=f"{context}.expected_output")
    _require_exact_keys(output_obj, OUTPUT_FIELDS[parser], context=f"{context}.expected_output")
    result: dict[str, ExpectedField] = {}
    for field, field_obj in output_obj.items():
        field_ctx = f"{context}.expected_output[{field!r}]"
        field_dict = _require_dict(field_obj, context=field_ctx)
        _require_exact_keys(field_dict, frozenset({"value", "provenance"}), context=field_ctx)
        value = field_dict["value"]
        provenance = field_dict["provenance"]
        if isinstance(value, bool):
            raise ContractRecordError(f"{field_ctx}.value: bool is never a valid expected value")
        expected_type = OUTPUT_FIELD_TYPES[parser][field]
        if value is not None and not isinstance(value, expected_type):
            raise ContractRecordError(
                f"{field_ctx}.value must be a {expected_type.__name__} or null for "
                f"parser {parser!r} field {field!r}, got {type(value).__name__}"
            )
        if not isinstance(provenance, str):
            raise ContractRecordError(f"{field_ctx}.provenance must be a string")
        try:
            result[field] = ExpectedField(value=value, provenance=provenance)
        except ContractRecordError as exc:
            raise ContractRecordError(f"{field_ctx}: {exc}") from exc
    return result


def _validate_record_id(record_id: str, parser: Parser, *, context: str) -> re.Match[str]:
    match = _RECORD_ID_RE.match(record_id)
    if match is None:
        raise ContractRecordError(
            f"{context}: record_id {record_id!r} does not match the required "
            "'<slug>--transform-<name>--target-<field>--boundary-<boundary>--variant-<n>' shape"
        )
    base_slug = match.group("base")
    if not base_slug.startswith(f"{parser}-"):
        raise ContractRecordError(
            f"{context}: record_id's slug {base_slug!r} does not start with the required "
            f"{parser!r} parser prefix ({parser}-...)"
        )
    return match


def _validate_record_id_kind_variant(
    record_id_match: re.Match[str], *, kind: str, transform_name: str, context: str
) -> None:
    """Base records are the designated primary-witness shape: identity
    transform, `variant-base`. A generated record must never reuse the
    `base` variant token -- that token is reserved so record_id alone
    (without opening the record) tells a reader which kind it is."""
    variant = record_id_match.group("variant")
    if kind == "base":
        if transform_name != "none":
            raise ContractRecordError(
                f"{context}: a base record must use transform 'none', got {transform_name!r}"
            )
        if variant != "base":
            raise ContractRecordError(
                f"{context}: a base record's record_id must use variant 'base', got {variant!r}"
            )
    else:  # generated
        if variant == "base":
            raise ContractRecordError(
                f"{context}: a generated record must not use variant 'base' -- that token is "
                "reserved for base records and a generated record must not masquerade as one"
            )


def _validate_record_id_matches_fields(
    record_id_match: re.Match[str],
    *,
    transform_name: str,
    target_input_field: str,
    target_boundary: str,
    context: str,
) -> None:
    """The record_id's embedded transform/target/boundary tokens are not
    just decoration -- they must actually describe the record's real
    fields, or record_id (used for audit/traceability and printed by
    the mutation-witness script) would not be trustworthy."""
    groups = record_id_match.groupdict()
    if groups["transform"] != transform_name:
        raise ContractRecordError(
            f"{context}: record_id declares transform {groups['transform']!r} but "
            f"transform.name is {transform_name!r}"
        )
    if groups["target"] != target_input_field:
        raise ContractRecordError(
            f"{context}: record_id declares target {groups['target']!r} but "
            f"target.input_field is {target_input_field!r}"
        )
    if groups["boundary"] != target_boundary:
        raise ContractRecordError(
            f"{context}: record_id declares boundary {groups['boundary']!r} but "
            f"target.boundary is {target_boundary!r}"
        )


def _validate_transformed_input(
    record_id: str,
    parser: Parser,
    target: Target,
    original_input: dict[str, str | None],
    transform: TransformSpec,
    expected_transformed_input: dict[str, str | None],
) -> None:
    for field in INPUT_FIELDS[parser]:
        original_value = original_input[field]
        expected_value = expected_transformed_input[field]
        if field == target.input_field:
            if original_value is None:
                raise ContractRecordError(
                    f"{record_id}: target.input_field {field!r} has a null original_input value"
                )
            try:
                computed = apply_transform(original_value, transform.name, transform.parameters)
            except ContractRecordError as exc:
                raise ContractRecordError(
                    f"{record_id}: transform application failed: {exc}"
                ) from exc
            if computed != expected_value:
                raise ContractRecordError(
                    f"{record_id}: transformed-input mismatch on field {field!r} -- "
                    f"applying transform {transform.name!r} to {original_value!r} produces "
                    f"{computed!r}, but expected_transformed_input declares {expected_value!r}"
                )
        else:
            if original_value != expected_value:
                raise ContractRecordError(
                    f"{record_id}: untouched field {field!r} differs between original_input "
                    f"({original_value!r}) and expected_transformed_input ({expected_value!r})"
                )


def _load_record(obj: Any, parser: Parser, *, index: int, file_context: str) -> CaseRecord:
    context = f"{file_context}[{index}]"
    record_obj = _require_dict(obj, context=context)
    _require_exact_keys(
        record_obj,
        _RECORD_REQUIRED_KEYS,
        context=context,
        optional=frozenset({"base_record_id", "historical_defect_ref"}),
    )

    record_id = _require_str(record_obj, "record_id", context=context)
    context = f"{file_context}[{index}] ({record_id})"
    record_id_match = _validate_record_id(record_id, parser, context=context)

    kind = record_obj["kind"]
    if kind not in ("base", "generated"):
        raise ContractRecordError(f"{context}: kind must be 'base' or 'generated', got {kind!r}")

    declared_parser = _require_str(record_obj, "parser", context=context)
    if declared_parser != parser:
        raise ContractRecordError(
            f"{context}: record declares parser {declared_parser!r} but was loaded from the "
            f"{parser!r} file"
        )

    guard_ref = _require_str(record_obj, "guard_ref", context=context)
    guard = GUARD_INVENTORY.get(guard_ref)
    if guard is None:
        raise ContractRecordError(
            f"{context}: guard_ref {guard_ref!r} is not in the guard inventory"
        )
    if guard.parser != parser:
        raise ContractRecordError(
            f"{context}: guard_ref {guard_ref!r} belongs to parser {guard.parser!r}, not {parser!r}"
        )
    if guard.status == "superseded":
        raise ContractRecordError(
            f"{context}: guard_ref {guard_ref!r} is superseded (by {guard.superseded_by!r}) -- "
            "a superseded guard must have no contract record of any kind, primary or otherwise"
        )

    target = _load_target(record_obj["target"], parser, context=context)
    original_input = _require_input_dict(
        record_obj["original_input"], parser, context=f"{context}.original_input"
    )
    transform = _load_transform(record_obj["transform"], context=context)
    _validate_record_id_matches_fields(
        record_id_match,
        transform_name=transform.name,
        target_input_field=target.input_field,
        target_boundary=target.boundary,
        context=context,
    )
    _validate_record_id_kind_variant(
        record_id_match, kind=kind, transform_name=transform.name, context=context
    )
    expected_transformed_input = _require_input_dict(
        record_obj["expected_transformed_input"],
        parser,
        context=f"{context}.expected_transformed_input",
    )
    expected_output = _load_expected_output(record_obj["expected_output"], parser, context=context)
    rationale = _require_str(record_obj, "rationale", context=context)
    is_primary_witness = _require_bool(record_obj, "is_primary_witness", context=context)

    base_record_id = record_obj.get("base_record_id")
    historical_defect_ref = record_obj.get("historical_defect_ref")

    if kind == "base":
        if "base_record_id" in record_obj:
            raise ContractRecordError(f"{context}: a base record must not declare base_record_id")
        if not isinstance(historical_defect_ref, str) or not historical_defect_ref:
            raise ContractRecordError(
                f"{context}: a base record requires a non-empty historical_defect_ref"
            )
        if historical_defect_ref != guard.historical_defect_ref:
            raise ContractRecordError(
                f"{context}: historical_defect_ref {historical_defect_ref!r} does not match "
                f"guard inventory entry {guard_ref!r}'s historical_defect_ref "
                f"{guard.historical_defect_ref!r}"
            )
    else:  # generated
        if "historical_defect_ref" in record_obj:
            raise ContractRecordError(
                f"{context}: a generated record must not declare its own historical_defect_ref "
                "(it inherits provenance from base_record_id)"
            )
        if not isinstance(base_record_id, str) or not base_record_id:
            raise ContractRecordError(
                f"{context}: a generated record requires a non-empty base_record_id"
            )
        if is_primary_witness:
            raise ContractRecordError(
                f"{context}: a generated record may never be a primary witness"
            )

    _validate_transformed_input(
        record_id, parser, target, original_input, transform, expected_transformed_input
    )

    return CaseRecord(
        record_id=record_id,
        kind=kind,
        parser=parser,
        guard_ref=guard_ref,
        target=target,
        original_input=original_input,
        transform=transform,
        expected_transformed_input=expected_transformed_input,
        expected_output=expected_output,
        rationale=rationale,
        is_primary_witness=is_primary_witness,
        base_record_id=base_record_id if kind == "generated" else None,
        historical_defect_ref=historical_defect_ref if kind == "base" else None,
    )


def load_parser_file(path: Path, parser: Parser) -> list[CaseRecord]:
    """Loads and fully validates one parser's record file in isolation
    (per-file checks only -- global uniqueness/cardinality is `collect_all`'s
    job, since it requires seeing all three files together)."""
    if parser not in PARSERS:
        raise ContractRecordError(f"unrecognized parser: {parser!r}")
    text = path.read_text(encoding="utf-8")
    data = _parse_json_no_duplicates(text, context=str(path))
    if not isinstance(data, dict):
        raise ContractRecordError(f"{path}: top-level JSON must be an object")
    _require_exact_keys(data, frozenset({"parser", "records"}), context=str(path))
    declared_parser = data["parser"]
    if declared_parser != parser:
        raise ContractRecordError(
            f"{path}: file declares parser {declared_parser!r}, expected {parser!r}"
        )
    records_raw = data["records"]
    if not isinstance(records_raw, list):
        raise ContractRecordError(f"{path}: 'records' must be an array")
    if not records_raw:
        raise ContractRecordError(f"{path}: 'records' must not be empty")

    records: list[CaseRecord] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(records_raw):
        record = _load_record(raw, parser, index=index, file_context=str(path))
        if record.record_id in seen_ids:
            raise ContractRecordError(f"{path}: duplicate record_id {record.record_id!r}")
        seen_ids.add(record.record_id)
        records.append(record)
    return records


def collect_all(paths: dict[Parser, Path]) -> dict[Parser, list[CaseRecord]]:
    """Loads all three parser files and enforces the cross-file, fail-
    closed invariants: global record_id uniqueness, every guard in the
    inventory covered by exactly one designated primary witness, and
    every generated record's base_record_id resolving to an actual
    record sharing its guard_ref."""
    missing = set(PARSERS) - set(paths)
    if missing:
        raise ContractRecordError(f"collect_all: missing required parser file(s) for {missing}")

    all_records: dict[Parser, list[CaseRecord]] = {}
    global_ids: dict[str, Parser] = {}
    for parser, path in paths.items():
        records = load_parser_file(path, parser)
        for record in records:
            if record.record_id in global_ids:
                raise ContractRecordError(
                    f"record_id {record.record_id!r} is not globally unique -- also present in "
                    f"the {global_ids[record.record_id]!r} file"
                )
            global_ids[record.record_id] = parser
        all_records[parser] = records

    by_id = {r.record_id: r for records in all_records.values() for r in records}

    for records in all_records.values():
        for record in records:
            if record.kind == "generated":
                base = by_id.get(record.base_record_id or "")
                if base is None:
                    raise ContractRecordError(
                        f"{record.record_id}: base_record_id {record.base_record_id!r} does "
                        "not resolve to any loaded record"
                    )
                if base.kind != "base":
                    raise ContractRecordError(
                        f"{record.record_id}: base_record_id {record.base_record_id!r} resolves "
                        f"to a {base.kind!r} record, not a base record -- generated records must "
                        "chain to an actual base record, never to another generated record"
                    )
                if base.parser != record.parser:
                    raise ContractRecordError(
                        f"{record.record_id}: base_record_id {record.base_record_id!r} belongs "
                        f"to parser {base.parser!r}, not {record.parser!r}"
                    )
                if base.guard_ref != record.guard_ref:
                    raise ContractRecordError(
                        f"{record.record_id}: guard_ref {record.guard_ref!r} does not match its "
                        f"base record's guard_ref {base.guard_ref!r}"
                    )
                if base.original_input != record.original_input:
                    raise ContractRecordError(
                        f"{record.record_id}: original_input {record.original_input!r} does not "
                        f"match its base record's original_input {base.original_input!r} -- a "
                        "generated record must vary only by its declared transform, not by "
                        "starting from different source text"
                    )
                if base.target != record.target:
                    raise ContractRecordError(
                        f"{record.record_id}: target {record.target!r} does not match its base "
                        f"record's target {base.target!r} -- a generated record must exercise "
                        "the same target context as its base"
                    )

    # Only active guards require exactly one designated primary witness.
    # A superseded guard is already blocked, at per-record load time,
    # from having any contract record at all (see `_load_record`), so it
    # is correctly excluded from this requirement rather than needing a
    # witness it cannot have.
    primary_witness_count: dict[str, int] = {ref: 0 for ref in active_guards()}
    for records in all_records.values():
        for record in records:
            if record.is_primary_witness:
                primary_witness_count[record.guard_ref] += 1

    zero_witness = [ref for ref, count in primary_witness_count.items() if count == 0]
    if zero_witness:
        raise ContractRecordError(
            f"the following active guard(s) have zero designated primary witnesses: "
            f"{sorted(zero_witness)}"
        )
    multi_witness = [ref for ref, count in primary_witness_count.items() if count > 1]
    if multi_witness:
        raise ContractRecordError(
            f"the following guard(s) have more than one designated primary witness: "
            f"{sorted(multi_witness)}"
        )

    return all_records
