import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import Uuid

from app.db.base import Base

# Same four-character whitespace set as `CandidateSkill._COVERED_WHITESPACE` /
# `SavedSearch._COVERED_WHITESPACE` / `SavedSearchTitle._COVERED_WHITESPACE`:
# space, tab, line feed, carriage return. `location_text` is trim-only, like
# `title`/`skill`/`name` — never lowercased; case-insensitive matching is
# handled separately by the functional unique index below.
_COVERED_WHITESPACE = " \t\n\r"


class SavedSearchLocation(Base):
    """One location for a `saved_searches` row
    (docs/DATA_MODEL.md §saved_search_locations). Split out rather than an
    array column on `saved_searches` because each location independently
    carries its own radius override and future per-location geocoding
    (master spec §30) keys off individual rows rather than a whole saved
    search.

    `latitude`/`longitude` are nullable until geocoded, and — per the
    coordinate-pair CHECK below — must be either both NULL or both non-NULL;
    a half-geocoded row is not a valid state. `radius_miles_override` is
    nullable and falls back to `saved_searches.radius_miles` when NULL, same
    as documented. All three numeric columns are deliberately left with no
    precision/scale, same as `saved_searches.radius_miles`.
    """

    __tablename__ = "saved_search_locations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    saved_search_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("saved_searches.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_text: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    radius_miles_override: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            r"location_text = trim(both E'\t\n\r ' from location_text)",
            name="location_text_normalized",
        ),
        CheckConstraint(
            r"trim(both E'\t\n\r ' from location_text) <> ''",
            name="location_text_not_empty",
        ),
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="latitude_in_range",
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="longitude_in_range",
        ),
        CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)",
            name="latitude_longitude_both_or_neither",
        ),
        CheckConstraint(
            "radius_miles_override IS NULL OR radius_miles_override >= 0",
            name="radius_miles_override_non_negative",
        ),
    )

    @validates("location_text")
    def _normalize_location_text(self, _key: str, value: str) -> str:
        """Trim `_COVERED_WHITESPACE` before the row ever reaches the
        database — case is preserved, unlike `User._normalize_email`."""
        return value.strip(_COVERED_WHITESPACE)


# A functional/expression unique index can't be expressed as a table-level
# UniqueConstraint (those only cover plain columns) — an Index is the only
# way to enforce case-insensitive, per-search uniqueness while still storing
# and returning the original case. Only `lower(...)` is needed here, not
# `lower(trim(...))`: the CHECK constraints above already guarantee every
# stored value is trimmed, so this index expresses an equivalent but
# stronger invariant on the stored data than a trim-inside-the-index
# formula would — see docs/DATA_MODEL.md.
Index(
    "uq_saved_search_locations_search_id_text_lower",
    SavedSearchLocation.saved_search_id,
    func.lower(SavedSearchLocation.location_text),
    unique=True,
)
