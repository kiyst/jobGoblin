"""Deterministic skill-taxonomy foundation (Phase 3 -- skill-taxonomy-
foundation slice; docs/ARCHITECTURE.md's `normalization/taxonomy.py` +
`taxonomy/skills.yaml`, docs/PHASE_RISK_CHECKLIST.md's Phase 3 exit gate).

Loads and validates a versioned, schema-closed YAML taxonomy file
(`app/taxonomy/skills.yaml`) into an immutable, exact-match lookup index.
Pure function -- no ORM, no provider, no network client, no I/O beyond
reading the one given path. `taxonomy/` itself holds only data
(docs/ARCHITECTURE.md's dependency table: "(data files, no code)"); this
module is the code `normalization/` is permitted to hold that reads it.

Deliberately does **not** scan free text or implement the future skill
classifier: `TaxonomyIndex.lookup()` is exact-match only against an
already-segmented candidate string, never substring/tokenizing scanning
of arbitrary prose. Segmenting free text into candidate tokens, and
wrapping results in a `NormalizationResult`, is a separate, future
Phase 3 parser slice's own responsibility -- not this one's.

Title normalization is not unblocked by this slice: job titles are
free-form multi-word phrases, not a flat alias-matched vocabulary, and
almost certainly need a different (likely hierarchical) schema of their
own. Only the general pattern here (versioned, duplicate-rejecting,
schema-validated YAML with a typed unknown result) is a reusable
template for that future work, never this schema or data directly.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

import yaml

from app.schemas.identifiers import is_canonical_slug

_SUPPORTED_SCHEMA_VERSION = 1

# Matches every trim-only text column's CHECK constraint in this schema
# (docs/DATA_MODEL.md), and the identical constant already used by
# normalization/location.py and normalization/salary.py.
_WHITESPACE = "\t\n\r "
_WS = r"[\t\n\r ]"

_ALLOWED_TOP_LEVEL_KEYS = frozenset({"schema_version", "entries"})
_ALLOWED_ENTRY_KEYS = frozenset({"canonical_id", "display_name", "aliases"})

DEFAULT_SKILLS_TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "taxonomy" / "skills.yaml"


class TaxonomyValidationError(Exception):
    """The taxonomy YAML file is malformed, or violates a closed-schema,
    uniqueness, or grammar invariant -- always fails closed, never a
    warning or a silently-skipped/coerced entry."""


class _StrictYamlLoader(yaml.SafeLoader):
    """Rejects a duplicate YAML mapping key outright. `yaml.safe_load`
    alone silently keeps the last value (last-write-wins) for a
    duplicate key -- exactly the class of defect this project's own
    `verification_receipts._StrictDecoder` (JSON) already guards against
    for every other versioned artifact (receipts, workflow metadata)."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise TaxonomyValidationError(f"duplicate YAML mapping key {key!r}")
            seen.add(key)
        return cast(dict[Any, Any], super().construct_mapping(node, deep=deep))


class TaxonomyLookupStatus(StrEnum):
    MATCHED = "matched"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TaxonomyEntry:
    canonical_id: str
    display_name: str


_STATUS_TYPE_ERROR = (
    "TaxonomyLookupResult invariant violated: status must be a " "TaxonomyLookupStatus enum member."
)
_NONE_INVARIANT_ERROR = (
    "TaxonomyLookupResult invariant violated: entry must be None if and "
    "only if status is TaxonomyLookupStatus.UNKNOWN."
)


@dataclass(frozen=True)
class TaxonomyLookupResult:
    """A typed, closed outcome for one lookup -- never a bare `None` a
    caller could confuse with "not yet looked up" or an error. `entry`
    is present if and only if `status` is `MATCHED`, enforced below
    exactly like `NormalizationResult`'s own value/provenance invariant.
    The two static factories are the only supported construction path."""

    status: TaxonomyLookupStatus
    entry: TaxonomyEntry | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, TaxonomyLookupStatus):
            raise ValueError(_STATUS_TYPE_ERROR)
        if (self.entry is None) != (self.status is TaxonomyLookupStatus.UNKNOWN):
            raise ValueError(_NONE_INVARIANT_ERROR)

    @staticmethod
    def matched(entry: TaxonomyEntry) -> TaxonomyLookupResult:
        return TaxonomyLookupResult(status=TaxonomyLookupStatus.MATCHED, entry=entry)

    @staticmethod
    def unknown() -> TaxonomyLookupResult:
        return TaxonomyLookupResult(status=TaxonomyLookupStatus.UNKNOWN, entry=None)


