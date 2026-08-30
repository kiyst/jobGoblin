from app.ingestion.natural_key import (
    NaturalKey,
    NaturalKeyDomain,
    canonical_url_advisory_lock_key,
    canonicalize_identifier,
    canonicalize_nullable_text,
    resolve_natural_key,
    tenant_requisition_advisory_lock_key,
)


def test_casing_and_covered_whitespace_variants_produce_the_same_lock_key() -> None:
    """A raw payload whose provider/source/tenant/job-id differ only by
    casing (provider/source) or covered whitespace (all four) must
    canonicalize to the exact same stored database identity — and
    therefore must take the exact same advisory lock."""
    plain = resolve_natural_key(
        "fixture_provider",
        "fixture_ats",
        source_tenant_id="acme-corp",
        source_job_id="REQ-1001",
        source_url_normalized=None,
    )
    noisy = resolve_natural_key(
        "  Fixture_Provider\t",
        "\nFIXTURE_ATS  ",
        source_tenant_id="  acme-corp\r",
        source_job_id="\tREQ-1001 ",
        source_url_normalized=None,
    )
    assert plain is not None and noisy is not None
    assert plain.canonical_bytes() == noisy.canonical_bytes()
    assert plain.advisory_lock_key() == noisy.advisory_lock_key()


def test_covered_whitespace_only_tenant_id_is_treated_as_absent() -> None:
    """A tenant id that is only covered whitespace collapses to `None`
    (matching `JobOccurrence._normalize_nullable_text`), so it must select
    the no-tenant domain, not the tenant domain."""
    key = resolve_natural_key(
        "fixture_provider",
        "fixture_ats",
        source_tenant_id="   \t\r\n  ",
        source_job_id="REQ-1001",
        source_url_normalized=None,
    )
    assert key is not None
    assert key.domain is NaturalKeyDomain.NO_TENANT


def test_structurally_different_component_boundaries_cannot_collide() -> None:
    """Length-prefixing each component must prevent a component-boundary
    ambiguity: `("AB", "C")` and `("A", "BC")` would concatenate to the
    same raw string (`"ABC"`) without length-prefixing, but must never
    produce the same canonical bytes or lock key."""
    key_ab_c = resolve_natural_key(
        "p", "s", source_tenant_id="AB", source_job_id="C", source_url_normalized=None
    )
    key_a_bc = resolve_natural_key(
        "p", "s", source_tenant_id="A", source_job_id="BC", source_url_normalized=None
    )
    assert key_ab_c is not None and key_a_bc is not None
    assert key_ab_c.canonical_bytes() != key_a_bc.canonical_bytes()
    assert key_ab_c.advisory_lock_key() != key_a_bc.advisory_lock_key()


def test_three_natural_key_domains_remain_distinct() -> None:
    """The same provider/source/component *value* under each of the three
    domains must never collide — the domain tag alone must separate them,
    independent of component content."""
    tenant_key = resolve_natural_key(
        "p", "s", source_tenant_id="x", source_job_id="x", source_url_normalized=None
    )
    no_tenant_key = resolve_natural_key(
        "p", "s", source_tenant_id=None, source_job_id="x", source_url_normalized=None
    )
    url_key = resolve_natural_key(
        "p", "s", source_tenant_id=None, source_job_id=None, source_url_normalized="x"
    )
    assert tenant_key is not None
    assert no_tenant_key is not None
    assert url_key is not None
    assert tenant_key.domain is NaturalKeyDomain.TENANT
    assert no_tenant_key.domain is NaturalKeyDomain.NO_TENANT
    assert url_key.domain is NaturalKeyDomain.URL

    keys = [tenant_key, no_tenant_key, url_key]
    canonical_forms = {key.canonical_bytes() for key in keys}
    lock_keys = {key.advisory_lock_key() for key in keys}
    assert len(canonical_forms) == 3
    assert len(lock_keys) == 3


def test_no_job_id_and_no_url_resolves_to_none() -> None:
    assert (
        resolve_natural_key(
            "p", "s", source_tenant_id=None, source_job_id=None, source_url_normalized=None
        )
        is None
    )


def test_canonicalize_identifier_trims_and_lowercases() -> None:
    assert canonicalize_identifier("  Fixture_Provider\t") == "fixture_provider"


def test_canonicalize_nullable_text_preserves_case_trims_and_collapses_blank() -> None:
    assert canonicalize_nullable_text("  REQ-1001 ") == "REQ-1001"
    assert canonicalize_nullable_text("   \t\r\n  ") is None
    assert canonicalize_nullable_text(None) is None


def test_canonical_url_lock_key_never_collides_with_a_natural_key_lock() -> None:
    """Tier 2's cross-occurrence lock domain (tag 4) must never collide
    with any of Tier 1's three natural-key-domain tags (1/2/3), even when
    the underlying string value is identical."""
    value = "https://example.com/jobs/1"
    canonical_url_key = canonical_url_advisory_lock_key(value)

    url_domain_key = NaturalKey(
        NaturalKeyDomain.URL, "p", "s", url_normalized=value
    ).advisory_lock_key()
    assert canonical_url_key != url_domain_key


def test_tenant_requisition_lock_key_never_collides_with_a_tenant_natural_key_lock() -> None:
    """Tier 3's lock domain (tag 5) must never collide with
    `NaturalKeyDomain.TENANT`'s own lock (tag 1), even when
    `source_job_id` and `requisition_id_raw` coincidentally hold the same
    value — the one scenario where the encoded component values would
    otherwise be byte-for-byte identical apart from the tag."""
    provider, source, tenant, identifier = "p", "s", "acme-corp", "REQ-1001"

    tenant_requisition_key = tenant_requisition_advisory_lock_key(
        provider, source, tenant, identifier
    )
    natural_tenant_key = NaturalKey(
        NaturalKeyDomain.TENANT, provider, source, tenant_id=tenant, job_id=identifier
    ).advisory_lock_key()

    assert tenant_requisition_key != natural_tenant_key


def test_canonical_url_and_tenant_requisition_lock_keys_are_deterministic() -> None:
    """Same input must always yield the same lock key (required for the
    advisory lock to actually serialize repeated calls for the same
    signal)."""
    assert canonical_url_advisory_lock_key("https://example.com/x") == (
        canonical_url_advisory_lock_key("https://example.com/x")
    )
    assert tenant_requisition_advisory_lock_key("p", "s", "t", "r") == (
        tenant_requisition_advisory_lock_key("p", "s", "t", "r")
    )


def test_tenant_requisition_lock_key_respects_component_boundaries() -> None:
    """Length-prefixing must prevent a component-boundary ambiguity across
    all four components, mirroring `NaturalKey`'s own boundary guarantee."""
    key_ab_c = tenant_requisition_advisory_lock_key("p", "s", "AB", "C")
    key_a_bc = tenant_requisition_advisory_lock_key("p", "s", "A", "BC")
    assert key_ab_c != key_a_bc
