import ast
import json
from pathlib import Path
from typing import Any, cast

import pytest

from app.normalization.skills import (
    SkillMatch,
    _cue_sentence_spans,
    _go_list_neighbor_rescue,
    _has_go_role_relevance_cue,
    _is_covered_terminator_boundary,
    _is_region_ending_boundary,
    _segments_with_offsets,
    _sentence_containing,
    classify_skills,
)
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
# Region-ending vs. anchor-start boundary helpers -- unit-level, direct
# coverage of the corrected mechanism (Sol's finding: a punctuation run
# followed by non-covered Unicode whitespace must still end an anchored
# region, fail-closed, rather than being skipped as "not genuine" and
# letting the region extend across the clause boundary). These two
# helpers are deliberately asymmetric: anchor-start stays strict
# (covered-whitespace-only, since creating an anchor grants extra
# permission and must stay hard to trigger), while region-ending is
# liberal (any Unicode whitespace, since a region also grants extra
# permission and must be hard to accidentally over-extend).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("char", "expected"),
    [
        ("\t", True),
        ("\n", True),
        ("\r", True),
        (" ", True),
        ("\u00a0", False),  # no-break space
        ("\u000b", False),  # vertical tab
        ("\u000c", False),  # form feed
        ("\u2003", False),  # em space
        ("\u200b", False),  # zero-width space (category Cf)
        ("\ufeff", False),  # BOM / zero-width no-break space (category Cf)
        ("\u180e", False),  # Mongolian vowel separator (category Cf)
        ("j", False),
        ("5", False),
        (".", False),
    ],
)
def test_is_covered_terminator_boundary_is_strict(char: str, expected: bool) -> None:
    """Format characters (category Cf) must never make a position eligible
    to *start* a new anchor -- only `_is_region_ending_boundary` (below)
    is widened for them."""
    text = f".{char}rest"
    assert _is_covered_terminator_boundary(text, 1) is expected


def test_is_covered_terminator_boundary_true_at_end_of_string() -> None:
    assert _is_covered_terminator_boundary(".", 1) is True


@pytest.mark.parametrize(
    ("char", "expected"),
    [
        ("\t", True),
        ("\n", True),
        ("\r", True),
        (" ", True),
        ("\u00a0", True),  # no-break space
        ("\u000b", True),  # vertical tab
        ("\u000c", True),  # form feed
        ("\u2003", True),  # em space
        ("\u200b", True),  # zero-width space (category Cf) -- this correction
        ("\ufeff", True),  # BOM / zero-width no-break space (category Cf)
        ("\u180e", True),  # Mongolian vowel separator (category Cf)
        ("j", False),
        ("5", False),
        (".", False),
    ],
)
def test_is_region_ending_boundary_is_liberal(char: str, expected: bool) -> None:
    """Any Unicode whitespace character, and any Unicode format character
    (category Cf), ends a region -- an ordinary letter, digit, or bare
    punctuation character never does."""
    text = f".{char}rest"
    assert _is_region_ending_boundary(text, 1) is expected


def test_is_region_ending_boundary_true_at_end_of_string() -> None:
    assert _is_region_ending_boundary(".", 1) is True


def test_region_ending_boundary_is_strictly_more_permissive_than_anchor_start() -> None:
    """Every character the strict (anchor-start) form accepts, the liberal
    (region-ending) form must also accept -- proving the widening is
    additive, never a narrowing that could reintroduce a different gap."""
    probe_chars = [
        "\t",
        "\n",
        "\r",
        " ",
        "\u00a0",
        "\u000b",
        "\u000c",
        "\u2003",
        "\u200b",
        "\ufeff",
        "\u180e",
        "j",
        "5",
        ".",
    ]
    for char in probe_chars:
        text = f".{char}rest"
        if _is_covered_terminator_boundary(text, 1):
            assert _is_region_ending_boundary(
                text, 1
            ), f"{char!r} is accepted by the strict form but rejected by the liberal one"


def test_region_ending_boundary_node_dot_js_internal_period_is_non_terminating() -> None:
    """Direct, isolated proof that the internal period in 'Node.js' is
    never a region-ending boundary either way -- it is followed by 'j',
    neither whitespace, format, nor end-of-input."""
    text = "Node.js"
    period_end = text.index(".") + 1
    assert text[period_end] == "j"
    assert _is_region_ending_boundary(text, period_end) is False
    assert _is_covered_terminator_boundary(text, period_end) is False


def test_region_ending_boundary_ordinary_letter_and_digit_are_non_terminating() -> None:
    """Direct, isolated proof that a punctuation run followed by an
    ordinary letter or digit never ends a region, matching the
    fixture-level positive controls."""
    assert _is_region_ending_boundary("e.g.Python", 2) is False  # '.' before 'g'
    assert _is_region_ending_boundary("v1.2Python", 3) is False  # '.' before '2'


