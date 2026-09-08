r"""Deterministic years-of-experience range classifier (Phase 3 — fourth
parser slice; docs/ARCHITECTURE.md §4's `normalization/experience.py`,
docs/PHASE_RISK_CHECKLIST.md's Phase 3 exit gate — Workflow v3.1 pilot
parser slice 1 of 3, reviewed by Astra).

Pure function: `title`/`description` free text in, one `ExperienceRange`
out — a composite of two independently-provenanced `NormalizationResult[int]`
bounds (`minimum`, `maximum`). This is the first parser needing
`app.normalization.types`' explicitly-deferred "dedicated structured
result type with a `NormalizationResult` per field" case for a composite
parser. No database, ORM, provider, network, or ingestion-pipeline
dependency; no `parser_version` threading, no `field_provenance`
writing — both Phase 4+ concerns.

**Independent implementation** — no import from `seniority.py`,
`employment.py`, or `remote.py`. This parser's core extraction unit is a
*number*, not a closed vocabulary word, so unlike those three modules it
operates on (lightly redacted, see below) raw text with regexes rather
than a whitespace/punctuation tokenizer — a deliberate, justified
difference in mechanism for the same "text in, provenance-tagged value
out" contract, not a partial reuse of any of those modules' code.

**Primary risk** (docs/PHASE_RISK_CHECKLIST.md's Phase 3 entry): confidently
storing false facts from ambiguous text. Every rule below is designed so an
excluded case resolves to `UNAVAILABLE`, never a fabricated number.

**Numeric-phrase grammar** — a number becomes a candidate only when
structurally adjacent to an experience-unit word, in one of:

    <N>[+]? (years|yrs) [of] experience              bare, min-only
    <N>-<M> (years|yrs) [of] experience               hyphen range
    <N> to <M> (years|yrs) [of] experience            "to" range
    between <N> and <M> (years|yrs) [of] experience   "between...and" range
    (at least|minimum of|minimum) <N> (years|yrs) [of] experience
    (up to|no more than|maximum of) <N> (years|yrs) [of] experience
    <N> (or more|or above|plus) (years|yrs) [of] experience
    <N> (or less|or fewer|or under) (years|yrs) [of] experience
    experience:? <N>[+]? (years|yrs)?                 reversed label:value

A bare number is read as "at least N" (`minimum=N`, `maximum=UNAVAILABLE`)
— never fabricates an upper bound the text didn't state. An open-upper
phrase never infers `minimum=0`; symmetrically an open-lower phrase never
infers a cap. `exp` is deliberately **not** a recognized unit abbreviation
— too collision-prone with unrelated substrings; a documented exclusion,
not an oversight.

**Numeric rejection is atomic, not a fallback chain** (Astra review
finding 4): before any grammar production runs, the whole title/description
text is scanned once for malformed numeric shapes — a decimal beside a
range hyphen (`3.5-5`), a fraction (`1/2`), a bare decimal (`3.5`), or a
free-standing negative number (`-5`, not the digit-hyphen-digit of a valid
range) — and every digit character inside a matched span is redacted to
`#` in a working copy of the text (same length, no offset shift). All
downstream sentence/segment splitting and grammar matching runs against
this redacted copy, so a poisoned digit can never resurface via a
narrower production matching a sub-part of the same span — range
consumption is therefore structurally prior to bare-number matching, not
merely a catalog-ordering convention. `"This role requires 3.5-5 years of
experience."`, `"...1/2 years..."`, and `"...-5 years..."` all redact to no
surviving digits at that location and resolve to double-`UNAVAILABLE`.

**Applicant attribution — closed frame, not subject/verb alone** (Astra
review finding 2): a description-side candidate (zero or non-zero) is
accepted only via

    ALLOWED_SUBJECT REQUIRE_VERB [ATTRIBUTION_OBJECT] <phrase> END

`ALLOWED_SUBJECT` and `REQUIRE_VERB` are closed catalogs (see
`_ALLOWED_SUBJECTS`/`_REQUIRE_VERBS`); `ATTRIBUTION_OBJECT` is either
absent (direct binding: `"requires 5 years..."`) or one of a closed set of
applicant-referring phrases (`"a candidate with"`, `"someone with"`, ...) —
**never** an arbitrary noun phrase. `"We require vendors with 5 years of
experience."` fails here: `"vendors with"` is not in the closed object
set, so the frame never reaches the number at all. `END` is the
continuation-boundary rule below.

**Continuation boundary is symmetric with negation, not merely
attribution** (Astra review finding 3): after the frame's matched phrase,
the sentence remainder must be **empty** (bare trailing punctuation) to
accept — any other remainder rejects, uniformly, whether it is a
recognized negation phrase (`", but that experience is not mandatory."`)
or a wholly unrecognized hedge (`", however this is negotiable."`). There
is deliberately no separate negation-phrase catalog: both must produce the
same fail-closed `UNAVAILABLE` outcome, so an *unrecognized* hedge can
never silently become a positive requirement by virtue of not matching a
specific catalogued phrase. Precedence over open-upper syntax is
automatic: `"no more than 5 years"` is consumed *whole* by the open-upper
production itself (the "no" is inside the matched phrase, never part of
the remainder), so `"This role requires no more than 5 years of
experience."` leaves an empty remainder and correctly yields
`maximum=5`, not a rejected candidate.

**Zero-phrase, description**: accepted via the frame above, or via a
**whole-sentence** (not suffix) match against a closed template set —
`"No experience required."`, `"No experience necessary."`, `"No prior
experience required."`, `"No prior experience necessary."` — case/
whitespace/terminal-punctuation normalized, compared as the complete
sentence. `"No experience required to use our platform."` normalizes to a
string that is *not* a member of the closed template set (it has a
trailing continuation) — whole-sentence comparison, not suffix matching,
is what makes this fail (Astra review finding 2).

**Title-side segment grammar**: title text splits into structural segments
(paired parens/brackets, then delimiter-split remainder — the same
category of segmentation `seniority.py`/`employment.py`/`remote.py` use,
independently re-derived here) with one experience-specific addition: a
hyphen directly between two digit runs with no surrounding whitespace
(`\d+-\d+`) is a **numeric-range separator, never a segment delimiter**
— resolved at tokenization time, before segmentation runs (Astra review
finding underlying the original Risk 5). A closed non-required marker
catalog (`"not required"`, `"not necessary"`, `"isn't required"`, ...,
explicitly acknowledged non-exhaustive) co-occurring with a *numeric*
candidate in the same segment suppresses that candidate entirely —
`"5 Years Experience Not Required"` → double-`UNAVAILABLE` — while the
separate, unaffected bare zero-phrase production (`"No Experience
Required"`, no numeric candidate present) keeps its approved zero
semantics unchanged. An isolated segment whose entire trimmed content is
exactly a short form (`"5+ yrs"`, `"3-5 yrs"`) waives the literal word
`experience` — `"Software Engineer - 5+ yrs"` → `minimum=5` — but
`"5+ yrs of coding"` is not *exactly* the short form, so it falls through
to the full grammar (which does not recognize `"coding"` as `experience`)
and correctly resolves to `UNAVAILABLE`.

**Preference-marker suppression, positional not lexical** (Astra review
finding 5): `"ideal"`/`"ideally"` collide between the preference-marker
catalog and the closed subject phrase `"the ideal candidate"`. Resolved by
*position*, not a case-list: the preference check only ever inspects (a) a
sentence-initial `"Ideally,"` (comma required, an adverbial clause) or (b)
a closed trailing tag immediately following an already-fully-matched
number-phrase (`"5+ years preferred"`). `"the ideal candidate"` is part of
the *subject* of a `REQUIRE_VERB` frame — a structurally different
position this check never inspects — so `"The ideal candidate must have 5
years of experience."` is never suppressed. An unrecognized trailing hedge
(`"...experience, preferably."`) is not given a dedicated preference rule
at all; it is caught by the general continuation-boundary fail-closed rule
above, the same way any other unrecognized remainder is.

**Multi-value resolution — internal conflict is distinct from absent
evidence, checked before cross-source reconciliation** (Astra review
finding 6, mirroring `seniority.py`'s own `_CONFLICT`-before-agreement
precedence exactly): within a single source (title alone, or description
alone), multiple candidates for the *same* bound collapse if identical,
or become an internal conflict if distinct — and an internal conflict is
checked, and short-circuits to `UNAVAILABLE` for that bound, **before**
title and description are ever compared against each other. Two distinct
title minima remain conflicting even if the description happens to match
one of them. `minimum` and `maximum` are reconciled completely
independently of each other throughout — a conflict or absence in one
bound never affects the other.

**Consistency invariant**: after independent per-bound reconciliation, if
both bounds resolved to real values and `minimum > maximum`, the
classifier returns both bounds `UNAVAILABLE` rather than constructing a
self-contradictory range.

**Explicit exclusions** (documented limitations, not defects): no
`"Requirements:"`/section-header-scoped attribution (would reintroduce a
proximity-window design); no `exp` unit abbreviation; the negation-marker
catalog is acknowledged non-exhaustive; no persistence, `field_provenance`,
`parser_version`, taxonomy, or skill cross-reference of any kind.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import cast

from app.normalization.types import NormalizationResult, Provenance

_INVERTED_RANGE_ERROR = (
    "ExperienceRange invariant violated: both bounds resolved but minimum > maximum."
)


@dataclass(frozen=True)
class ExperienceRange:
    """Composite result: two independently-provenanced bounds. Never
    persisted directly — see the module docstring. `__post_init__` is
    defense-in-depth against a future internal bug constructing a
    self-contradictory object directly; `classify_experience` itself is
    responsible for detecting an inverted reconciled range and choosing
    double-`UNAVAILABLE` before construction (see the consistency
    invariant in the module docstring) — this is never the mechanism by
    which that coercion happens."""

    minimum: NormalizationResult[int]
    maximum: NormalizationResult[int]

    def __post_init__(self) -> None:
        if (
            self.minimum.provenance is not Provenance.UNAVAILABLE
            and self.maximum.provenance is not Provenance.UNAVAILABLE
            and cast(int, self.minimum.value) > cast(int, self.maximum.value)
        ):
            raise ValueError(_INVERTED_RANGE_ERROR)


_UNAVAILABLE_RESULT: NormalizationResult[int] = NormalizationResult(None, Provenance.UNAVAILABLE)
_UNAVAILABLE_RANGE = ExperienceRange(_UNAVAILABLE_RESULT, _UNAVAILABLE_RESULT)

# Internal-conflict sentinel — distinct from `None` (absent evidence, per
# Astra review finding 6, mirroring seniority.py's own `_CONFLICT`).
_CONFLICT = "conflict"

_CURLY_APOSTROPHES = ("‘", "’")


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    for curly in _CURLY_APOSTROPHES:
        normalized = normalized.replace(curly, "'")
    return normalized


# ---------------------------------------------------------------------------
# Numeric-rejection redaction — applied once, before any sentence/segment
# splitting or grammar matching. See module docstring.
# ---------------------------------------------------------------------------

_DECIMAL_RANGE_RE = re.compile(r"\d+\.\d+\s*-\s*\d+|\d+\s*-\s*\d+\.\d+")
_FRACTION_RE = re.compile(r"\d+\s*/\s*\d+")
_NEGATIVE_NUMBER_RE = re.compile(r"(?<!\d)-\d+")
_DECIMAL_RE = re.compile(r"\d+\.\d+")
_POISON_PATTERNS = (_DECIMAL_RANGE_RE, _FRACTION_RE, _NEGATIVE_NUMBER_RE, _DECIMAL_RE)


def _redact_poisoned_numbers(text: str) -> str:
    """Replaces every digit character inside a malformed-numeric-shape
    span with `#` — same length, no offset shift, so all downstream
    splitting/matching behaves identically to operating on the original
    text except that poisoned digits can never match `\\d`."""
    chars = list(text)
    for pattern in _POISON_PATTERNS:
        for match in pattern.finditer(text):
            for i in range(match.start(), match.end()):
                if chars[i].isdigit():
                    chars[i] = "#"
    return "".join(chars)


# ---------------------------------------------------------------------------
# Numeric-phrase grammar — forward order (number ... years [of] experience).
# ---------------------------------------------------------------------------

_UNIT = r"(?:years?|yrs?)"
_OF_EXPERIENCE = r"\s*(?:of\s+)?experience\b"

_FORWARD_PHRASE_RE = re.compile(
    "".join(
        [
            r"between\s+(?P<between_lo>\d+)\s+and\s+(?P<between_hi>\d+)\s*"
            + _UNIT
            + _OF_EXPERIENCE,
            r"|(?P<to_lo>\d+)\s+to\s+(?P<to_hi>\d+)\s*" + _UNIT + _OF_EXPERIENCE,
            r"|(?P<hy_lo>\d+)-(?P<hy_hi>\d+)\s*" + _UNIT + _OF_EXPERIENCE,
            r"|(?:at least|minimum of|minimum)\s+(?P<open_lo_prefix>\d+)\s*"
            + _UNIT
            + _OF_EXPERIENCE,
            r"|(?:up to|no more than|maximum of)\s+(?P<open_hi_prefix>\d+)\s*"
            + _UNIT
            + _OF_EXPERIENCE,
            r"|(?P<open_lo_suffix>\d+)\s*(?:or more|or above|plus)\s*" + _UNIT + _OF_EXPERIENCE,
            r"|(?P<open_hi_suffix>\d+)\s*(?:or less|or fewer|or under)\s*" + _UNIT + _OF_EXPERIENCE,
            r"|(?P<plus_lo>\d+)\+\s*" + _UNIT + _OF_EXPERIENCE,
            r"|(?P<bare>\d+)\s*" + _UNIT + _OF_EXPERIENCE,
        ]
    ),
    re.IGNORECASE,
)

# Reversed label:value order: "Experience: 5+ years" / "Experience: 3-5 years".
_LABEL_VALUE_RE = re.compile(
    "".join(
        [
            r"experience\s*:?\s*",
            r"(?:(?P<lv_hy_lo>\d+)-(?P<lv_hy_hi>\d+)",
            r"|(?P<lv_plus>\d+)\+",
            r"|(?P<lv_bare>\d+))",
            r"\s*" + _UNIT + r"?\b",
        ]
    ),
    re.IGNORECASE,
)

# Isolated-title-segment short form: the segment's *entire* trimmed content
# is exactly this shape (no literal "experience" word required).
_SHORT_FORM_RE = re.compile(
    r"^(?:(?P<sf_hy_lo>\d+)-(?P<sf_hy_hi>\d+)|(?P<sf_plus>\d+)\+|(?P<sf_bare>\d+))\s*"
    + _UNIT
    + r"$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _Phrase:
    minimum: int | None
    maximum: int | None
    end: int  # end offset of the full match, for remainder/continuation checks


def _phrase_from_forward_match(match: re.Match[str]) -> _Phrase:
    groups = match.groupdict()
    if groups["between_lo"] is not None:
        return _Phrase(int(groups["between_lo"]), int(groups["between_hi"]), match.end())
    if groups["to_lo"] is not None:
        return _Phrase(int(groups["to_lo"]), int(groups["to_hi"]), match.end())
    if groups["hy_lo"] is not None:
        return _Phrase(int(groups["hy_lo"]), int(groups["hy_hi"]), match.end())
    if groups["open_lo_prefix"] is not None:
        return _Phrase(int(groups["open_lo_prefix"]), None, match.end())
    if groups["open_hi_prefix"] is not None:
        return _Phrase(None, int(groups["open_hi_prefix"]), match.end())
    if groups["open_lo_suffix"] is not None:
        return _Phrase(int(groups["open_lo_suffix"]), None, match.end())
    if groups["open_hi_suffix"] is not None:
        return _Phrase(None, int(groups["open_hi_suffix"]), match.end())
    if groups["plus_lo"] is not None:
        return _Phrase(int(groups["plus_lo"]), None, match.end())
    return _Phrase(int(cast(str, groups["bare"])), None, match.end())


def _match_forward_phrase(text: str, start: int = 0) -> tuple[_Phrase, re.Match[str]] | None:
    match = _FORWARD_PHRASE_RE.search(text, start)
    if match is None:
        return None
    return _phrase_from_forward_match(match), match


def _match_label_value_phrase(text: str) -> _Phrase | None:
    match = _LABEL_VALUE_RE.search(text)
    if match is None:
        return None
    groups = match.groupdict()
    if groups["lv_hy_lo"] is not None:
        return _Phrase(int(groups["lv_hy_lo"]), int(groups["lv_hy_hi"]), match.end())
    if groups["lv_plus"] is not None:
        return _Phrase(int(groups["lv_plus"]), None, match.end())
    return _Phrase(int(cast(str, groups["lv_bare"])), None, match.end())


def _match_short_form(segment: str) -> _Phrase | None:
    match = _SHORT_FORM_RE.match(segment.strip())
    if match is None:
        return None
    groups = match.groupdict()
    if groups["sf_hy_lo"] is not None:
        return _Phrase(int(groups["sf_hy_lo"]), int(groups["sf_hy_hi"]), match.end())
    if groups["sf_plus"] is not None:
        return _Phrase(int(groups["sf_plus"]), None, match.end())
    return _Phrase(int(cast(str, groups["sf_bare"])), None, match.end())


# ---------------------------------------------------------------------------
# Title-side: structural segments with hyphen-in-numeric-range disambiguation.
# ---------------------------------------------------------------------------

_PAREN_BRACKET_RE = re.compile(r"\(([^()\[\]]*)\)|\[([^()\[\]]*)\]")
# A hyphen that is NOT a numeric-range separator (i.e. not digit-hyphen-digit
# with no surrounding whitespace) is a segment delimiter, same as
# whitespace-surrounded " - " or the other listed delimiters.
_TITLE_SEGMENT_DELIMITER_RE = re.compile(r"\s[-–—]\s|(?<!\d)-(?!\d)|[,|:]")

_TITLE_NOT_REQUIRED_MARKERS = (
    "not required",
    "not necessary",
    "isn't required",
    "isn't necessary",
    "is not required",
    "no longer required",
    "not mandatory",
    "not a requirement",
    "without requiring",
    "not needed",
)

_TITLE_PREFERENCE_TAG_RE = re.compile(
    r"(?:preferred|ideal|optional|desired|a plus|nice to have|bonus)\s*[.!?]*\s*$",
    re.IGNORECASE,
)

_TITLE_ZERO_RE = re.compile(
    r"no\s+(?:prior\s+)?experience\s+(?:required|necessary)\b", re.IGNORECASE
)


def _title_segments(text: str) -> list[str]:
    segments = [
        match.group(1) if match.group(1) is not None else match.group(2)
        for match in _PAREN_BRACKET_RE.finditer(text)
    ]
    remainder = _PAREN_BRACKET_RE.sub(" ", text)
    segments.extend(_TITLE_SEGMENT_DELIMITER_RE.split(remainder))
    return segments


def _extract_title_bounds(title: str | None) -> tuple[int | str | None, int | str | None]:
    if not title:
        return None, None
    working = _redact_poisoned_numbers(_normalize_text(title))

    minimums: list[int] = []
    maximums: list[int] = []

    for raw_segment in _title_segments(working):
        segment = raw_segment.strip()
        if not segment:
            continue
        segment_lower = segment.lower()

        if _TITLE_ZERO_RE.fullmatch(segment_lower) or _TITLE_ZERO_RE.fullmatch(
            segment_lower.rstrip(".")
        ):
            minimums.append(0)
            continue

        has_not_required = any(marker in segment_lower for marker in _TITLE_NOT_REQUIRED_MARKERS)
        has_preference = bool(_TITLE_PREFERENCE_TAG_RE.search(segment_lower))

        phrase = _match_short_form(segment)
        if phrase is None:
            forward = _match_forward_phrase(segment)
            phrase = forward[0] if forward is not None else None
        if phrase is None:
            phrase = _match_label_value_phrase(segment)
        if phrase is None:
            continue

        if has_not_required or has_preference:
            # Whole segment suppressed — contributes nothing (Risk 4 /
            # preference suppression), never a partial/degraded candidate.
            continue

        if phrase.minimum is not None:
            minimums.append(phrase.minimum)
        if phrase.maximum is not None:
            maximums.append(phrase.maximum)

    return _collapse_or_conflict(minimums), _collapse_or_conflict(maximums)


# ---------------------------------------------------------------------------
# Description-side: sentence-level attribution frame + continuation
# boundary.
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])|(?<=[.!?])\s*$")

_ALLOWED_SUBJECTS = (
    "this role",
    "this position",
    "the role",
    "the position",
    "our team",
    "the team",
    "the ideal candidate",
    "the successful candidate",
    "the right candidate",
    "candidates",
    "applicants",
    "we",
    "you",
)
_REQUIRE_VERBS = (
    "requires",
    "require",
    "requiring",
    "must have",
    "should have",
    "are looking for",
    "is looking for",
    "look for",
    "needs",
    "need",
    "wants",
    "want",
)
_ATTRIBUTION_OBJECTS = (
    "a candidate with",
    "candidates with",
    "an applicant with",
    "applicants with",
    "someone with",
    "a person with",
    "the ideal candidate with",
)

_FRAME_RE = re.compile(
    r"^\s*(?P<subject>"
    + "|".join(re.escape(s) for s in sorted(_ALLOWED_SUBJECTS, key=len, reverse=True))
    + r")\s+(?P<verb>"
    + "|".join(re.escape(v) for v in sorted(_REQUIRE_VERBS, key=len, reverse=True))
    + r")\s+(?:(?P<object>"
    + "|".join(re.escape(o) for o in sorted(_ATTRIBUTION_OBJECTS, key=len, reverse=True))
    + r")\s+)?(?P<rest>.*)$",
    re.IGNORECASE,
)

_ZERO_PHRASE_RE = re.compile(r"^no experience\b(?P<after>.*)$", re.IGNORECASE)

_ZERO_TEMPLATES = frozenset(
    {
        "no experience required",
        "no experience necessary",
        "no prior experience required",
        "no prior experience necessary",
    }
)

_TRAILING_PUNCTUATION_RE = re.compile(r"^[\s.!?]*$")


def _normalize_sentence_for_template(sentence: str) -> str:
    stripped = sentence.strip().rstrip(".!?").strip()
    return re.sub(r"\s+", " ", stripped).lower()


def _split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def _remainder_is_acceptable(remainder: str) -> bool:
    """The continuation-boundary rule: empty (just trailing punctuation) is
    the *only* positive path. A recognized negation phrase (e.g. "...but
    that experience is not mandatory") and a wholly unrecognized hedge
    (e.g. "...however this is negotiable") both reject identically — there
    is deliberately no separate negation-phrase catalog to maintain, since
    both must produce the same fail-closed outcome (see module docstring,
    Astra review finding 3)."""
    return bool(_TRAILING_PUNCTUATION_RE.match(remainder))


def _extract_description_bounds(
    description: str | None,
) -> tuple[int | str | None, int | str | None]:
    if not description:
        return None, None
    working = _redact_poisoned_numbers(_normalize_text(description))

    minimums: list[int] = []
    maximums: list[int] = []

    for sentence in _split_sentences(working):
        stripped = sentence.strip()
        if not stripped:
            continue

        # Leading preference marker suppresses the whole sentence outright.
        if re.match(r"^ideally\s*,", stripped, re.IGNORECASE):
            continue

        # Whole-sentence (not suffix) zero-phrase template match.
        if _normalize_sentence_for_template(stripped) in _ZERO_TEMPLATES:
            minimums.append(0)
            continue

        # Reversed label:value order is inherently role-scoped, like a
        # structured field — no subject-frame gate needed, but still
        # subject to the same continuation-boundary rule.
        label_match = _LABEL_VALUE_RE.search(stripped)
        if label_match is not None and _FRAME_RE.match(stripped) is None:
            phrase = _match_label_value_phrase(stripped)
            if phrase is not None:
                remainder = stripped[phrase.end :]
                if _remainder_is_acceptable(remainder):
                    if phrase.minimum is not None:
                        minimums.append(phrase.minimum)
                    if phrase.maximum is not None:
                        maximums.append(phrase.maximum)
            continue

        frame_match = _FRAME_RE.match(stripped)
        if frame_match is None:
            continue
        rest = frame_match.group("rest")

        zero_match = _ZERO_PHRASE_RE.match(rest)
        if zero_match is not None:
            remainder = zero_match.group("after")
            # A recognized negation on the zero-phrase itself (e.g.
            # "...requires no experience, but that is not mandatory")
            # suppresses without contributing anything; an unrecognized
            # remainder rejects the same way (fail-closed safety net).
            if _remainder_is_acceptable(remainder):
                minimums.append(0)
            continue

        forward = _match_forward_phrase(rest)
        if forward is None:
            continue
        phrase, match = forward
        if match.start() != 0:
            # The number-phrase must begin the frame's remainder directly
            # (only an approved ATTRIBUTION_OBJECT may precede it) — a gap
            # here means unsupported intervening text, same fail-closed
            # rule as an unsupported trailing remainder.
            continue
        remainder = rest[phrase.end :]
        # A recognized negation continuation suppresses without
        # contributing anything; an unrecognized remainder rejects the
        # same way (Astra review finding 3's fail-closed safety net) —
        # only an empty (bare trailing punctuation) remainder accepts.
        if _remainder_is_acceptable(remainder):
            if phrase.minimum is not None:
                minimums.append(phrase.minimum)
            if phrase.maximum is not None:
                maximums.append(phrase.maximum)

    return _collapse_or_conflict(minimums), _collapse_or_conflict(maximums)


def _collapse_or_conflict(values: list[int]) -> int | str | None:
    if not values:
        return None
    distinct = set(values)
    if len(distinct) == 1:
        return values[0]
    return _CONFLICT


def _reconcile_bound(
    title_signal: int | str | None, description_signal: int | str | None
) -> NormalizationResult[int]:
    """Mirrors `seniority.py`'s exact precedence: internal conflict (within
    either source alone) is checked, and wins, before cross-source
    agreement/disagreement is ever considered."""
    if title_signal == _CONFLICT or description_signal == _CONFLICT:
        return NormalizationResult(None, Provenance.UNAVAILABLE)
    if title_signal is None and description_signal is None:
        return NormalizationResult(None, Provenance.UNAVAILABLE)
    if title_signal is not None and description_signal is None:
        return NormalizationResult(cast(int, title_signal), Provenance.INFERRED)
    if title_signal is None and description_signal is not None:
        return NormalizationResult(cast(int, description_signal), Provenance.PARSED_DESCRIPTION)
    if title_signal == description_signal:
        return NormalizationResult(cast(int, title_signal), Provenance.PARSED_DESCRIPTION)
    return NormalizationResult(None, Provenance.UNAVAILABLE)


def classify_experience(
    title: str | None,
    description: str | None,
) -> ExperienceRange:
    """Classifies a posting's years-of-experience range from free text
    alone. Pure function — no I/O, no persistence, no `parser_version`.
    See the module docstring for the full grammar and precedence rules."""
    title_min, title_max = _extract_title_bounds(title)
    description_min, description_max = _extract_description_bounds(description)

    minimum = _reconcile_bound(title_min, description_min)
    maximum = _reconcile_bound(title_max, description_max)

    if (
        minimum.provenance is not Provenance.UNAVAILABLE
        and maximum.provenance is not Provenance.UNAVAILABLE
        and cast(int, minimum.value) > cast(int, maximum.value)
    ):
        return _UNAVAILABLE_RANGE

    return ExperienceRange(minimum, maximum)
