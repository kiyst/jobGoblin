"""Job-title classifier (Phase 3, title-normalization slice).

Pure function: one raw job-title string in, one `TitleResult` out — a
canonical title and its role family, each its own `NormalizationResult`,
plus a closed `TitleOutcome`. No ORM, provider, UI, database, or network
dependency; only the standard library, `types.py`, and `identifiers.py`.
Deterministic normalization over a closed, frozen nine-title vocabulary —
not natural-language understanding. Any doubt yields `(None, UNAVAILABLE)`
for both fields, never a confident guess.

**What is returned, and what is not.** The raw title is never modified,
returned, or echoed — it stays the caller's (`jobs.title`).
`canonical_title` names the role only (never seniority, team, location,
specialization, or bracketed text); `role_family` is always exactly
`CANONICAL_TO_FAMILY[canonical_title]`. Nothing here writes
`jobs.normalized_title`/`jobs.job_family` — that wiring is a Phase 4+
concern. Seniority is not extracted: seniority words are ignored only
structurally (they sit in an alias's prefix), never listed or removed by
name, and `seniority.py` is neither imported nor mirrored.

**Provenance.** Every matched value is `Provenance.INFERRED` — the title is
interpreted from raw text, not computed from other established fields —
and the family inherits that weakest provenance. No result ever carries
`DERIVED`, `EXPLICIT_SOURCE`, `STRUCTURED_METADATA`, or
`PARSED_DESCRIPTION`.

**Outcomes.** `NO_TITLE`: `None`, or a title made only of accepted
whitespace. `UNSUPPORTED`: any rejected code point anywhere, or no segment
matches an alias. `AMBIGUOUS`: the rules below cannot pick exactly one
canonical title. `MATCHED`: exactly one canonical title.

**Bounded per-code-point character policy** (no unrestricted NFKC, no
Unicode casefold). Accepted: ASCII letters/digits (`A-Z` lowered to
`a-z`, the only case mapping); ASCII tab/CR/LF/space and every `Zs` code
point, mapped to a space; U+2028/U+2029 as segment boundaries; the dash
characters U+2010-U+2015 and U+2212, mapped to `-`; the ASCII punctuation
`, ; : | / @ ( ) [ ] { } & - +`; and U+FF01-U+FF5E only when that single
code point's own NFKC mapping is one permitted ASCII character. Every
other code point — every `Cf` format character, any non-ASCII letter or
digit, combining marks, ligatures, unlisted symbols/punctuation, other
compatibility characters, controls, lone surrogates — makes the whole
title `UNSUPPORTED`; nothing is silently dropped or treated as a
separator.

**Decoration.** Exactly one leading square-bracket group whose tokens are
exactly `expression of interest` (letters and spaces only) is ignored.
Every other bracketed group participates in normal processing.

**Segments and tokens.** Segments split at `, ; : | / @ ( ) [ ] { }`,
U+2028/U+2029, and at a dash with whitespace on both sides; a dash inside
a word, and `+`, only end a token. Tokens are maximal runs of ASCII
letters/digits, plus a standalone `&` token. Plurals are never folded.

**Per-segment verdict.** A segment matches an alias only when the alias is
a suffix of its token sequence (no alias is a suffix of another, so at
most one can match). The segment is then `AMBIGUOUS` when any token before
the alias is a `PREFIX_BLOCKERS` or `PREFIX_ROLE_DESIGNATORS` member, or
the prefix contains a family signal belonging to any family other than the
alias's own; otherwise it is `MATCH(canonical)`. `lead` is an allowed
prefix modifier. A segment matching no alias is `NONE`, and is
role-bearing when its final token is a `LATER_TERMINAL_ROLE_DESIGNATORS`
member, optionally followed by one ASCII level token (`1`-`99` or
`i`-`v`).

**Precedence.** If the head segment (the first one with any token)
matches C, the title is `MATCHED(C)` unless a later segment is
`AMBIGUOUS`, matches a different canonical title, or is a role-bearing
`NONE` — any of which makes it `AMBIGUOUS` (the same canonical may
repeat). If the head is `AMBIGUOUS`, so is the title. If the head is
`NONE`, any later match or ambiguous segment makes the title `AMBIGUOUS`;
otherwise it is `UNSUPPORTED`.

**Complexity and exceptions.** One linear pass maps code points, one
linear pass segments, and each segment does a bounded number of lookups
into frozen, bounded tables — no regular expressions at all. Every Python
`str`, including control and lone-surrogate input, either classifies or
returns `UNSUPPORTED`; nothing raises.

**Vocabulary validation.** The frozen tables are validated at import
(`TitleVocabularyError` on any violation): unique canonical IDs that are
canonical slugs; snake-case enum values; non-empty, normalized alias
tuples with no duplicates and no suffix collisions; one exact
canonical-to-family mapping; and no duplicate or malformed entry in the
blocker, role-designator, or family-signal tables.

**Honest evidence statement.** The 30 realistic titles in
`title_cases.json` are byte-identical copies of the frozen Phase 3 corpus
titles with primary-reviewer-approved smoke/regression expectations —
never accuracy, holdout, coverage, precision, recall, or generalization
evidence. The frozen corpus carries no title labels and is not modified.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, StrEnum
from types import MappingProxyType

from app.normalization.types import NormalizationResult, Provenance
from app.schemas.identifiers import is_canonical_slug

TITLE_VOCABULARY_VERSION = "1"


class RoleFamily(StrEnum):
    SOFTWARE_ENGINEERING = "software_engineering"
    SECURITY_ENGINEERING = "security_engineering"
    ENGINEERING_MANAGEMENT = "engineering_management"
    RESEARCH = "research"
    PRODUCT_MANAGEMENT = "product_management"
    SOLUTIONS_ARCHITECTURE = "solutions_architecture"
    SALES = "sales"


class TitleOutcome(StrEnum):
    MATCHED = "matched"
    NO_TITLE = "no_title"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"


class TitleVocabularyError(Exception):
    """Raised at import time (or by `_compile_tables` on an injected table
    in tests) when a frozen table is malformed. A programmer error, never a
    per-title outcome."""


# ---------------------------------------------------------------------------
# Frozen tables. Tuples (not sets), so a duplicate entry is detectable and
# rejected rather than silently collapsed.
# ---------------------------------------------------------------------------

_VOCABULARY: tuple[tuple[str, RoleFamily, tuple[tuple[str, ...], ...]], ...] = (
    (
        "software-engineer",
        RoleFamily.SOFTWARE_ENGINEERING,
        (
            ("software", "engineer"),
            ("software", "developer"),
            ("backend", "engineer"),
            ("back", "end", "engineer"),
            ("frontend", "engineer"),
            ("front", "end", "engineer"),
            ("full", "stack", "engineer"),
            ("fullstack", "engineer"),
        ),
    ),
    ("security-engineer", RoleFamily.SECURITY_ENGINEERING, (("security", "engineer"),)),
    ("research-engineer", RoleFamily.RESEARCH, (("research", "engineer"),)),
    ("research-scientist", RoleFamily.RESEARCH, (("research", "scientist"),)),
    ("engineering-manager", RoleFamily.ENGINEERING_MANAGEMENT, (("engineering", "manager"),)),
    (
        "engineering-director",
        RoleFamily.ENGINEERING_MANAGEMENT,
        (("director", "of", "engineering"), ("engineering", "director")),
    ),
    ("product-manager", RoleFamily.PRODUCT_MANAGEMENT, (("product", "manager"),)),
    (
        "solutions-architect",
        RoleFamily.SOLUTIONS_ARCHITECTURE,
        (("solutions", "architect"), ("solution", "architect")),
    ),
    ("account-executive", RoleFamily.SALES, (("account", "executive"),)),
)

_PREFIX_BLOCKERS_TABLE: tuple[str, ...] = (
    "recruiter",
    "sourcer",
    "manager",
    "director",
    "head",
    "vp",
    "president",
    "coordinator",
    "partner",
    "consultant",
    "analyst",
    "specialist",
    "intern",
    "assistant",
    "of",
    "for",
    "to",
    "and",
    "or",
    "&",
)

# `lead` is deliberately absent: it is an allowed prefix modifier.
_PREFIX_ROLE_DESIGNATORS_TABLE: tuple[str, ...] = (
    "engineer",
    "engineers",
    "developer",
    "developers",
    "architect",
    "architects",
    "scientist",
    "scientists",
    "manager",
    "managers",
    "director",
    "directors",
    "executive",
    "executives",
    "recruiter",
    "recruiters",
    "sourcer",
    "sourcers",
    "coordinator",
    "coordinators",
    "partner",
    "partners",
    "consultant",
    "consultants",
    "analyst",
    "analysts",
    "specialist",
    "specialists",
    "intern",
    "interns",
    "assistant",
    "assistants",
    "counsel",
    "attorney",
    "attorneys",
    "designer",
    "designers",
    "researcher",
    "researchers",
    "head",
    "heads",
    "president",
    "presidents",
    "vp",
    "vps",
)

# Added to `_PREFIX_ROLE_DESIGNATORS_TABLE` to form
# `LATER_TERMINAL_ROLE_DESIGNATORS` (later unmatched segments only).
_LATER_TERMINAL_EXTRA_TABLE: tuple[str, ...] = ("lead", "leads")

_FAMILY_SIGNAL_TABLE: tuple[tuple[RoleFamily, tuple[tuple[str, ...], ...]], ...] = (
    (
        RoleFamily.SOFTWARE_ENGINEERING,
        (
            ("software",),
            ("backend",),
            ("back", "end"),
            ("frontend",),
            ("front", "end"),
            ("fullstack",),
            ("full", "stack"),
        ),
    ),
    (RoleFamily.SECURITY_ENGINEERING, (("security",),)),
    (RoleFamily.ENGINEERING_MANAGEMENT, (("management",),)),
    (RoleFamily.RESEARCH, (("research",),)),
    (RoleFamily.PRODUCT_MANAGEMENT, (("product",),)),
    (RoleFamily.SOLUTIONS_ARCHITECTURE, (("solution",), ("solutions",), ("architecture",))),
    (RoleFamily.SALES, (("account",), ("sales",))),
)

_ROMAN_LEVELS: frozenset[str] = frozenset({"i", "ii", "iii", "iv", "v"})


# ---------------------------------------------------------------------------
# Table validation/compilation.
# ---------------------------------------------------------------------------

_ASCII_LOWER = frozenset("abcdefghijklmnopqrstuvwxyz")
_ASCII_DIGITS = frozenset("0123456789")
_ASCII_ALNUM = _ASCII_LOWER | _ASCII_DIGITS


def _is_alnum_token(token: object) -> bool:
    return isinstance(token, str) and token != "" and all(c in _ASCII_ALNUM for c in token)


def _is_token_tuple(value: object) -> bool:
    return isinstance(value, tuple) and len(value) > 0 and all(_is_alnum_token(t) for t in value)


def _is_snake_case(value: str) -> bool:
    return (
        value != ""
        and all(c in _ASCII_LOWER or c == "_" for c in value)
        and not value.startswith("_")
        and not value.endswith("_")
        and "__" not in value
    )


def _require_unique(items: tuple[object, ...], what: str) -> None:
    if len(set(items)) != len(items):
        raise TitleVocabularyError(f"duplicate entry in {what}")


@dataclass(frozen=True)
class _Tables:
    canonical_to_family: Mapping[str, RoleFamily]
    alias_to_canonical: Mapping[tuple[str, ...], str]
    max_alias_len: int
    prefix_blockers: frozenset[str]
    prefix_role_designators: frozenset[str]
    later_terminal_role_designators: frozenset[str]
    signal_to_family: Mapping[tuple[str, ...], RoleFamily]
    max_signal_len: int


def _compile_tables(
    vocabulary: tuple[tuple[str, RoleFamily, tuple[tuple[str, ...], ...]], ...],
    prefix_blockers: tuple[str, ...],
    prefix_role_designators: tuple[str, ...],
    later_terminal_extra: tuple[str, ...],
    family_signals: tuple[tuple[RoleFamily, tuple[tuple[str, ...], ...]], ...],
) -> _Tables:
    for enum_cls in (RoleFamily, TitleOutcome):
        members: list[Enum] = list(enum_cls)
        for member in members:
            if not isinstance(member.value, str) or not _is_snake_case(member.value):
                raise TitleVocabularyError(f"{enum_cls.__name__} value is not snake_case")

    if not isinstance(vocabulary, tuple) or not vocabulary:
        raise TitleVocabularyError("vocabulary must be a non-empty tuple")
    canonical_to_family: dict[str, RoleFamily] = {}
    alias_to_canonical: dict[tuple[str, ...], str] = {}
    all_aliases: list[tuple[str, ...]] = []
    for entry in vocabulary:
        if not isinstance(entry, tuple) or len(entry) != 3:
            raise TitleVocabularyError("vocabulary entry must be (canonical, family, aliases)")
        canonical, family, aliases = entry
        if not isinstance(canonical, str) or not is_canonical_slug(canonical):
            raise TitleVocabularyError("canonical title is not a canonical slug")
        if canonical in canonical_to_family:
            raise TitleVocabularyError("duplicate canonical title")
        if not isinstance(family, RoleFamily):
            raise TitleVocabularyError("family is not a RoleFamily member")
        if not isinstance(aliases, tuple) or not aliases:
            raise TitleVocabularyError("aliases must be a non-empty tuple")
        canonical_to_family[canonical] = family
        for alias in aliases:
            if not _is_token_tuple(alias):
                raise TitleVocabularyError("alias is not a non-empty normalized token tuple")
            if alias in alias_to_canonical:
                raise TitleVocabularyError("duplicate alias")
            alias_to_canonical[alias] = canonical
            all_aliases.append(alias)
    for a in all_aliases:
        for b in all_aliases:
            if a is not b and len(a) <= len(b) and b[len(b) - len(a) :] == a:
                raise TitleVocabularyError("alias suffix collision")

    for table, what, allow_amp in (
        (prefix_blockers, "prefix blockers", True),
        (prefix_role_designators, "prefix role designators", False),
        (later_terminal_extra, "later terminal extras", False),
    ):
        if not isinstance(table, tuple) or not table:
            raise TitleVocabularyError(f"{what} must be a non-empty tuple")
        for token in table:
            if not (_is_alnum_token(token) or (allow_amp and token == "&")):
                raise TitleVocabularyError(f"malformed entry in {what}")
        _require_unique(table, what)
    if "lead" in prefix_role_designators or "leads" in prefix_role_designators:
        raise TitleVocabularyError("lead must not be a prefix role designator")
    if set(later_terminal_extra) & set(prefix_role_designators):
        raise TitleVocabularyError("later terminal extras overlap prefix role designators")

    if not isinstance(family_signals, tuple) or not family_signals:
        raise TitleVocabularyError("family signals must be a non-empty tuple")
    signal_to_family: dict[tuple[str, ...], RoleFamily] = {}
    seen_families: list[RoleFamily] = []
    for signal_entry in family_signals:
        if not isinstance(signal_entry, tuple) or len(signal_entry) != 2:
            raise TitleVocabularyError("family signal entry must be (family, signals)")
        signal_family, signals = signal_entry
        if not isinstance(signal_family, RoleFamily):
            raise TitleVocabularyError("signal family is not a RoleFamily member")
        seen_families.append(signal_family)
        if not isinstance(signals, tuple) or not signals:
            raise TitleVocabularyError("signals must be a non-empty tuple")
        for signal in signals:
            if not _is_token_tuple(signal):
                raise TitleVocabularyError("malformed family signal")
            if signal in signal_to_family:
                raise TitleVocabularyError("duplicate family signal")
            signal_to_family[signal] = signal_family
    _require_unique(tuple(seen_families), "family signal families")

    return _Tables(
        canonical_to_family=MappingProxyType(canonical_to_family),
        alias_to_canonical=MappingProxyType(alias_to_canonical),
        max_alias_len=max(len(a) for a in all_aliases),
        prefix_blockers=frozenset(prefix_blockers),
        prefix_role_designators=frozenset(prefix_role_designators),
        later_terminal_role_designators=frozenset(prefix_role_designators)
        | frozenset(later_terminal_extra),
        signal_to_family=MappingProxyType(signal_to_family),
        max_signal_len=max(len(s) for s in signal_to_family),
    )


_TABLES = _compile_tables(
    _VOCABULARY,
    _PREFIX_BLOCKERS_TABLE,
    _PREFIX_ROLE_DESIGNATORS_TABLE,
    _LATER_TERMINAL_EXTRA_TABLE,
    _FAMILY_SIGNAL_TABLE,
)

CANONICAL_TO_FAMILY: Mapping[str, RoleFamily] = _TABLES.canonical_to_family
PREFIX_BLOCKERS: frozenset[str] = _TABLES.prefix_blockers
PREFIX_ROLE_DESIGNATORS: frozenset[str] = _TABLES.prefix_role_designators
LATER_TERMINAL_ROLE_DESIGNATORS: frozenset[str] = _TABLES.later_terminal_role_designators


# ---------------------------------------------------------------------------
# Result type.
# ---------------------------------------------------------------------------

_RESULT_INVARIANT_ERROR = "TitleResult invariant violated."


def _matched_pair_is_exact(canonical: object, family: object) -> bool:
    if type(canonical) is not str or canonical not in CANONICAL_TO_FAMILY:
        return False
    return isinstance(family, RoleFamily) and family is CANONICAL_TO_FAMILY[canonical]


@dataclass(frozen=True)
class TitleResult:
    """Invariants (enforced in `__post_init__`, one fixed, input-free
    `ValueError` for every violation): `outcome` is a `TitleOutcome`
    member and both fields are `NormalizationResult` instances. For
    `MATCHED`, the canonical title is an exact `CANONICAL_TO_FAMILY` key,
    the family is exactly its mapped `RoleFamily` member (never a raw
    string), and both provenances are exactly `INFERRED`. For every other
    outcome, both fields are `(None, UNAVAILABLE)`."""

    canonical_title: NormalizationResult[str]
    role_family: NormalizationResult[RoleFamily]
    outcome: TitleOutcome

    def __post_init__(self) -> None:
        if not (
            isinstance(self.outcome, TitleOutcome)
            and isinstance(self.canonical_title, NormalizationResult)
            and isinstance(self.role_family, NormalizationResult)
        ):
            raise ValueError(_RESULT_INVARIANT_ERROR)
        canonical = self.canonical_title.value
        family = self.role_family.value
        if self.outcome is TitleOutcome.MATCHED:
            if not _matched_pair_is_exact(canonical, family):
                raise ValueError(_RESULT_INVARIANT_ERROR)
            if (
                self.canonical_title.provenance is not Provenance.INFERRED
                or self.role_family.provenance is not Provenance.INFERRED
            ):
                raise ValueError(_RESULT_INVARIANT_ERROR)
        elif not (
            canonical is None
            and family is None
            and self.canonical_title.provenance is Provenance.UNAVAILABLE
            and self.role_family.provenance is Provenance.UNAVAILABLE
        ):
            raise ValueError(_RESULT_INVARIANT_ERROR)


def _absent_result(outcome: TitleOutcome) -> TitleResult:
    return TitleResult(
        canonical_title=NormalizationResult(None, Provenance.UNAVAILABLE),
        role_family=NormalizationResult(None, Provenance.UNAVAILABLE),
        outcome=outcome,
    )


_NO_TITLE_RESULT = _absent_result(TitleOutcome.NO_TITLE)
_UNSUPPORTED_RESULT = _absent_result(TitleOutcome.UNSUPPORTED)
_AMBIGUOUS_RESULT = _absent_result(TitleOutcome.AMBIGUOUS)
_MATCHED_RESULTS: Mapping[str, TitleResult] = MappingProxyType(
    {
        canonical: TitleResult(
            canonical_title=NormalizationResult(canonical, Provenance.INFERRED),
            role_family=NormalizationResult(family, Provenance.INFERRED),
            outcome=TitleOutcome.MATCHED,
        )
        for canonical, family in CANONICAL_TO_FAMILY.items()
    }
)


# ---------------------------------------------------------------------------
# Bounded per-code-point character policy.
# ---------------------------------------------------------------------------

_SPACE = " "
_SEGMENT_BOUNDARY = "|"
_ASCII_UPPER = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_ASCII_WHITESPACE = frozenset("\t\r\n ")
_PERMITTED_ASCII_PUNCTUATION = frozenset(",;:|/@()[]{}&-+")
_SEGMENT_SEPARATORS = frozenset(",;:|/@()[]{}")
_LINE_PARAGRAPH_SEPARATORS = frozenset("  ")
_UNICODE_DASHES = frozenset("‐‑‒–—―−")
_FULLWIDTH_FIRST = 0xFF01
_FULLWIDTH_LAST = 0xFF5E


def _map_ascii(ch: str) -> str | None:
    if ch in _ASCII_ALNUM or ch in _PERMITTED_ASCII_PUNCTUATION:
        return ch
    if ch in _ASCII_UPPER:
        return chr(ord(ch) + 32)
    if ch in _ASCII_WHITESPACE:
        return _SPACE
    return None


def _map_code_point(ch: str) -> str | None:
    """One code point to its normalized ASCII character, or `None` when the
    code point is rejected (the whole title is then `UNSUPPORTED`)."""
    if ch.isascii():
        return _map_ascii(ch)
    if ch in _LINE_PARAGRAPH_SEPARATORS:
        return _SEGMENT_BOUNDARY
    if ch in _UNICODE_DASHES:
        return "-"
    if _FULLWIDTH_FIRST <= ord(ch) <= _FULLWIDTH_LAST:
        mapped = unicodedata.normalize("NFKC", ch)
        if len(mapped) == 1 and mapped.isascii() and mapped not in _ASCII_WHITESPACE:
            return _map_ascii(mapped)
        return None
    category = unicodedata.category(ch)
    if category == "Cf":
        return None  # every format character fails closed
    if category == "Zs":
        return _SPACE
    return None


def _map_text(title: str) -> str | None:
    mapped: list[str] = []
    for ch in title:
        out = _map_code_point(ch)
        if out is None:
            return None
        mapped.append(out)
    return "".join(mapped)


# ---------------------------------------------------------------------------
# Decoration, segmentation, tokens.
# ---------------------------------------------------------------------------

_APPROVED_DECORATION: tuple[str, ...] = ("expression", "of", "interest")


def _is_approved_decoration(inner: str) -> bool:
    if not all(c in _ASCII_LOWER or c == _SPACE for c in inner):
        return False
    return tuple(t for t in inner.split(_SPACE) if t) == _APPROVED_DECORATION


def _strip_approved_decoration(text: str) -> str:
    """Removes exactly one leading `[expression of interest]` group; any
    other leading bracket group is left in place."""
    i = 0
    while i < len(text) and text[i] == _SPACE:
        i += 1
    if i < len(text) and text[i] == "[":
        close = text.find("]", i + 1)
        if close != -1 and _is_approved_decoration(text[i + 1 : close]):
            return text[close + 1 :]
    return text


def _flush_token(buffer: list[str], tokens: list[str]) -> None:
    if buffer:
        tokens.append("".join(buffer))
        buffer.clear()


def _flush_segment(tokens: list[str], segments: list[tuple[str, ...]]) -> None:
    if tokens:
        segments.append(tuple(tokens))
        tokens.clear()


def _segments(text: str) -> list[tuple[str, ...]]:
    segments: list[tuple[str, ...]] = []
    tokens: list[str] = []
    buffer: list[str] = []
    last = len(text) - 1
    for i, ch in enumerate(text):
        if ch in _ASCII_ALNUM:
            buffer.append(ch)
            continue
        _flush_token(buffer, tokens)
        if ch == "&":
            tokens.append("&")
        elif ch == "-":
            if 0 < i < last and text[i - 1] == _SPACE and text[i + 1] == _SPACE:
                _flush_segment(tokens, segments)
        elif ch in _SEGMENT_SEPARATORS:
            _flush_segment(tokens, segments)
        # a space or `+` only ends the current token
    _flush_token(buffer, tokens)
    _flush_segment(tokens, segments)
    return segments


# ---------------------------------------------------------------------------
# Per-segment verdicts.
# ---------------------------------------------------------------------------


class _SegmentKind(Enum):
    MATCH = "match"
    AMBIGUOUS = "ambiguous"
    NONE = "none"


@dataclass(frozen=True)
class _SegmentVerdict:
    kind: _SegmentKind
    canonical: str | None = None
    role_bearing: bool = False


_AMBIGUOUS_SEGMENT = _SegmentVerdict(_SegmentKind.AMBIGUOUS)


def _prefix_has_blocker(prefix: tuple[str, ...]) -> bool:
    return any(token in _TABLES.prefix_blockers for token in prefix)


def _prefix_has_role_designator(prefix: tuple[str, ...]) -> bool:
    return any(token in _TABLES.prefix_role_designators for token in prefix)


def _prefix_has_foreign_family_signal(prefix: tuple[str, ...], family: RoleFamily) -> bool:
    for start in range(len(prefix)):
        for length in range(1, _TABLES.max_signal_len + 1):
            if start + length > len(prefix):
                break
            signal_family = _TABLES.signal_to_family.get(prefix[start : start + length])
            if signal_family is not None and signal_family is not family:
                return True
    return False


def _is_level_token(token: str) -> bool:
    if token in _ROMAN_LEVELS:
        return True
    return 1 <= len(token) <= 2 and all(c in _ASCII_DIGITS for c in token) and token[0] != "0"


def _is_role_bearing(tokens: tuple[str, ...]) -> bool:
    terminal = _TABLES.later_terminal_role_designators
    if tokens[-1] in terminal:
        return True
    return len(tokens) >= 2 and _is_level_token(tokens[-1]) and tokens[-2] in terminal


def _evaluate_segment(tokens: tuple[str, ...]) -> _SegmentVerdict:
    canonical: str | None = None
    alias_len = 0
    for length in range(1, min(len(tokens), _TABLES.max_alias_len) + 1):
        found = _TABLES.alias_to_canonical.get(tokens[len(tokens) - length :])
        if found is not None:
            if canonical is not None:
                return _AMBIGUOUS_SEGMENT  # unreachable: suffix collisions rejected at import
            canonical, alias_len = found, length
    if canonical is None:
        return _SegmentVerdict(_SegmentKind.NONE, role_bearing=_is_role_bearing(tokens))
    prefix = tokens[: len(tokens) - alias_len]
    if _prefix_has_blocker(prefix):
        return _AMBIGUOUS_SEGMENT
    if _prefix_has_role_designator(prefix):
        return _AMBIGUOUS_SEGMENT
    if _prefix_has_foreign_family_signal(prefix, _TABLES.canonical_to_family[canonical]):
        return _AMBIGUOUS_SEGMENT
    return _SegmentVerdict(_SegmentKind.MATCH, canonical=canonical)


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


def classify_title(title: str | None) -> TitleResult:
    if title is None:
        return _NO_TITLE_RESULT
    text = _map_text(title)
    if text is None:
        return _UNSUPPORTED_RESULT
    if not text.strip(_SPACE):
        return _NO_TITLE_RESULT
    text = _strip_approved_decoration(text)
    segments = _segments(text)
    if not segments:
        return _UNSUPPORTED_RESULT
    head = _evaluate_segment(segments[0])
    later = [_evaluate_segment(segment) for segment in segments[1:]]
    if head.kind is _SegmentKind.AMBIGUOUS:
        return _AMBIGUOUS_RESULT
    if head.kind is _SegmentKind.MATCH:
        for verdict in later:
            if verdict.kind is _SegmentKind.AMBIGUOUS:
                return _AMBIGUOUS_RESULT
            if verdict.kind is _SegmentKind.MATCH and verdict.canonical != head.canonical:
                return _AMBIGUOUS_RESULT
            if verdict.kind is _SegmentKind.NONE and verdict.role_bearing:
                return _AMBIGUOUS_RESULT
        if head.canonical is None:
            return _AMBIGUOUS_RESULT  # unreachable: a MATCH verdict always names its canonical
        return _MATCHED_RESULTS[head.canonical]
    for verdict in later:
        if verdict.kind is not _SegmentKind.NONE:
            return _AMBIGUOUS_RESULT  # head unmatched, later segment matched or ambiguous
    return _UNSUPPORTED_RESULT