# ---------------------------------------------------------------------------
# Go-only list-neighbor rescue -- unit-level, direct coverage of each
# mechanical conjunct in isolation, supplementing the fixture-driven
# end-to-end cases above.
# ---------------------------------------------------------------------------
def test_segments_with_offsets_preserves_empty_segment_without_skipping() -> None:
    """A double delimiter (`",,"`) must produce a real, empty entry at its
    own position -- never be silently collapsed or skipped -- so the
    rescue rule's neighbor lookup can see "the immediately adjacent
    segment is empty" rather than reaching past it."""
    text = "Python,,Go"
    segments = _segments_with_offsets(text)
    assert [tokens for _offset, tokens in segments] == [["Python"], [], ["Go"]]


def test_segments_with_offsets_offsets_point_at_raw_segment_start() -> None:
    text = "Python, Go, Java"
    segments = _segments_with_offsets(text)
    offsets = [offset for offset, _tokens in segments]
    assert offsets == [0, 7, 11]
    assert text[offsets[1] :].startswith(" Go")


def test_cue_sentence_spans_splits_on_newline_and_terminator_only() -> None:
    text = "First sentence. Second sentence\nThird line"
    spans = _cue_sentence_spans(text)
    assert [text[start:end] for start, end in spans] == [
        "First sentence.",
        " Second sentence\n",
        "Third line",
    ]


def test_cue_sentence_spans_never_splits_on_segment_delimiters() -> None:
    """A comma, pipe, colon, or slash must never end a cue-scope sentence
    -- only a newline or a genuine `.!?` terminator run does."""
    text = "Skills: Python, Go | Java / Ruby"
    spans = _cue_sentence_spans(text)
    assert len(spans) == 1
    assert spans[0] == (0, len(text))


def test_sentence_containing_returns_the_correct_span() -> None:
    text = "First sentence. Second sentence."
    spans = _cue_sentence_spans(text)
    assert _sentence_containing(spans, text, 0) == "First sentence."
    assert _sentence_containing(spans, text, len("First sentence.")) == " Second sentence."
    assert _sentence_containing(spans, text, len(text) - 1) == " Second sentence."


def test_has_go_role_relevance_cue_accepts_exact_token_subsequence() -> None:
    assert _has_go_role_relevance_cue("We value production experience here.") is True
    assert _has_go_role_relevance_cue("Strong coding ability is required.") is True
    assert _has_go_role_relevance_cue("Please be fluent in our tooling.") is True


def test_has_go_role_relevance_cue_rejects_substring_lookalike() -> None:
    """'encoding ability' must never satisfy the 'coding ability' cue --
    this is an exact token-subsequence match, never a raw substring
    search."""
    assert _has_go_role_relevance_cue("Our encoding ability is excellent.") is False


def test_has_go_role_relevance_cue_rejects_weak_product_company_phrases() -> None:
    assert _has_go_role_relevance_cue("Our product supports these programming languages.") is False
    assert _has_go_role_relevance_cue("Our technology stack is modern.") is False
    assert _has_go_role_relevance_cue("Our tech stack includes many tools.") is False


def test_has_go_role_relevance_cue_handles_trailing_colon() -> None:
    """A cue word immediately followed by a colon (introducing the list it
    describes) must still be recognized -- the colon is stripped, specific
    to cue tokenization only."""
    assert _has_go_role_relevance_cue("Required: production experience: five years.") is True


def test_go_list_neighbor_rescue_unit_level_boundary_vs_elsewhere_in_segment() -> None:
    """Direct, isolated proof (supplementing the fixture-level case) that
    only the boundary-touching token of an adjacent segment is ever
    consulted -- a match elsewhere in that same segment never counts."""
    taxonomy = load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)
    text = "Production experience with Ruby, Go, great Python skills a plus."
    result = _go_list_neighbor_rescue(text, taxonomy)
    assert "golang" not in result


def test_go_list_neighbor_rescue_unit_level_cross_sentence_cue_rejected() -> None:
    """Direct, isolated proof that a cue in a different cue-scoped sentence
    never authorizes the rescue, even with a genuine boundary-adjacent
    neighbor in the go-segment's own sentence."""
    taxonomy = load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)
    text = "We value production experience. Our team enjoys trivia, Go, Python meetups."
    result = _go_list_neighbor_rescue(text, taxonomy)
    assert "golang" not in result


def test_go_list_neighbor_rescue_never_applies_to_c_r_or_node() -> None:
    taxonomy = load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)
    for ambiguous_word in ("C", "R", "Node"):
        text = f"Production experience with Python, {ambiguous_word}, and Java."
        result = _go_list_neighbor_rescue(text, taxonomy)
        assert result == {}, f"{ambiguous_word} must never be rescued by this go-only rule"


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
            "unicodedata",
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
