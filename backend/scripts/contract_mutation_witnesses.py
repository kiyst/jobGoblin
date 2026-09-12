"""Replays every committed mutation-registry selector (Workflow v3.2
Slice 2) and asserts both the documented erroneous output (under the
mutant) and the documented restored output (matching the real contract
record's own `expected_output`). Standalone script, never collected by
pytest -- run explicitly, once at Slice 2 acceptance and again whenever
a covered guard's contract case, adapter, or target source changes.

Records are loaded through the harness's own fail-closed loader
(`tests.contracts.loader.collect_all`), never via raw `json.loads` --
so a record that would itself be rejected by the harness (a malformed
shape, a cardinality violation, a superseded-guard reference, ...) can
never be silently used as a witness's evidence. Before executing each
witness, this script additionally requires: the registry's declared
record actually exists in the loaded set; it is that guard's
designated primary witness (never a non-primary/generated record); its
parser and guard_ref agree with the registry entry; and the registry's
own `input_` is byte-for-byte identical to the record's
`expected_transformed_input` (the registry never invents its own
notion of "the input" independent of the record it claims to test).

Usage: `python -m scripts.contract_mutation_witnesses [--guard <ref>]`
"""

from __future__ import annotations

import argparse
import importlib
import sys
import tempfile
import types
import uuid
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from tests.contracts.loader import collect_all  # noqa: E402
from tests.contracts.mutation_registry import (  # noqa: E402
    MUTATION_REGISTRY,
    SimpleMutation,
    StructuralMutation,
    fingerprint_file,
    fingerprint_record,
)
from tests.contracts.schema import CaseRecord, Parser  # noqa: E402
from tests.contracts.taxonomy import active_guards  # noqa: E402

_RECORDS_DIR = _BACKEND_ROOT / "tests" / "contracts" / "records"
_RECORD_PATHS: dict[Parser, Path] = {
    "location": _RECORDS_DIR / "location.json",
    "salary": _RECORDS_DIR / "salary.json",
    "experience": _RECORDS_DIR / "experience.json",
}


class WitnessError(Exception):
    pass


def _load_records_by_id() -> dict[str, CaseRecord]:
    all_records = collect_all(_RECORD_PATHS)
    return {r.record_id: r for records in all_records.values() for r in records}


def _expected_output_as_tuples(record: CaseRecord) -> dict[str, tuple[object, str]]:
    return {field: (ef.value, ef.provenance) for field, ef in record.expected_output.items()}


def _invoke(
    parser: str, module: types.ModuleType, inputs: dict[str, str | None]
) -> dict[str, tuple[object, str]]:
    fields: tuple[str, ...]
    if parser == "location":
        result = module.classify_location(inputs["location"])
        fields = ("city", "state", "country", "postal_code")
    elif parser == "salary":
        result = module.classify_salary(inputs["compensation_text"])
        fields = ("minimum", "maximum", "currency", "period")
    else:
        result = module.classify_experience(inputs.get("title"), inputs.get("description"))
        fields = ("minimum", "maximum")
    return {
        field: (getattr(result, field).value, getattr(result, field).provenance.value)
        for field in fields
    }


def _check_fingerprints(entry: SimpleMutation | StructuralMutation) -> None:
    current_source = fingerprint_file(
        {
            "location": "app/normalization/location.py",
            "salary": "app/normalization/salary.py",
            "experience": "app/normalization/experience.py",
        }[entry.parser]
    )
    current_record = fingerprint_record(entry.record_id, entry.parser)
    current_adapter = fingerprint_file(f"tests/contracts/adapters/{entry.parser}.py")
    if current_source != entry.source_fingerprint:
        raise WitnessError(
            f"{entry.guard_ref}: STALE source fingerprint (production source changed since "
            "this witness was last verified)"
        )
    if current_record != entry.record_fingerprint:
        raise WitnessError(
            f"{entry.guard_ref}: STALE record fingerprint (contract record changed since "
            "this witness was last verified)"
        )
    if current_adapter != entry.adapter_fingerprint:
        raise WitnessError(
            f"{entry.guard_ref}: STALE adapter fingerprint (adapter changed since this "
            "witness was last verified)"
        )


def _check_record_matches_registry_entry(
    entry: SimpleMutation | StructuralMutation, record: CaseRecord | None
) -> CaseRecord:
    if record is None:
        raise WitnessError(
            f"{entry.guard_ref}: record {entry.record_id!r} does not exist in the loaded, "
            "fail-closed record set"
        )
    if not record.is_primary_witness:
        raise WitnessError(
            f"{entry.guard_ref}: record {entry.record_id!r} is not marked as a designated "
            "primary witness -- a mutation witness may only be run against the guard's own "
            "primary witness, never a non-primary or generated record"
        )
    if record.guard_ref != entry.guard_ref:
        raise WitnessError(
            f"{entry.guard_ref}: record {entry.record_id!r} belongs to guard "
            f"{record.guard_ref!r}, not the registry entry's guard {entry.guard_ref!r}"
        )
    if record.parser != entry.parser:
        raise WitnessError(
            f"{entry.guard_ref}: record parser {record.parser!r} does not match the registry "
            f"entry's parser {entry.parser!r}"
        )
    if entry.input_ != record.expected_transformed_input:
        raise WitnessError(
            f"{entry.guard_ref}: registry input {entry.input_!r} does not exactly equal the "
            f"record's own expected_transformed_input {record.expected_transformed_input!r}"
        )
    return record


