"""Unit contract for the pure `normalize_posting` composition (Phase 4 S2,
docs/DECISIONS/0014-pure-posting-composition-and-scoped-d2.md): pre-parser
validation, exact call order and wiring, same-object pass-through, exception
propagation, salary absence, the exact import allow-list, and synthetic edge
cases. Realistic-output (D2) protection lives in
`tests/test_normalization_posting_realistic.py`.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
from typing import Any

import pytest

from app.normalization import posting
from app.normalization.employment import classify_employment_type
from app.normalization.experience import classify_experience
from app.normalization.location import classify_location
from app.normalization.posting import NormalizedPosting, PostingInputs, normalize_posting
from app.normalization.remote import classify_remote_type
from app.normalization.seniority import classify_seniority
from app.normalization.skills import classify_skills
from app.normalization.taxonomy import DEFAULT_SKILLS_TAXONOMY_PATH, TaxonomyIndex, load_taxonomy
from app.normalization.titles import TitleOutcome, classify_title
from app.normalization.types import Provenance

_POSTING_PATH = Path(__file__).resolve().parent.parent / "app" / "normalization" / "posting.py"

_PARSER_NAMES = (
    "classify_title",
    "classify_remote_type",
    "classify_employment_type",
    "classify_seniority",
    "classify_experience",
    "classify_location",
    "classify_skills",
)


@pytest.fixture(scope="module")
def taxonomy() -> TaxonomyIndex:
    return load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)


class _Spies:
    """Replaces every parser name in `app.normalization.posting` with a spy
    that records `(name, args, kwargs)` and returns a unique sentinel (or a
    list of unique sentinels for skills)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, raise_at: str | None = None) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.returned: dict[str, Any] = {}
        self.raised: dict[str, BaseException] = {}
        for name in _PARSER_NAMES:
            monkeypatch.setattr(posting, name, self._make(name, raise_at))

    def _make(self, name: str, raise_at: str | None) -> Any:
        def spy(*args: Any, **kwargs: Any) -> Any:
            self.calls.append((name, args, kwargs))
            if name == raise_at:
                error = RuntimeError("synthetic parser failure")
                self.raised[name] = error
                raise error
            value: Any = [object(), object(), object()] if name == "classify_skills" else object()
            self.returned[name] = value
            return value

        return spy


# --- data shape and salary absence ---


def test_posting_inputs_fields_are_exact_and_frozen() -> None:
    assert [f.name for f in dataclasses.fields(PostingInputs)] == [
        "title",
        "description",
        "location",
    ]
    inputs = PostingInputs(title="a", description="b", location="c")
    with pytest.raises(dataclasses.FrozenInstanceError):
        inputs.title = "x"  # type: ignore[misc]


def test_normalized_posting_fields_are_exact_with_no_salary() -> None:
    names = [f.name for f in dataclasses.fields(NormalizedPosting)]
    assert names == [
        "inputs",
        "title",
        "remote_type",
        "employment_type",
        "seniority",
        "experience",
        "location",
        "skills",
    ]
    assert not hasattr(NormalizedPosting, "salary")
    assert not any("salary" in name or "compensation" in name for name in names)
    assert dataclasses.is_dataclass(NormalizedPosting)
    assert NormalizedPosting.__dataclass_params__.frozen  # type: ignore[attr-defined]


def test_posting_inputs_has_no_compensation_field() -> None:
    names = {f.name for f in dataclasses.fields(PostingInputs)}
    assert not any("salary" in name or "compensation" in name for name in names)


def test_result_has_no_salary_attribute(taxonomy: TaxonomyIndex) -> None:
    result = normalize_posting(PostingInputs(None, None, None), taxonomy=taxonomy)
    assert not hasattr(result, "salary")


# --- import boundary (exact allow-list) ---


def _imported_module_names(source: str) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append("." * node.level + (node.module or ""))
    return names


_ALLOWED_IMPORTS = frozenset(
    {
        "__future__",
        "dataclasses",
        "app.normalization.employment",
        "app.normalization.experience",
        "app.normalization.location",
        "app.normalization.remote",
        "app.normalization.seniority",
        "app.normalization.skills",
        "app.normalization.taxonomy",
        "app.normalization.titles",
        "app.normalization.types",
    }
)


def test_import_boundary_is_the_exact_allow_list() -> None:
    """Fail-closed exact allow-list: no salary parser, provider, ingestion,
    ORM, network client, logging, I/O, or `scripts` import."""
    imports = _imported_module_names(_POSTING_PATH.read_text(encoding="utf-8"))
    for name in imports:
        assert name in _ALLOWED_IMPORTS, f"posting.py imports {name!r}, not on its allow-list"
    assert set(imports) == _ALLOWED_IMPORTS
    assert len(imports) == len(set(imports))


