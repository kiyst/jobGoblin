"""Normalization context, binding, projection, and merge-rule tests (Phase 4 S3;
ADR 0018 A1, A3, A5). Pure: no database or network.

Every parser version used here comes from the real builder over a real
configuration; no version string is injected.
"""

from __future__ import annotations

import ast
import uuid
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app.ingestion import normalization_version as nv
from app.ingestion import normalized_fields as nf
from app.ingestion.normalized_fields import (
    EntryOrigin,
    NormalizationBindingError,
    NormalizationContext,
    ProvenanceEscalationError,
    ProvenanceIntegrityError,
    VerifiedNormalization,
    build_normalization_context,
    merge_field,
    verify_normalization_context,
)
from app.normalization.posting import PostingInputs, normalize_posting
from app.normalization.taxonomy import DEFAULT_SKILLS_TAXONOMY_PATH, load_taxonomy
from app.normalization.types import NormalizationResult, Provenance
from app.providers.fixture import FixtureProvider
from app.providers.greenhouse import GreenhouseBoard, GreenhouseJobBoardProvider
from app.providers.greenhouse_content import GreenhouseContentMode
from app.schemas.discovered_job import DiscoveredJob

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"
DECLARED: GreenhouseContentMode = "declared-double-escaped"
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
ACME = GreenhouseBoard("acme-synthetic", "Acme Synthetic", content_mode=DECLARED)
BETA = GreenhouseBoard("beta-synthetic", "Beta Synthetic", content_mode=DECLARED)


def _provider(*boards: GreenhouseBoard) -> GreenhouseJobBoardProvider:
    return GreenhouseJobBoardProvider(boards)


def _context(*boards: GreenhouseBoard) -> NormalizationContext:
    return build_normalization_context(_provider(*boards).board_content_modes)


def _verified(*boards: GreenhouseBoard) -> VerifiedNormalization:
    return verify_normalization_context(_context(*boards), _provider(*boards))


def _job(**overrides: Any) -> DiscoveredJob:
    values: dict[str, Any] = {
        "provider": "greenhouse",
        "source": "greenhouse",
        "source_tenant_id": "acme-synthetic",
        "source_job_id": "1001",
        "requisition_id_raw": None,
        "title": "Senior Software Engineer",
        "company": "Acme Synthetic",
        "location": "Toronto, Canada",
        "source_url": "https://job-boards.greenhouse.io/acme-synthetic/jobs/1001",
        "apply_url": None,
        "canonical_url": "https://job-boards.greenhouse.io/acme-synthetic/jobs/1001",
        "description": "This is a full-time position.",
        "compensation_text": None,
        "posted_at": None,
        "discovered_at": NOW,
        "raw": {"id": 1001},
    }
    values.update(overrides)
    return DiscoveredJob(**values)


# --- A1: construction guards ---


def test_contexts_cannot_be_constructed_outside_their_builders() -> None:
    context = _context(ACME)
    with pytest.raises(TypeError):
        NormalizationContext(
            authority=object(),
            canonical=context.manifest,
            version=context.parser_version,
            taxonomy=context.taxonomy,
            content_modes=context.content_modes,
        )
    with pytest.raises(TypeError):
        VerifiedNormalization(authority=object(), context=context, normalizes=True)
    with pytest.raises(AttributeError):
        context._version = "x"
    verified = _verified(ACME)
    with pytest.raises(AttributeError):
        verified._normalizes = False
    with pytest.raises(TypeError):
        context.content_modes["beta-synthetic"] = DECLARED  # type: ignore[index]


def test_a_valid_freshly_built_context_verifies() -> None:
    context = _context(ACME, BETA)
    verified = verify_normalization_context(context, _provider(ACME, BETA))
    assert verified.is_authentic()
    assert verified.parser_version == context.parser_version
    assert context.parser_version == nv.parser_version_for(context.manifest)


