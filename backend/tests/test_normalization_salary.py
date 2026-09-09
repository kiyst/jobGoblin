import ast
import json
from pathlib import Path
from typing import Any, cast

import pytest

from app.normalization.salary import SalaryResult, classify_salary
from app.normalization.types import NormalizationResult, Provenance

_FIXTURES_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "normalization" / "salary_cases.json"
)


def _load_cases() -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], json.loads(_FIXTURES_PATH.read_text(encoding="utf-8")))


_CASES = _load_cases()


@pytest.mark.parametrize("case", _CASES, ids=[case["id"] for case in _CASES])
def test_salary_classifier_matches_corpus_expectation(case: dict[str, Any]) -> None:
    result = classify_salary(case["compensation_text"])
    assert result.minimum.value == case["expected_min"], case["note"]
    assert result.minimum.provenance == Provenance(case["expected_min_provenance"]), case["note"]
    assert result.maximum.value == case["expected_max"], case["note"]
    assert result.maximum.provenance == Provenance(case["expected_max_provenance"]), case["note"]
    assert result.currency.value == case["expected_currency"], case["note"]
    assert result.currency.provenance == Provenance(case["expected_currency_provenance"]), case[
        "note"
    ]
    assert result.period.value == case["expected_period"], case["note"]
    assert result.period.provenance == Provenance(case["expected_period_provenance"]), case["note"]


def test_corpus_origin_values_are_honestly_labeled() -> None:
    """Every case is 'synthetic_representative' or 'synthetic_adversarial'
    -- no 'sanitized_capture' claim is made for this corpus, since no real
    salary-bearing posting text was collected or reviewed for this slice
    (disclosed evidence limitation, not treated as satisfied -- see the
    module docstring's "Evidence limitation" section)."""
    allowed = {"synthetic_representative", "synthetic_adversarial"}
    for case in _CASES:
        assert (
            case["origin"] in allowed
        ), f"{case['id']}: origin must be one of {allowed}, got {case['origin']!r}"


def test_classify_salary_is_deterministic() -> None:
    """Identical input always yields a bit-for-bit identical result across
    repeated calls."""
    for case in _CASES:
        first = classify_salary(case["compensation_text"])
        second = classify_salary(case["compensation_text"])
        assert first == second


def test_every_period_synonym_is_covered_by_the_fixture_corpus() -> None:
    """docs/LLM_WORKFLOW.md's claim-to-evidence discipline: every synonym
    in the closed period catalog must have at least one fixture proving it
    maps to its canonical database literal, not merely the four canonical
    words themselves."""
    from app.normalization.salary import _SUPPORTED_PERIOD_SYNONYMS

    covered_periods = {case["expected_period"] for case in _CASES if case["expected_period"]}
    assert covered_periods == {"hourly", "daily", "monthly", "annual"}

    synonym_fixture_ids = {
        case["id"] for case in _CASES if case["id"].startswith("period_synonym_")
    }
    assert len(synonym_fixture_ids) == len(_SUPPORTED_PERIOD_SYNONYMS)


def test_all_five_currency_codes_and_both_unambiguous_symbols_are_covered() -> None:
    """docs/LLM_WORKFLOW.md's claim-to-evidence discipline, Codex round-4
    clarification 4: every one of the five explicit currency codes and
    both unambiguous symbols must have at least one fixture resolving to
    it."""
    covered_currencies = {case["expected_currency"] for case in _CASES if case["expected_currency"]}
    assert covered_currencies == {"USD", "CAD", "AUD", "GBP", "EUR"}


# ---------------------------------------------------------------------------
# SalaryResult invariant -- defense-in-depth against direct construction
# with a self-contradictory pair (see module docstring: classify_salary
# itself is responsible for the coercion; this is the backstop).
# ---------------------------------------------------------------------------


def test_salary_result_rejects_direct_construction_with_inverted_bounds() -> None:
    with pytest.raises(ValueError, match="minimum > maximum"):
        SalaryResult(
            NormalizationResult(150000, Provenance.PARSED_DESCRIPTION),
            NormalizationResult(120000, Provenance.PARSED_DESCRIPTION),
            NormalizationResult(None, Provenance.UNAVAILABLE),
            NormalizationResult(None, Provenance.UNAVAILABLE),
        )