_DYNAMIC_IMPORT_NAMES = frozenset({"__import__", "importlib", "import_module", "exec", "eval"})


def _dynamic_import_names(source: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name) and node.id in _DYNAMIC_IMPORT_NAMES:
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in _DYNAMIC_IMPORT_NAMES:
            found.add(node.attr)
    return found


def test_module_uses_no_dynamic_import_or_execution() -> None:
    """Self-review finding P3-2: the static allow-list above cannot see
    `__import__`, `importlib`, `exec`, or `eval`, so their absence is
    asserted separately."""
    assert _dynamic_import_names(_POSTING_PATH.read_text(encoding="utf-8")) == set()


@pytest.mark.parametrize(
    "synthetic_source",
    [
        '__import__("app.normalization.salary")\n',
        'importlib.import_module("app.normalization.salary")\n',
        'exec("import app.normalization.salary")\n',
    ],
)
def test_dynamic_import_check_rejects_synthetic_sources(synthetic_source: str) -> None:
    assert _dynamic_import_names(synthetic_source)


@pytest.mark.parametrize(
    "synthetic_source",
    [
        "from app.normalization.salary import classify_salary\n",
        "from .salary import classify_salary\n",
        "from app.schemas.discovered_job import DiscoveredJob\n",
        "from app.providers.greenhouse import GreenhouseJobBoardProvider\n",
        "import httpx\n",
        "import logging\n",
        "from scripts.evaluate_phase3_corpus import load_corpus\n",
    ],
)
def test_import_boundary_rejects_forbidden_imports(synthetic_source: str) -> None:
    imports = _imported_module_names(synthetic_source)
    assert imports
    assert not all(name in _ALLOWED_IMPORTS for name in imports)


# --- validation before any parser call ---


@pytest.mark.parametrize(
    "argument",
    [None, {"title": "a", "description": None, "location": None}, ("a", None, None), "a"],
    ids=["none", "dict", "tuple", "str"],
)
def test_non_posting_inputs_argument_is_rejected_before_any_parser(
    argument: Any, monkeypatch: pytest.MonkeyPatch, taxonomy: TaxonomyIndex
) -> None:
    spies = _Spies(monkeypatch)
    with pytest.raises(TypeError) as excinfo:
        normalize_posting(argument, taxonomy=taxonomy)
    assert str(excinfo.value) == "normalize_posting requires a PostingInputs instance"
    assert spies.calls == []


def test_duck_typed_lookalike_is_rejected(
    monkeypatch: pytest.MonkeyPatch, taxonomy: TaxonomyIndex
) -> None:
    @dataclasses.dataclass(frozen=True)
    class Lookalike:
        title: str | None
        description: str | None
        location: str | None

    spies = _Spies(monkeypatch)
    with pytest.raises(TypeError):
        normalize_posting(Lookalike("a", None, None), taxonomy=taxonomy)  # type: ignore[arg-type]
    assert spies.calls == []


@pytest.mark.parametrize("field", ["title", "description", "location"])
@pytest.mark.parametrize(
    "bad_value", [b"bytes", 7, 1.5, ["x"], object()], ids=["bytes", "int", "float", "list", "obj"]
)
def test_non_str_field_is_rejected_before_any_parser_with_a_fixed_message(
    field: str, bad_value: Any, monkeypatch: pytest.MonkeyPatch, taxonomy: TaxonomyIndex
) -> None:
    values: dict[str, Any] = {"title": "t", "description": "d", "location": "l"}
    values[field] = bad_value
    spies = _Spies(monkeypatch)
    with pytest.raises(TypeError) as excinfo:
        normalize_posting(PostingInputs(**values), taxonomy=taxonomy)
    assert str(excinfo.value) == "PostingInputs fields must each be a str or None"
    assert repr(bad_value) not in str(excinfo.value)
    assert spies.calls == []


