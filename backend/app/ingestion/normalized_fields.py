"""Opt-in normalized-field persistence: the verified normalization context, the
three-field projection, and the S3 provenance merge rule (Phase 4 S3, Class H;
`docs/DECISIONS/0018-d1-parser-version-and-normalized-persistence.md`).

Pure: no database, ORM, logging, or network. `app/ingestion/persistence.py`
applies the merge to the locked `Job` row inside Transaction B.

Two guarded stages, neither constructible through the public API without its
check (ADR 0018 A1):

1. `build_normalization_context(content_modes)` builds and validates the
   complete D1 manifest (`app/ingestion/normalization_version.py`) and returns a
   `NormalizationContext`.
2. `verify_normalization_context(context, provider)` -- called by
   `pipeline.run` before it creates a `CollectionRun` or invokes the provider --
   independently rebuilds the manifest from the current repository, runtime,
   taxonomy, and the provider's own board/content-mode snapshot, requires every
   binding to match, and only then returns a `VerifiedNormalization`.
   `persist_posting` accepts nothing else.

The guards stop ordinary misuse (a forged or stale context, a context built for
another configuration, a bare version string). They are not a defense against
hostile in-process code, which can bypass any Python-level check.

Only `employment_type`, `seniority`, and `location.country` are persisted -- the
three components ADR 0014's D2 covers -- and only for jobs whose `provider` and
`source` are both `greenhouse` from a verified Greenhouse provider whose board
used an approved content mode. Every other job is a no-op (raw-only, exactly as
in Phase 2).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import cast

from app.ingestion.normalization_version import (
    APPROVED_CONTENT_MODES,
    NORMALIZED_PROVIDER,
    PARSER_VERSION_PREFIX,
    build_manifest,
    parser_version_for,
    taxonomy_identity,
)
from app.normalization.posting import normalize_posting
from app.normalization.taxonomy import TaxonomyIndex
from app.normalization.types import NormalizationResult, Provenance
from app.providers.greenhouse_posting_inputs import greenhouse_posting_inputs
from app.schemas.discovered_job import DiscoveredJob

# `jobs` column -> D2 component. The only normalized values S3 may write.
PERSISTED_COLUMNS = ("employment_type", "seniority", "country")

# DATA_MODEL.md's provenance order. `unavailable` has no rank: it never writes.
TRUST_RANK: Mapping[Provenance, int] = MappingProxyType(
    {
        Provenance.EXPLICIT_SOURCE: 5,
        Provenance.STRUCTURED_METADATA: 4,
        Provenance.PARSED_DESCRIPTION: 3,
        Provenance.DERIVED: 2,
        Provenance.INFERRED: 1,
    }
)
# Tags a parser result may carry into a write. No composed parser can state an
# explicit or structured fact, so either tag arriving here is a defect.
WRITABLE_PROVENANCE = frozenset(
    {Provenance.PARSED_DESCRIPTION, Provenance.DERIVED, Provenance.INFERRED}
)

ENTRY_KEYS = frozenset(
    {
        "source",
        "provider",
        "provider_source",
        "occurrence_id",
        "raw_job_ingestion_id",
        "parser_version",
        "observed_at",
    }
)
_PARSER_VERSION_RE = re.compile(re.escape(PARSER_VERSION_PREFIX) + "[0-9a-f]{64}")
_COVERED_WHITESPACE = " \t\n\r"

_BUILDER_AUTHORITY = object()
_VERIFIER_AUTHORITY = object()


class NormalizationError(Exception):
    """Base class. Every message is fixed and contains no runtime value."""


class NormalizationBindingError(NormalizationError):
    """A context, provider, or job does not match its verified bindings."""


class ProvenanceEscalationError(NormalizationError):
    """A parser result claims explicit or structured provenance."""


class ProvenanceIntegrityError(NormalizationError):
    """An existing value/provenance pair is malformed, inconsistent, or from an
    unsupported provider. S3 rejects it rather than overwrite it."""


class NormalizationContext:
    """A built, validated D1 manifest with its taxonomy and configuration.
    Construct only through `build_normalization_context`. Immutable."""

    __slots__ = ("_authority", "_canonical", "_version", "_taxonomy", "_content_modes")

    _authority: object
    _canonical: bytes
    _version: str
    _taxonomy: TaxonomyIndex
    _content_modes: Mapping[str, str]

    def __init__(
        self,
        *,
        authority: object,
        canonical: bytes,
        version: str,
        taxonomy: TaxonomyIndex,
        content_modes: Mapping[str, str],
    ) -> None:
        if authority is not _BUILDER_AUTHORITY:
            raise TypeError("NormalizationContext is built only by build_normalization_context")
        object.__setattr__(self, "_authority", authority)
        object.__setattr__(self, "_canonical", canonical)
        object.__setattr__(self, "_version", version)
        object.__setattr__(self, "_taxonomy", taxonomy)
        object.__setattr__(self, "_content_modes", MappingProxyType(dict(content_modes)))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("NormalizationContext is immutable")

    @property
    def parser_version(self) -> str:
        return self._version

    @property
    def manifest(self) -> bytes:
        return self._canonical

    @property
    def taxonomy(self) -> TaxonomyIndex:
        return self._taxonomy

    @property
    def content_modes(self) -> Mapping[str, str]:
        return self._content_modes


def build_normalization_context(content_modes: Mapping[str, str]) -> NormalizationContext:
    """Builds the D1 manifest for a Greenhouse provider's board/content-mode
    snapshot. Raises `ParserVersionError` if any version evidence is missing,
    unresolvable, undeclared, stale, or unapproved."""
    evidence = build_manifest(content_modes)
    return NormalizationContext(
        authority=_BUILDER_AUTHORITY,
        canonical=evidence.canonical,
        version=evidence.version,
        taxonomy=evidence.taxonomy,
        content_modes=evidence.content_modes,
    )


@dataclass(frozen=True)
class NormalizedProjection:
    """The persisted subset of one job's `normalize_posting` result: exactly
    `PERSISTED_COLUMNS`, each still the parser's own `NormalizationResult`."""

    parser_version: str
    fields: Mapping[str, NormalizationResult[str]]


