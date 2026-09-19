"""Deterministic skill-mention classifier (Phase 3 -- skill-classifier
slice; docs/ARCHITECTURE.md's `normalization/skills.py`,
docs/PHASE_RISK_CHECKLIST.md's Phase 3 exit gate).

Pure function: `title`/`description` free text plus an already-loaded
`TaxonomyIndex` in, a list of `SkillMatch` out. No database, ORM,
provider, network, or ingestion-pipeline dependency, and no file I/O of
its own -- loading `app/taxonomy/skills.yaml` via
`app.normalization.taxonomy.load_taxonomy` is the caller's
responsibility, not this module's. `test_normalization_skills.py`'s
`test_import_boundary_allow_list` proves the no-I/O, no-cross-parser
boundary by AST inspection against an exact, fail-closed
permitted-import allow-list.

**Independent implementation** -- this module does not import
`app.normalization.remote`, `app.normalization.seniority`, or any other
parser's private helpers. Its tokenizer and segment grammar are modeled
on `remote.py`'s proven pattern but freshly, independently written here,
sized to this parser's own (different) grammar.

**Exact-match taxonomy lookup only** -- `TaxonomyIndex.lookup()` never
scans or tokenizes; this module supplies the segmentation and hands it
one already-isolated candidate string at a time. No taxonomy growth, no
persistence, no `parser_version` threading -- writing into
`jobs.skills`/`jobs.field_provenance` is a Phase 4+ ingestion-layer
concern, out of scope here.

**Tokenizer and segment grammar** (one grammar, shared by title and
description):

    _SEGMENT_DELIMITER_RE = [,;|:/]
    _TOKEN_RE = [^\\s()\\[\\]{}"&]+

Text is first split into **segments** on comma/semicolon/pipe/colon/
slash -- the punctuation marks that conventionally separate enumerated
list items in job-posting prose. Each segment is then **tokenized** on
whitespace, parentheses/brackets/braces, the double quote, and the
ampersand. Hyphen and internal punctuation (`+`, `#`, `.`, `-`) are
never excluded from either regex, so `c++`, `c#`, `c-sharp`, and
`node.js` all survive as single tokens.

Ampersand is deliberately a *token* delimiter only, never a *segment*
delimiter: `"R&D"` must tokenize to two tokens (`"r"`, `"d"`) that stay
in **one** segment, so the ambiguous-key standalone rule below sees two
tokens and correctly does not treat `"r"` as a standalone list item.
Parentheses, brackets, and the double quote are token-only for the same
reason -- a parenthetical is a clarifying aside, not a delimited list
item.

**Terminal punctuation**: after tokenizing, a token ending in exactly
one trailing `.`/`!`/`?` (not preceded by another character from that
same set) has that one character stripped before lookup, so `"Python."`,
`"Python!"`, `"Python?"`, and `"Node.js."` all resolve correctly (the
internal `.` in `"Node.js"` is never touched -- it is not the *last*
character). A token ending in **two or more** characters from `.!?`
(`"Python!!"`, `"Python?!"`, `"Node.js.."`) is left untouched and
therefore fails to match -- a deliberate, narrow, conservative gap, never
silently over-corrected.

**Ambiguous-alias fail-closed rule**: the normalized keys `"c"`, `"r"`,
`"go"`, and `"node"` collide with ordinary English words/single letters
(a network "node", "go" as a verb, bare initials) and are never accepted
merely because they appear -- they need additional structural evidence,
which differs by field:

- **`title`**: accepted if the key stands alone as the only token in its
  segment (`"Go, Python"` -- `"Go"` is alone in its comma segment), *or*
  -- for exactly `"c"`, `"r"`, `"go"` (never bare `"node"`) -- if the very
  next token in the same segment is exactly `"developer"`, `"engineer"`,
  or `"programmer"` (`"Go Developer"`, `"R Developer"`, `"C Developer"`).
  This second rule is narrow and structural: `"Go To Market Developer"`
  (not adjacent), `"R&D Developer"` (adjacent token is `"d"`, not
  `"developer"`), and `"C-Level Developer"` (the token is `"c-level"`,
  not `"c"`, because hyphen is preserved) all correctly do not match.
  Bare `"node"` gets no such shortcut in a title -- only the unambiguous
  `"node.js"`/`"nodejs"` keys match there, unconditionally, like anywhere
  else.
- **`description`**: standalone-in-segment is *never* sufficient by
  itself. An ambiguous key only counts inside an explicit,
  anchor-bounded list region -- see below. Outside any such region, it
  is always dropped, regardless of punctuation structure
  (`"each node stores data"`, `"/cluster/node/status"`, `"press C, then
  continue"`, and `"Go, see the deployment"` all contribute nothing).

Every other taxonomy entry (anything not `"c"`/`"r"`/`"go"`/`"node"`) is
unaffected by any of this -- it matches anywhere, in either field, the
moment its normalized key is found.

**Description anchor grammar** -- the only mechanism that can authorize
an ambiguous key in `description`:

A **label** is one of the closed set `"skills"`, `"languages"`,
`"technologies"`, `"tech stack"`, matched with an ASCII-only,
literal-character grammar -- never `re.IGNORECASE`, never `\\s`, never
`.lower()`/Unicode casefolding. Letters are compared via a same-length
ASCII upper-to-lower `str.translate` table; the whitespace between a
multi-word label's own words, between the label and its colon, and
after the colon is restricted to exactly `\t`, `\n`, `\r`, and space
(this module's own covered-whitespace class, matching
`app.normalization.taxonomy`'s, declared independently rather than
imported). A non-ASCII or non-covered-whitespace character anywhere in
that span (a no-break space, a fullwidth colon, ...) simply fails the
literal match -- there is no fuzzy fallback, so a lookalike never
produces an accidental anchor.

A label match is a valid **anchor** only if it begins at one of three
positions: index 0 (start-of-field), immediately after a `\n`
(start-of-line), or immediately after a genuine **terminator**'s
trailing whitespace (a sentence boundary). This closes the
`"Soft skills:"` gap -- `"skills"` there begins mid-phrase, satisfying
none of the three, so it is not an anchor at all (the ambiguous key in
that sentence is still dropped, though any *unambiguous* key elsewhere in
the same text is unaffected and still matches via the ordinary
whole-text pass below).

A **terminator** is a complete run of `.`/`!`/`?` immediately followed by
covered whitespace, or by end-of-input. Critically, the lone `.` inside
`"Node.js"` is never a terminator -- it is followed by `j`, not
whitespace or end-of-input -- so an anchored region never ends there.

The **region** bound to an anchor runs from the anchor's own match end
(Python's ordinary exclusive-slice convention -- `region_end` is always
a `Pattern.end()` value, and the slice `text[anchor_end:region_end]`
already includes the complete terminator run) to the first genuine
terminator found afterward, or to end-of-input if none exists. The
terminator run is deliberately *not* trimmed out of the region text --
it is handed to tokenization unchanged, so the existing single-vs-
doubled trailing-punctuation rule above remains the only thing deciding
match/no-match. This is why `"Skills: Python!!"` still correctly
produces no match (the doubled `"!!"` survives into the token) and why
`"Skills: Node.js. Languages: Go"` correctly yields both
`node.js` and `golang` (the terminator that ends the first region is the
period *after* `"js"`, which is followed by a space, never the internal
one).

Within a region, the same segment/token grammar applies, and an
ambiguous key is accepted only if it is the sole token in its
region-local segment -- exactly the same standalone test used elsewhere,
just scoped to the region's own substring rather than the whole field.

**Provenance and ordering**: each matched canonical ID gets
`Provenance.PARSED_DESCRIPTION` if it was found via `description` (with
or without also appearing in `title`), else `Provenance.INFERRED` if
found via `title` only -- decided per skill, not once for the whole
result, since a multi-value result can legitimately mix both. Results
are deduplicated by `canonical_id` and returned sorted ascending by
`canonical_id`; an empty list means no skill was recognized in either
field, never a "conflict" state (unlike the single-value parsers, a
list has no not-representable-as-one-value case).

**Known, accepted limitation**: an Oxford-comma-less final list item
(`"Skills: Python, and Go"`) puts `"and"` and `"Go"` in one two-token
segment, so `"Go"` is not standalone there and is not rescued. Not
handled in this slice -- fixing it would require an `"and"`-aware
segment rule beyond what was reviewed and approved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.normalization.taxonomy import (
    TaxonomyEntry,
    TaxonomyIndex,
    TaxonomyLookupStatus,
    normalize_lookup_key,
)
from app.normalization.types import Provenance
from app.schemas.identifiers import is_canonical_slug

# Mirrors app.normalization.taxonomy's whitespace class -- declared
# independently here, not imported, per this module's own-implementation
# convention (see the module docstring's "Independent implementation").
_COVERED_WHITESPACE = "\t\n\r "
_COVERED_WS_CLASS = "[\\t\\n\\r ]"

_TERMINAL_PUNCTUATION = ".!?"

_SEGMENT_DELIMITER_RE = re.compile(r"[,;|:/]")
_TOKEN_RE = re.compile(r'[^\s()\[\]{}"&]+')

_AMBIGUOUS_ALIAS_KEYS = frozenset({"go", "node"})
_TITLE_ADJACENCY_ELIGIBLE_KEYS = frozenset({"c", "r", "go"})
_TITLE_ROLE_NOUN_KEYS = frozenset({"developer", "engineer", "programmer"})

_TERMINATOR_RUN_RE = re.compile(r"[.!?]+")

_ASCII_UPPER_TO_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")

# Closed anchor-label set. Each pattern is built from literal ASCII
# characters and the covered-whitespace class only -- no `\s`, no
# `re.IGNORECASE`. Applied against an ASCII-casefolded, same-length copy
# of the input, never against the raw text directly.
_LABEL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"tech"
        + _COVERED_WS_CLASS
        + r"+stack"
        + _COVERED_WS_CLASS
        + r"*:"
        + _COVERED_WS_CLASS
        + r"*"
    ),
    re.compile(r"technologies" + _COVERED_WS_CLASS + r"*:" + _COVERED_WS_CLASS + r"*"),
    re.compile(r"languages" + _COVERED_WS_CLASS + r"*:" + _COVERED_WS_CLASS + r"*"),
    re.compile(r"skills" + _COVERED_WS_CLASS + r"*:" + _COVERED_WS_CLASS + r"*"),
)

_PROVENANCE_TYPE_ERROR = (
    "SkillMatch invariant violated: provenance must be a Provenance enum member."
)
_CANONICAL_ID_ERROR = (
    "SkillMatch invariant violated: canonical_id must satisfy is_canonical_slug()."
)
_DISPLAY_NAME_ERROR = (
    "SkillMatch invariant violated: display_name must contain non-whitespace content."
)


@dataclass(frozen=True)
class SkillMatch:
    """One recognized skill mention. `canonical_id` is revalidated against
    the taxonomy's own grammar (`is_canonical_slug`), not merely checked
    for truthiness -- a whitespace-only string is truthy in Python and
    would otherwise silently pass a bare `not value` check. Every
    invariant-violation message is fixed and categorical, with no
    interpolated runtime content, matching `NormalizationResult`'s own
    convention."""

    canonical_id: str
    display_name: str
    provenance: Provenance

    def __post_init__(self) -> None:
        if not isinstance(self.provenance, Provenance):
            raise ValueError(_PROVENANCE_TYPE_ERROR)
        if not isinstance(self.canonical_id, str) or not is_canonical_slug(self.canonical_id):
            raise ValueError(_CANONICAL_ID_ERROR)
        if (
            not isinstance(self.display_name, str)
            or self.display_name.strip(_COVERED_WHITESPACE) == ""
        ):
            raise ValueError(_DISPLAY_NAME_ERROR)


def _strip_terminal_punctuation(token: str) -> str:
    if (
        len(token) >= 2
        and token[-1] in _TERMINAL_PUNCTUATION
        and token[-2] in _TERMINAL_PUNCTUATION
    ):
        return token
    if token and token[-1] in _TERMINAL_PUNCTUATION:
        return token[:-1]
    return token


def _tokenize_segment(segment: str) -> list[str]:
    return [_strip_terminal_punctuation(match.group()) for match in _TOKEN_RE.finditer(segment)]


def _segments(text: str) -> list[list[str]]:
    return [_tokenize_segment(segment) for segment in _SEGMENT_DELIMITER_RE.split(text)]


def _is_ambiguous_key(normalized_key: str) -> bool:
    return len(normalized_key) <= 1 or normalized_key in _AMBIGUOUS_ALIAS_KEYS


def _match_token(taxonomy: TaxonomyIndex, token: str) -> tuple[str, TaxonomyEntry] | None:
    result = taxonomy.lookup(token)
    if result.status is not TaxonomyLookupStatus.MATCHED or result.entry is None:
        return None
    return normalize_lookup_key(token), result.entry


def _extract_title_matches(text: str | None, taxonomy: TaxonomyIndex) -> dict[str, TaxonomyEntry]:
    if text is None or not text.strip():
        return {}

    matches: dict[str, TaxonomyEntry] = {}
    for segment_tokens in _segments(text):
        for position, token in enumerate(segment_tokens):
            found = _match_token(taxonomy, token)
            if found is None:
                continue
            normalized_key, entry = found
            if not _is_ambiguous_key(normalized_key):
                matches[entry.canonical_id] = entry
                continue

            standalone = len(segment_tokens) == 1
            adjacent_role_noun = False
            if normalized_key in _TITLE_ADJACENCY_ELIGIBLE_KEYS and position + 1 < len(
                segment_tokens
            ):
                next_key = normalize_lookup_key(segment_tokens[position + 1])
                adjacent_role_noun = next_key in _TITLE_ROLE_NOUN_KEYS

            if standalone or adjacent_role_noun:
                matches[entry.canonical_id] = entry
    return matches


def _is_genuine_terminator_end(text: str, end: int) -> bool:
    return end == len(text) or text[end] in _COVERED_WHITESPACE


def _sentence_boundary_start_positions(text: str) -> frozenset[int]:
    starts: set[int] = set()
    for match in _TERMINATOR_RUN_RE.finditer(text):
        end = match.end()
        if not _is_genuine_terminator_end(text, end):
            continue
        if end == len(text):
            continue
        whitespace_end = end
        while whitespace_end < len(text) and text[whitespace_end] in _COVERED_WHITESPACE:
            whitespace_end += 1
        starts.add(whitespace_end)
    return frozenset(starts)


def _next_genuine_terminator_end(text: str, start: int) -> int:
    for match in _TERMINATOR_RUN_RE.finditer(text, start):
        if _is_genuine_terminator_end(text, match.end()):
            return match.end()
    return len(text)


def _has_uncovered_whitespace_immediately_after(text: str, position: int) -> bool:
    """True if the character at `position` is Unicode whitespace (e.g. a
    no-break space) that is *not* in this module's covered-whitespace
    class. The label patterns' final `[\\t\\n\\r ]*` group is
    zero-or-more with no mandatory literal after it, so it never itself
    rejects a whitespace lookalike sitting right after the colon --
    unlike every other whitespace span in the grammar, which is always
    followed by a mandatory literal (the label's next word, or the
    colon itself) that a lookalike character cannot satisfy. Without
    this explicit check, a lookalike would be left unconsumed as the
    first character of the region text, where the region's own
    (ordinary, Unicode-`\\s`-aware) tokenizer would still treat it as a
    token separator -- silently rescuing exactly the ambiguous key this
    anchor grammar exists to gate."""
    return (
        position < len(text)
        and text[position].isspace()
        and text[position] not in _COVERED_WHITESPACE
    )


def _anchor_regions(text: str) -> list[str]:
    casefolded = text.translate(_ASCII_UPPER_TO_LOWER)
    valid_starts = _sentence_boundary_start_positions(text)

    regions: list[str] = []
    for pattern in _LABEL_PATTERNS:
        for match in pattern.finditer(casefolded):
            start = match.start()
            if not (start == 0 or text[start - 1] == "\n" or start in valid_starts):
                continue
            if _has_uncovered_whitespace_immediately_after(text, match.end()):
                continue
            region_end = _next_genuine_terminator_end(text, match.end())
            regions.append(text[match.end() : region_end])
    return regions


def _extract_description_matches(
    text: str | None, taxonomy: TaxonomyIndex
) -> dict[str, TaxonomyEntry]:
    if text is None or not text.strip():
        return {}

    matches: dict[str, TaxonomyEntry] = {}

    # Whole-text pass: unambiguous keys match anywhere, regardless of
    # any anchor.
    for segment_tokens in _segments(text):
        for token in segment_tokens:
            found = _match_token(taxonomy, token)
            if found is None:
                continue
            normalized_key, entry = found
            if not _is_ambiguous_key(normalized_key):
                matches[entry.canonical_id] = entry

    # Region-scoped pass: ambiguous keys require both an anchor and a
    # standalone position within that anchor's own bounded region.
    for region_text in _anchor_regions(text):
        for segment_tokens in _segments(region_text):
            if len(segment_tokens) != 1:
                continue
            found = _match_token(taxonomy, segment_tokens[0])
            if found is None:
                continue
            normalized_key, entry = found
            if _is_ambiguous_key(normalized_key):
                matches[entry.canonical_id] = entry

    return matches


def classify_skills(
    title: str | None,
    description: str | None,
    *,
    taxonomy: TaxonomyIndex,
) -> list[SkillMatch]:
    """Classifies every skill mention recognized in `title`/`description`
    against `taxonomy`. Pure function -- no I/O, no persistence, no
    `parser_version`. See the module docstring for the full grammar and
    the field-specific ambiguous-key rules.
    """
    title_matches = _extract_title_matches(title, taxonomy)
    description_matches = _extract_description_matches(description, taxonomy)

    combined: dict[str, TaxonomyEntry] = {**title_matches, **description_matches}
    if not combined:
        return []

    results = [
        SkillMatch(
            canonical_id=entry.canonical_id,
            display_name=entry.display_name,
            provenance=(
                Provenance.PARSED_DESCRIPTION
                if canonical_id in description_matches
                else Provenance.INFERRED
            ),
        )
        for canonical_id, entry in combined.items()
    ]
    return sorted(results, key=lambda match: match.canonical_id)
