import ast
import json
from pathlib import Path
from typing import Any, cast

import pytest

from app.normalization.remote import classify_remote_type
from app.normalization.types import Provenance

_FIXTURES_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "normalization" / "remote_type_cases.json"
)


def _load_cases() -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], json.loads(_FIXTURES_PATH.read_text(encoding="utf-8")))


_CASES = _load_cases()


@pytest.mark.parametrize("case", _CASES, ids=[case["id"] for case in _CASES])
def test_remote_classifier_matches_corpus_expectation(case: dict[str, Any]) -> None:
    result = classify_remote_type(case["title"], case["description"])
    assert result.value == case["expected_value"], case["note"]
    assert result.provenance == Provenance(case["expected_provenance"]), case["note"]


def test_corpus_origin_values_are_honestly_labeled() -> None:
    """docs/LLM_HANDOFF.md's binding correction: every case is either
    'synthetic_representative' or 'synthetic_adversarial' — none of this
    initial corpus is a genuine 'sanitized_capture', since no real captured
    project text exists yet for this parser, and claiming otherwise would
    misrepresent hand-authored examples as real data."""
    allowed = {"synthetic_representative", "synthetic_adversarial"}
    for case in _CASES:
        assert (
            case["origin"] in allowed
        ), f"{case['id']}: origin must be one of {allowed}, got {case['origin']!r}"
    assert not any(case["origin"] == "sanitized_capture" for case in _CASES)


def test_classify_remote_type_is_deterministic() -> None:
    """Idempotence, narrowly defined: identical input always yields a
    bit-for-bit identical result across repeated calls. This is not a claim
    that feeding the output back in as title text is stable — the output
    type (a 3-value enum) isn't the same shape as the input (free text), so
    that would not be a meaningful invariant."""
    for case in _CASES:
        first = classify_remote_type(case["title"], case["description"])
        second = classify_remote_type(case["title"], case["description"])
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
# named here is rejected, including a legitimate future addition (which
# must update this list deliberately) and any not-yet-invented network
# client this list was never written to anticipate.
_ALLOWED_IMPORTS: dict[str, frozenset[str]] = {
    "app/normalization/types.py": frozenset({"__future__", "dataclasses", "enum", "typing"}),
    "app/normalization/remote.py": frozenset(
        {"__future__", "re", "unicodedata", "typing", "app.normalization.types"}
    ),
}


@pytest.mark.parametrize("relative_path", sorted(_ALLOWED_IMPORTS))
def test_import_boundary_allow_list(relative_path: str) -> None:
    """docs/PHASE_RISK_CHECKLIST.md's Phase 3 exit gate: no parser imports
    providers, ORM models, UI code, or network clients. Proven by AST
    inspection against an exact permitted-import allow-list, not a
    deny-list — a deny-list would silently accept any import (e.g.
    `requests`, `aiohttp`, `socket`) it was never written to name."""
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
    fail-closed: a network client that was never written into any
    allow-list is rejected on its own terms, not merely absent from a
    deny-list that would have silently let it through."""
    synthetic_source = "import requests\n"
    imports = _imported_module_names(synthetic_source)
    allowed = _ALLOWED_IMPORTS["app/normalization/remote.py"]
    assert imports == ["requests"]
    assert not all(name in allowed for name in imports)
