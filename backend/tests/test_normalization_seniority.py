import ast
import json
from pathlib import Path
from typing import Any, cast

import pytest

from app.normalization.seniority import classify_seniority
from app.normalization.types import Provenance

_FIXTURES_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "normalization" / "seniority_cases.json"
)


def _load_cases() -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], json.loads(_FIXTURES_PATH.read_text(encoding="utf-8")))


_CASES = _load_cases()


@pytest.mark.parametrize("case", _CASES, ids=[case["id"] for case in _CASES])
def test_seniority_classifier_matches_corpus_expectation(case: dict[str, Any]) -> None:
    result = classify_seniority(case["title"], case["description"])
    assert result.value == case["expected_value"], case["note"]
    assert result.provenance == Provenance(case["expected_provenance"]), case["note"]


def test_corpus_origin_values_are_honestly_labeled() -> None:
    """Every case is 'synthetic_representative', 'synthetic_adversarial',
    or the single 'sanitized_capture' case honestly citing its real
    source (backend/tests/fixtures/discovery/greenhouse_live_canary.json).
    Exactly one sanitized_capture case is expected — this is a single
    negative-control data point, not broad realistic-positive coverage
    (see the module docstring's honest evidence-gap statement)."""
    allowed = {"synthetic_representative", "synthetic_adversarial", "sanitized_capture"}
    sanitized_count = 0
    for case in _CASES:
        assert (
            case["origin"] in allowed
        ), f"{case['id']}: origin must be one of {allowed}, got {case['origin']!r}"
        if case["origin"] == "sanitized_capture":
            sanitized_count += 1
    assert sanitized_count == 1


def test_classify_seniority_is_deterministic() -> None:
    """Identical input always yields a bit-for-bit identical result across
    repeated calls."""
    for case in _CASES:
        first = classify_seniority(case["title"], case["description"])
        second = classify_seniority(case["title"], case["description"])
        assert first == second


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
# `app.normalization.employment` or `app.normalization.remote` — this
# module's hyphen handling, tokenizer, and negation are independently
# implemented, not reused across parser modules.
_ALLOWED_IMPORTS: dict[str, frozenset[str]] = {
    "app/normalization/seniority.py": frozenset(
        {"__future__", "re", "unicodedata", "typing", "app.normalization.types"}
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
    allowed = _ALLOWED_IMPORTS["app/normalization/seniority.py"]
    assert imports == ["requests"]
    assert not all(name in allowed for name in imports)


def test_import_boundary_rejects_cross_parser_private_helper_import() -> None:
    """Binding-correction regression: this module must not import
    `app.normalization.employment` or `app.normalization.remote`'s private
    helpers. A synthetic source doing so is rejected by the same
    allow-list, even though neither module name is inherently forbidden
    elsewhere in this codebase — it is simply not on *this* module's own
    exact allow-list."""
    allowed = _ALLOWED_IMPORTS["app/normalization/seniority.py"]
    for forbidden_module in ("app.normalization.employment", "app.normalization.remote"):
        synthetic_source = f"from {forbidden_module} import _tokenize\n"
        imports = _imported_module_names(synthetic_source)
        assert imports == [forbidden_module]
        assert not all(name in allowed for name in imports)