def normalize_lookup_key(text: str) -> str:
    """The taxonomy's own exact-matching rule -- not a reuse of any other
    parser's normalization, since none of them normalize skill-shaped
    tokens. `location.py`/`salary.py` share only the first two steps
    below (NFKC normalize, strip the shared whitespace set) before
    diverging into field-specific casing (uppercase codes, lowercase
    lexicon words) -- neither is "the" convention for a skill name.

    Steps: NFKC-normalize -> strip the shared whitespace set -> collapse
    repeated internal whitespace to one space -> lowercase-fold.
    Punctuation (`+`, `#`, `.`, `-`) is preserved literally, never
    stripped, since it distinguishes real skills (`c` vs `c++` vs `c#`).
    Whitespace directly adjacent to punctuation is not reconciled
    (`"node . js"` does not equal `"node.js"`) -- aliases must be
    authored in their exact expected form; this is a stated limitation,
    not an oversight.
    """
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.strip(_WHITESPACE)
    normalized = re.sub(f"{_WS}+", " ", normalized)
    return normalized.lower()


@dataclass(frozen=True)
class TaxonomyIndex:
    """Immutable, exact-match lookup index built once by `load_taxonomy`.
    Never mutated after construction -- genuinely enforced, not merely
    asserted: `@dataclass(frozen=True)` alone only blocks rebinding the
    `_by_normalized_key` attribute itself, never mutation of the `dict`
    object it points to. `__post_init__` below defensively copies
    whatever mapping the caller passed in and wraps it in a read-only
    `MappingProxyType`, so neither the constructor's caller nor anything
    holding a reference to this instance can corrupt the index after
    construction -- exactly the "confidently storing a false fact"
    failure mode this module's own validation exists to prevent, one
    layer later."""

    _by_normalized_key: Mapping[str, TaxonomyEntry]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "_by_normalized_key", MappingProxyType(dict(self._by_normalized_key))
        )

    def lookup(self, text: str) -> TaxonomyLookupResult:
        """Exact-match only -- `text` is normalized and looked up whole,
        never tokenized or scanned as a substring of a larger string.
        A single-token collision with an ordinary English word (e.g. the
        Go/R languages) is intentionally not this function's concern:
        segmenting free text into candidate tokens, with whatever word-
        boundary safety that requires, is a future skill-classifier
        parser's own responsibility."""
        entry = self._by_normalized_key.get(normalize_lookup_key(text))
        if entry is None:
            return TaxonomyLookupResult.unknown()
        return TaxonomyLookupResult.matched(entry)

    def canonical_ids(self) -> frozenset[str]:
        """The complete set of distinct canonical IDs this index resolves
        to -- never the raw lookup-key count, which double-counts every
        alias of the same entry."""
        return frozenset(entry.canonical_id for entry in self._by_normalized_key.values())


def _require_type(value: Any, expected: type, *, context: str) -> Any:
    if not isinstance(value, expected):
        raise TaxonomyValidationError(
            f"{context} must be a {expected.__name__}, got {type(value).__name__}"
        )
    return value