def _run_simple(entry: SimpleMutation, record: CaseRecord) -> None:
    import app.normalization.experience as experience_module
    import app.normalization.location as location_module
    import app.normalization.salary as salary_module

    module = {
        "location": location_module,
        "salary": salary_module,
        "experience": experience_module,
    }[entry.parser]

    restore = entry.mutate(module)
    try:
        actual_erroneous = _invoke(entry.parser, module, entry.input_)
        if actual_erroneous != entry.erroneous_output:
            raise WitnessError(
                f"{entry.guard_ref}: mutant did not reproduce the documented erroneous "
                f"output -- expected {entry.erroneous_output!r}, got {actual_erroneous!r}"
            )
    finally:
        for attr, value in restore.items():
            setattr(module, attr, value)

    actual_restored = _invoke(entry.parser, module, entry.input_)
    expected_restored = _expected_output_as_tuples(record)
    if actual_restored != expected_restored:
        raise WitnessError(
            f"{entry.guard_ref}: restored module did not reproduce the contract record's "
            f"own expected_output -- expected {expected_restored!r}, got {actual_restored!r}"
        )


def _run_structural(entry: StructuralMutation, record: CaseRecord) -> None:
    source_path = _BACKEND_ROOT / entry.source_file
    source_text = source_path.read_text(encoding="utf-8")
    occurrences = source_text.count(entry.anchor)
    if occurrences == 0:
        raise WitnessError(f"{entry.guard_ref}: anchor not found in {entry.source_file}")
    if occurrences > 1:
        raise WitnessError(
            f"{entry.guard_ref}: anchor occurs {occurrences} times in {entry.source_file}, "
            "expected exactly 1"
        )
    mutated_text = source_text.replace(entry.anchor, entry.replacement, 1)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_module_name = f"_contract_mutant_{uuid.uuid4().hex}"
        tmp_path = Path(tmp_dir) / f"{tmp_module_name}.py"
        tmp_path.write_text(mutated_text, encoding="utf-8")

        spec = importlib.util.spec_from_file_location(tmp_module_name, tmp_path)
        assert spec is not None and spec.loader is not None
        mutant_module = importlib.util.module_from_spec(spec)
        sys.modules[tmp_module_name] = mutant_module
        try:
            spec.loader.exec_module(mutant_module)
            actual_erroneous = _invoke(entry.parser, mutant_module, entry.input_)
            if actual_erroneous != entry.erroneous_output:
                raise WitnessError(
                    f"{entry.guard_ref}: mutant did not reproduce the documented erroneous "
                    f"output -- expected {entry.erroneous_output!r}, got {actual_erroneous!r}"
                )
        finally:
            del sys.modules[tmp_module_name]

    # The real, already-imported module was never touched by a structural
    # mutation (a fresh isolated copy was used instead) -- confirm the
    # restored/real behavior separately, directly against it.
    real_module = importlib.import_module(entry.module_path)
    actual_restored = _invoke(entry.parser, real_module, entry.input_)
    expected_restored = _expected_output_as_tuples(record)
    if actual_restored != expected_restored:
        raise WitnessError(
            f"{entry.guard_ref}: real module did not reproduce the contract record's own "
            f"expected_output -- expected {expected_restored!r}, got {actual_restored!r}"
        )


def run_witness(guard_ref: str, records_by_id: dict[str, CaseRecord]) -> None:
    entry = MUTATION_REGISTRY[guard_ref]
    record = _check_record_matches_registry_entry(entry, records_by_id.get(entry.record_id))
    _check_fingerprints(entry)
    if isinstance(entry, SimpleMutation):
        _run_simple(entry, record)
    else:
        _run_structural(entry, record)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--guard", default=None)
    args = parser.parse_args()

    active = active_guards()
    registry_refs = set(MUTATION_REGISTRY)
    if registry_refs != set(active):
        missing = set(active) - registry_refs
        extra = registry_refs - set(active)
        print(
            f"FAIL: registry/active-guard mismatch -- missing={sorted(missing)} "
            f"extra={sorted(extra)}"
        )
        return 1

    try:
        records_by_id = _load_records_by_id()
    except Exception as exc:  # noqa: BLE001 -- report, never crash uninformatively
        print(f"FAIL: could not load contract records through the fail-closed loader: {exc}")
        return 1

    targets = [args.guard] if args.guard else sorted(MUTATION_REGISTRY)
    passed = 0
    failed: list[str] = []
    for ref in targets:
        try:
            run_witness(ref, records_by_id)
        except Exception as exc:  # noqa: BLE001 -- report every failure, never crash the run
            print(f"FAIL {ref}: {type(exc).__name__}: {exc}")
            failed.append(ref)
        else:
            print(f"PASS {ref}")
            passed += 1

    print(f"\n{passed} passed, {len(failed)} failed, out of {len(targets)} active-guard witnesses")
    print(
        "(experience/g07-reversed-label-anchor is superseded -- no witness exists for it, "
        "by design)"
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
