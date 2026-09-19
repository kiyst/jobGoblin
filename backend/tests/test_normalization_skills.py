import ast
import json
from pathlib import Path
from typing import Any, cast

import pytest

from app.normalization.skills import SkillMatch, classify_skills
from app.normalization.taxonomy import DEFAULT_SKILLS_TAXONOMY_PATH, TaxonomyIndex, load_taxonomy
from app.normalization.types import Provenance

_FIXTURES_PATH = Path(__file__).resolve().parent / "fixtures" / "normalization" / "skill_cases.json"


def _load_cases() -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], json.loads(_FIXTURES_PATH.read_text(encoding="utf-8")))


_CASES = _load_cases()
_TAXONOMY: TaxonomyIndex = load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)


def _expected_matches(case: dict[str, Any]) -> list[SkillMatch]:
    return [
        SkillMatch(
            canonical_id=entry["canonical_id"],
            display_name=entry["display_name"],
            provenance=Provenance(entry["provenance"]),
        )
        for entry in case["expected_matches"]
    ]


@pytest.mark.parametrize("case", _CASES, ids=[case["id"] for case in _CASES])
def test_skill_classifier_matches_corpus_expectation(case: dict[str, Any]) -> None:
    result = classify_skills(case["title"], case["description"], taxonomy=_TAXONOMY)
    assert result == _expected_matches(case), case["note"]


def test_corpus_origin_values_are_honestly_labeled() -> None:
    """Every case is either 'synthetic_representative' or
    'synthetic_adversarial' -- none of this corpus is a genuine
    'sanitized_capture', since no real captured project text exists yet
    for this parser."""
    allowed = {"synthetic_representative", "synthetic_adversarial"}
    for case in _CASES:
        assert (
            case["origin"] in allowed
        ), f"{case['id']}: origin must be one of {allowed}, got {case['origin']!r}"
    assert not any(case["origin"] == "sanitized_capture" for case in _CASES)


def test_classify_skills_is_deterministic() -> None:
    for case in _CASES:
        first = classify_skills(case["title"], case["description"], taxonomy=_TAXONOMY)
        second = classify_skills(case["title"], case["description"], taxonomy=_TAXONOMY)
        assert first == second


def test_classify_skills_result_is_sorted_ascending_by_canonical_id() -> None:
    for case in _CASES:
        result = classify_skills(case["title"], case["description"], taxonomy=_TAXONOMY)
        ids = [match.canonical_id for match in result]
        assert ids == sorted(ids), case["note"]


def test_classify_skills_result_has_no_duplicate_canonical_ids() -> None:
    for case in _CASES:
        result = classify_skills(case["title"], case["description"], taxonomy=_TAXONOMY)
        ids = [match.canonical_id for match in result]
        assert len(ids) == len(set(ids)), case["note"]


# ---------------------------------------------------------------------------
# SkillMatch invariants -- unit-level, not fixture-driven.
# ---------------------------------------------------------------------------
def test_skill_match_accepts_valid_construction() -> None:
    match = SkillMatch(canonical_id="python", display_name="Python", provenance=Provenance.INFERRED)
    assert match.canonical_id == "python"
    assert match.display_name == "Python"
    assert match.provenance is Provenance.INFERRED


def test_skill_match_rejects_non_slug_canonical_id() -> None:
    with pytest.raises(ValueError, match="canonical_id must satisfy is_canonical_slug"):
        SkillMatch(
            canonical_id="Not A Slug!", display_name="Python", provenance=Provenance.INFERRED
        )


def test_skill_match_rejects_empty_canonical_id() -> None:
    with pytest.raises(ValueError, match="canonical_id must satisfy is_canonical_slug"):
        SkillMatch(canonical_id="", display_name="Python", provenance=Provenance.INFERRED)


def test_skill_match_rejects_whitespace_only_display_name() -> None:
    with pytest.raises(ValueError, match="display_name must contain non-whitespace content"):
        SkillMatch(canonical_id="python", display_name="   ", provenance=Provenance.INFERRED)


def test_skill_match_rejects_covered_whitespace_only_display_name() -> None:
    with pytest.raises(ValueError, match="display_name must contain non-whitespace content"):
        SkillMatch(canonical_id="python", display_name="\t\n", provenance=Provenance.INFERRED)


def test_skill_match_rejects_empty_display_name() -> None:
    with pytest.raises(ValueError, match="display_name must contain non-whitespace content"):
        SkillMatch(canonical_id="python", display_name="", provenance=Provenance.INFERRED)


def test_skill_match_rejects_non_enum_provenance() -> None:
    with pytest.raises(ValueError, match="provenance must be a Provenance enum member"):
        SkillMatch(canonical_id="python", display_name="Python", provenance="inferred")  # type: ignore[arg-type]


def test_skill_match_error_messages_never_interpolate_input() -> None:
    """Categorical, fixed error messages -- no runtime value ever appears
    in the message text."""
    secret_display_name = "TOP SECRET CLIENT NAME"
    with pytest.raises(ValueError) as exc_info:
        SkillMatch(canonical_id="python", display_name="   ", provenance=Provenance.INFERRED)
    assert secret_display_name not in str(exc_info.value)
    assert "   " not in str(exc_info.value)


# ---------------------------------------------------------------------------
# Import boundary -- AST-based exact allow-list, not a deny-list.
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


_ALLOWED_IMPORTS: dict[str, frozenset[str]] = {
    "app/normalization/skills.py": frozenset(
        {
            "__future__",
            "re",
            "dataclasses",
            "app.normalization.taxonomy",
            "app.normalization.types",
            "app.schemas.identifiers",
        }
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
    allowed = _ALLOWED_IMPORTS["app/normalization/skills.py"]
    assert imports == ["requests"]
    assert not all(name in allowed for name in imports)


def test_import_boundary_rejects_cross_parser_private_helper_import() -> None:
    """This module must not import another parser's private helpers. A
    synthetic source doing so is rejected by the same allow-list, even
    though neither module name is inherently forbidden elsewhere in this
    codebase -- it is simply not on *this* module's own exact allow-list."""
    allowed = _ALLOWED_IMPORTS["app/normalization/skills.py"]
    for forbidden_module in ("app.normalization.remote", "app.normalization.seniority"):
        synthetic_source = f"from {forbidden_module} import _tokenize\n"
        imports = _imported_module_names(synthetic_source)
        assert imports == [forbidden_module]
        assert not all(name in allowed for name in imports)