@pytest.mark.parametrize(
    "value", [None, "jgnorm-v1:sha256:" + "0" * 64, {"parser_version": "x"}, object()]
)
def test_anything_but_a_built_context_fails_closed(value: object) -> None:
    with pytest.raises(NormalizationBindingError):
        verify_normalization_context(value, _provider(ACME))


def test_a_syntactically_valid_forged_version_fails_closed() -> None:
    context = _context(ACME)
    object.__setattr__(context, "_version", "jgnorm-v1:sha256:" + "0" * 64)
    with pytest.raises(NormalizationBindingError):
        verify_normalization_context(context, _provider(ACME))


def test_a_manifest_hash_mismatch_fails_closed() -> None:
    context = _context(ACME)
    other = _context(ACME, BETA)
    object.__setattr__(context, "_canonical", other.manifest)
    with pytest.raises(NormalizationBindingError):
        verify_normalization_context(context, _provider(ACME))


def test_a_taxonomy_mismatch_fails_closed(tmp_path: Path) -> None:
    alternative = tmp_path / "skills.yaml"
    alternative.write_bytes(
        DEFAULT_SKILLS_TAXONOMY_PATH.read_bytes().rstrip()
        + b"\n  - canonical_id: zzzsynthetic\n    display_name: Zzzsynthetic\n    aliases: []\n"
    )
    context = _context(ACME)
    object.__setattr__(context, "_taxonomy", load_taxonomy(alternative))
    with pytest.raises(NormalizationBindingError):
        verify_normalization_context(context, _provider(ACME))


@pytest.mark.parametrize(
    ("target", "attribute", "value"),
    [
        ("platform", "python_version", lambda: "3.99.0"),
        ("unicodedata", "unidata_version", "99.0.0"),
        ("yaml", "__version__", "0.0.0-synthetic"),
    ],
)
def test_stale_runtime_evidence_fails_closed(
    monkeypatch: pytest.MonkeyPatch, target: str, attribute: str, value: object
) -> None:
    context = _context(ACME)
    monkeypatch.setattr(getattr(nv, target), attribute, value)
    with pytest.raises(NormalizationBindingError):
        verify_normalization_context(context, _provider(ACME))


def test_stale_source_evidence_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    context = _context(ACME)
    stale = dict(nv._FIRST_SEEN)
    stale["app/normalization/employment.py"] = "0" * 64
    monkeypatch.setattr(nv, "_FIRST_SEEN", stale)
    with pytest.raises(nv.ParserVersionError):
        verify_normalization_context(context, _provider(ACME))


# --- A3: board/content-mode binding ---


def test_the_provider_snapshot_is_read_only_and_exact() -> None:
    disabled = GreenhouseBoard("gamma-synthetic", "Gamma Synthetic")
    snapshot = _provider(ACME, disabled).board_content_modes
    assert dict(snapshot) == {"acme-synthetic": DECLARED, "gamma-synthetic": "disabled"}
    with pytest.raises(TypeError):
        snapshot["acme-synthetic"] = "disabled"  # type: ignore[index]


def test_a_disabled_board_cannot_be_normalized() -> None:
    disabled = GreenhouseBoard("gamma-synthetic", "Gamma Synthetic")
    with pytest.raises(nv.ParserVersionError):
        build_normalization_context(_provider(disabled).board_content_modes)
    with pytest.raises(nv.ParserVersionError):
        build_normalization_context(_provider(ACME, disabled).board_content_modes)


def test_a_mismatched_mode_or_board_set_fails_closed() -> None:
    context = _context(ACME)
    with pytest.raises(NormalizationBindingError):
        verify_normalization_context(context, _provider(GreenhouseBoard("acme-synthetic", "A")))
    with pytest.raises(NormalizationBindingError):
        verify_normalization_context(context, _provider(ACME, BETA))
    with pytest.raises(NormalizationBindingError):
        verify_normalization_context(_context(ACME, BETA), _provider(ACME))