class VerifiedNormalization:
    """A context that `verify_normalization_context` checked against the current
    repository, runtime, taxonomy, and the run's provider. The only object
    `persist_posting` accepts."""

    __slots__ = ("_authority", "_context", "_normalizes")

    _authority: object
    _context: NormalizationContext
    _normalizes: bool

    def __init__(
        self, *, authority: object, context: NormalizationContext, normalizes: bool
    ) -> None:
        if authority is not _VERIFIER_AUTHORITY:
            raise TypeError("VerifiedNormalization is created only by verification")
        object.__setattr__(self, "_authority", authority)
        object.__setattr__(self, "_context", context)
        object.__setattr__(self, "_normalizes", normalizes)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("VerifiedNormalization is immutable")

    def is_authentic(self) -> bool:
        try:
            return self._authority is _VERIFIER_AUTHORITY
        except AttributeError:
            return False

    @property
    def parser_version(self) -> str:
        return self._context.parser_version

    def project(self, job: DiscoveredJob) -> NormalizedProjection | None:
        """`None` for any job this verified run does not normalize. Otherwise
        the three-field projection, after checking the job's board against the
        verified content-mode snapshot. A parser exception propagates."""
        if not self._normalizes:
            return None
        if job.provider != NORMALIZED_PROVIDER or job.source != NORMALIZED_PROVIDER:
            return None
        mode = self._context.content_modes.get(job.source_tenant_id or "")
        if mode is None:
            raise NormalizationBindingError("the job's board is not in the verified configuration")
        if mode not in APPROVED_CONTENT_MODES:
            raise NormalizationBindingError("the job's board content mode is not approved")
        result = normalize_posting(greenhouse_posting_inputs(job), taxonomy=self._context.taxonomy)
        fields: dict[str, NormalizationResult[str]] = {
            # The Literal-typed results are `str` values at runtime.
            "employment_type": cast(NormalizationResult[str], result.employment_type),
            "seniority": cast(NormalizationResult[str], result.seniority),
            "country": result.location.country,
        }
        for value in fields.values():
            _check_incoming(value)
        return NormalizedProjection(parser_version=self.parser_version, fields=fields)


def verify_normalization_context(context: object, provider: object) -> VerifiedNormalization:
    """Independently re-derives every binding of `context` and fails closed on
    any mismatch. Called before any collection run, provider call, or write."""
    if type(context) is not NormalizationContext:
        raise NormalizationBindingError("normalization requires a built NormalizationContext")
    try:
        authentic = context._authority is _BUILDER_AUTHORITY
    except AttributeError:
        authentic = False
    if not authentic:
        raise NormalizationBindingError("normalization requires a built NormalizationContext")

    normalizes = getattr(provider, "name", None) == NORMALIZED_PROVIDER
    if normalizes:
        snapshot = getattr(provider, "board_content_modes", None)
        if not isinstance(snapshot, Mapping):
            raise NormalizationBindingError("the provider exposes no board content-mode snapshot")
        if dict(snapshot) != dict(context.content_modes):
            raise NormalizationBindingError("the provider's board configuration does not match")

    # Raises `ParserVersionError` itself when current evidence cannot be built.
    fresh = build_manifest(context.content_modes)
    if (
        fresh.canonical != context.manifest
        or fresh.version != context.parser_version
        or parser_version_for(context.manifest) != context.parser_version
        or taxonomy_identity(context.taxonomy) != taxonomy_identity(fresh.taxonomy)
        or dict(fresh.content_modes) != dict(context.content_modes)
    ):
        raise NormalizationBindingError("the normalization context does not match current evidence")
    return VerifiedNormalization(
        authority=_VERIFIER_AUTHORITY, context=context, normalizes=normalizes
    )