def load_taxonomy(path: Path) -> TaxonomyIndex:
    """Loads, validates, and indexes a taxonomy YAML file. Fails closed
    on any malformed content, duplicate key (YAML-level or semantic),
    invalid `canonical_id` grammar, or unreachable `display_name` --
    never silently skips or coerces a bad entry."""
    text = path.read_text(encoding="utf-8")
    try:
        raw = yaml.load(text, Loader=_StrictYamlLoader)
    except yaml.YAMLError as exc:
        raise TaxonomyValidationError(f"{path} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise TaxonomyValidationError(f"{path} must contain a YAML mapping at the top level")
    unknown_top = set(raw) - _ALLOWED_TOP_LEVEL_KEYS
    if unknown_top:
        raise TaxonomyValidationError(f"unrecognized top-level field(s): {sorted(unknown_top)}")
    missing_top = _ALLOWED_TOP_LEVEL_KEYS - set(raw)
    if missing_top:
        raise TaxonomyValidationError(f"missing required top-level field(s): {sorted(missing_top)}")

    schema_version = raw["schema_version"]
    if schema_version != _SUPPORTED_SCHEMA_VERSION:
        raise TaxonomyValidationError(
            f"schema_version must be {_SUPPORTED_SCHEMA_VERSION!r}, got {schema_version!r}"
        )

    entries_raw = _require_type(raw["entries"], list, context="'entries'")

    by_key: dict[str, TaxonomyEntry] = {}
    seen_canonical_ids: set[str] = set()

    for index, raw_entry in enumerate(entries_raw):
        context = f"entries[{index}]"
        _require_type(raw_entry, dict, context=context)
        unknown_fields = set(raw_entry) - _ALLOWED_ENTRY_KEYS
        if unknown_fields:
            raise TaxonomyValidationError(
                f"{context} declares unrecognized field(s): {sorted(unknown_fields)}"
            )
        missing_fields = _ALLOWED_ENTRY_KEYS - set(raw_entry)
        if missing_fields:
            raise TaxonomyValidationError(
                f"{context} is missing required field(s): {sorted(missing_fields)}"
            )

        canonical_id = _require_type(
            raw_entry["canonical_id"], str, context=f"{context}.canonical_id"
        )
        display_name = _require_type(
            raw_entry["display_name"], str, context=f"{context}.display_name"
        )
        aliases = _require_type(raw_entry["aliases"], list, context=f"{context}.aliases")
        for alias_index, alias in enumerate(aliases):
            _require_type(alias, str, context=f"{context}.aliases[{alias_index}]")

        if not canonical_id:
            raise TaxonomyValidationError(f"{context}.canonical_id must not be empty")
        if not is_canonical_slug(canonical_id):
            raise TaxonomyValidationError(
                f"{context}.canonical_id {canonical_id!r} is not a canonical slug"
            )
        if not display_name.strip(_WHITESPACE):
            raise TaxonomyValidationError(f"{context}.display_name must not be blank")

        if canonical_id in seen_canonical_ids:
            raise TaxonomyValidationError(f"duplicate canonical_id {canonical_id!r}")
        seen_canonical_ids.add(canonical_id)

        entry = TaxonomyEntry(canonical_id=canonical_id, display_name=display_name)

        candidate_keys = [canonical_id, *aliases]
        normalized_keys: list[str] = []
        for raw_key in candidate_keys:
            normalized_key = normalize_lookup_key(raw_key)
            if not normalized_key:
                raise TaxonomyValidationError(
                    f"{context} ({canonical_id!r}) has a blank lookup key"
                )
            if normalized_key in normalized_keys:
                raise TaxonomyValidationError(
                    f"{context} ({canonical_id!r}) has a self-colliding key -- "
                    f"{raw_key!r} normalizes to {normalized_key!r}, already used by "
                    "another key in the same entry"
                )
            normalized_keys.append(normalized_key)
            if normalized_key in by_key:
                raise TaxonomyValidationError(
                    f"key {normalized_key!r} (from {context}, {canonical_id!r}) collides "
                    f"with an existing entry {by_key[normalized_key].canonical_id!r}"
                )
            by_key[normalized_key] = entry

        display_key = normalize_lookup_key(display_name)
        if display_key not in normalized_keys:
            raise TaxonomyValidationError(
                f"{context} ({canonical_id!r}) display_name {display_name!r} normalizes to "
                f"{display_key!r}, which is not reachable via its own canonical_id or "
                "any of its aliases"
            )

    return TaxonomyIndex(_by_normalized_key=by_key)
