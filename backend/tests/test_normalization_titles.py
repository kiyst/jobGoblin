import ast
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, cast

import pytest

from app.normalization import titles as t
from app.normalization.titles import (
    CANONICAL_TO_FAMILY,
    LATER_TERMINAL_ROLE_DESIGNATORS,
    PREFIX_BLOCKERS,
    PREFIX_ROLE_DESIGNATORS,
    TITLE_VOCABULARY_VERSION,
    RoleFamily,
    TitleOutcome,
    TitleResult,
    TitleVocabularyError,
    classify_title,
)
from app.normalization.types import NormalizationResult, Provenance

_TESTS_DIR = Path(__file__).resolve().parent
_FIXTURES_PATH = _TESTS_DIR / "fixtures" / "normalization" / "title_cases.json"
_CORPUS_PATH = _TESTS_DIR / "fixtures" / "evaluation" / "phase3_realistic_corpus.json"
_MODULE_PATH = _TESTS_DIR.parent / "app" / "normalization" / "titles.py"


def _load_cases() -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], json.loads(_FIXTURES_PATH.read_text(encoding="utf-8")))


_CASES = _load_cases()
_REALISTIC = [case for case in _CASES if case["category"] == "realistic"]


def _outcome(title: str | None) -> TitleOutcome:
    return classify_title(title).outcome


def _assert_absent(result: TitleResult, outcome: TitleOutcome) -> None:
    assert result.outcome is outcome
    assert result.canonical_title == NormalizationResult(None, Provenance.UNAVAILABLE)
    assert result.role_family == NormalizationResult(None, Provenance.UNAVAILABLE)


def _assert_matched(result: TitleResult, canonical: str) -> None:
    assert result.outcome is TitleOutcome.MATCHED
    assert result.canonical_title == NormalizationResult(canonical, Provenance.INFERRED)
    assert result.role_family == NormalizationResult(
        CANONICAL_TO_FAMILY[canonical], Provenance.INFERRED
    )


# ---------------------------------------------------------------------------
# Fixture-driven cases.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _CASES, ids=[case["id"] for case in _CASES])
def test_title_classifier_matches_fixture_expectation(case: dict[str, Any]) -> None:
    result = classify_title(case["title"])
    assert result.outcome is TitleOutcome(case["expected_outcome"]), case["note"]
    if case["expected_outcome"] == "matched":
        _assert_matched(result, case["expected_canonical_title"])
        assert result.role_family.value is RoleFamily(case["expected_role_family"])
    else:
        assert case["expected_canonical_title"] is None
        assert case["expected_role_family"] is None
        _assert_absent(result, result.outcome)


def test_fixture_schema_is_closed_and_honestly_labeled() -> None:
    fields = {
        "id",
        "category",
        "origin",
        "record_id",
        "title",
        "expected_outcome",
        "expected_canonical_title",
        "expected_role_family",
        "note",
    }
    categories = {
        "positive",
        "negative",
        "boundary",
        "ambiguity",
        "collision",
        "unicode",
        "realistic",
    }
    ids = [case["id"] for case in _CASES]
    assert len(ids) == len(set(ids))
    for case in _CASES:
        assert set(case) == fields, case["id"]
        assert case["category"] in categories, case["id"]
        assert case["expected_outcome"] in {o.value for o in TitleOutcome}, case["id"]
        if case["category"] == "realistic":
            assert case["origin"] == "realistic_corpus_title", case["id"]
            assert isinstance(case["record_id"], str), case["id"]
            assert "smoke/regression" in case["note"], case["id"]
        else:
            assert case["origin"] in {"synthetic_representative", "synthetic_adversarial"}
            assert case["record_id"] is None, case["id"]
        if case["expected_canonical_title"] is not None:
            assert (
                CANONICAL_TO_FAMILY[case["expected_canonical_title"]].value
                == case["expected_role_family"]
            )
    for category in categories:
        assert any(case["category"] == category for case in _CASES), category


# ---------------------------------------------------------------------------
# A10: realistic titles -- primary-reviewer-approved smoke/regression
# expectations only, byte-identical to the frozen corpus.
# ---------------------------------------------------------------------------


def test_realistic_titles_are_byte_identical_to_the_frozen_corpus() -> None:
    corpus = json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))
    corpus_titles = {record["id"]: record["fields"]["title"] for record in corpus}
    assert len(_REALISTIC) == 30
    assert sorted(case["record_id"] for case in _REALISTIC) == sorted(corpus_titles)
    for case in _REALISTIC:
        assert case["title"].encode("utf-8") == corpus_titles[case["record_id"]].encode("utf-8")