def _check_incoming(result: NormalizationResult[str]) -> None:
    if result.provenance is Provenance.UNAVAILABLE:
        return
    if result.provenance not in WRITABLE_PROVENANCE:
        raise ProvenanceEscalationError("a parser result claims explicit or structured provenance")
    value = result.value
    if not isinstance(value, str) or not value or value.strip(_COVERED_WHITESPACE) != value:
        raise NormalizationBindingError("a normalized value is not already trimmed text")


@dataclass(frozen=True)
class EntryOrigin:
    """Where one write comes from: the evidence every entry records."""

    occurrence_id: uuid.UUID
    raw_job_ingestion_id: uuid.UUID
    parser_version: str
    observed_at: datetime


@dataclass(frozen=True)
class FieldWrite:
    value: str
    entry: dict[str, str]


@dataclass(frozen=True)
class _ExistingEntry:
    rank: int
    parser_version: str
    observed_at: datetime


def _parse_existing_entry(entry: object) -> _ExistingEntry:
    if not isinstance(entry, dict) or set(entry) != ENTRY_KEYS:
        raise ProvenanceIntegrityError("an existing provenance entry is malformed")
    if not all(isinstance(value, str) for value in entry.values()):
        raise ProvenanceIntegrityError("an existing provenance entry is malformed")
    if entry["provider"] != NORMALIZED_PROVIDER or entry["provider_source"] != NORMALIZED_PROVIDER:
        raise ProvenanceIntegrityError("an existing provenance entry is from another provider")
    try:
        provenance = Provenance(entry["source"])
        uuid.UUID(entry["occurrence_id"])
        uuid.UUID(entry["raw_job_ingestion_id"])
        observed_at = datetime.fromisoformat(entry["observed_at"])
    except ValueError as exc:
        raise ProvenanceIntegrityError("an existing provenance entry is malformed") from exc
    if provenance not in TRUST_RANK:
        raise ProvenanceIntegrityError("an existing provenance entry is malformed")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ProvenanceIntegrityError("an existing provenance entry is malformed")
    if not _PARSER_VERSION_RE.fullmatch(entry["parser_version"]):
        raise ProvenanceIntegrityError("an existing provenance entry is malformed")
    return _ExistingEntry(TRUST_RANK[provenance], entry["parser_version"], observed_at)


def merge_field(
    incoming: NormalizationResult[str],
    *,
    existing_value: object,
    existing_entry: object,
    origin: EntryOrigin,
) -> FieldWrite | None:
    """The S3 precedence rule for one field. `None` means "leave the column and
    its entry exactly as they are".

    1. An `unavailable` result never writes, so an abstention never erases.
    2. An explicit or structured incoming tag raises (escalation).
    3. No existing value and no entry: write.
    4. A value without an entry, an entry without a value, or a malformed or
       foreign-provider entry: raise, never overwrite.
    5. Higher trust replaces; lower trust is kept.
    6. Equal trust: a strictly later `observed_at` replaces and an earlier one
       is kept. At an equal instant, an identical value is a no-op (so a rerun
       is idempotent) and a differing value is refused, whatever the parser
       versions: a parser version is evidence, not an ordering signal, so it
       never decides which of two equal-time results wins. A corrected parser
       result replaces an equal-trust value only through a later observation.

    S3 has exactly one normalized provider. Cross-provider priority is not
    implemented: entries from any other provider are rejected (rule 4), and
    enabling a second normalized provider requires a separately reviewed
    provider-priority policy first.
    """
    _check_incoming(incoming)
    if incoming.provenance is Provenance.UNAVAILABLE:
        return None
    assert incoming.value is not None
    if existing_value is None and existing_entry is None:
        return _write(incoming, origin)
    if existing_value is None or existing_entry is None:
        raise ProvenanceIntegrityError("an existing value and its provenance are inconsistent")
    existing = _parse_existing_entry(existing_entry)
    rank = TRUST_RANK[incoming.provenance]
    if rank != existing.rank:
        return _write(incoming, origin) if rank > existing.rank else None
    if origin.observed_at != existing.observed_at:
        return _write(incoming, origin) if origin.observed_at > existing.observed_at else None
    if incoming.value == existing_value:
        return None
    raise ProvenanceIntegrityError(
        "conflicting equal-trust values were observed at the same instant"
    )


def _write(incoming: NormalizationResult[str], origin: EntryOrigin) -> FieldWrite:
    if not _PARSER_VERSION_RE.fullmatch(origin.parser_version):
        raise NormalizationBindingError("a write carries a malformed parser version")
    if origin.observed_at.tzinfo is None or origin.observed_at.utcoffset() is None:
        raise NormalizationBindingError("a write carries a naive observation time")
    assert incoming.value is not None
    return FieldWrite(
        value=incoming.value,
        entry={
            "source": incoming.provenance.value,
            "provider": NORMALIZED_PROVIDER,
            "provider_source": NORMALIZED_PROVIDER,
            "occurrence_id": str(origin.occurrence_id),
            "raw_job_ingestion_id": str(origin.raw_job_ingestion_id),
            "parser_version": origin.parser_version,
            "observed_at": origin.observed_at.isoformat(),
        },
    )
