import pytest

from app.ingestion.hashing import canonical_json_hash


def test_top_level_key_order_does_not_affect_hash() -> None:
    a = {"title": "Engineer", "company": "Acme", "salary": 100000}
    b = {"salary": 100000, "company": "Acme", "title": "Engineer"}
    assert canonical_json_hash(a) == canonical_json_hash(b)


def test_nested_key_order_does_not_affect_hash() -> None:
    a = {"job": {"title": "Engineer", "location": {"city": "Austin", "state": "TX"}}}
    b = {"job": {"location": {"state": "TX", "city": "Austin"}, "title": "Engineer"}}
    assert canonical_json_hash(a) == canonical_json_hash(b)


def test_unicode_equivalent_but_distinct_strings_hash_differently() -> None:
    """Two Python strings that render identically but are not code-point-
    identical (no NFC/NFKC normalization is applied) must hash differently
    -- this hash canonicalizes key order, not Unicode text itself. Built
    with `chr()` (never a literal accented character typed into this
    source file) so the two variants are unambiguously distinct code-point
    sequences regardless of any editor/encoding normalization."""
    composed_title = "Caf" + chr(0x00E9) + " Engineer"  # precomposed e-acute, U+00E9
    decomposed_title = "Cafe" + chr(0x0301) + " Engineer"  # "e" + combining acute, U+0301
    assert composed_title != decomposed_title  # sanity: genuinely distinct code points
    assert len(composed_title) != len(decomposed_title)

    composed = {"title": composed_title}
    decomposed = {"title": decomposed_title}
    assert canonical_json_hash(composed) != canonical_json_hash(decomposed)


def test_changed_value_hashes_differently() -> None:
    a = {"title": "Engineer", "salary": 100000}
    b = {"title": "Engineer", "salary": 100001}
    assert canonical_json_hash(a) != canonical_json_hash(b)


def test_rejects_nan_and_infinity() -> None:
    """`allow_nan=False` must reject exactly the values PostgreSQL's own
    `jsonb` input function rejects -- hashing must fail where storage
    would, not silently accept a payload JSONB can never persist."""
    with pytest.raises(ValueError, match="Out of range float values are not JSON compliant"):
        canonical_json_hash({"score": float("nan")})
    with pytest.raises(ValueError, match="Out of range float values are not JSON compliant"):
        canonical_json_hash({"score": float("inf")})
    with pytest.raises(ValueError, match="Out of range float values are not JSON compliant"):
        canonical_json_hash({"score": float("-inf")})