def test_a_greenhouse_named_provider_without_a_snapshot_fails_closed() -> None:
    class Impostor:
        name = "greenhouse"

    with pytest.raises(NormalizationBindingError):
        verify_normalization_context(_context(ACME), Impostor())


def test_configuration_changes_rotate_the_legitimate_version() -> None:
    assert _context(ACME).parser_version != _context(ACME, BETA).parser_version
    assert _context(ACME).parser_version == _context(ACME).parser_version


def test_the_expected_board_binding_projects() -> None:
    projection = _verified(ACME).project(_job())
    assert projection is not None
    assert set(projection.fields) == {"employment_type", "seniority", "country"}


def test_an_unknown_board_token_fails_closed() -> None:
    verified = _verified(ACME)
    with pytest.raises(NormalizationBindingError):
        verified.project(_job(source_tenant_id="unknown-synthetic"))
    with pytest.raises(NormalizationBindingError):
        verified.project(_job(source_tenant_id=None))


def test_unmapped_jobs_and_providers_are_a_no_op() -> None:
    verified = _verified(ACME)
    assert verified.project(_job(provider="fixture_provider", source="fixture_ats")) is None
    assert verified.project(_job(source="other")) is None
    unmapped = verify_normalization_context(_context(ACME), FixtureProvider([], called_at=NOW))
    assert unmapped.project(_job()) is None


# --- projection ---


def test_the_projection_is_exactly_the_three_d2_covered_components() -> None:
    job = _job()
    projection = _verified(ACME).project(job)
    assert projection is not None
    taxonomy = load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)
    expected = normalize_posting(
        PostingInputs(job.title, job.description, job.location), taxonomy=taxonomy
    )
    assert projection.fields == {
        "employment_type": expected.employment_type,
        "seniority": expected.seniority,
        "country": expected.location.country,
    }
    assert nf.PERSISTED_COLUMNS == ("employment_type", "seniority", "country")
    assert "salary" not in repr(projection)


def test_an_escalated_provenance_tag_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    real = nf.normalize_posting

    def escalate(inputs: PostingInputs, *, taxonomy: Any) -> Any:
        result = real(inputs, taxonomy=taxonomy)
        object.__setattr__(
            result,
            "seniority",
            NormalizationResult("senior", Provenance.EXPLICIT_SOURCE),
        )
        return result

    monkeypatch.setattr(nf, "normalize_posting", escalate)
    with pytest.raises(ProvenanceEscalationError):
        _verified(ACME).project(_job())


def test_an_untrimmed_value_is_rejected() -> None:
    with pytest.raises(NormalizationBindingError):
        nf._check_incoming(NormalizationResult(" Canada", Provenance.PARSED_DESCRIPTION))


def test_a_parser_exception_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(inputs: PostingInputs, *, taxonomy: Any) -> Any:
        raise RuntimeError("parser defect")

    monkeypatch.setattr(nf, "normalize_posting", boom)
    with pytest.raises(RuntimeError, match="parser defect"):
        _verified(ACME).project(_job())


# --- A5: merge rule ---

V1 = _context(ACME).parser_version
V2 = _context(ACME, BETA).parser_version
T1 = NOW
T2 = NOW + timedelta(hours=1)
OCC = uuid.uuid4()
RAW_OLD = uuid.uuid4()
RAW_NEW = uuid.uuid4()


def _origin(version: str = V1, observed_at: datetime = T1, raw: uuid.UUID = RAW_NEW) -> EntryOrigin:
    return EntryOrigin(
        occurrence_id=OCC,
        raw_job_ingestion_id=raw,
        parser_version=version,
        observed_at=observed_at,
    )


def _entry(
    tag: str = "inferred", version: str = V1, observed_at: datetime = T1, **overrides: object
) -> dict[str, object]:
    entry: dict[str, object] = {
        "source": tag,
        "provider": "greenhouse",
        "provider_source": "greenhouse",
        "occurrence_id": str(OCC),
        "raw_job_ingestion_id": str(RAW_OLD),
        "parser_version": version,
        "observed_at": observed_at.isoformat(),
    }
    entry.update(overrides)
    return entry