def test_realistic_titles_aggregate_and_exact_non_matched_records() -> None:
    counts = Counter(_outcome(case["title"]) for case in _REALISTIC)
    assert counts == {
        TitleOutcome.MATCHED: 22,
        TitleOutcome.UNSUPPORTED: 6,
        TitleOutcome.AMBIGUOUS: 2,
    }
    by_outcome: dict[TitleOutcome, set[str]] = {}
    for case in _REALISTIC:
        by_outcome.setdefault(_outcome(case["title"]), set()).add(case["record_id"])
    assert by_outcome[TitleOutcome.AMBIGUOUS] == {"anthropic:4595463008", "anthropic:4610158008"}
    assert by_outcome[TitleOutcome.UNSUPPORTED] == {
        "gitlab:8396674002",
        "gitlab:8500014002",
        "gitlab:8512432002",
        "anthropic:4020350008",
        "anthropic:4461444008",
        "discord:8575166002",
    }


def test_module_contains_no_record_ids_employer_names_or_splits() -> None:
    """A12: no record IDs, employer names, corpus splits, or per-title
    exceptions. (The module docstring may name the word "holdout" only to
    disclaim it, so splits are checked against code string constants.)"""
    source = _MODULE_PATH.read_text(encoding="utf-8")
    for forbidden in ("gitlab", "anthropic", "discord"):
        assert forbidden not in source.lower(), forbidden
    for case in _REALISTIC:
        assert case["record_id"].split(":", 1)[1] not in source
        assert case["title"].strip().lower() not in source.lower()
    tree = ast.parse(source)
    docstring = ast.get_docstring(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value == docstring or "\n" in node.value:
                continue
            assert node.value.lower() not in {"dev", "holdout", "split"}, node.value


# ---------------------------------------------------------------------------
# Final mutation-witness inventory (each also mutation-proven ad hoc; see
# docs/LLM_HANDOFF.md). One dedicated test per witness.
# ---------------------------------------------------------------------------


def test_witness_01_head_segment_precedence() -> None:
    _assert_absent(classify_title("Recruiter / Software Engineer"), TitleOutcome.AMBIGUOUS)


def test_witness_02_prefix_blockers_isolating() -> None:
    _assert_absent(classify_title("Data and Software Engineer"), TitleOutcome.AMBIGUOUS)


def test_witness_03_prefix_role_designators() -> None:
    _assert_absent(classify_title("Architect Software Engineer"), TitleOutcome.AMBIGUOUS)


def test_witness_03_positive_control_lead_prefix() -> None:
    _assert_matched(classify_title("Lead Software Engineer"), "software-engineer")


def test_witness_04_foreign_family_signal() -> None:
    _assert_absent(classify_title("Security Software Engineer"), TitleOutcome.AMBIGUOUS)


def test_witness_05_format_character_rejection() -> None:
    _assert_absent(classify_title("Software​Engineer"), TitleOutcome.UNSUPPORTED)


def test_witness_06_bounded_compatibility_whitelist() -> None:
    _assert_absent(classify_title("Softwarℯ Engineer"), TitleOutcome.UNSUPPORTED)


def test_witness_07_no_plural_folding() -> None:
    _assert_absent(classify_title("Software Engineers"), TitleOutcome.UNSUPPORTED)


def test_witness_08_later_different_canonical() -> None:
    _assert_absent(classify_title("Software Engineer / Product Manager"), TitleOutcome.AMBIGUOUS)


def test_witness_09_later_unmatched_terminal_role() -> None:
    _assert_absent(classify_title("Research Engineer / Scientist"), TitleOutcome.AMBIGUOUS)


def test_witness_09_positive_control_developer_experience() -> None:
    _assert_matched(
        classify_title("Staff Backend Engineer, Developer Experience"), "software-engineer"
    )


def test_witness_10_approved_decoration_stripping() -> None:
    _assert_matched(
        classify_title("[Expression of Interest] Research Engineer"), "research-engineer"
    )


def test_witness_11_closed_decoration_boundary() -> None:
    _assert_absent(classify_title("[Product Manager] Software Engineer"), TitleOutcome.AMBIGUOUS)


def test_witness_12_exact_vocabulary_family_invariant() -> None:
    with pytest.raises(ValueError) as excinfo:
        TitleResult(
            canonical_title=NormalizationResult("software-engineer", Provenance.INFERRED),
            role_family=NormalizationResult(RoleFamily.SECURITY_ENGINEERING, Provenance.INFERRED),
            outcome=TitleOutcome.MATCHED,
        )
    assert str(excinfo.value) == "TitleResult invariant violated."


# ---------------------------------------------------------------------------
# A1: provenance.
# ---------------------------------------------------------------------------


def test_every_result_uses_only_inferred_or_unavailable_provenance() -> None:
    forbidden = {
        Provenance.DERIVED,
        Provenance.EXPLICIT_SOURCE,
        Provenance.STRUCTURED_METADATA,
        Provenance.PARSED_DESCRIPTION,
    }
    for case in _CASES:
        result = classify_title(case["title"])
        for field in (result.canonical_title, result.role_family):
            assert field.provenance not in forbidden, case["id"]
            expected = (
                Provenance.INFERRED
                if result.outcome is TitleOutcome.MATCHED
                else Provenance.UNAVAILABLE
            )
            assert field.provenance is expected, case["id"]


def test_senior_software_engineer_is_inferred_for_both_fields() -> None:
    result = classify_title("Senior Software Engineer")
    assert result.canonical_title.provenance is Provenance.INFERRED
    assert result.role_family.provenance is Provenance.INFERRED


# ---------------------------------------------------------------------------
# A8: TitleResult invariants.
# ---------------------------------------------------------------------------


def _inferred(value: object) -> NormalizationResult[Any]:
    return NormalizationResult(value, Provenance.INFERRED)


_ABSENT: NormalizationResult[Any] = NormalizationResult(None, Provenance.UNAVAILABLE)


@pytest.mark.parametrize(
    ("canonical", "family", "outcome"),
    [
        (_inferred("invented-valid-slug"), _inferred(RoleFamily.SOFTWARE_ENGINEERING), "matched"),
        (_inferred("software-engineer"), _inferred(RoleFamily.SECURITY_ENGINEERING), "matched"),
        (_inferred("software-engineer"), _inferred("software_engineering"), "matched"),
        (
            NormalizationResult("software-engineer", Provenance.DERIVED),
            _inferred(RoleFamily.SOFTWARE_ENGINEERING),
            "matched",
        ),
        (
            _inferred("software-engineer"),
            NormalizationResult(RoleFamily.SOFTWARE_ENGINEERING, Provenance.EXPLICIT_SOURCE),
            "matched",
        ),
        (_inferred("software-engineer"), _ABSENT, "matched"),
        (_ABSENT, _inferred(RoleFamily.SOFTWARE_ENGINEERING), "matched"),
        (_ABSENT, _ABSENT, "matched"),
        (_inferred("software-engineer"), _ABSENT, "ambiguous"),
        (_ABSENT, _inferred(RoleFamily.SOFTWARE_ENGINEERING), "unsupported"),
        (
            _inferred("software-engineer"),
            _inferred(RoleFamily.SOFTWARE_ENGINEERING),
            "no_title",
        ),
    ],
)
def test_title_result_rejects_invalid_construction(
    canonical: NormalizationResult[Any], family: NormalizationResult[Any], outcome: str
) -> None:
    with pytest.raises(ValueError) as excinfo:
        TitleResult(canonical_title=canonical, role_family=family, outcome=TitleOutcome(outcome))
    assert str(excinfo.value) == "TitleResult invariant violated."


def test_title_result_rejects_raw_string_outcome_and_non_result_fields() -> None:
    good_canonical = _inferred("software-engineer")
    good_family = _inferred(RoleFamily.SOFTWARE_ENGINEERING)
    for kwargs in (
        {"canonical_title": good_canonical, "role_family": good_family, "outcome": "matched"},
        {
            "canonical_title": "software-engineer",
            "role_family": good_family,
            "outcome": TitleOutcome.MATCHED,
        },
        {
            "canonical_title": good_canonical,
            "role_family": RoleFamily.SOFTWARE_ENGINEERING,
            "outcome": TitleOutcome.MATCHED,
        },
    ):
        with pytest.raises(ValueError) as excinfo:
            TitleResult(**kwargs)  # type: ignore[arg-type]
        assert str(excinfo.value) == "TitleResult invariant violated."


def test_title_result_accepts_every_exact_vocabulary_pair() -> None:
    for canonical, family in CANONICAL_TO_FAMILY.items():
        result = TitleResult(
            canonical_title=_inferred(canonical),
            role_family=_inferred(family),
            outcome=TitleOutcome.MATCHED,
        )
        assert result.role_family.value is family
    for outcome in (TitleOutcome.NO_TITLE, TitleOutcome.UNSUPPORTED, TitleOutcome.AMBIGUOUS):
        TitleResult(canonical_title=_ABSENT, role_family=_ABSENT, outcome=outcome)


def test_invariant_error_message_never_contains_input() -> None:
    with pytest.raises(ValueError) as excinfo:
        TitleResult(
            canonical_title=_inferred("secret-looking-slug"),
            role_family=_inferred(RoleFamily.SALES),
            outcome=TitleOutcome.MATCHED,
        )
    assert "secret" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# A9: frozen vocabulary and table validation.
# ---------------------------------------------------------------------------


def test_frozen_vocabulary_is_exactly_the_approved_nine_titles() -> None:
    assert TITLE_VOCABULARY_VERSION == "1"
    assert dict(CANONICAL_TO_FAMILY) == {
        "software-engineer": RoleFamily.SOFTWARE_ENGINEERING,
        "security-engineer": RoleFamily.SECURITY_ENGINEERING,
        "research-engineer": RoleFamily.RESEARCH,
        "research-scientist": RoleFamily.RESEARCH,
        "engineering-manager": RoleFamily.ENGINEERING_MANAGEMENT,
        "engineering-director": RoleFamily.ENGINEERING_MANAGEMENT,
        "product-manager": RoleFamily.PRODUCT_MANAGEMENT,
        "solutions-architect": RoleFamily.SOLUTIONS_ARCHITECTURE,
        "account-executive": RoleFamily.SALES,
    }
    aliases = {alias: canonical for canonical, _f, entry in t._VOCABULARY for alias in entry}
    assert aliases == {
        ("software", "engineer"): "software-engineer",
        ("software", "developer"): "software-engineer",
        ("backend", "engineer"): "software-engineer",
        ("back", "end", "engineer"): "software-engineer",
        ("frontend", "engineer"): "software-engineer",
        ("front", "end", "engineer"): "software-engineer",
        ("full", "stack", "engineer"): "software-engineer",
        ("fullstack", "engineer"): "software-engineer",
        ("security", "engineer"): "security-engineer",
        ("research", "engineer"): "research-engineer",
        ("research", "scientist"): "research-scientist",
        ("engineering", "manager"): "engineering-manager",
        ("director", "of", "engineering"): "engineering-director",
        ("engineering", "director"): "engineering-director",
        ("product", "manager"): "product-manager",
        ("solutions", "architect"): "solutions-architect",
        ("solution", "architect"): "solutions-architect",
        ("account", "executive"): "account-executive",
    }


def test_enums_have_exact_snake_case_values() -> None:
    assert [f.value for f in RoleFamily] == [
        "software_engineering",
        "security_engineering",
        "engineering_management",
        "research",
        "product_management",
        "solutions_architecture",
        "sales",
    ]
    assert [o.value for o in TitleOutcome] == ["matched", "no_title", "unsupported", "ambiguous"]
    for bad in ("", "Software", "software-engineering", "_x", "x_", "a__b", "x1"):
        assert not t._is_snake_case(bad), bad


def test_closed_prefix_and_terminal_tables_are_exact() -> None:
    assert (
        frozenset(
            {
                "recruiter",
                "sourcer",
                "manager",
                "director",
                "head",
                "vp",
                "president",
                "coordinator",
                "partner",
                "consultant",
                "analyst",
                "specialist",
                "intern",
                "assistant",
                "of",
                "for",
                "to",
                "and",
                "or",
                "&",
            }
        )
        == PREFIX_BLOCKERS
    )
    stems = (
        "engineer developer architect scientist manager director executive recruiter "
        "sourcer coordinator partner consultant analyst specialist intern assistant "
        "attorney designer researcher head president vp"
    ).split()
    assert frozenset(stems) | {s + "s" for s in stems} | {"counsel"} == PREFIX_ROLE_DESIGNATORS
    assert "lead" not in PREFIX_ROLE_DESIGNATORS
    assert PREFIX_ROLE_DESIGNATORS | {"lead", "leads"} == LATER_TERMINAL_ROLE_DESIGNATORS
    assert dict(t._TABLES.signal_to_family) == {
        ("software",): RoleFamily.SOFTWARE_ENGINEERING,
        ("backend",): RoleFamily.SOFTWARE_ENGINEERING,
        ("back", "end"): RoleFamily.SOFTWARE_ENGINEERING,
        ("frontend",): RoleFamily.SOFTWARE_ENGINEERING,
        ("front", "end"): RoleFamily.SOFTWARE_ENGINEERING,
        ("fullstack",): RoleFamily.SOFTWARE_ENGINEERING,
        ("full", "stack"): RoleFamily.SOFTWARE_ENGINEERING,
        ("security",): RoleFamily.SECURITY_ENGINEERING,
        ("management",): RoleFamily.ENGINEERING_MANAGEMENT,
        ("research",): RoleFamily.RESEARCH,
        ("product",): RoleFamily.PRODUCT_MANAGEMENT,
        ("solution",): RoleFamily.SOLUTIONS_ARCHITECTURE,
        ("solutions",): RoleFamily.SOLUTIONS_ARCHITECTURE,
        ("architecture",): RoleFamily.SOLUTIONS_ARCHITECTURE,
        ("account",): RoleFamily.SALES,
        ("sales",): RoleFamily.SALES,
    }


def test_public_tables_are_immutable() -> None:
    with pytest.raises(TypeError):
        CANONICAL_TO_FAMILY["invented"] = RoleFamily.SALES  # type: ignore[index]
    with pytest.raises(TypeError):
        t._TABLES.alias_to_canonical[("x",)] = "y"  # type: ignore[index]


_SE = RoleFamily.SOFTWARE_ENGINEERING
_VALID_VOCAB: tuple[Any, ...] = (
    ("alpha-role", _SE, (("alpha", "engineer"),)),
    ("beta-role", RoleFamily.SALES, (("beta", "executive"),)),
)
_VALID_SIGNALS: tuple[Any, ...] = ((_SE, (("alpha",),)), (RoleFamily.SALES, (("beta",),)))


def _compile(
    vocabulary: tuple[Any, ...] = _VALID_VOCAB,
    blockers: tuple[Any, ...] = ("of", "&"),
    designators: tuple[Any, ...] = ("engineer",),
    extra: tuple[Any, ...] = ("lead", "leads"),
    signals: tuple[Any, ...] = _VALID_SIGNALS,
) -> object:
    return t._compile_tables(vocabulary, blockers, designators, extra, signals)


def test_compile_tables_accepts_a_valid_minimal_table() -> None:
    _compile()


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"vocabulary": ()}, id="empty_vocabulary"),
        pytest.param({"vocabulary": (("alpha-role", _SE),)}, id="short_entry"),
        pytest.param(
            {"vocabulary": _VALID_VOCAB + (("alpha-role", _SE, (("gamma", "engineer"),)),)},
            id="duplicate_canonical",
        ),
        pytest.param({"vocabulary": (("Alpha_Role", _SE, (("a", "b"),)),)}, id="bad_slug"),
        pytest.param(
            {"vocabulary": (("alpha-role", "software_engineering", (("a", "b"),)),)},
            id="raw_family_string",
        ),
        pytest.param({"vocabulary": (("alpha-role", _SE, ()),)}, id="empty_aliases"),
        pytest.param({"vocabulary": (("alpha-role", _SE, ((),)),)}, id="empty_alias_tuple"),
        pytest.param(
            {"vocabulary": (("alpha-role", _SE, (("Alpha", "engineer"),)),)},
            id="unnormalized_alias_token",
        ),
        pytest.param(
            {"vocabulary": (("alpha-role", _SE, (("alpha", ""),)),)}, id="empty_alias_token"
        ),
        pytest.param(
            {"vocabulary": (("alpha-role", _SE, (("alpha", "&"),)),)}, id="ampersand_in_alias"
        ),
        pytest.param(
            {"vocabulary": (("alpha-role", _SE, (("a", "b"), ("a", "b"))),)},
            id="duplicate_alias_within_entry",
        ),
        pytest.param(
            {
                "vocabulary": (
                    ("alpha-role", _SE, (("a", "b"),)),
                    ("beta-role", RoleFamily.SALES, (("a", "b"),)),
                )
            },
            id="duplicate_alias_across_entries",
        ),
        pytest.param(
            {
                "vocabulary": (
                    ("alpha-role", _SE, (("security", "engineer"),)),
                    ("beta-role", RoleFamily.SALES, (("app", "security", "engineer"),)),
                )
            },
            id="suffix_collision_across_entries",
        ),
        pytest.param(
            {"vocabulary": (("alpha-role", _SE, (("b", "c"), ("a", "b", "c"))),)},
            id="suffix_collision_within_entry",
        ),
        pytest.param({"blockers": ()}, id="empty_blockers"),
        pytest.param({"blockers": ("of", "of")}, id="duplicate_blocker"),
        pytest.param({"blockers": ("Recruiter",)}, id="malformed_blocker"),
        pytest.param({"blockers": ("re cruiter",)}, id="blocker_with_space"),
        pytest.param({"designators": ("engineer", "engineer")}, id="duplicate_designator"),
        pytest.param({"designators": ("&",)}, id="ampersand_designator"),
        pytest.param({"designators": ("engineer", "lead")}, id="lead_as_prefix_designator"),
        pytest.param({"designators": ("engineer", "leads")}, id="leads_as_prefix_designator"),
        pytest.param({"extra": ("lead", "lead")}, id="duplicate_later_extra"),
        pytest.param({"extra": ("engineer",)}, id="extra_overlaps_designators"),
        pytest.param({"signals": ()}, id="empty_signals"),
        pytest.param(
            {"signals": ((_SE, (("alpha",),)), (RoleFamily.SALES, (("alpha",),)))},
            id="duplicate_signal_across_families",
        ),
        pytest.param({"signals": ((_SE, (("alpha",), ("alpha",))),)}, id="duplicate_signal"),
        pytest.param(
            {"signals": ((_SE, (("alpha",),)), (_SE, (("beta",),)))},
            id="duplicate_signal_family",
        ),
        pytest.param({"signals": (("sales", (("beta",),)),)}, id="raw_signal_family"),
        pytest.param({"signals": ((_SE, (("Alpha",),)),)}, id="malformed_signal"),
        pytest.param({"signals": ((_SE, ()),)}, id="empty_signal_list"),
    ],
)
def test_compile_tables_rejects_malformed_tables(overrides: dict[str, Any]) -> None:
    with pytest.raises(TitleVocabularyError):
        _compile(**overrides)


