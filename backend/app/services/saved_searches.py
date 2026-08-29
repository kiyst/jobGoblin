import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.saved_search import POLLING_SCHEDULES, REMOTE_RULES, SavedSearch

# Every mapped column except `id`/`user_id`/`created_at`/`updated_at` — identity,
# ownership, and audit columns are never caller-settable through `update()`.
# `is_active` is deliberately included here even though `create()` omits it
# from its own parameters (see below).
_UPDATABLE_FIELDS = frozenset(
    {
        "name",
        "excluded_titles",
        "industries",
        "employment_types",
        "seniority",
        "must_have_skills",
        "preferred_skills",
        "excluded_keywords",
        "preferred_companies",
        "excluded_companies",
        "enabled_providers",
        "radius_miles",
        "remote_rules",
        "salary_floor",
        "preferred_salary",
        "recency_limit_hours",
        "enabled_sources",
        "polling_schedule",
        "scoring_weights",
        "is_active",
    }
)

# Every enum-valued column, mapped to its allowed set — checked in `update()`
# the same way `create()` checks them as explicit parameters.
_ENUM_FIELDS: dict[str, tuple[str, ...]] = {
    "remote_rules": REMOTE_RULES,
    "polling_schedule": POLLING_SCHEDULES,
}


async def create(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    name: str,
    remote_rules: str,
    polling_schedule: str,
    excluded_titles: list[str] | None = None,
    industries: list[str] | None = None,
    employment_types: list[str] | None = None,
    seniority: list[str] | None = None,
    must_have_skills: list[str] | None = None,
    preferred_skills: list[str] | None = None,
    excluded_keywords: list[str] | None = None,
    preferred_companies: list[str] | None = None,
    excluded_companies: list[str] | None = None,
    enabled_providers: list[str] | None = None,
    radius_miles: Decimal | None = None,
    salary_floor: int | None = None,
    preferred_salary: int | None = None,
    recency_limit_hours: int | None = None,
    enabled_sources: dict[str, object] | None = None,
    scoring_weights: dict[str, object] | None = None,
) -> SavedSearch:
    """Insert a new `SavedSearch` for `user_id`. `is_active` is deliberately
    not a parameter here: the column has a `server_default` (`true`), and
    omitting it entirely — rather than passing `None` or `True` — is this
    schema's established convention for letting the database's own default
    apply (see `app/db/models/saved_search.py`). It becomes settable once the
    row exists, through `update()`.

    `enabled_sources`/`scoring_weights` are likewise omitted from the ORM
    constructor call when left as `None`, never passed through as an explicit
    `None` value: SQLAlchemy's `JSONB` type (without `none_as_null=True`,
    which this column does not set) serializes an explicitly-assigned Python
    `None` as the JSON literal `null`, not SQL `NULL` — which then fails
    `enabled_sources`/`scoring_weights`'s own `jsonb_typeof(...) = 'object'`
    `CHECK` (a JSON `null` is neither SQL `NULL` nor a JSON object). Omitting
    the attribute entirely leaves it genuinely unset, which the database
    correctly stores as SQL `NULL`.

    Flushes (so `CHECK` constraints are evaluated immediately) but never
    commits or rolls back — the caller owns the transaction. A user may own
    any number of `SavedSearch` rows; there is no uniqueness constraint to
    violate here.
    """
    if remote_rules not in REMOTE_RULES:
        raise ValueError(f"invalid remote_rules: {remote_rules!r}")
    if polling_schedule not in POLLING_SCHEDULES:
        raise ValueError(f"invalid polling_schedule: {polling_schedule!r}")

    search = SavedSearch(
        user_id=user_id,
        name=name,
        remote_rules=remote_rules,
        polling_schedule=polling_schedule,
        excluded_titles=excluded_titles,
        industries=industries,
        employment_types=employment_types,
        seniority=seniority,
        must_have_skills=must_have_skills,
        preferred_skills=preferred_skills,
        excluded_keywords=excluded_keywords,
        preferred_companies=preferred_companies,
        excluded_companies=excluded_companies,
        enabled_providers=enabled_providers,
        radius_miles=radius_miles,
        salary_floor=salary_floor,
        preferred_salary=preferred_salary,
        recency_limit_hours=recency_limit_hours,
    )
    if enabled_sources is not None:
        search.enabled_sources = enabled_sources
    if scoring_weights is not None:
        search.scoring_weights = scoring_weights
    session.add(search)
    await session.flush()
    return search


async def get_for_user(
    session: AsyncSession, user_id: uuid.UUID, saved_search_id: uuid.UUID
) -> SavedSearch | None:
    """Fetch the `SavedSearch` identified by `saved_search_id`, scoped to
    `user_id` in the same query. A row that exists but belongs to a different
    user is indistinguishable from a nonexistent row — both return `None`.
    Deliberate for Phase 1: a future API layer (Phase 8) consuming this
    return value cannot recover a 403-vs-404 distinction from this boundary
    alone and will need to accept "404 either way" or add its own separate
    ownership check if it wants to differ."""
    result = await session.execute(
        select(SavedSearch).where(
            SavedSearch.id == saved_search_id, SavedSearch.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def update(
    session: AsyncSession,
    user_id: uuid.UUID,
    saved_search_id: uuid.UUID,
    **fields: object,
) -> SavedSearch | None:
    """Update the `SavedSearch` identified by `saved_search_id`, scoped to
    `user_id`. Never accepts a pre-fetched instance as the update authority —
    ownership is re-derived from both `user_id` and `saved_search_id` on
    every call, internally, via `get_for_user()`.

    The entire request is validated — every field name against
    `_UPDATABLE_FIELDS`, every enum value against its allowed set — before any
    row is fetched or mutated: an unknown field name or an invalid
    `remote_rules`/`polling_schedule` raises `ValueError` with zero mutation,
    regardless of whether a matching row exists. Only after that validation
    passes is the row fetched; a missing row, or a row owned by a different
    user, returns `None` with zero mutation — the two cases are deliberately
    indistinguishable. Non-enum `CHECK`-backed fields are intentionally not
    re-validated here — the database constraint remains the sole backstop.

    Known limitation: passing `enabled_sources=None`/`scoring_weights=None`
    here to explicitly clear an existing value will raise `IntegrityError`
    rather than clear it, for the same `JSONB`-serializes-`None`-as-JSON-
    `null` reason documented on `create()` above — `setattr(search, key,
    None)` on an already-persistent row hits the identical `CHECK` as an
    explicit `None` at construction time, and this function does not work
    around it (no Phase 1 caller needs to clear either field yet — no
    routes exist). Every other field, including every other nullable one,
    clears to a genuine `NULL` correctly via `None`.

    Flushes but never commits or rolls back — the caller owns the
    transaction.
    """
    unknown_fields = set(fields) - _UPDATABLE_FIELDS
    if unknown_fields:
        raise ValueError(f"cannot update fields: {sorted(unknown_fields)}")
    for field_name, allowed_values in _ENUM_FIELDS.items():
        if field_name in fields and fields[field_name] not in allowed_values:
            raise ValueError(f"invalid {field_name}: {fields[field_name]!r}")

    search = await get_for_user(session, user_id, saved_search_id)
    if search is None:
        return None

    for key, value in fields.items():
        setattr(search, key, value)
    await session.flush()
    return search