def _result(value: str | None, tag: Provenance) -> NormalizationResult[str]:
    return NormalizationResult(value, tag)


PARSED = Provenance.PARSED_DESCRIPTION
INFERRED = Provenance.INFERRED


def test_versions_used_here_are_two_distinct_real_versions() -> None:
    assert V1 != V2
    assert V1.startswith("jgnorm-v1:sha256:") and V2.startswith("jgnorm-v1:sha256:")


def test_unavailable_never_writes_or_erases() -> None:
    unavailable = _result(None, Provenance.UNAVAILABLE)
    assert (
        merge_field(unavailable, existing_value=None, existing_entry=None, origin=_origin()) is None
    )
    assert (
        merge_field(unavailable, existing_value="senior", existing_entry=_entry(), origin=_origin())
        is None
    )


def test_a_first_value_is_written_with_a_complete_entry() -> None:
    write = merge_field(
        _result("senior", INFERRED), existing_value=None, existing_entry=None, origin=_origin()
    )
    assert write is not None
    assert write.value == "senior"
    assert write.entry == {
        "source": "inferred",
        "provider": "greenhouse",
        "provider_source": "greenhouse",
        "occurrence_id": str(OCC),
        "raw_job_ingestion_id": str(RAW_NEW),
        "parser_version": V1,
        "observed_at": T1.isoformat(),
    }


@pytest.mark.parametrize(
    ("existing_tag", "incoming_tag", "writes"),
    [
        ("inferred", PARSED, True),  # higher trust replaces
        ("parsed_description", INFERRED, False),  # lower trust is kept
        ("explicit_source", PARSED, False),
        ("structured_metadata", PARSED, False),
        ("derived", PARSED, True),
        ("parsed_description", Provenance.DERIVED, False),
    ],
)
def test_trust_order_decides_first(
    existing_tag: str, incoming_tag: Provenance, writes: bool
) -> None:
    # The incoming observation is older, so only trust can explain a write.
    write = merge_field(
        _result("full_time", incoming_tag),
        existing_value="part_time",
        existing_entry=_entry(existing_tag, observed_at=T2),
        origin=_origin(observed_at=T1),
    )
    assert (write is not None) is writes


def test_equal_trust_newer_observation_replaces_and_older_is_kept() -> None:
    newer = merge_field(
        _result("staff", INFERRED),
        existing_value="senior",
        existing_entry=_entry(observed_at=T1),
        origin=_origin(observed_at=T2),
    )
    assert newer is not None and newer.value == "staff"
    older = merge_field(
        _result("staff", INFERRED),
        existing_value="senior",
        existing_entry=_entry(observed_at=T2),
        origin=_origin(observed_at=T1),
    )
    assert older is None


def test_equal_time_identical_values_are_a_no_op_under_any_version() -> None:
    for existing_version, incoming_version in ((V1, V1), (V1, V2), (V2, V1)):
        assert (
            merge_field(
                _result("senior", INFERRED),
                existing_value="senior",
                existing_entry=_entry(version=existing_version),
                origin=_origin(version=incoming_version),
            )
            is None
        )


@pytest.mark.parametrize(
    ("existing_version", "incoming_version"),
    [("V1", "V2"), ("V2", "V1"), ("V1", "V1")],
)
def test_equal_time_conflicting_values_are_refused_whatever_the_versions(
    existing_version: str, incoming_version: str
) -> None:
    """A parser version is evidence, never an ordering signal: neither V1 then
    V2 nor V2 then V1 decides a winner, and the same version producing two
    values at one instant is refused rather than masked."""
    versions = {"V1": V1, "V2": V2}
    with pytest.raises(ProvenanceIntegrityError):
        merge_field(
            _result("staff", INFERRED),
            existing_value="senior",
            existing_entry=_entry(version=versions[existing_version]),
            origin=_origin(version=versions[incoming_version]),
        )


