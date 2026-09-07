"""Deterministic entry_level/mid_level/senior/staff/principal/director
classifier (Phase 3 — third parser slice; docs/ARCHITECTURE.md §4's
`normalization/seniority.py`, docs/PHASE_RISK_CHECKLIST.md's Phase 3 exit
gate).

Pure function: `title`/`description` free text in, one
`NormalizationResult` out. No database, ORM, provider, network, or
ingestion-pipeline dependency — `test_normalization_seniority.py`'s
`test_import_boundary_allow_list` proves this by AST inspection against an
exact, fail-closed permitted-import allow-list. Writing the result into
`jobs.seniority` and `jobs.field_provenance`, and threading
`parser_version`, are both Phase 4+ ingestion-layer concerns — this module
performs no writes of any kind.

**Independent implementation** — this module does not import from, or
modify, `app.normalization.employment` or `app.normalization.remote`. Its
tokenizer, hyphen-compound canonicalization, segment extraction, and
negation handling are modeled on those modules' proven *patterns* but are
each freshly, independently written here, sized to this parser's own
(different) grammar.

**Canonical v1 vocabulary** (closed, exhaustive — adversarial review may
find defects but may not silently grow this list):

    Seniority = entry_level | mid_level | senior | staff | principal | director

`junior`/`jr` fold into `entry_level` (not a seventh value). `manager`,
`lead`, `associate`, `executive`, `vp`/`vice president`, and C-level
acronyms are in no catalog at all — never evidence themselves, though a
*different*, actually-recognized qualifier can still fire independently in
the same title (see "Senior Manager" below). Numeric/roman levels
(`Engineer II`, `Level 3`) are deliberately unhandled: no catalog entry
matches them, so they produce no signal, not a silent guess.

**Title grammar — two different matching strategies per qualifier**, because
seniority qualifiers are used two structurally different ways in real
titles (unlike `remote_type`/`employment_type`, where one structural rule
sufficed):

- **Prefix-eligible qualifiers** (`senior`/`sr`/`sr.`, `staff`,
  `entry level`/`entry-level`/`junior`/`jr`/`jr.`, `mid level`/`mid-level`):
  recognized when they occupy the **leading position** (token index 0) of
  a structural segment (segments: paired parenthesis/bracket groups, then
  delimiter-split remainder — same segment extraction remote.py/employment.py
  use, independently re-derived here). Trailing text is unconstrained —
  this is what makes `"Senior Software Engineer"`, `"Sr. Data Analyst"`,
  `"Staff Engineer"`, and `"Entry-Level Analyst"` all recognize correctly.
  This is a *leading-position* rule, not "matches anywhere": if the
  leading token is unrecognized, nothing later in the segment is ever
  checked — `"Lead Senior Engineer"` returns `unavailable` because `"lead"`
  occupies the leading position and the rule never looks past it to find
  `"senior"` at index 1.
- **Explicit-phrase qualifiers** (`principal`, `director`): a bare
  "Principal" or "Director" is genuinely undecidable from text alone (a
  school principal and a corporate "Principal Engineer" are structurally
  identical strings), so these two get no bare-word or prefix treatment at
  all. They match only via a small, closed, exact multi-word phrase list,
  and that phrase must **also occupy the segment's leading position**
  (`tokens[0:len(phrase)] == phrase`) — never found merely somewhere inside
  the segment. `"Director of Engineering"` and `"Principal Software
  Engineer"` match (the phrase fills the leading position); `"Assistant to
  the Director of Engineering"`, `"Office of the Director of Operations"`,
  and `"Assistant to the Principal Engineer"` do not (an unrecognized word
  occupies the leading position instead), even though the phrase itself is
  present later in the string.

**Exclusion masking** (title and description, applied before any
qualifier matching): a small, closed set of phrases removed entirely
before matching runs — `"senior living"`, `"senior center"`, `"senior
citizen"`, `"senior year"`, `"senior thesis"` (domain-collision terms), plus
`"senior executive assistant"`, `"senior vice president"`, `"senior vp"`
(the exact three phrases needed so these specific unsupported
executive/support titles do not emit a misleading `senior` tier — added
narrowly for these named outcomes, not as a broad executive/manager
heuristic). `"Senior Manager"` and `"Senior Vice President"` are NOT the
same case: masking removes all three tokens of `"senior vice president"`
together, but `"senior manager"` is not masked at all, so `"Senior
Manager"` still resolves to `senior` — `manager` contributes nothing
itself, but does not block `senior` from firing.

**Compound rule** (title and description, checked before the general
leading-qualifier rule): a senior-alias immediately followed by bare
`"staff"` or bare `"principal"` resolves directly to `staff`/`principal`
(trailing text ignored) — `"Senior Staff Engineer"` -> `staff`, `"Senior
Principal Engineer"` -> `principal`. **Deliberately not extended to
`director`**: "Senior Art Director," "Senior Creative Director," "Senior
Managing Director" are all real, differently-meaning titles, so a blanket
"senior + director" shortcut would be unsafe. `"Senior Director"` therefore
resolves via the general rule instead (`senior` matches, trailing
`"director"` trips the conflict-scan below) -> conflict -> `unavailable`.

**Conflict-scan** (title only, within one segment's trailing tokens after
a leading-qualifier match): if any *other* value's root word (`staff`,
`principal`, `director` bare, `senior`/`sr` bare, or the `entry
level`/`mid level` compound) appears anywhere in the trailing tokens, both
values survive -> two distinct values -> conflict. This is what makes
`"Senior Director"` and `"Staff/Principal Engineer"` (`/` is its own hard
token, not a segment delimiter) both resolve to `unavailable`, and what
makes `"Senior, Staff Engineer"` (comma splits this into two *separate*
segments, defeating the compound rule, which only fires within one
segment) differ deterministically from the undelimited `"Senior Staff
Engineer"`.

**Description — a different mechanism, not title's rule reused**:
description evidence must establish that the phrase describes *the
advertised position itself*, not a colleague, manager, or mentor
("Reports to the Director of Engineering" must never count). Each
sentence (split on `. ; : ! ?`) is gated by a small, closed set of 8
self-referential anchors, checked at the sentence's own leading position:

    this is | it is | the position is | this position is |
    the role is | this role is | we are hiring | seeking

A sentence with no anchor at its leading position contributes **no
signal at all** — the rest of the sentence is never scanned, even if a
qualifier phrase appears later in it. This is why `"This role is supported
by a senior engineer."`, `"This position is reporting to the Director of
Engineering."`, and `"We are hiring alongside a staff engineer."` all
resolve to `unavailable`: each anchor matches, but the token(s)
immediately following it (`"supported"`, `"reporting"`, `"alongside"`) are
neither a valid grammatical prefix nor a qualifier candidate, and the rule
does not search arbitrarily later in the sentence.

Immediately after a matched anchor, the **only** tokens allowed before the
first candidate are drawn from one small closed grammar (longest match
wins):

    (empty) | a | an | the |
    not | no | neither | not either |
    not a | not an | not the | no a | no an | no the |
    neither a | neither an | neither the |
    not either a | not either an | not either the

A prefix starting with `not`/`no`/`neither`/`not either` marks the
candidate that follows as **negated**. The candidate itself is then
checked using the exact same compound/bare/explicit-phrase logic as
title's leading-qualifier rule (with `sr`/`sr.`/`jr.` dropped — see below),
anchored at that exact position, never searched for further into the
sentence. If a negated candidate is immediately followed by a
coordination gap (`or`/`nor`, optionally followed by exactly one
determiner `a`/`an`/`the` — the same narrow, article-tolerant rule
`employment.py` uses, independently re-derived here) and a second
candidate, that second candidate is suppressed too (`"This is neither
senior nor a staff position."` -> both suppressed -> `unavailable`). If
the first candidate was *not* negated and a coordinated second candidate
is found, both are simply added as independent survivors, naturally
becoming a two-distinct-values conflict via the same rule title uses.

`sr`/`sr.` are **title-only** — description sentence-splitting breaks on
`.`, so `"Sr. Data Analyst position"` mid-sentence would have its period
read as a sentence boundary, severing `"Sr"` from the rest; rather than
special-casing period-protection, description simply doesn't support the
abbreviation, only the spelled-out `"senior"`. `jr.` (with period) is
similarly description-excluded for the same reason; bare `"junior"`/`"jr"`
(no period) are still supported there.

**Cross-field precedence** (identical to `remote.py`/`employment.py`): a
conflict anywhere always yields `(None, UNAVAILABLE)`; title-only evidence
is `INFERRED`; description-only evidence is `PARSED_DESCRIPTION`; title and
description agreeing is `PARSED_DESCRIPTION`; no evidence anywhere is
`(None, UNAVAILABLE)`.

**Alignment with `SavedSearch.seniority`**: that column is `text[]` with no
`CHECK` constraint today — it accepts any string. This classifier's
six-value vocabulary is intended to become the *reference* vocabulary for
that field, but nothing in this slice enforces it: a saved search entered
as `['Senior']` or `['Sr']` will not exact-match `jobs.seniority =
'senior'` at query time unless a future query-planner normalization step
or a `SavedSearch.seniority` `CHECK` constraint is added. That alignment
work is out of scope here.

**Taxonomy framing**: this slice remains code-defined and bounded — no
`taxonomy/` directory or YAML file is created. `docs/ARCHITECTURE.md`'s
`seniority.yaml` entry is annotated (as part of this same slice) as
planned future enrichment, not abandoned — a later, separately-approved
slice could use it to add synonyms or non-English aliases on top of this
v1 vocabulary. `title` and `skill` remain fully blocked pending their own
separately-approved taxonomy-foundation decision (an open/extensible
canonical list a hand-written closed vocabulary cannot substitute for) —
unaffected by this slice.

**Honest evidence-gap statement**: this corpus contains exactly one real
sanitized fixture (`backend/tests/fixtures/discovery/
greenhouse_live_canary.json`'s real title, documented there as a
`sanitized_derived_sample`) — a single negative-control data point, not
broad realistic-positive coverage. This remains an acknowledged, open gap
against Phase 3's exit-gate expectation of a regression corpus built from
realistic captured payloads; every positive fixture here is
`synthetic_representative`/`synthetic_adversarial`, honestly labeled, not
a substitute for real captured data across the vocabulary.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal, cast

from app.normalization.types import NormalizationResult, Provenance

Seniority = Literal["entry_level", "mid_level", "senior", "staff", "principal", "director"]

_CONFLICT: Literal["conflict"] = "conflict"

_SENTENCE_SPLIT_RE = re.compile(r"[.;:!?]+")

_TOKEN_RE = re.compile(r"[^\s,()\[\]{}\"/&\-–—]+|[,/&\-–—]")

# Exactly two glued-hyphen compounds need canonicalizing, and only when
# not embedded in a larger hyphen chain (mirrors employment.py's fix for
# the same class of defect, independently re-derived at this module's own
# smaller scope — no import, no shared list).
_APPROVED_HYPHEN_COMPOUNDS = ("entry-level", "mid-level")
_APPROVED_HYPHEN_COMPOUND_PATTERNS = tuple(
    (re.compile(r"(?<!-)\b" + re.escape(compound) + r"\b(?!-)"), compound.replace("-", " "))
    for compound in _APPROVED_HYPHEN_COMPOUNDS
)

_CURLY_APOSTROPHES = ("‘", "’")


def _canonicalize_approved_hyphen_compounds(text: str) -> str:
    result = text
    for pattern, spaced in _APPROVED_HYPHEN_COMPOUND_PATTERNS:
        result = pattern.sub(spaced, result)
    return result


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    for curly in _CURLY_APOSTROPHES:
        normalized = normalized.replace(curly, "'")
    normalized = normalized.casefold()
    return _canonicalize_approved_hyphen_compounds(normalized)


def _tokenize(sentence: str) -> list[str]:
    return _TOKEN_RE.findall(sentence)


def _compile_phrase(phrase: str) -> tuple[str, ...]:
    return tuple(_tokenize(_normalize_text(phrase)))


def _compile_all(phrases: frozenset[str]) -> frozenset[tuple[str, ...]]:
    return frozenset(_compile_phrase(p) for p in phrases)


# ---------------------------------------------------------------------------
# Title's structural-segment extraction — same paired-delimiter design as
# remote.py/employment.py, independently written here.
# ---------------------------------------------------------------------------
_TITLE_SEGMENT_DELIMITER_RE = re.compile(r"\s[-–—]\s|[,|:]")
_PAREN_BRACKET_RE = re.compile(r"\(([^()\[\]]*)\)|\[([^()\[\]]*)\]")


def _title_segments(text: str) -> list[str]:
    segments = [
        match.group(1) if match.group(1) is not None else match.group(2)
        for match in _PAREN_BRACKET_RE.finditer(text)
    ]
    remainder = _PAREN_BRACKET_RE.sub(" ", text)
    segments.extend(_TITLE_SEGMENT_DELIMITER_RE.split(remainder))
    return segments


# ---------------------------------------------------------------------------
# Catalogs.
# ---------------------------------------------------------------------------
_TITLE_BARE_PHRASE_STRINGS: dict[Seniority, frozenset[str]] = {
    "entry_level": frozenset({"entry level", "junior", "jr", "jr."}),
    "mid_level": frozenset({"mid level"}),
    "senior": frozenset({"senior", "sr", "sr."}),
    "staff": frozenset({"staff"}),
}
_TITLE_BARE_PHRASES: dict[Seniority, frozenset[tuple[str, ...]]] = {
    label: _compile_all(phrases) for label, phrases in _TITLE_BARE_PHRASE_STRINGS.items()
}

# Description drops sr/sr./jr. (see module docstring: sentence-splitting on
# "." would sever the abbreviation from the rest of the sentence).
_DESCRIPTION_BARE_PHRASE_STRINGS: dict[Seniority, frozenset[str]] = {
    "entry_level": frozenset({"entry level", "junior", "jr"}),
    "mid_level": frozenset({"mid level"}),
    "senior": frozenset({"senior"}),
    "staff": frozenset({"staff"}),
}
_DESCRIPTION_BARE_PHRASES: dict[Seniority, frozenset[tuple[str, ...]]] = {
    label: _compile_all(phrases) for label, phrases in _DESCRIPTION_BARE_PHRASE_STRINGS.items()
}

_EXPLICIT_PHRASE_STRINGS: dict[Seniority, frozenset[str]] = {
    "principal": frozenset(
        {
            "principal engineer",
            "principal architect",
            "principal consultant",
            "principal scientist",
            "principal analyst",
            "principal software engineer",
            "principal data scientist",
            "principal product manager",
        }
    ),
    "director": frozenset(
        {
            "director of engineering",
            "engineering director",
            "director of product",
            "product director",
            "director of operations",
            "director of technology",
            "technology director",
            "director of software engineering",
        }
    ),
}
_EXPLICIT_PHRASES: dict[Seniority, frozenset[tuple[str, ...]]] = {
    label: _compile_all(phrases) for label, phrases in _EXPLICIT_PHRASE_STRINGS.items()
}

_ROOT_TOKENS_BY_VALUE: dict[Seniority, frozenset[tuple[str, ...]]] = {
    "entry_level": _TITLE_BARE_PHRASES["entry_level"],
    "mid_level": _TITLE_BARE_PHRASES["mid_level"],
    "senior": _TITLE_BARE_PHRASES["senior"],
    "staff": frozenset({("staff",)}),
    "principal": frozenset({("principal",)}),
    "director": frozenset({("director",)}),
}

# Exactly the phrases needed to keep specific unsupported executive/support
# titles from emitting a misleading tier (see module docstring) — not a
# broad executive/manager heuristic.
_EXCLUSION_PHRASE_STRINGS = frozenset(
    {
        "senior living",
        "senior center",
        "senior citizen",
        "senior year",
        "senior thesis",
        "senior executive assistant",
        "senior vice president",
        "senior vp",
    }
)
_EXCLUSION_PHRASES_BY_LENGTH = tuple(
    sorted(_compile_all(_EXCLUSION_PHRASE_STRINGS), key=len, reverse=True)
)

_ANCHOR_STRINGS = (
    "this is",
    "it is",
    "the position is",
    "this position is",
    "the role is",
    "this role is",
    "we are hiring",
    "seeking",
)
_ANCHORS_BY_LENGTH = tuple(
    sorted((_compile_phrase(a) for a in _ANCHOR_STRINGS), key=len, reverse=True)
)

_ARTICLES: tuple[tuple[str, ...], ...] = (("a",), ("an",), ("the",))
_NEGATORS: tuple[tuple[str, ...], ...] = (("not",), ("no",), ("neither",), ("not", "either"))


def _build_prefixes() -> tuple[tuple[tuple[str, ...], bool], ...]:
    """Every valid grammatical prefix immediately following an anchor:
    an optional article, an optional negator, or a negator plus an
    optional article — longest first so e.g. "not either a" is matched
    whole rather than stopping at "not"."""
    prefixes: list[tuple[tuple[str, ...], bool]] = [((), False)]
    prefixes.extend((article, False) for article in _ARTICLES)
    for negator in _NEGATORS:
        prefixes.append((negator, True))
        prefixes.extend((negator + article, True) for article in _ARTICLES)
    return tuple(sorted(prefixes, key=lambda pair: len(pair[0]), reverse=True))


_PREFIXES = _build_prefixes()

_COORD_TOKENS = frozenset({"or", "nor"})
_COORD_DETERMINERS = frozenset({"a", "an", "the"})


def _find_spans(tokens: list[str], phrase: tuple[str, ...]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    phrase_len = len(phrase)
    for start in range(len(tokens) - phrase_len + 1):
        end = start + phrase_len - 1
        if tuple(tokens[start : end + 1]) == phrase:
            spans.append((start, end))
    return spans


def _mask_exclusions(tokens: list[str]) -> list[bool]:
    masked = [False] * len(tokens)
    for phrase in _EXCLUSION_PHRASES_BY_LENGTH:
        for start, end in _find_spans(tokens, phrase):
            if any(masked[i] for i in range(start, end + 1)):
                continue
            for i in range(start, end + 1):
                masked[i] = True
    return masked


def _compact(tokens: list[str], masked: list[bool]) -> list[str]:
    return [token for token, is_masked in zip(tokens, masked, strict=True) if not is_masked]


def _match_compound(
    tokens: list[str], bare_phrases: dict[Seniority, frozenset[tuple[str, ...]]]
) -> tuple[Seniority, int] | None:
    """A senior-alias immediately followed by bare 'staff' or 'principal'
    resolves to that second value. Never extended to 'director' — see
    module docstring."""
    for senior_phrase in bare_phrases["senior"]:
        n = len(senior_phrase)
        if tuple(tokens[:n]) == senior_phrase:
            remainder = tokens[n:]
            if remainder[:1] == ["staff"]:
                return "staff", n + 1
            if remainder[:1] == ["principal"]:
                return "principal", n + 1
    return None


def _match_leading_qualifier(
    tokens: list[str], bare_phrases: dict[Seniority, frozenset[tuple[str, ...]]]
) -> tuple[Seniority, int] | None:
    """Whichever qualifier form matches at position 0 of `tokens`: the
    compound rule first, then the longest matching bare/explicit phrase.
    Returns None if nothing matches at position 0 — never searches
    further into `tokens`."""
    compound = _match_compound(tokens, bare_phrases)
    if compound is not None:
        return compound

    candidates: list[tuple[Seniority, tuple[str, ...]]] = []
    for label, phrases in bare_phrases.items():
        candidates.extend((label, phrase) for phrase in phrases)
    for label, phrases in _EXPLICIT_PHRASES.items():
        candidates.extend((label, phrase) for phrase in phrases)

    for label, phrase in sorted(candidates, key=lambda pair: len(pair[1]), reverse=True):
        n = len(phrase)
        if tuple(tokens[:n]) == phrase:
            return label, n
    return None


def _trailing_conflict_labels(trailing: list[str], matched_value: Seniority) -> set[Seniority]:
    found: set[Seniority] = set()
    for label, phrases in _ROOT_TOKENS_BY_VALUE.items():
        if label == matched_value:
            continue
        for phrase in phrases:
            if _find_spans(trailing, phrase):
                found.add(label)
                break
    return found


def _extract_title_signal(text: str | None) -> Seniority | Literal["conflict"] | None:
    if text is None or not text.strip():
        return None

    normalized = _normalize_text(text)
    survivors: set[Seniority] = set()

    for segment in _title_segments(normalized):
        tokens = _tokenize(segment)
        if not tokens:
            continue
        masked = _mask_exclusions(tokens)
        compacted = _compact(tokens, masked)
        if not compacted:
            continue

        match = _match_leading_qualifier(compacted, _TITLE_BARE_PHRASES)
        if match is None:
            continue
        value, consumed = match
        survivors.add(value)
        trailing = compacted[consumed:]
        if trailing:
            survivors |= _trailing_conflict_labels(trailing, value)

    if not survivors:
        return None
    if len(survivors) == 1:
        return next(iter(survivors))
    return _CONFLICT


def _match_anchor(tokens: list[str]) -> int | None:
    for anchor in _ANCHORS_BY_LENGTH:
        n = len(anchor)
        if tuple(tokens[:n]) == anchor:
            return n
    return None


def _match_prefix(tokens: list[str]) -> tuple[int, bool]:
    for prefix, negated in _PREFIXES:
        n = len(prefix)
        if tuple(tokens[:n]) == prefix:
            return n, negated
    return 0, False  # unreachable — the empty prefix always matches


def _match_coordination_gap(tokens: list[str]) -> int | None:
    """Tokens immediately following a just-matched candidate. Returns the
    gap length (1 for bare or/nor, 2 for or/nor + exactly one determiner)
    if a coordination gap sits at position 0, else None — never a longer
    or otherwise-shaped gap."""
    if not tokens or tokens[0] not in _COORD_TOKENS:
        return None
    if len(tokens) >= 2 and tokens[1] in _COORD_DETERMINERS:
        return 2
    return 1


def _extract_description_signal(text: str | None) -> Seniority | Literal["conflict"] | None:
    if text is None or not text.strip():
        return None

    normalized = _normalize_text(text)
    survivors: set[Seniority] = set()

    for sentence in _SENTENCE_SPLIT_RE.split(normalized):
        tokens = _tokenize(sentence)
        if not tokens:
            continue
        masked = _mask_exclusions(tokens)
        compacted = _compact(tokens, masked)
        if not compacted:
            continue

        anchor_len = _match_anchor(compacted)
        if anchor_len is None:
            continue
        remainder = compacted[anchor_len:]

        prefix_len, negated = _match_prefix(remainder)
        after_prefix = remainder[prefix_len:]

        match = _match_leading_qualifier(after_prefix, _DESCRIPTION_BARE_PHRASES)
        if match is None:
            continue
        value, consumed = match
        if not negated:
            survivors.add(value)

        after_candidate = after_prefix[consumed:]
        gap = _match_coordination_gap(after_candidate)
        if gap is None:
            continue
        second = _match_leading_qualifier(after_candidate[gap:], _DESCRIPTION_BARE_PHRASES)
        if second is None:
            continue
        second_value, _second_consumed = second
        if not negated:
            survivors.add(second_value)
        # If `negated` is True, the coordinated second candidate is
        # suppressed too (propagated negation) — contributes nothing.

    if not survivors:
        return None
    if len(survivors) == 1:
        return next(iter(survivors))
    return _CONFLICT


def classify_seniority(
    title: str | None,
    description: str | None,
) -> NormalizationResult[Seniority]:
    """Classifies a posting's seniority tier from free text alone. Pure
    function — no I/O, no persistence, no `parser_version`. See the
    module docstring for the full algorithm and its title/description
    asymmetry."""
    title_signal = _extract_title_signal(title)
    description_signal = _extract_description_signal(description)

    if title_signal == _CONFLICT or description_signal == _CONFLICT:
        return NormalizationResult(None, Provenance.UNAVAILABLE)
    if title_signal is None and description_signal is None:
        return NormalizationResult(None, Provenance.UNAVAILABLE)
    if title_signal is not None and description_signal is None:
        return NormalizationResult(cast(Seniority, title_signal), Provenance.INFERRED)
    if title_signal is None and description_signal is not None:
        return NormalizationResult(
            cast(Seniority, description_signal), Provenance.PARSED_DESCRIPTION
        )
    if title_signal == description_signal:
        return NormalizationResult(cast(Seniority, title_signal), Provenance.PARSED_DESCRIPTION)
    return NormalizationResult(None, Provenance.UNAVAILABLE)
