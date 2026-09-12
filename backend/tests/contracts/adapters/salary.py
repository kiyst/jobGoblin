"""Salary adapter (Workflow v3.2 Slice 2). Imports only the public
`classify_salary` entry point -- see `adapters/location.py`'s docstring
for the shared rationale."""

from __future__ import annotations

from app.normalization.salary import classify_salary


def invoke(inputs: dict[str, str | None]) -> dict[str, tuple[object, str]]:
    result = classify_salary(inputs["compensation_text"])
    return {
        "minimum": (result.minimum.value, result.minimum.provenance.value),
        "maximum": (result.maximum.value, result.maximum.provenance.value),
        "currency": (result.currency.value, result.currency.provenance.value),
        "period": (result.period.value, result.period.provenance.value),
    }