def test_a_new_parser_version_replaces_only_through_a_later_observation() -> None:
    later = merge_field(
        _result("staff", INFERRED),
        existing_value="senior",
        existing_entry=_entry(version=V1, observed_at=T1),
        origin=_origin(version=V2, observed_at=T2),
    )
    assert later is not None
    assert (later.value, later.entry["parser_version"]) == ("staff", V2)
    earlier = merge_field(
        _result("staff", INFERRED),
        existing_value="senior",
        existing_entry=_entry(version=V1, observed_at=T2),
        origin=_origin(version=V2, observed_at=T1),
    )
    assert earlier is None


def test_an_equal_time_across_offsets_is_the_same_instant() -> None:
    offset = T1.astimezone(timezone(timedelta(hours=-4)))
    assert (
        merge_field(
            _result("senior", INFERRED),
            existing_value="senior",
            existing_entry=_entry(observed_at=offset),
            origin=_origin(observed_at=T1),
        )
        is None
    )
    with pytest.raises(ProvenanceIntegrityError):
        merge_field(
            _result("staff", INFERRED),
            existing_value="senior",
            existing_entry=_entry(observed_at=offset),
            origin=_origin(observed_at=T1),
        )


@pytest.mark.parametrize(
    ("existing_value", "existing_entry"),
    [
        ("senior", None),  # a value without provenance
        (None, _entry()),  # provenance without a value
        ("senior", "inferred"),
        ("senior", {}),
        ("senior", {k: v for k, v in _entry().items() if k != "observed_at"}),
        ("senior", {**_entry(), "extra": "x"}),
        ("senior", _entry(tag="unavailable")),
        ("senior", _entry(tag="guessed")),
        ("senior", _entry(provider="lever")),
        ("senior", _entry(provider_source="lever")),
        ("senior", _entry(occurrence_id="not-a-uuid")),
        ("senior", _entry(raw_job_ingestion_id="not-a-uuid")),
        ("senior", _entry(parser_version="jgnorm-v1:sha256:short")),
        ("senior", {**_entry(), "observed_at": "2026-10-20T12:00:00"}),  # naive
        ("senior", {**_entry(), "observed_at": "not-a-time"}),
        ("senior", _entry(source=3)),
    ],
)
def test_malformed_inconsistent_or_foreign_provenance_is_rejected(
    existing_value: object, existing_entry: object
) -> None:
    with pytest.raises(ProvenanceIntegrityError):
        merge_field(
            _result("staff", PARSED),
            existing_value=existing_value,
            existing_entry=existing_entry,
            origin=_origin(),
        )


def test_incoming_explicit_or_structured_provenance_is_rejected() -> None:
    for tag in (Provenance.EXPLICIT_SOURCE, Provenance.STRUCTURED_METADATA):
        with pytest.raises(ProvenanceEscalationError):
            merge_field(
                _result("senior", tag), existing_value=None, existing_entry=None, origin=_origin()
            )


# --- no runtime activation (no registry, scheduler, or composition-root use) ---


def _calls(path: Path, name: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(
        isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == name)
            or (isinstance(node.func, ast.Attribute) and node.func.attr == name)
        )
        for node in ast.walk(tree)
    )


def test_nothing_in_the_application_activates_normalization() -> None:
    modules = sorted(p for p in APP_DIR.rglob("*.py") if "__pycache__" not in p.parts)
    builders = [
        p.relative_to(BACKEND_DIR).as_posix()
        for p in modules
        if _calls(p, "build_normalization_context")
    ]
    assert builders == []
    adapters = [
        p.relative_to(BACKEND_DIR).as_posix()
        for p in modules
        if _calls(p, "GreenhouseJobBoardProvider")
    ]
    assert adapters == []
    tree = ast.parse((APP_DIR / "providers" / "registry.py").read_text(encoding="utf-8"))
    registry_imports = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not [
        name
        for name in registry_imports
        if name and ("greenhouse" in name or name.startswith("app.ingestion"))
    ]
