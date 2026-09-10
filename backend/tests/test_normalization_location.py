import ast
import json
from pathlib import Path
from typing import Any, cast

import pytest

from app.normalization.location import LocationResult, classify_location
from app.normalization.types import NormalizationResult, Provenance

_FIXTURES_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "normalization" / "location_cases.json"
)
_GREENHOUSE_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "discovery" / "greenhouse_live_canary.json"
)


def _load_cases() -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], json.loads(_FIXTURES_PATH.read_text(encoding="utf-8")))


_CASES = _load_cases()


@pytest.mark.parametrize("case", _CASES, ids=[case["id"] for case in _CASES])
def test_location_classifier_matches_corpus_expectation(case: dict[str, Any]) -> None:
    result = classify_location(case["location"])
    assert result.city.value == case["expected_city"], case["note"]
    assert result.city.provenance == Provenance(case["expected_city_provenance"]), case["note"]
    assert result.state.value == case["expected_state"], case["note"]
    assert result.state.provenance == Provenance(case["expected_state_provenance"]), case["note"]
    assert result.country.value == case["expected_country"], case["note"]
    assert result.country.provenance == Provenance(case["expected_country_provenance"]), case[
        "note"
    ]
    assert result.postal_code.value == case["expected_postal_code"], case["note"]
    assert result.postal_code.provenance == Provenance(
        case["expected_postal_code_provenance"]
    ), case["note"]


def test_corpus_origin_values_are_honestly_labeled() -> None:
    """Every case is 'synthetic_representative' or 'synthetic_adversarial'
    -- no 'sanitized_capture' claim is made for this corpus, since the one
    real sanitized location string is exercised separately, by loading the
    actual committed fixture file (see
    test_real_sanitized_greenhouse_fixture_classifies_correctly below),
    not by duplicating its literal value here where it could silently
    drift out of sync."""
    allowed = {"synthetic_representative", "synthetic_adversarial"}
    for case in _CASES:
        assert (
            case["origin"] in allowed
        ), f"{case['id']}: origin must be one of {allowed}, got {case['origin']!r}"


def test_classify_location_is_deterministic() -> None:
    """Identical input always yields a bit-for-bit identical result across
    repeated calls."""
    for case in _CASES:
        first = classify_location(case["location"])
        second = classify_location(case["location"])
        assert first == second


def test_city_field_is_always_unavailable_v1_deferred() -> None:
    """City resolution is deferred, not implemented, in this slice (see
    the module docstring) -- this is a structural invariant, not merely
    incidentally true across the corpus: every fixture, regardless of
    what anchor it has, must show city as unconditionally unavailable."""
    for case in _CASES:
        result = classify_location(case["location"])
        assert result.city.value is None, case["id"]
        assert result.city.provenance == Provenance.UNAVAILABLE, case["id"]


def test_every_collision_code_is_covered_by_the_fixture_corpus() -> None:
    """docs/LLM_WORKFLOW.md's claim-to-evidence discipline: every one of
    the 26 frozen collision-set codes must have at least one no-anchor
    rejection fixture proving it fails closed."""
    from app.normalization.location import _COLLISION_STATES

    covered_codes = {
        case["id"].removeprefix("collision_").removesuffix("_no_anchor_rejected").upper()
        for case in _CASES
        if case["id"].startswith("collision_") and case["id"].endswith("_no_anchor_rejected")
    }
    assert covered_codes == _COLLISION_STATES


def test_real_sanitized_greenhouse_fixture_classifies_correctly() -> None:
    """Loads the actual committed sanitized-derived-sample fixture and
    asserts the source value before asserting the classification, so this
    "real sanitized evidence" claim cannot silently drift out of sync if
    the fixture is ever regenerated."""
    data = json.loads(_GREENHOUSE_FIXTURE_PATH.read_text(encoding="utf-8"))
    location_text = data["job"]["location"]["name"]
    assert location_text == "Remote, US"

    result = classify_location(location_text)
    assert result.city.value is None
    assert result.city.provenance == Provenance.UNAVAILABLE
    assert result.state.value is None
    assert result.state.provenance == Provenance.UNAVAILABLE
    assert result.country.value == "United States"
    assert result.country.provenance == Provenance.PARSED_DESCRIPTION
    assert result.postal_code.value is None
    assert result.postal_code.provenance == Provenance.UNAVAILABLE


# ---------------------------------------------------------------------------
# Import boundary -- same AST-inspection allow-list pattern as
# experience.py/salary.py/seniority.py/employment.py/remote.py.
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
# `app.normalization.experience`, `app.normalization.salary`,
# `app.normalization.seniority`, `app.normalization.employment`, or
# `app.normalization.remote` -- this module's whole-field grammar is
# independently implemented, not reused across parser modules.
_ALLOWED_IMPORTS: dict[str, frozenset[str]] = {
    "app/normalization/location.py": frozenset(
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
    allowed = _ALLOWED_IMPORTS["app/normalization/location.py"]
    assert imports == ["requests"]
    assert not all(name in allowed for name in imports)


def test_import_boundary_rejects_cross_parser_private_helper_import() -> None:
    """Binding-correction regression pattern (mirroring salary.py's own
    test): this module must not import `app.normalization.experience`,
    `app.normalization.salary`, `app.normalization.seniority`,
    `app.normalization.employment`, or `app.normalization.remote`."""
    synthetic_source = "from app.normalization.salary import _resolve_currency\n"
    imports = _imported_module_names(synthetic_source)
    allowed = _ALLOWED_IMPORTS["app/normalization/location.py"]
    assert imports == ["app.normalization.salary"]
    assert not all(name in allowed for name in imports)


def test_location_result_is_a_plain_dataclass_with_no_ordering_invariant() -> None:
    """Unlike `ExperienceRange`/`SalaryResult`, `LocationResult` has no
    `__post_init__` invariant -- there is no ordering/range concept for
    geography to defend against. This test documents that choice was
    deliberate, not an omission: direct construction with any combination
    of values/provenances must never raise."""
    LocationResult(
        city=NormalizationResult(None, Provenance.UNAVAILABLE),
        state=NormalizationResult("TX", Provenance.PARSED_DESCRIPTION),
        country=NormalizationResult("United States", Provenance.INFERRED),
        postal_code=NormalizationResult(None, Provenance.UNAVAILABLE),
    )
