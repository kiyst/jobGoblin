import hashlib
from dataclasses import dataclass
from enum import Enum

# Must stay byte-for-byte in sync with `JobOccurrence`'s own ORM validators
# (`app/db/models/job_occurrence.py::_normalize_canonical_identifier`/
# `_normalize_nullable_text`) — this module canonicalizes *before* the ORM
# ever sees the value (to pick a lock key and query the database), so a
# divergence here would mean two logically-identical rows take different
# advisory locks or query different values than what's actually stored.
_COVERED_WHITESPACE = " \t\n\r"


def canonicalize_identifier(value: str) -> str:
    """`provider`/`source` canonicalization: trim + lowercase — must match
    `JobOccurrence._normalize_canonical_identifier` exactly."""
    return value.strip(_COVERED_WHITESPACE).lower()


def canonicalize_nullable_text(value: str | None) -> str | None:
    """`source_tenant_id`/`source_job_id`/`requisition_id_raw` canonicalization:
    trim only, case preserved, blank collapses to `None` — must match
    `JobOccurrence._normalize_nullable_text` exactly."""
    if value is None:
        return None
    trimmed = value.strip(_COVERED_WHITESPACE)
    return trimmed or None


class NaturalKeyDomain(Enum):
    """One domain per partial unique index on `job_occurrences` (ADR 0004).
    Values are fixed, single-byte tags baked into the canonical
    representation below — never renumber an existing member; add new
    members with new values only, since existing advisory-lock keys must
    stay stable across a deploy.

    These tags distinguish Tier 1's *three natural-key forms* only — they
    are unrelated to ARCHITECTURE.md §8's Tier 1-5 *precedence* numbering.
    The Tier-2/Tier-3 cross-occurrence advisory-lock tags below
    (`_CANONICAL_URL_LOCK_TAG` / `_TENANT_REQUISITION_LOCK_TAG`) live in
    the same encoded-byte namespace as these but are deliberately assigned
    values (4, 5) outside this enum's range — see their own docstrings for
    why reusing e.g. `TENANT`'s tag (1) for the Tier-3 lock would be
    unsafe.
    """

    TENANT = 1
    NO_TENANT = 2
    URL = 3


_DOMAIN_BYTES: dict[NaturalKeyDomain, bytes] = {
    domain: bytes([domain.value]) for domain in NaturalKeyDomain
}

# Bump only if the encoding scheme itself changes shape (e.g. a new
# component, a different length-prefix width) — never to fix a value bug,
# which would silently change every existing lock key without warning.
_ENCODING_VERSION = 1
_VERSION_BYTE = bytes([_ENCODING_VERSION])

# Tier-2 (canonical URL) and Tier-3 (tenant-scoped requisition)
# cross-occurrence advisory-lock domain tags — see
# `canonical_url_advisory_lock_key`/`tenant_requisition_advisory_lock_key`.
_CANONICAL_URL_LOCK_TAG = bytes([4])
_TENANT_REQUISITION_LOCK_TAG = bytes([5])


def _encode_length_prefixed(*components: str) -> bytes:
    """Length-prefixes each component (4-byte big-endian byte count, then
    its UTF-8 bytes) so component *boundaries* are unambiguous — shared by
    `NaturalKey.canonical_bytes()` and the two module-level lock-key
    functions below, so all three encodings follow one audited scheme."""
    encoded = bytearray()
    for component in components:
        component_bytes = component.encode("utf-8")
        encoded += len(component_bytes).to_bytes(4, "big")
        encoded += component_bytes
    return bytes(encoded)


def _lock_key_from_bytes(encoded: bytes) -> int:
    """SHA-256 the encoded byte sequence, then reinterpret the first 8
    digest bytes as a signed 64-bit integer suitable for
    `pg_advisory_xact_lock(bigint)` — shared by every lock-key function in
    this module. Never Python's salted, process-randomized `hash()`, and
    never PostgreSQL's own 32-bit `hashtext()`, whose narrower range
    collides far more often."""
    digest = hashlib.sha256(encoded).digest()
    unsigned = int.from_bytes(digest[:8], "big", signed=False)
    return unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned


