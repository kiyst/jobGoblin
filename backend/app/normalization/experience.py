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
    experience:? <N>[+]? (years|yrs)                  reversed label:value, title-only (see below)
    <N> (years|yrs) [of] experience (or less|or fewer|or under)   trailing marker, whole-phrase form
    <N> (years|yrs) [of] experience (or more|or above|plus)       trailing marker, whole-phrase form

A bare number is read as "at least N" (`minimum=N`, `maximum=UNAVAILABLE`)
— never fabricates an upper bound the text didn't state. An open-upper
phrase never infers `minimum=0`; symmetrically an open-lower phrase never
infers a cap. `exp` is deliberately **not** a recognized unit abbreviation
— too collision-prone with unrelated substrings; a documented exclusion,
not an oversight. The two trailing-marker forms above are distinct from
`open_lo_suffix`/`open_hi_suffix` (marker positioned *before* the unit
word, e.g. `"10 or fewer years"`) — these instead recognize the marker
*after* the complete "N years of experience" phrase (e.g. `"5 years of
experience or fewer"`), listed before the plain bare production so they
take precedence when present (Astra re-review finding 3). An unsupported
prefix marker (`"less than"`, `"fewer than"`) is not part of the
recognized open-upper catalog at all — rather than silently falling back
to a bare match that ignores it, it is treated as a poison trigger (see
below), so `"less than 5 years of experience"` never fabricates
`minimum=5`.

