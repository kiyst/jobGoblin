"""Replays every committed mutation-registry selector (Workflow v3.2
Slice 2) and asserts both the documented erroneous output (under the
mutant) and the documented restored output (matching the real contract
record's own `expected_output`). Standalone script, never collected by
pytest -- run explicitly, once at Slice 2 acceptance and again whenever
a covered guard's contract case, adapter, or target source changes.

Usage: `python -m scripts.contract_mutation_witnesses [--guard <ref>]`
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import tempfile
import types
import uuid
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from tests.contracts.mutation_registry import (  # noqa: E402
    MUTATION_REGISTRY,
    SimpleMutation,
    StructuralMutation,
    fingerprint_file,
    fingerprint_record,
)
from tests.contracts.taxonomy import active_guards  # noqa: E402

_RECORDS_DIR = _BACKEND_ROOT / "tests" / "contracts" / "records"


class WitnessError(Exception):
    pass


def _load_record_expected_output(record_id: str, parser: str) -> dict[str, tuple[object, str]]:
    data = json.loads((_RECORDS_DIR / f"{parser}.json").read_text(encoding="utf-8"))
    for raw in data["records"]:
        if raw["record_id"] == record_id:
            return {
                field: (body["value"], body["provenance"])
                for field, body in raw["expected_output"].items()
            }
    raise WitnessError(f"record {record_id!r} not found in {parser}.json")


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


def _check_fingerprints(entry) -> None:  # type: ignore[no-untyped-def]
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


def _run_simple(entry: SimpleMutation) -> None:
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
    expected_restored = _load_record_expected_output(entry.record_id, entry.parser)
    if actual_restored != expected_restored:
        raise WitnessError(
            f"{entry.guard_ref}: restored module did not reproduce the contract record's "
            f"own expected_output -- expected {expected_restored!r}, got {actual_restored!r}"
        )


def _run_structural(entry: StructuralMutation) -> None:
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
    expected_restored = _load_record_expected_output(entry.record_id, entry.parser)
    if actual_restored != expected_restored:
        raise WitnessError(
            f"{entry.guard_ref}: real module did not reproduce the contract record's own "
            f"expected_output -- expected {expected_restored!r}, got {actual_restored!r}"
        )


def run_witness(guard_ref: str) -> None:
    entry = MUTATION_REGISTRY[guard_ref]
    _check_fingerprints(entry)
    if isinstance(entry, SimpleMutation):
        _run_simple(entry)
    else:
        _run_structural(entry)


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

    targets = [args.guard] if args.guard else sorted(MUTATION_REGISTRY)
    passed = 0
    failed: list[str] = []
    for ref in targets:
        try:
            run_witness(ref)
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
