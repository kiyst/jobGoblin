import ast
import json
from pathlib import Path
from typing import Any, cast

import pytest

from app.normalization.experience import ExperienceRange, classify_experience
from app.normalization.types import NormalizationResult, Provenance

_FIXTURES_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "normalization" / "experience_cases.json"
)


def _load_cases() -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], json.loads(_FIXTURES_PATH.read_text(encoding="utf-8")))


_CASES = _load_cases()


@pytest.mark.parametrize("case", _CASES, ids=[case["id"] for case in _CASES])
def test_experience_classifier_matches_corpus_expectation(case: dict[str, Any]) -> None:
    result = classify_experience(case["title"], case["description"])
    assert result.minimum.value == case["expected_min"], case["note"]
    assert result.minimum.provenance == Provenance(case["expected_min_provenance"]), case["note"]
    assert result.maximum.value == case["expected_max"], case["note"]
    assert result.maximum.provenance == Provenance(case["expected_max_provenance"]), case["note"]


def test_corpus_origin_values_are_honestly_labeled() -> None:
    """Every case is 'synthetic_representative' or 'synthetic_adversarial'
    — no 'sanitized_capture' claim is made for this corpus (unlike
    seniority.py's single negative-control data point), since no real
    experience-range-bearing posting text was available to sanitize for
    this slice. Stated honestly, not claimed otherwise."""
    allowed = {"synthetic_representative", "synthetic_adversarial"}
    for case in _CASES:
        assert (
            case["origin"] in allowed
        ), f"{case['id']}: origin must be one of {allowed}, got {case['origin']!r}"


def test_classify_experience_is_deterministic() -> None:
    """Identical input always yields a bit-for-bit identical result across
    repeated calls."""
    for case in _CASES:
        first = classify_experience(case["title"], case["description"])
        second = classify_experience(case["title"], case["description"])
        assert first == second


# ---------------------------------------------------------------------------
# ExperienceRange invariant — defense-in-depth against direct construction
# with a self-contradictory pair (see module docstring: classify_experience
# itself is responsible for the coercion; this is the backstop).
# ---------------------------------------------------------------------------


def test_experience_range_rejects_direct_construction_with_inverted_bounds() -> None:
    with pytest.raises(ValueError, match="minimum > maximum"):
        ExperienceRange(
            NormalizationResult(7, Provenance.INFERRED),
            NormalizationResult(5, Provenance.INFERRED),
        )


def test_experience_range_accepts_one_bound_unavailable_regardless_of_the_other() -> None:
    # Must not raise: an UNAVAILABLE bound is never compared numerically.
    ExperienceRange(
        NormalizationResult(None, Provenance.UNAVAILABLE),
        NormalizationResult(5, Provenance.INFERRED),
    )
    ExperienceRange(
        NormalizationResult(5, Provenance.INFERRED),
        NormalizationResult(None, Provenance.UNAVAILABLE),
    )


def test_experience_range_accepts_equal_bounds() -> None:
    # minimum == maximum is not inverted.
    ExperienceRange(
        NormalizationResult(5, Provenance.INFERRED),
        NormalizationResult(5, Provenance.INFERRED),
    )


# ---------------------------------------------------------------------------
# Import boundary — same AST-inspection allow-list pattern as
# seniority.py/employment.py/remote.py.
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
# `app.normalization.seniority`, `app.normalization.employment`, or
# `app.normalization.remote` — this module's numeric grammar, sentence/
# segment splitting, and negation/attribution handling are independently
# implemented, not reused across parser modules.
_ALLOWED_IMPORTS: dict[str, frozenset[str]] = {
    "app/normalization/experience.py": frozenset(
        {"__future__", "re", "unicodedata", "dataclasses", "typing", "app.normalization.types"}
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
    allowed = _ALLOWED_IMPORTS["app/normalization/experience.py"]
    assert imports == ["requests"]
    assert not all(name in allowed for name in imports)


def test_import_boundary_rejects_cross_parser_private_helper_import() -> None:
    """Binding-correction regression pattern (mirroring seniority.py's own
    test): this module must not import `app.normalization.seniority`,
    `app.normalization.employment`, or `app.normalization.remote`."""
    synthetic_source = "from app.normalization.seniority import _title_segments\n"
    imports = _imported_module_names(synthetic_source)
    allowed = _ALLOWED_IMPORTS["app/normalization/experience.py"]
    assert imports == ["app.normalization.seniority"]
    assert not all(name in allowed for name in imports)