**Numeric rejection is atomic, not a fallback chain** (Astra review
finding 4, extended by Astra re-review findings 4/round-2 and 2/round-3
and round-4): before any grammar production runs, the whole
title/description text is scanned once for malformed or unsupported
numeric shapes and every digit character inside a matched span is
redacted to `#` in a working copy of the text (same length, no offset
shift) — a bare decimal (`3.5`), a fraction (`1/2`), an unsupported
`"less than"`/`"fewer than"` prefix, a Unicode dash-like character (figure
dash, en dash, em dash, or the Unicode minus sign U+2212 — distinct from
the ASCII hyphen the range grammar recognizes) forming either a
digit-dash-digit range or a leading negative shape, and — poisoned as a
**whole composite span**, not just the decimal/fraction/negative-number's
own operands — a decimal, fraction, **or free-standing negative number**
combined with *any* adjacent range separator (hyphen, `"to"`, or `"and"`,
in either operand order). Poisoning only the malformed component's own
operand(s) previously left the *other* endpoint of a combined range as a
surviving, independent-looking bare candidate: `"3.5 to 5 years
experience"` fabricated `minimum=5` (the `"3.5"` was poisoned, but the
separate `"5"` after `"to"` was untouched and still satisfied the plain
bare production), `"1/2-5 years experience"` fabricated `minimum=5` the
same way (the fraction's own poisoning left the hyphen-adjacent `"5"`
untouched, and it was not preceded by a digit, so the negative-number
pattern didn't catch it either), and `"-3 to 5 years experience"`
fabricated `minimum=5` the same way again (only `"-3"` was poisoned,
leaving the `"5"` after `"to"` untouched — Astra re-review finding 2,
round 4). The composite pattern generalizes across all three separators,
both operand orders, and all three malformed-component kinds rather than
hand-coding each combination, and a separate, well-formed phrase
elsewhere in the same text is never swept up by it (`"...5 years
experience and 10 years experience"` still yields `minimum=10` from the
untouched second phrase, whether the composite ahead of it is a decimal,
fraction, or negative-number one). The three composite patterns are
case-insensitive, matching the extraction grammar's own case-insensitive
`"to"`/`"and"` separators — without this, an uppercase or mixed-case
separator (`"3.5 TO 5 years experience"`, `"-3 TO 5 years experience"`,
`"between 3.5 AND 5 years experience"`) escaped the composite poison
pattern entirely while the plain single-operand decimal/fraction pattern
still poisoned its own operand, leaving the *other* endpoint to survive
as a bare candidate the same way the lowercase-only defect did before
this class of pattern existed (Astra re-review finding, round 5).
NFKC normalization decomposes a vulgar fraction (`"½"`) into digits joined
by U+2044 FRACTION SLASH, not the ASCII `/` the fraction pattern
matches — normalized to ASCII `/` before poisoning runs, so `"1½ years
experience"` is caught the same way `"1/2 years experience"` is, never
fabricating `minimum=2` from the decomposed second operand. All downstream
sentence/segment splitting and grammar matching runs against this
redacted copy, so a poisoned digit can never resurface via a narrower
production matching a sub-part of the same span — range consumption is
therefore structurally prior to bare-number matching, not merely a
catalog-ordering convention. Deliberately narrower than full
numeric-language support: returning `UNAVAILABLE` for an unsupported
numeric shape is sufficient; upgrading it to a valid ASCII-equivalent
range is not attempted.

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

**Reversed label:value order has no independent acceptance path on the
description side at all** (Astra re-review finding 3, superseding the
prior "sentence-initial is inherently role-scoped" design): a description
candidate expressed as `"Experience: 5+ years"` must obey the *same*
`ALLOWED_SUBJECT`/`REQUIRE_VERB` attribution frame as any other candidate
— sentence-initial position is not an approved exception, regardless of
anchoring. In practice this phrasing almost never occurs inside a
subject+verb frame, so a standalone structured-field-style description
line is an accepted, documented coverage gap (a safe miss, never a wrong
value — see the explicit-exclusions section). The **title** side has no
attribution-frame concept to begin with (titles are structural, not
prose), so `"Experience: 5+ years"` as a *title* remains supported —
checked against the **whole title, anchored at position 0**, before
segmentation runs, because the colon is itself a segment delimiter
(`_TITLE_SEGMENT_DELIMITER_RE`) and would otherwise always separate the
literal word `experience` from its value before this grammar ever saw
them together. (Found while mutation-proving the mandatory-unit fix
below: without this whole-title check, `"Experience: 5+ years"` only ever
"worked" by coincidence, via the isolated-segment short-form waiver
matching the post-colon fragment `"5+ years"` on its own — a form this
grammar was never actually exercising — and a value this grammar was
meant to cover but the short-form waiver cannot, like a range with a
prefix marker, silently failed with no test ever catching it.) The
label:value grammar's unit word is now **mandatory** in both contexts —
it previously accepted a bare `"Experience: 5"` with no `"years"`/`"yrs"`
at all, which violated the same number/unit adjacency every other
production requires.

**Title-side segment grammar**: title text splits into structural segments
in **original left-to-right order** (paired parens/brackets interleaved
with delimiter-split text around them — the same category of segmentation
`seniority.py`/`employment.py`/`remote.py` use, independently re-derived
here, but order-preserving rather than hoisting all parenthesized content
to the front of the list) with one experience-specific addition: a hyphen
directly between two digit runs with no surrounding whitespace (`\d+-\d+`)
is a **numeric-range separator, never a segment delimiter** — resolved at
tokenization time, before segmentation runs (Astra review finding
underlying the original Risk 5). Every non-overlapping numeric candidate
within a segment is collected, not only the first (Astra re-review
finding 5) — `"3 years experience and 5 years experience"` surfaces both 3
and 5 as competing minima (a same-segment conflict), while `"5 years
experience and up to 10 years of experience"` surfaces one minimum and
one maximum candidate that populate independent bounds without
contaminating each other, since a segment can validly state more than one
non-conflicting fact.

A closed non-required marker catalog (`"not required"`, `"not necessary"`,
`"isn't required"`, ..., explicitly acknowledged non-exhaustive) or a
leading preference marker (`"preferred"`, `"ideal"`, `"ideally"`, ...)
co-occurring with a *numeric* candidate suppresses that candidate
entirely, whether the marker shares the *same* segment (`"5 Years
Experience Not Required"`) or occupies a qualifier-only **neighboring**
segment on **either side** — a comma or parenthesis boundary can place the
qualifier before *or* after the segment it modifies (`"5 years
experience, not required"`, `"5 years experience (not required)"`,
`"Ideally, 5 years of experience"`, `"Preferred, 3-5 years experience"` —
Astra re-review findings 2 and 1 respectively). Getting this right
depends on the segmentation itself preserving original text order: a
parenthesized qualifier appearing *after* its target in the source text
must also appear after it in the segment list, never reordered ahead of
it, or adjacency-checking a "preceding" or "following" neighbor becomes
meaningless. Neighbor-checking also skips past a **blank segment** rather
than treating it as a barrier — combining a parenthesis boundary with a
comma boundary (`"(Preferred), 5 years experience"`, `"5 years
experience, (not required)"`) inserts an empty or whitespace-only
segment directly between the qualifier and its target, and a raw
adjacent-index check would otherwise stop there instead of looking past
it to the real neighbor (Astra re-review finding 1, round 4). Both forms
resolve to double-`UNAVAILABLE`. The separate,
unaffected bare zero-phrase production (`"No Experience Required"`, no
numeric candidate present) keeps its approved zero semantics unchanged.
An isolated segment whose entire trimmed content is exactly a short form
(`"5+ yrs"`, `"3-5 yrs"`) waives the literal word `experience` —
`"Software Engineer - 5+ yrs"` → `minimum=5` — but `"5+ yrs of coding"` is
not *exactly* the short form, so it falls through to the full grammar
(which does not recognize `"coding"` as `experience`) and correctly
resolves to `UNAVAILABLE`.

**Preference-marker suppression, positional not lexical** (Astra review
finding 5, extended by Astra re-review finding 2): `"ideal"`/`"ideally"`
collide between the preference-marker catalog and the closed subject
phrase `"the ideal candidate"`. Resolved by *position*, not a case-list:
the preference check inspects (a) a sentence-initial `"Ideally,"` in
description (comma required, an adverbial clause) or a *leading* marker
in a title segment (comma optional — titles are terser than description
prose, e.g. `"Ideally 5 years of experience"` with no comma, or
`"Preferred 3-5 years experience"`), or (b) a closed trailing tag
immediately following an already-fully-matched number-phrase (`"5+ years
preferred"`). `"the ideal candidate"` is part of the *subject* of a
`REQUIRE_VERB` frame — a structurally different position this check never
inspects — so `"The ideal candidate must have 5 years of experience."` is
never suppressed. An unrecognized trailing hedge (`"...experience,
preferably."`) is not given a dedicated preference rule at all; it is
caught by the general continuation-boundary fail-closed rule above, the
same way any other unrecognized remainder is.

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
    # NFKC decomposes a vulgar fraction (e.g. "½") into digits joined by
    # U+2044 FRACTION SLASH, not the ASCII "/" `_FRACTION_RE` matches —
    # normalizing it here lets the existing fraction-poisoning pattern
    # catch the decomposed form too (Astra review finding 4).
    normalized = normalized.replace("⁄", "/")
    return normalized


# ---------------------------------------------------------------------------
# Numeric-rejection redaction — applied once, before any sentence/segment
# splitting or grammar matching. See module docstring.
# ---------------------------------------------------------------------------

_FRACTION_RE = re.compile(r"\d+\s*/\s*\d+")
_NEGATIVE_NUMBER_RE = re.compile(r"(?<!\d)-\d+")
_DECIMAL_RE = re.compile(r"\d+\.\d+")
# A decimal or fraction combined with an adjacent range separator (hyphen,
# "to", or "and") and another number is a single malformed *composite*
# shape — poisoning only the decimal/fraction's own two operands left the
# "other" endpoint of the range as a surviving, independent-looking bare
# candidate (Astra re-review finding 2: "3.5 to 5 years experience" ->
# fabricated minimum=5; "1/2-5 years experience" -> fabricated minimum=5).
# The whole composite span — every number in it — is poisoned instead,
# covering both operand orders and all three separators, generalizing
# rather than hand-coding each combination.
_RANGE_SEPARATOR = r"(?:\s*-\s*|\s+to\s+|\s+and\s+)"
_DECIMAL_COMPOSITE_RANGE_RE = re.compile(
    rf"\d+\.\d+{_RANGE_SEPARATOR}\d+|\d+{_RANGE_SEPARATOR}\d+\.\d+", re.IGNORECASE
)
_FRACTION_COMPOSITE_RANGE_RE = re.compile(
    rf"\d+\s*/\s*\d+{_RANGE_SEPARATOR}\d+|\d+{_RANGE_SEPARATOR}\d+\s*/\s*\d+", re.IGNORECASE
)
# A free-standing negative number combined with an adjacent range
# separator is the same class of composite defect: poisoning only the
# negative component ("-3") left the range's other endpoint ("5" in "-3
# to 5") untouched and still satisfying the plain bare production (Astra
# re-review finding 2: "-3 to 5 years experience" -> fabricated
# minimum=5). Covers both endpoint orders, same as the decimal/fraction
# composites above.
_NEGATIVE_COMPOSITE_RANGE_RE = re.compile(
    rf"(?<!\d)-\d+{_RANGE_SEPARATOR}\d+|\d+{_RANGE_SEPARATOR}(?<!\d)-\d+", re.IGNORECASE
)
# Unsupported prefix markers ("less than 5", "fewer than 5") are not part
# of the recognized open-upper catalog (Astra review finding 3) — treated
# as a poison trigger, same as any other unsupported numeric shape, rather
# than silently falling back to a bare-number match that would ignore the
# marker entirely.
_UNSUPPORTED_PREFIX_RE = re.compile(r"(?:less than|fewer than)\s+\d+", re.IGNORECASE)
# Figure dash, en dash, em dash, and the Unicode minus sign are not the
# ASCII hyphen `_TITLE_SEGMENT_DELIMITER_RE`/the range grammar recognize —
# treated as unsupported and poisoned rather than silently accepted as
# either a range separator or ignored as a negative sign (Astra review
# finding 4). Deliberately narrower than full numeric-language support:
# returning UNAVAILABLE for these is sufficient.
_UNICODE_DASH_CHARS = "‒–—−"
_UNICODE_DASH_NUMERIC_RE = re.compile(
    rf"\d+\s*[{_UNICODE_DASH_CHARS}]\s*\d+|(?<!\d)[{_UNICODE_DASH_CHARS}]\d+"
)
_POISON_PATTERNS = (
    _DECIMAL_COMPOSITE_RANGE_RE,
    _FRACTION_COMPOSITE_RANGE_RE,
    _NEGATIVE_COMPOSITE_RANGE_RE,
    _FRACTION_RE,
    _NEGATIVE_NUMBER_RE,
    _DECIMAL_RE,
    _UNSUPPORTED_PREFIX_RE,
    _UNICODE_DASH_NUMERIC_RE,
)


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
            # Trailing marker *after* the complete "N years of experience"
            # phrase (as opposed to open_hi_suffix/open_lo_suffix's marker
            # positioned before the unit word) — listed before the plain
            # `bare` alternative so it takes precedence when present
            # (Astra review finding 3).
            r"|(?P<bare_trail_hi>\d+)\s*"
            + _UNIT
            + _OF_EXPERIENCE
            + r"\s+(?:or less|or fewer|or under)\b",
            r"|(?P<bare_trail_lo>\d+)\s*"
            + _UNIT
            + _OF_EXPERIENCE
            + r"\s+(?:or more|or above|plus)\b",
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
            r"\s*" + _UNIT + r"\b",
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
    if groups["bare_trail_hi"] is not None:
        return _Phrase(None, int(groups["bare_trail_hi"]), match.end())
    if groups["bare_trail_lo"] is not None:
        return _Phrase(int(groups["bare_trail_lo"]), None, match.end())
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

_TITLE_PREFERENCE_WORDS = ("preferred", "ideal", "ideally", "optional", "desired", "bonus")
_TITLE_PREFERENCE_PHRASES = _TITLE_PREFERENCE_WORDS + ("a plus", "nice to have")

_TITLE_PREFERENCE_TAG_RE = re.compile(
    r"(?:" + "|".join(_TITLE_PREFERENCE_PHRASES) + r")\s*[.!?]*\s*$",
    re.IGNORECASE,
)

# A preference marker *leading* the segment — "Preferred 3-5 years
# experience", "Ideally 5 years of experience" — not only trailing
# (Astra review finding 2). Comma after the marker is optional; titles are
# terser than description prose and rarely punctuate this fully.
_TITLE_LEADING_PREFERENCE_RE = re.compile(
    r"^(?:" + "|".join(_TITLE_PREFERENCE_PHRASES) + r")\b\s*,?\s*",
    re.IGNORECASE,
)

_TITLE_ZERO_RE = re.compile(
    r"no\s+(?:prior\s+)?experience\s+(?:required|necessary)\b", re.IGNORECASE
)

# A segment consisting of *nothing but* a qualifier phrase — reached when a
# comma splits "5 years experience, not required" into two segments; the
# second segment modifies the first rather than standing alone (Astra
# review finding 2: "preserve modifiers that qualify the requirement
# across punctuation").
_QUALIFIER_ONLY_PHRASES = frozenset(_TITLE_NOT_REQUIRED_MARKERS) | frozenset(
    _TITLE_PREFERENCE_PHRASES
)


def _normalize_segment_for_qualifier_check(segment: str) -> str:
    stripped = segment.strip().rstrip(".!?").strip()
    return re.sub(r"\s+", " ", stripped).lower()


def _is_qualifier_only_segment(segment: str) -> bool:
    return _normalize_segment_for_qualifier_check(segment) in _QUALIFIER_ONLY_PHRASES


def _nearest_meaningful_neighbor_is_qualifier(
    raw_segments: list[str], qualifier_only: list[bool], index: int, step: int
) -> bool:
    """Walks in `step` direction (-1 or +1) from `index`, skipping any
    empty/whitespace-only segment, and returns whether the first
    *meaningful* (non-blank) segment found is qualifier-only. Combined
    comma+parenthesis splitting can insert a blank segment directly
    between a qualifier and its target — `"(Preferred), 5 years
    experience"` splits into `["Preferred", "", " 5 years experience"]`,
    with the blank middle segment sitting between them — and a raw
    `index ± 1` check treats that blank as a barrier rather than looking
    past it to the real neighbor (Astra re-review finding 1)."""
    i = index + step
    while 0 <= i < len(raw_segments):
        if raw_segments[i].strip():
            return qualifier_only[i]
        i += step
    return False


def _title_segments(text: str) -> list[str]:
    """Splits `text` into structural segments in **original left-to-right
    order** — paired-parenthesis/bracket content interleaved with the
    delimiter-split text around it, not all parenthesized content hoisted
    to the front of the list. Order matters because qualifier-adjacency
    (see `_extract_title_bounds`) checks a segment's *actual* neighbors:
    `"5 years experience (not required)"` must place `"not required"`
    immediately *after* `"5 years experience"`, matching the text's own
    order, not before it (Astra re-review finding 1)."""
    segments: list[str] = []
    pos = 0
    for match in _PAREN_BRACKET_RE.finditer(text):
        before = text[pos : match.start()]
        segments.extend(_TITLE_SEGMENT_DELIMITER_RE.split(before))
        content = match.group(1) if match.group(1) is not None else match.group(2)
        segments.append(content)
        pos = match.end()
    segments.extend(_TITLE_SEGMENT_DELIMITER_RE.split(text[pos:]))
    return segments


def _iter_forward_phrases(text: str) -> list[_Phrase]:
    """Collects every non-overlapping forward-phrase match in `text`, not
    only the first — "3 years experience and 5 years experience" must
    surface both candidates so same-segment conflict resolution can run
    (Astra review finding 5), the same way multiple sentences/segments
    already do across a description/title."""
    phrases: list[_Phrase] = []
    pos = 0
    while pos <= len(text):
        result = _match_forward_phrase(text, pos)
        if result is None:
            break
        phrase, match = result
        phrases.append(phrase)
        pos = match.end() if match.end() > match.start() else match.start() + 1
    return phrases


def _extract_title_bounds(title: str | None) -> tuple[int | str | None, int | str | None]:
    if not title:
        return None, None
    working = _redact_poisoned_numbers(_normalize_text(title))
    stripped_working = working.strip()

    minimums: list[int] = []
    maximums: list[int] = []

    # Reversed label:value order ("Experience: up to 10 years") must be
    # checked against the *whole* title before segmentation runs: the
    # colon is itself a segment delimiter (`_TITLE_SEGMENT_DELIMITER_RE`),
    # so splitting first would always separate the literal word
    # "experience" from its value before `_LABEL_VALUE_RE` ever sees them
    # together — a genuine defect found while mutation-proving the
    # mandatory-unit fix below (a bare short-form-shaped value like "5+
    # years" only ever "worked" by coincidence, via the isolated-segment
    # short-form waiver on the post-colon fragment, never via this
    # mechanism at all; a non-short-form value like an open-upper prefix
    # never worked). Anchored at position 0 and remainder-checked, the
    # same discipline the description side already applies.
    whole_label_match = _LABEL_VALUE_RE.match(stripped_working)
    if whole_label_match is not None:
        whole_phrase = _match_label_value_phrase(stripped_working)
        if whole_phrase is not None:
            remainder = stripped_working[whole_phrase.end :]
            if _remainder_is_acceptable(remainder):
                if whole_phrase.minimum is not None:
                    minimums.append(whole_phrase.minimum)
                if whole_phrase.maximum is not None:
                    maximums.append(whole_phrase.maximum)
                return _collapse_or_conflict(minimums), _collapse_or_conflict(maximums)

    raw_segments = _title_segments(working)
    qualifier_only = [_is_qualifier_only_segment(s) for s in raw_segments]

    for index, raw_segment in enumerate(raw_segments):
        if qualifier_only[index]:
            # Consumed as a modifier of the preceding segment below (or,
            # if first, standalone noise with nothing to modify) — never
            # processed as its own independent segment.
            continue

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
        has_preference = bool(_TITLE_PREFERENCE_TAG_RE.search(segment_lower)) or bool(
            _TITLE_LEADING_PREFERENCE_RE.match(segment_lower)
        )
        # A qualifier-only neighbor modifies this segment whether it comes
        # *before* ("Ideally, 5 years of experience", "Preferred, 3-5
        # years experience") or *after* ("5 years experience, not
        # required", "5 years experience (not required)") — both
        # directions, across both comma and parenthesis boundaries (Astra
        # review finding 1), computed over the *nearest meaningful*
        # neighbor in each direction rather than the raw adjacent index,
        # since combined comma+parenthesis splitting can insert a blank
        # segment directly between the qualifier and its target (Astra
        # re-review finding 1).
        has_adjacent_qualifier = _nearest_meaningful_neighbor_is_qualifier(
            raw_segments, qualifier_only, index, -1
        ) or _nearest_meaningful_neighbor_is_qualifier(raw_segments, qualifier_only, index, 1)

        short_form = _match_short_form(segment)
        if short_form is not None:
            phrases = [short_form]
        else:
            phrases = _iter_forward_phrases(segment)
            if not phrases:
                label_value = _match_label_value_phrase(segment)
                phrases = [label_value] if label_value is not None else []
        if not phrases:
            continue

        if has_not_required or has_preference or has_adjacent_qualifier:
            # Whole segment suppressed — contributes nothing (Risk 4 /
            # preference suppression, including a qualifier carried across
            # a punctuation boundary), never a partial/degraded candidate.
            continue

        for phrase in phrases:
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

        # Reversed label:value order ("Experience: 5+ years") is NOT an
        # exempt, inherently role-scoped form on the description side —
        # sentence-initial position is not an approved exception (Astra
        # re-review finding 3). A reversed-label description candidate
        # must obey the same `ALLOWED_SUBJECT`/`REQUIRE_VERB` attribution
        # frame as any other candidate, exactly like the non-reversed
        # forms below; it has no separate acceptance path. In practice
        # this form almost never occurs *inside* a subject+verb frame, so
        # a standalone structured-field-style line is an accepted,
        # documented coverage gap (safe miss, not a wrong value) — see
        # the module docstring's explicit-exclusions section. The
        # equivalent title-side form remains supported unchanged, since a
        # title has no attribution-frame concept to begin with.

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