def test_parsers_receive_exactly_the_values_that_were_validated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Self-review finding P3-1 regression: a `PostingInputs` subclass whose
    attribute reads change between reads must not let an unvalidated value
    reach a parser. Every parser receives the values read once and
    validated, never a second read."""
    reads: dict[str, int] = {}

    class ShiftingInputs(PostingInputs):
        def __getattribute__(self, name: str) -> Any:
            if name in {"title", "description", "location"}:
                reads[name] = reads.get(name, 0) + 1
                return "ok" if reads[name] == 1 else 123
            return super().__getattribute__(name)

    spies = _Spies(monkeypatch)
    normalize_posting(ShiftingInputs("t", "d", "l"), taxonomy=TaxonomyIndex({}))
    received = [value for _, args, _ in spies.calls for value in args]
    assert received
    assert all(value == "ok" for value in received)
    assert reads == {"title": 1, "description": 1, "location": 1}


def test_taxonomy_is_a_required_keyword_argument(taxonomy: TaxonomyIndex) -> None:
    inputs = PostingInputs(None, None, None)
    with pytest.raises(TypeError):
        normalize_posting(inputs, taxonomy)  # type: ignore[misc]
    with pytest.raises(TypeError):
        normalize_posting(inputs)  # type: ignore[call-arg]


def test_posting_inputs_performs_no_normalization() -> None:
    inputs = PostingInputs(title="  Senior Engineer \n", description="​", location=" X ")
    assert inputs.title == "  Senior Engineer \n"
    assert inputs.description == "​"
    assert inputs.location == " X "


# --- call order, wiring, and pass-through ---


def test_parsers_are_called_once_each_in_the_exact_order_with_exact_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spies = _Spies(monkeypatch)
    taxonomy_sentinel: Any = object()
    inputs = PostingInputs(title="T", description="D", location="L")
    normalize_posting(inputs, taxonomy=taxonomy_sentinel)
    assert [name for name, _, _ in spies.calls] == list(_PARSER_NAMES)
    by_name = {name: (args, kwargs) for name, args, kwargs in spies.calls}
    assert by_name["classify_title"] == (("T",), {})
    for name in (
        "classify_remote_type",
        "classify_employment_type",
        "classify_seniority",
        "classify_experience",
    ):
        assert by_name[name] == (("T", "D"), {})
    assert by_name["classify_location"] == (("L",), {})
    args, kwargs = by_name["classify_skills"]
    assert args == ("T", "D")
    assert set(kwargs) == {"taxonomy"}
    assert kwargs["taxonomy"] is taxonomy_sentinel


def test_results_pass_through_as_the_identical_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    spies = _Spies(monkeypatch)
    inputs = PostingInputs(title="T", description="D", location="L")
    result = normalize_posting(inputs, taxonomy=TaxonomyIndex({}))
    assert result.inputs is inputs
    assert result.title is spies.returned["classify_title"]
    assert result.remote_type is spies.returned["classify_remote_type"]
    assert result.employment_type is spies.returned["classify_employment_type"]
    assert result.seniority is spies.returned["classify_seniority"]
    assert result.experience is spies.returned["classify_experience"]
    assert result.location is spies.returned["classify_location"]
    skills_list = spies.returned["classify_skills"]
    assert isinstance(result.skills, tuple)
    assert result.skills is not skills_list
    assert len(result.skills) == len(skills_list)
    assert all(result.skills[i] is skills_list[i] for i in range(len(skills_list)))


def test_real_results_are_unmodified_and_skill_matches_are_not_copied(
    monkeypatch: pytest.MonkeyPatch, taxonomy: TaxonomyIndex
) -> None:
    captured: dict[str, Any] = {}
    real = {name: getattr(posting, name) for name in _PARSER_NAMES}
    for name in _PARSER_NAMES:

        def capture(*args: Any, _name: str = name, **kwargs: Any) -> Any:
            value = real[_name](*args, **kwargs)
            captured[_name] = (value, repr(value))
            return value

        monkeypatch.setattr(posting, name, capture)
    inputs = PostingInputs(
        title="Senior Software Engineer",
        description="Full-time. 5+ years of experience with Python and Kubernetes.",
        location="London, UK",
    )
    result = normalize_posting(inputs, taxonomy=taxonomy)
    fields = {
        "classify_title": result.title,
        "classify_remote_type": result.remote_type,
        "classify_employment_type": result.employment_type,
        "classify_seniority": result.seniority,
        "classify_experience": result.experience,
        "classify_location": result.location,
    }
    for name, value in fields.items():
        original, original_repr = captured[name]
        assert value is original
        assert repr(value) == original_repr
    skills_list, skills_repr = captured["classify_skills"]
    assert skills_list
    assert len(result.skills) == len(skills_list)
    assert all(result.skills[i] is skills_list[i] for i in range(len(skills_list)))
    assert repr(list(result.skills)) == skills_repr


@pytest.mark.parametrize("raise_at", _PARSER_NAMES)
def test_parser_exception_propagates_and_no_later_parser_runs(
    raise_at: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    spies = _Spies(monkeypatch, raise_at=raise_at)
    with pytest.raises(RuntimeError) as excinfo:
        normalize_posting(PostingInputs("T", "D", "L"), taxonomy=TaxonomyIndex({}))
    assert excinfo.value is spies.raised[raise_at]
    position = _PARSER_NAMES.index(raise_at)
    assert [name for name, _, _ in spies.calls] == list(_PARSER_NAMES[: position + 1])


# --- synthetic edge cases with the real parsers ---


def _direct(inputs: PostingInputs, taxonomy: TaxonomyIndex) -> dict[str, Any]:
    t, d = inputs.title, inputs.description
    return {
        "title": classify_title(t),
        "remote_type": classify_remote_type(t, d),
        "employment_type": classify_employment_type(t, d),
        "seniority": classify_seniority(t, d),
        "experience": classify_experience(t, d),
        "location": classify_location(inputs.location),
        "skills": tuple(classify_skills(t, d, taxonomy=taxonomy)),
    }


_SYNTHETIC = {
    "all-none": PostingInputs(None, None, None),
    "whitespace-only": PostingInputs("  \t", "\n\r ", " "),
    "format-chars-only": PostingInputs("​", "﻿", "​​"),
    "title-only": PostingInputs("Staff Backend Engineer", None, None),
    "description-only": PostingInputs(None, "Part-time role. Remote. Uses Python.", None),
    "location-only": PostingInputs(None, None, "Bangalore, India"),
    "all-fields": PostingInputs(
        "Senior Product Manager", "Hybrid, full-time. Experience with SQL.", "London, UK"
    ),
}


@pytest.mark.parametrize("case", sorted(_SYNTHETIC))
def test_composition_equals_direct_parser_calls_on_synthetic_inputs(
    case: str, taxonomy: TaxonomyIndex
) -> None:
    inputs = _SYNTHETIC[case]
    result = normalize_posting(inputs, taxonomy=taxonomy)
    assert result.inputs is inputs
    expected = _direct(inputs, taxonomy)
    assert {name: getattr(result, name) for name in expected} == expected


@pytest.mark.parametrize(
    ("case", "title_outcome"),
    [
        ("all-none", TitleOutcome.NO_TITLE),
        ("whitespace-only", TitleOutcome.NO_TITLE),
        # classify_title's own approved contract fails closed on a
        # format-character-only title; composition passes that through.
        ("format-chars-only", TitleOutcome.UNSUPPORTED),
    ],
)
def test_empty_inputs_yield_only_unavailable_results(
    case: str, title_outcome: TitleOutcome, taxonomy: TaxonomyIndex
) -> None:
    result = normalize_posting(_SYNTHETIC[case], taxonomy=taxonomy)
    assert result.title.outcome is title_outcome
    for value in (
        result.title.canonical_title,
        result.title.role_family,
        result.remote_type,
        result.employment_type,
        result.seniority,
        result.experience.minimum,
        result.experience.maximum,
        result.location.city,
        result.location.state,
        result.location.country,
        result.location.postal_code,
    ):
        assert value.value is None
        assert value.provenance is Provenance.UNAVAILABLE
    assert result.skills == ()


@pytest.mark.parametrize("case", sorted(_SYNTHETIC))
def test_composition_is_deterministic(case: str, taxonomy: TaxonomyIndex) -> None:
    inputs = _SYNTHETIC[case]
    assert normalize_posting(inputs, taxonomy=taxonomy) == normalize_posting(
        inputs, taxonomy=taxonomy
    )


@pytest.mark.parametrize("case", sorted(_SYNTHETIC))
def test_synthetic_outputs_never_claim_explicit_or_structured_provenance(
    case: str, taxonomy: TaxonomyIndex
) -> None:
    result = normalize_posting(_SYNTHETIC[case], taxonomy=taxonomy)
    provenances = {
        result.title.canonical_title.provenance,
        result.title.role_family.provenance,
        result.remote_type.provenance,
        result.employment_type.provenance,
        result.seniority.provenance,
        result.experience.minimum.provenance,
        result.experience.maximum.provenance,
        result.location.city.provenance,
        result.location.state.provenance,
        result.location.country.provenance,
        result.location.postal_code.provenance,
    } | {match.provenance for match in result.skills}
    assert Provenance.EXPLICIT_SOURCE not in provenances
    assert Provenance.STRUCTURED_METADATA not in provenances
