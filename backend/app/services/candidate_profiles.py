import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.candidate_profile import REMOTE_PREFERENCES, CandidateProfile

# Every mapped column except `id`/`user_id`/`created_at`/`updated_at` — identity,
# ownership, and audit columns are never caller-settable through `update()`.
_UPDATABLE_FIELDS = frozenset(
    {
        "target_role_families",
        "years_experience",
        "education",
        "certifications",
        "clearance",
        "preferred_industries",
        "excluded_industries",
        "preferred_locations",
        "relocation_willingness",
        "remote_preference",
        "salary_expectation_min",
        "salary_expectation_max",
    }
)


async def create(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    remote_preference: str,
    years_experience: int | None = None,
    education: str | None = None,
    certifications: list[str] | None = None,
    clearance: str | None = None,
    preferred_industries: list[str] | None = None,
    excluded_industries: list[str] | None = None,
    preferred_locations: list[str] | None = None,
    relocation_willingness: bool | None = None,
    target_role_families: list[str] | None = None,
    salary_expectation_min: int | None = None,
    salary_expectation_max: int | None = None,
) -> CandidateProfile:
    """Insert a new `CandidateProfile` for `user_id`. Flushes (so the
    `UNIQUE(user_id)`/`CHECK` constraints are evaluated immediately) but never
    commits or rolls back — the caller owns the transaction. A second `create()`
    for the same `user_id` is rejected by the database's own `UNIQUE` constraint,
    not a Python-side pre-check, matching this schema's existing precedent that
    the constraint itself is the backstop.
    """
    if remote_preference not in REMOTE_PREFERENCES:
        raise ValueError(f"invalid remote_preference: {remote_preference!r}")

    profile = CandidateProfile(
        user_id=user_id,
        remote_preference=remote_preference,
        years_experience=years_experience,
        education=education,
        certifications=certifications,
        clearance=clearance,
        preferred_industries=preferred_industries,
        excluded_industries=excluded_industries,
        preferred_locations=preferred_locations,
        relocation_willingness=relocation_willingness,
        target_role_families=target_role_families,
        salary_expectation_min=salary_expectation_min,
        salary_expectation_max=salary_expectation_max,
    )
    session.add(profile)
    await session.flush()
    return profile


async def get_for_user(session: AsyncSession, user_id: uuid.UUID) -> CandidateProfile | None:
    """Fetch the `CandidateProfile` owned by `user_id`, or `None` if it doesn't
    exist. `CandidateProfile.user_id` is `UNIQUE`, so this is always at most
    one row."""
    result = await session.execute(
        select(CandidateProfile).where(CandidateProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update(
    session: AsyncSession, user_id: uuid.UUID, **fields: object
) -> CandidateProfile | None:
    """Update the `CandidateProfile` owned by `user_id`. Never accepts a
    pre-fetched instance as the update authority — ownership is re-derived
    from `user_id` on every call, internally, via `get_for_user()`.

    The entire request is validated — every field name against
    `_UPDATABLE_FIELDS`, every enum value against its allowed set — before any
    row is fetched or mutated: an unknown field name or an invalid
    `remote_preference` raises `ValueError` with zero mutation, regardless of
    whether a profile exists for `user_id`. Only after that validation passes
    is the profile fetched; a missing profile returns `None` with zero
    mutation. Non-enum `CHECK`-backed fields (the non-negative/ordering
    checks) are intentionally not re-validated here — the database constraint
    remains the sole backstop, as it is for every other table in this schema.

    Flushes but never commits or rolls back — the caller owns the
    transaction.
    """
    unknown_fields = set(fields) - _UPDATABLE_FIELDS
    if unknown_fields:
        raise ValueError(f"cannot update fields: {sorted(unknown_fields)}")
    if "remote_preference" in fields and fields["remote_preference"] not in REMOTE_PREFERENCES:
        raise ValueError(f"invalid remote_preference: {fields['remote_preference']!r}")

    profile = await get_for_user(session, user_id)
    if profile is None:
        return None

    for key, value in fields.items():
        setattr(profile, key, value)
    await session.flush()
    return profile
