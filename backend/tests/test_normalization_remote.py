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


_DISALLOWED_IMPORT_PREFIXES = (
    "app.providers",
    "app.db",
    "app.ingestion",
    "app.services",
    "app.api",
    "sqlalchemy",
    "asyncpg",
    "alembic",
    "httpx",
    "fastapi",
)
_CHECKED_MODULES = ("app/normalization/remote.py", "app/normalization/types.py")


def test_import_boundary() -> None:
    """docs/PHASE_RISK_CHECKLIST.md's Phase 3 exit gate: no parser imports
    providers, ORM models, UI code, or network clients. Proven by AST
    inspection of the actual source files, not merely a docstring claim
    that could silently go stale."""
    backend_root = Path(__file__).resolve().parent.parent
    for relative_path in _CHECKED_MODULES:
        source_path = backend_root / relative_path
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        imported_names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_names.append(node.module)
        for name in imported_names:
            assert not name.startswith(_DISALLOWED_IMPORT_PREFIXES), (
                f"{relative_path} imports {name!r}, violating the Phase 3 "
                "no-provider/no-database/no-network import boundary"
            )
