"""add saved_search_locations table

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-26

Sixth Phase 1 domain table (docs/DATA_MODEL.md's `saved_search_locations`
section) — the final child table of the `saved_searches` group. No other
table is touched by this migration.

Product rules resolved by explicit approval before this migration was
written (not inferred silently):

- `location_text` is normalized the same way `saved_search_titles.title` is:
  trimmed of the four-character whitespace set (space, tab, LF, CR),
  enforced by database `CHECK`s in addition to an ORM `@validates`
  normalizer — case preserved, never lowercased.
- Case-insensitive, per-search uniqueness is enforced by a functional unique
  index on `(saved_search_id, lower(location_text))` only — not
  `lower(trim(location_text))`. Because the normalization `CHECK`s above
  already guarantee every stored value is trimmed, the stored-value
  invariant is equivalent to (and stronger than) trimming again inside the
  index expression, so the redundant `trim()` is not repeated here. See
  `docs/DATA_MODEL.md` for the corrected explanation.
- `latitude`/`longitude` are nullable (until geocoded) `numeric` columns
  with no precision/scale, each restricted by a `CHECK` to a valid
  coordinate range (`[-90, 90]` / `[-180, 180]`), plus a coordinate-pair
  `CHECK` requiring both be NULL or both be non-NULL — a half-geocoded row
  is not a valid state.
- `radius_miles_override` is a nullable `numeric` column with no
  precision/scale, restricted by a `CHECK` to NULL or `>= 0`, matching
  `saved_searches.radius_miles`'s established pattern. It falls back to
  `saved_searches.radius_miles` at the application layer when NULL; nothing
  about that fallback is enforced by this migration.
- `created_at`/`updated_at` are added as non-null `timestamptz` columns with
  `server_default now()`, consistent with every other implemented table,
  even though the column list in `docs/DATA_MODEL.md`'s
  `saved_search_locations` section omitted them (the same recurring gap
  already fixed for `users`, `candidate_skills`, `saved_searches`, and
  `saved_search_titles`).
- No separate plain index on `saved_search_id`: it is already the leading
  column of the composite unique index above, so a second index would be
  redundant for lookups.

`docs/DATA_MODEL.md`'s prose previously said each location carries its own
"radius/remote override." No remote-override column has ever been
documented or approved for this table (only `radius_miles_override`
exists) — that phrase was stale wording, corrected alongside this migration
rather than treated as a request to add a new column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        "saved_search_locations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("saved_search_id", sa.Uuid(), nullable=False),
        sa.Column("location_text", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Numeric(), nullable=True),
        sa.Column("longitude", sa.Numeric(), nullable=True),
        sa.Column("radius_miles_override", sa.Numeric(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            r"location_text = trim(both E'\t\n\r ' from location_text)",
            name=op.f("ck_saved_search_locations_location_text_normalized"),
        ),
        sa.CheckConstraint(
            r"trim(both E'\t\n\r ' from location_text) <> ''",
            name=op.f("ck_saved_search_locations_location_text_not_empty"),
        ),
        sa.CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name=op.f("ck_saved_search_locations_latitude_in_range"),
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name=op.f("ck_saved_search_locations_longitude_in_range"),
        ),
        sa.CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)",
            name=op.f("ck_saved_search_locations_latitude_longitude_both_or_neither"),
        ),
        sa.CheckConstraint(
            "radius_miles_override IS NULL OR radius_miles_override >= 0",
            name=op.f("ck_saved_search_locations_radius_miles_override_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["saved_search_id"],
            ["saved_searches.id"],
            name=op.f("fk_saved_search_locations_saved_search_id_saved_searches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_search_locations")),
    )
    # Expression/functional unique index — a UNIQUE table constraint can only
    # cover plain columns, not lower(location_text), so an index is the only
    # way to enforce case-insensitive, per-search uniqueness while still
    # storing and returning the original case. Only lower(...) is needed,
    # not lower(trim(...)): the CHECK constraints above already guarantee
    # every stored value is trimmed.
    op.create_index(
        "uq_saved_search_locations_search_id_text_lower",
        "saved_search_locations",
        ["saved_search_id", sa.text("lower(location_text)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_saved_search_locations_search_id_text_lower", table_name="saved_search_locations"
    )
    op.drop_table("saved_search_locations")