@dataclass(frozen=True, slots=True)
class NaturalKey:
    """One of the three scoped identity signals ADR 0004 defines, already
    canonicalized (see `resolve_natural_key` below) — never construct this
    directly from raw, un-canonicalized input."""

    domain: NaturalKeyDomain
    provider: str
    source: str
    tenant_id: str | None = None
    job_id: str | None = None
    url_normalized: str | None = None

    def _components(self) -> tuple[str, ...]:
        if self.domain is NaturalKeyDomain.TENANT:
            assert self.tenant_id is not None and self.job_id is not None
            return (self.provider, self.source, self.tenant_id, self.job_id)
        if self.domain is NaturalKeyDomain.NO_TENANT:
            assert self.job_id is not None
            return (self.provider, self.source, self.job_id)
        assert self.url_normalized is not None
        return (self.provider, self.source, self.url_normalized)

    def canonical_bytes(self) -> bytes:
        """Versioned, domain-tagged, length-prefixed encoding — never a bare
        colon-joined string. Length-prefixing each component makes
        component *boundaries* unambiguous: `("AB", "C")` and `("A", "BC")`
        encode to different byte sequences even though a naive
        concatenation would collide. The domain byte additionally
        guarantees the three natural-key forms can never collide with each
        other even given identical component values, and the version byte
        lets this scheme change shape later without silently colliding
        with keys computed under an earlier version.
        """
        return (
            _VERSION_BYTE
            + _DOMAIN_BYTES[self.domain]
            + _encode_length_prefixed(*self._components())
        )

    def advisory_lock_key(self) -> int:
        """A stable signed 64-bit integer suitable for
        `pg_advisory_xact_lock(bigint)`."""
        return _lock_key_from_bytes(self.canonical_bytes())


def canonical_url_advisory_lock_key(canonical_url_normalized: str) -> int:
    """Tier 2's own advisory-lock domain (ARCHITECTURE.md §8 item 2,
    cross-occurrence normalized-canonical-URL matching) — tag `4`, never a
    `NaturalKeyDomain` member (canonical-URL matching is not one of Tier
    1's three natural-key *forms*; it is a separate, later precedence
    tier). Serializes concurrent attempts to attach a new occurrence to,
    or create a Job for, the same canonical URL — see
    `ingestion/persistence.py::_attach_to_candidate`.
    """
    encoded = (
        _VERSION_BYTE + _CANONICAL_URL_LOCK_TAG + _encode_length_prefixed(canonical_url_normalized)
    )
    return _lock_key_from_bytes(encoded)


def tenant_requisition_advisory_lock_key(
    provider: str, source: str, tenant_id: str, requisition_id: str
) -> int:
    """Tier 3's own advisory-lock domain (ARCHITECTURE.md §8 item 3,
    tenant-scoped requisition matching) — tag `5`, deliberately distinct
    from `NaturalKeyDomain.TENANT`'s tag (`1`) even though both encode a
    `(provider, source, tenant, <identifier>)`-shaped key: a posting's
    `source_job_id` and `requisition_id_raw` are different fields that can
    coincidentally hold the same value, so reusing tag `1` here could let a
    real Tier-1 natural-key lock collide byte-for-byte with an unrelated
    Tier-3 lookup lock whenever that coincidence occurs. All four
    components must already be canonicalized by the caller
    (`canonicalize_identifier`/`canonicalize_nullable_text`) before this
    function is called.
    """
    encoded = (
        _VERSION_BYTE
        + _TENANT_REQUISITION_LOCK_TAG
        + _encode_length_prefixed(provider, source, tenant_id, requisition_id)
    )
    return _lock_key_from_bytes(encoded)


def resolve_natural_key(
    provider: str,
    source: str,
    *,
    source_tenant_id: str | None,
    source_job_id: str | None,
    source_url_normalized: str | None,
) -> NaturalKey | None:
    """Selects and canonicalizes whichever of the three natural-key forms
    applies, in ADR 0004's own precedence order. Returns `None` only when
    none of the three can be established — `source_job_id` is absent *and*
    no normalized fallback URL is available either; the caller
    (`ingestion/identity.py`) raises `UnresolvableIdentityError` for that
    case."""
    provider_c = canonicalize_identifier(provider)
    source_c = canonicalize_identifier(source)
    tenant_c = canonicalize_nullable_text(source_tenant_id)
    job_id_c = canonicalize_nullable_text(source_job_id)

    # `url_normalized` is carried on every returned `NaturalKey` regardless of
    # which domain actually wins, purely so `ingestion/persistence.py` can
    # populate `JobOccurrence.source_url_normalized` without calling
    # `normalize_url()` a second time — `_components()` only *uses* it (for
    # locking/lookup) when `domain is URL`.
    if job_id_c is not None and tenant_c is not None:
        return NaturalKey(
            NaturalKeyDomain.TENANT,
            provider_c,
            source_c,
            tenant_id=tenant_c,
            job_id=job_id_c,
            url_normalized=source_url_normalized,
        )
    if job_id_c is not None:
        return NaturalKey(
            NaturalKeyDomain.NO_TENANT,
            provider_c,
            source_c,
            job_id=job_id_c,
            url_normalized=source_url_normalized,
        )
    if source_url_normalized is not None:
        return NaturalKey(
            NaturalKeyDomain.URL, provider_c, source_c, url_normalized=source_url_normalized
        )
    return None