def test_salary_result_accepts_one_bound_unavailable_regardless_of_the_other() -> None:
    # Must not raise: an UNAVAILABLE bound is never compared numerically.
    SalaryResult(
        NormalizationResult(None, Provenance.UNAVAILABLE),
        NormalizationResult(150000, Provenance.PARSED_DESCRIPTION),
        NormalizationResult(None, Provenance.UNAVAILABLE),
        NormalizationResult(None, Provenance.UNAVAILABLE),
    )
    SalaryResult(
        NormalizationResult(150000, Provenance.PARSED_DESCRIPTION),
        NormalizationResult(None, Provenance.UNAVAILABLE),
        NormalizationResult(None, Provenance.UNAVAILABLE),
        NormalizationResult(None, Provenance.UNAVAILABLE),
    )


def test_salary_result_accepts_equal_bounds() -> None:
    # minimum == maximum is not inverted.
    SalaryResult(
        NormalizationResult(130000, Provenance.PARSED_DESCRIPTION),
        NormalizationResult(130000, Provenance.PARSED_DESCRIPTION),
        NormalizationResult(None, Provenance.UNAVAILABLE),
        NormalizationResult(None, Provenance.UNAVAILABLE),
    )


# ---------------------------------------------------------------------------
# Import boundary -- same AST-inspection allow-list pattern as
# experience.py/seniority.py/employment.py/remote.py.
# ---------------------------------------------------------------------------


def _imported_module_names(source: str) -> list[str]:
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


# Fail-closed exact allow-list, not a deny-list: anything not explicitly
# named here is rejected. Deliberately does not import anything from
# `app.normalization.experience`, `app.normalization.seniority`,
# `app.normalization.employment`, or `app.normalization.remote` -- this
# module reads only `compensation_text` and its whole-field grammar is
# independently implemented, not reused across parser modules.
_ALLOWED_IMPORTS: dict[str, frozenset[str]] = {
    "app/normalization/salary.py": frozenset(
        {"__future__", "re", "unicodedata", "dataclasses", "app.normalization.types"}
    ),
}


@pytest.mark.parametrize("relative_path", sorted(_ALLOWED_IMPORTS))
def test_import_boundary_allow_list(relative_path: str) -> None:
    """docs/PHASE_RISK_CHECKLIST.md's Phase 3 exit gate: no parser imports
    providers, ORM models, UI code, network clients, or another parser
    module's private helpers. Proven by AST inspection against an exact
    permitted-import allow-list, not a deny-list."""
    backend_root = Path(__file__).resolve().parent.parent
    source = (backend_root / relative_path).read_text(encoding="utf-8")
    imports = _imported_module_names(source)
    allowed = _ALLOWED_IMPORTS[relative_path]
    for name in imports:
        assert name in allowed, (
            f"{relative_path} imports {name!r}, which is not on its exact "
            f"allow-list {sorted(allowed)!r}"
        )


def test_import_boundary_rejects_unrecognized_import() -> None:
    """Synthetic regression proving the allow-list check is genuinely
    fail-closed."""
    synthetic_source = "import requests\n"
    imports = _imported_module_names(synthetic_source)
    allowed = _ALLOWED_IMPORTS["app/normalization/salary.py"]
    assert imports == ["requests"]
    assert not all(name in allowed for name in imports)


def test_import_boundary_rejects_cross_parser_private_helper_import() -> None:
    """Binding-correction regression pattern (mirroring experience.py's own
    test): this module must not import `app.normalization.experience`,
    `app.normalization.seniority`, `app.normalization.employment`, or
    `app.normalization.remote`."""
    synthetic_source = "from app.normalization.experience import _title_segments\n"
    imports = _imported_module_names(synthetic_source)
    allowed = _ALLOWED_IMPORTS["app/normalization/salary.py"]
    assert imports == ["app.normalization.experience"]
    assert not all(name in allowed for name in imports)
