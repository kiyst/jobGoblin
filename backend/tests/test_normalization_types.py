import pytest

from app.normalization.types import NormalizationResult, Provenance


def test_provenance_has_exactly_the_documented_six_values() -> None:
    assert len(Provenance) == 6
    assert {member.value for member in Provenance} == {
        "explicit_source",
        "structured_metadata",
        "parsed_description",
        "derived",
        "inferred",
        "unavailable",
    }


@pytest.mark.parametrize(
    ("value", "provenance"),
    [
        (None, Provenance.UNAVAILABLE),
        ("remote", Provenance.INFERRED),
        ("remote", Provenance.PARSED_DESCRIPTION),
        ("remote", Provenance.EXPLICIT_SOURCE),
        ("remote", Provenance.STRUCTURED_METADATA),
        ("remote", Provenance.DERIVED),
    ],
)
def test_valid_value_provenance_pairs_construct_successfully(
    value: str | None, provenance: Provenance
) -> None:
    result = NormalizationResult(value=value, provenance=provenance)
    assert result.value == value
    assert result.provenance == provenance


@pytest.mark.parametrize(
    ("value", "provenance"),
    [
        (None, Provenance.INFERRED),
        (None, Provenance.DERIVED),
        ("remote", Provenance.UNAVAILABLE),
    ],
)
def test_none_invariant_violation_raises_the_fixed_categorical_message(
    value: str | None, provenance: Provenance
) -> None:
    with pytest.raises(ValueError) as exc_info:
        NormalizationResult(value=value, provenance=provenance)
    assert str(exc_info.value) == (
        "NormalizationResult invariant violated: value must be None if and "
        "only if provenance is Provenance.UNAVAILABLE."
    )


@pytest.mark.parametrize(
    ("value", "provenance"),
    [
        (None, "unavailable"),
        (None, "bogus_provenance"),
        # The case that would otherwise silently bypass the None invariant:
        # a present value paired with a raw string that merely *looks like*
        # a valid provenance tag, but is not an actual Provenance member.
        ("remote", "inferred"),
    ],
)
def test_non_enum_provenance_raises_the_fixed_categorical_type_message(
    value: str | None, provenance: object
) -> None:
    with pytest.raises(ValueError) as exc_info:
        NormalizationResult(value=value, provenance=provenance)  # type: ignore[arg-type]
    assert str(exc_info.value) == (
        "NormalizationResult invariant violated: provenance must be a " "Provenance enum member."
    )
