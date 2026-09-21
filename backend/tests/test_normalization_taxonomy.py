"""Tests for `app.normalization.taxonomy`: the skill-taxonomy-foundation
slice. Covers schema/YAML validation, duplicate-key rejection (both
YAML-syntax and semantic-normalization layers), the canonical-ID grammar,
display-name reachability, the taxonomy's own lookup-normalization rule,
`TaxonomyLookupResult`'s invariant, exact-match-only behavior (no free-text
scanning), the real shipped `skills.yaml`, and the ambiguous-alias
false-match guards the proposal required."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.normalization import taxonomy as tx

_FIXTURES = Path(__file__).parent / "fixtures" / "taxonomy"


# ---------------------------------------------------------------------------
# Import boundary -- no ORM/DB/network/provider dependency.
# ---------------------------------------------------------------------------


def test_taxonomy_module_has_no_forbidden_imports() -> None:
    source = Path(tx.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_roots = {"app.db", "app.providers", "app.ingestion", "app.services", "app.api"}
    forbidden_libraries = {"httpx", "ats_scrapers", "jobspy", "sqlalchemy", "asyncpg"}
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    for module in imported_modules:
        assert not any(
            module == root or module.startswith(root + ".") for root in forbidden_roots
        ), f"forbidden import: {module}"
        assert not any(
            module == lib or module.startswith(lib + ".") for lib in forbidden_libraries
        ), f"forbidden import: {module}"


# ---------------------------------------------------------------------------
# Duplicate YAML mapping key -- _StrictYamlLoader itself.
# ---------------------------------------------------------------------------


def test_duplicate_yaml_mapping_key_is_rejected() -> None:
    with pytest.raises(tx.TaxonomyValidationError, match="duplicate YAML mapping key"):
        tx.load_taxonomy(_FIXTURES / "duplicate_yaml_key.yaml")


def test_sequence_mapping_key_is_rejected_as_taxonomy_error_not_raw_type_error() -> None:
    """YAML's explicit `? ... : ...` syntax permits a non-scalar
    (sequence/mapping) mapping key, which is unhashable -- `key in seen`/
    `seen.add(key)` would otherwise raise a bare `TypeError` straight out
    of `_StrictYamlLoader.construct_mapping`, escaping this module's own
    closed exception type. Must surface as `TaxonomyValidationError`."""
    with pytest.raises(tx.TaxonomyValidationError, match="unhashable"):
        tx.load_taxonomy(_FIXTURES / "sequence_mapping_key.yaml")


def test_valid_minimal_taxonomy_loads_and_resolves() -> None:
    index = tx.load_taxonomy(_FIXTURES / "valid_minimal.yaml")
    result = index.lookup("Alpha")
    assert result.status is tx.TaxonomyLookupStatus.MATCHED
    assert result.entry is not None
    assert result.entry.canonical_id == "alpha"

    alias_result = index.lookup("alpha-lang")
    assert alias_result.status is tx.TaxonomyLookupStatus.MATCHED
    assert alias_result.entry is not None
    assert alias_result.entry.canonical_id == "alpha"


def test_index_is_genuinely_immutable_not_merely_frozen() -> None:
    """`@dataclass(frozen=True)` alone only blocks rebinding the
    `_by_normalized_key` attribute -- it does not stop the dict object
    itself from being mutated in place. `__post_init__`'s defensive copy
    into a `MappingProxyType` must reject that too."""
    index = tx.load_taxonomy(_FIXTURES / "valid_minimal.yaml")
    with pytest.raises(TypeError):
        index._by_normalized_key["alpha"] = tx.TaxonomyEntry(  # type: ignore[index]
            canonical_id="corrupted", display_name="Corrupted"
        )
    # The lookup must still resolve to the genuine, untampered entry.
    result = index.lookup("alpha")
    assert result.entry is not None
    assert result.entry.canonical_id == "alpha"


def test_index_copies_its_input_so_the_callers_own_dict_cant_corrupt_it_later() -> None:
    """Wrapping the *same* dict object the caller passed in would still
    leave it corruptible via the caller's own remaining reference --
    `__post_init__` must copy, not merely wrap."""
    mutable_source: dict[str, tx.TaxonomyEntry] = {
        "alpha": tx.TaxonomyEntry(canonical_id="alpha", display_name="Alpha")
    }
    index = tx.TaxonomyIndex(_by_normalized_key=mutable_source)
    mutable_source["alpha"] = tx.TaxonomyEntry(canonical_id="corrupted", display_name="Corrupted")
    result = index.lookup("alpha")
    assert result.entry is not None
    assert result.entry.canonical_id == "alpha"


def test_blank_after_strip_alias_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "blank_alias.yaml"
    bad.write_text(
        "schema_version: 1\nentries:\n  - canonical_id: alpha\n"
        '    display_name: Alpha\n    aliases: ["   "]\n',
        encoding="utf-8",
    )
    with pytest.raises(tx.TaxonomyValidationError, match="blank lookup key"):
        tx.load_taxonomy(bad)


# ---------------------------------------------------------------------------
# Schema validation.
# ---------------------------------------------------------------------------


def test_wrong_schema_version_is_rejected() -> None:
    with pytest.raises(tx.TaxonomyValidationError, match="schema_version must be"):
        tx.load_taxonomy(_FIXTURES / "wrong_schema_version.yaml")


def test_boolean_schema_version_is_rejected_not_silently_accepted_as_one() -> None:
    """`bool` is an `int` subclass and `True == 1` in Python -- a bare
    `!=` comparison (or a plain `isinstance(x, int)` check) would
    silently accept `schema_version: true`. Must be rejected outright."""
    with pytest.raises(tx.TaxonomyValidationError, match="schema_version must be the int"):
        tx.load_taxonomy(_FIXTURES / "schema_version_boolean_true.yaml")


def test_unknown_top_level_field_is_rejected() -> None:
    with pytest.raises(tx.TaxonomyValidationError, match="unrecognized top-level field"):
        tx.load_taxonomy(_FIXTURES / "unknown_top_level_field.yaml")


def test_unknown_entry_field_is_rejected() -> None:
    with pytest.raises(tx.TaxonomyValidationError, match="unrecognized field"):
        tx.load_taxonomy(_FIXTURES / "unknown_entry_field.yaml")


def test_invalid_canonical_id_slug_is_rejected() -> None:
    with pytest.raises(tx.TaxonomyValidationError, match="not a canonical slug"):
        tx.load_taxonomy(_FIXTURES / "invalid_canonical_id_slug.yaml")


def test_not_valid_yaml_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "broken.yaml"
    bad.write_text("schema_version: [1, \n", encoding="utf-8")
    with pytest.raises(tx.TaxonomyValidationError, match="not valid YAML"):
        tx.load_taxonomy(bad)


def test_non_mapping_top_level_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "list_top.yaml"
    bad.write_text("- 1\n- 2\n", encoding="utf-8")
    with pytest.raises(tx.TaxonomyValidationError, match="must contain a YAML mapping"):
        tx.load_taxonomy(bad)


# ---------------------------------------------------------------------------
# Duplicate/collision rejection -- the semantic (normalized-key) layer.
# ---------------------------------------------------------------------------


def test_duplicate_canonical_id_is_rejected() -> None:
    with pytest.raises(tx.TaxonomyValidationError, match="duplicate canonical_id"):
        tx.load_taxonomy(_FIXTURES / "duplicate_canonical_id.yaml")


def test_duplicate_alias_cross_entry_is_rejected() -> None:
    with pytest.raises(tx.TaxonomyValidationError, match="collides with an existing entry"):
        tx.load_taxonomy(_FIXTURES / "duplicate_alias_cross_entry.yaml")


def test_alias_colliding_with_another_entrys_canonical_id_is_rejected() -> None:
    with pytest.raises(tx.TaxonomyValidationError, match="collides with an existing entry"):
        tx.load_taxonomy(_FIXTURES / "alias_collides_with_other_canonical_id.yaml")


def test_alias_equal_to_its_own_canonical_id_is_rejected() -> None:
    with pytest.raises(tx.TaxonomyValidationError, match="self-colliding key"):
        tx.load_taxonomy(_FIXTURES / "alias_equals_own_canonical_id.yaml")


def test_duplicate_alias_within_the_same_entry_is_rejected() -> None:
    with pytest.raises(tx.TaxonomyValidationError, match="self-colliding key"):
        tx.load_taxonomy(_FIXTURES / "duplicate_alias_within_entry.yaml")


def test_unreachable_display_name_is_rejected() -> None:
    with pytest.raises(tx.TaxonomyValidationError, match="not reachable"):
        tx.load_taxonomy(_FIXTURES / "unreachable_display_name.yaml")


# ---------------------------------------------------------------------------
# normalize_lookup_key -- the taxonomy's own precise rule.
# ---------------------------------------------------------------------------


def test_normalize_lookup_key_case_insensitive() -> None:
    assert tx.normalize_lookup_key("Python") == tx.normalize_lookup_key("PYTHON")
    assert tx.normalize_lookup_key("Python") == tx.normalize_lookup_key("python")


def test_normalize_lookup_key_strips_and_collapses_whitespace() -> None:
    assert tx.normalize_lookup_key("  node  ") == "node"
    assert tx.normalize_lookup_key("node   js") == "node js"


def test_normalize_lookup_key_preserves_punctuation() -> None:
    assert tx.normalize_lookup_key("C++") == "c++"
    assert tx.normalize_lookup_key("C#") == "c#"
    assert tx.normalize_lookup_key("C") == "c"
    assert tx.normalize_lookup_key("c++") != tx.normalize_lookup_key("c")
    assert tx.normalize_lookup_key("c#") != tx.normalize_lookup_key("c")


def test_normalize_lookup_key_does_not_reconcile_whitespace_around_punctuation() -> None:
    """Stated limitation, not a defect: exact form is required."""
    assert tx.normalize_lookup_key("node . js") != tx.normalize_lookup_key("node.js")


def test_normalize_lookup_key_nfkc_folds_fullwidth_characters() -> None:
    # Fullwidth Latin "Ｃ" (U+FF23) NFKC-folds to ASCII "C".
    assert tx.normalize_lookup_key("Ｃ") == "c"


# ---------------------------------------------------------------------------
# TaxonomyLookupResult invariant.
# ---------------------------------------------------------------------------


def test_lookup_result_matched_factory() -> None:
    entry = tx.TaxonomyEntry(canonical_id="x", display_name="X")
    result = tx.TaxonomyLookupResult.matched(entry)
    assert result.status is tx.TaxonomyLookupStatus.MATCHED
    assert result.entry is entry


def test_lookup_result_unknown_factory() -> None:
    result = tx.TaxonomyLookupResult.unknown()
    assert result.status is tx.TaxonomyLookupStatus.UNKNOWN
    assert result.entry is None


def test_lookup_result_rejects_matched_status_with_no_entry() -> None:
    with pytest.raises(ValueError, match="entry must be None if and only if"):
        tx.TaxonomyLookupResult(status=tx.TaxonomyLookupStatus.MATCHED, entry=None)


def test_lookup_result_rejects_unknown_status_with_an_entry() -> None:
    entry = tx.TaxonomyEntry(canonical_id="x", display_name="X")
    with pytest.raises(ValueError, match="entry must be None if and only if"):
        tx.TaxonomyLookupResult(status=tx.TaxonomyLookupStatus.UNKNOWN, entry=entry)


def test_lookup_result_rejects_a_non_enum_status() -> None:
    with pytest.raises(ValueError, match="must be a TaxonomyLookupStatus"):
        tx.TaxonomyLookupResult(status="matched", entry=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Exact-match only -- no free-text scanning.
# ---------------------------------------------------------------------------


def test_lookup_is_exact_match_only_not_a_substring_scan() -> None:
    index = tx.load_taxonomy(tx.DEFAULT_SKILLS_TAXONOMY_PATH)
    sentence = "I love javascript development and also python"
    result = index.lookup(sentence)
    assert result.status is tx.TaxonomyLookupStatus.UNKNOWN
    # The individual token still resolves -- proving the sentence-level
    # miss above is because lookup() never tokenizes/scans, not because
    # the underlying entries are somehow unreachable.
    assert index.lookup("javascript").status is tx.TaxonomyLookupStatus.MATCHED


def test_unknown_skill_returns_typed_unknown_never_raises() -> None:
    index = tx.load_taxonomy(tx.DEFAULT_SKILLS_TAXONOMY_PATH)
    result = index.lookup("some-skill-that-does-not-exist")
    assert result.status is tx.TaxonomyLookupStatus.UNKNOWN
    assert result.entry is None


# ---------------------------------------------------------------------------
# The real, shipped skills.yaml.
# ---------------------------------------------------------------------------

_EXPECTED_CANONICAL_IDS = {
    "python",
    "javascript",
    "typescript",
    "java",
    "cpp",
    "csharp",
    "c",
    "golang",
    "rlang",
    "postgresql",
    "mysql",
    "mongodb",
    "kubernetes",
    "docker",
    "node.js",
}


def test_real_skills_yaml_loads_clean() -> None:
    index = tx.load_taxonomy(tx.DEFAULT_SKILLS_TAXONOMY_PATH)
    assert index.canonical_ids() == _EXPECTED_CANONICAL_IDS


@pytest.mark.parametrize("canonical_id", sorted(_EXPECTED_CANONICAL_IDS))
def test_every_seed_entry_resolves_by_its_own_canonical_id(canonical_id: str) -> None:
    index = tx.load_taxonomy(tx.DEFAULT_SKILLS_TAXONOMY_PATH)
    result = index.lookup(canonical_id)
    assert result.status is tx.TaxonomyLookupStatus.MATCHED
    assert result.entry is not None
    assert result.entry.canonical_id == canonical_id


@pytest.mark.parametrize(
    ("alias", "expected_canonical_id"),
    [
        ("js", "javascript"),
        ("ts", "typescript"),
        ("c++", "cpp"),
        ("cplusplus", "cpp"),
        ("c#", "csharp"),
        ("c-sharp", "csharp"),
        ("go", "golang"),
        ("r", "rlang"),
        ("postgres", "postgresql"),
        ("mongo", "mongodb"),
        ("k8s", "kubernetes"),
        ("node", "node.js"),
        ("nodejs", "node.js"),
    ],
)
def test_every_seed_alias_resolves_to_its_canonical_id(
    alias: str, expected_canonical_id: str
) -> None:
    index = tx.load_taxonomy(tx.DEFAULT_SKILLS_TAXONOMY_PATH)
    result = index.lookup(alias)
    assert result.status is tx.TaxonomyLookupStatus.MATCHED
    assert result.entry is not None
    assert result.entry.canonical_id == expected_canonical_id


# ---------------------------------------------------------------------------
# Ambiguous-alias false-match guards (the proposal's required negative
# controls).
# ---------------------------------------------------------------------------


def test_c_cpp_csharp_are_three_distinct_entries_never_aliased_to_each_other() -> None:
    index = tx.load_taxonomy(tx.DEFAULT_SKILLS_TAXONOMY_PATH)
    c_result = index.lookup("c")
    cpp_result = index.lookup("c++")
    csharp_result = index.lookup("c#")
    assert c_result.entry is not None
    assert cpp_result.entry is not None
    assert csharp_result.entry is not None
    assert c_result.entry.canonical_id == "c"
    assert cpp_result.entry.canonical_id == "cpp"
    assert csharp_result.entry.canonical_id == "csharp"
    ids = {
        c_result.entry.canonical_id,
        cpp_result.entry.canonical_id,
        csharp_result.entry.canonical_id,
    }
    assert len(ids) == 3


def test_java_and_javascript_never_resolve_to_each_other() -> None:
    index = tx.load_taxonomy(tx.DEFAULT_SKILLS_TAXONOMY_PATH)
    java_result = index.lookup("java")
    javascript_result = index.lookup("javascript")
    assert java_result.entry is not None
    assert javascript_result.entry is not None
    assert java_result.entry.canonical_id == "java"
    assert javascript_result.entry.canonical_id == "javascript"
    assert java_result.entry.canonical_id != javascript_result.entry.canonical_id


def test_go_and_r_exact_lookup_resolve_correctly_despite_being_common_words() -> None:
    """Positive control only -- proves the exact-match lookup itself is
    correct for these two names. Does not, and cannot, guarantee a future
    free-text classifier's word-boundary safety; that remains its own
    responsibility (see `TaxonomyIndex.lookup`'s docstring)."""
    index = tx.load_taxonomy(tx.DEFAULT_SKILLS_TAXONOMY_PATH)
    go_result = index.lookup("go")
    r_result = index.lookup("r")
    assert go_result.entry is not None
    assert r_result.entry is not None
    assert go_result.entry.canonical_id == "golang"
    assert r_result.entry.canonical_id == "rlang"


def test_case_insensitivity_across_the_real_seed() -> None:
    index = tx.load_taxonomy(tx.DEFAULT_SKILLS_TAXONOMY_PATH)
    for variant in ("Python", "python", "PYTHON", "PyThOn"):
        result = index.lookup(variant)
        assert result.entry is not None
        assert result.entry.canonical_id == "python"