# ---------------------------------------------------------------------------
# A7/A12: character policy, exceptions, complexity.
# ---------------------------------------------------------------------------

# Independent oracle: the only code points that can sit between "Software"
# and "Engineer" and still yield a match are those mapping to a token
# boundary within one segment (space, tab/CR/LF, Zs, `+`, an unspaced dash)
# -- or, via fullwidth U+FF0B/U+FF0D, the same.
_JOINING_OK = (
    {"\t", "\r", "\n", " ", "+", "-", "＋", "－"} | {chr(c) for c in range(0x2010, 0x2016)} | {"−"}
)


def test_every_code_point_classifies_without_raising() -> None:
    import unicodedata

    for cp in range(0x110000):
        ch = chr(cp)
        result = classify_title("Software" + ch + "Engineer")
        assert isinstance(result, TitleResult)
        if result.outcome is TitleOutcome.MATCHED:
            assert ch in _JOINING_OK or unicodedata.category(ch) == "Zs", hex(cp)
        single = classify_title(ch)
        assert single.outcome is not TitleOutcome.MATCHED


def test_control_surrogate_and_mixed_inputs_never_raise() -> None:
    samples = [
        "\ud800",
        "\udfff",
        "🚀",
        "\x00" * 10,
        "\x7f",
        "\u0085",
        "Software Engineer\x1b[31m",
        "[" * 1000,
        "]" * 1000,
        "[Expression of Interest" * 100,
        "- " * 1000,
        "&" * 1000,
    ]
    for sample in samples:
        assert isinstance(classify_title(sample), TitleResult)


def test_very_long_unmatched_text_stays_linear() -> None:
    for text in (
        "a " * 1_000_000,
        "x" * 2_000_000,
        "Software Engineer, " * 100_000,
        "security " * 200_000 + "engineer",
        "[" + "a " * 500_000,
    ):
        start = time.perf_counter()
        classify_title(text)
        assert time.perf_counter() - start < 10.0


def test_classify_title_is_deterministic() -> None:
    for case in _CASES:
        assert classify_title(case["title"]) == classify_title(case["title"])


# ---------------------------------------------------------------------------
# Purity and import boundary.
# ---------------------------------------------------------------------------


def test_module_imports_only_the_allowed_pure_modules() -> None:
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module is not None
            imported.add(node.module)
    assert imported == {
        "__future__",
        "unicodedata",
        "collections.abc",
        "dataclasses",
        "enum",
        "types",
        "app.normalization.types",
        "app.schemas.identifiers",
    }


def test_module_uses_no_regular_expressions() -> None:
    source = _MODULE_PATH.read_text(encoding="utf-8")
    assert "import re" not in source
    assert "re.compile" not in source
