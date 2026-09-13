"""Runner: invokes a parser's adapter against a loaded case record's
`expected_transformed_input` and compares the actual result to
`expected_output` (Workflow v3.2 Slice 2). This module imports only the
adapters package -- never a parser module directly -- so it stays
inside the same import boundary the adapters themselves are held to.
"""

from __future__ import annotations

from tests.contracts.adapters import experience as experience_adapter
from tests.contracts.adapters import location as location_adapter
from tests.contracts.adapters import salary as salary_adapter
from tests.contracts.schema import CaseRecord

_ADAPTERS = {
    "location": location_adapter.invoke,
    "salary": salary_adapter.invoke,
    "experience": experience_adapter.invoke,
}


def run_case(record: CaseRecord) -> None:
    invoke = _ADAPTERS[record.parser]
    actual = invoke(record.expected_transformed_input)
    for field, expected in record.expected_output.items():
        actual_value, actual_provenance = actual[field]
        assert actual_value == expected.value, (
            f"{record.record_id}: field {field!r} value mismatch -- "
            f"expected {expected.value!r}, got {actual_value!r}"
        )
        assert actual_provenance == expected.provenance, (
            f"{record.record_id}: field {field!r} provenance mismatch -- "
            f"expected {expected.provenance!r}, got {actual_provenance!r}"
        )
