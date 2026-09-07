"""Deterministic full_time/part_time/seasonal/internship classifier (Phase 3
— second parser slice; docs/ARCHITECTURE.md §4's `normalization/employment.py`,
docs/PHASE_RISK_CHECKLIST.md's Phase 3 exit gate).

Pure function: `title`/`description` free text in, one `NormalizationResult`
out. No database, ORM, provider, network, or ingestion-pipeline dependency —
`test_normalization_employment.py`'s `test_import_boundary_allow_list` proves
this by AST inspection against an exact, fail-closed permitted-import
allow-list. Writing the result into `jobs.employment_type` (the eventual
persistence target) and `jobs.field_provenance`, and threading
`parser_version`, are both Phase 4+ ingestion-layer concerns — this module
performs no writes of any kind.

**Scope boundary — three separate schema columns, one parser:**

`jobs.employment_type`, `jobs.contract_type`, and `jobs.shift` are three
independent free-text columns (docs/DATA_MODEL.md, no enum on any of them),
each describing a different axis of a posting:

- `employment_type` (this module) — the **schedule/commitment** axis: how
  many hours, how continuously. This slice's vocabulary:
  `full_time | part_time | seasonal | internship`.
- `contract_type` — the **engagement/payroll-classification** axis: the
  legal nature of the relationship (`contract`, `temporary`,
  `contract_to_hire`, `1099`/`W2` tax classification, ...). **Deferred to
  its own future slice.** This module never reads, writes, or reasons about
  `jobs.contract_type` — that column remains exactly as it is today (`NULL`)
  until its own parser exists.
- `shift` — the **time-of-day/pattern** axis (day/night/weekend/rotating/
  on-call). Not deferred in the sense of "coming next" — it is simply
  outside this slice's scope and is not currently represented by any
  dedicated `normalization/` module in docs/ARCHITECTURE.md §4's diagram.
  Nothing here forecloses a future `shift` parser; there just isn't one
  planned yet.

Because `contract_type`/`1099`/`W2`/`per diem` vocabulary is not part of
*this* parser's catalog at all, words like "contract", "temporary" (and its
common abbreviation "temp"), "contract-to-hire" (and "temp-to-perm", the
same transitional-arrangement concept), "W2", "1099", and "per diem" are
simply **inert** to this classifier — they contribute zero candidate evidence and can never
compete with, mask, or falsely conflict against an `employment_type` value.
A posting reading "Full-Time Contract" is `employment_type=full_time` with
"Contract" as inert noise this parser does not claim; a future
`contract_type` parser reading the same raw text independently would be the
one to classify "Contract" itself. No information is destroyed by this
slice — deferred axes stay `NULL`, ready for their own parser, exactly as
they were before this slice existed.

**Cross-axis inert masking (the mechanism that makes this work):** before
either field is matched against this parser's own catalogs, every
occurrence of a small, closed, explicitly-enumerated set of *other-axis*
phrases (`_OTHER_AXIS_MASK_PHRASES`: `contract`, `temporary`, `contract to
hire`, `1099`, `w2`, `w 2`, `per diem`) is removed entirely from the token
sequence before any `employment_type` phrase search runs. This is narrowly
scoped to that one small, named, currently-deferred vocabulary — never to
arbitrary occupational or domain words — so it cannot reopen the "a bare
word matches anywhere inside an arbitrary undelimited phrase" risk that
`remote.py`'s own structural-marker redesign closed. `"Remote Infrastructure
Engineer"`-style false positives have no analog here: an *occupational*
trailing word (e.g. "Recruiter" in "Full-Time Contract Recruiter") is never
masked, so it still correctly breaks an exact structural match.

**Same-axis conflicts are never selectively resolved.** `seasonal` and
`internship` are full, equally-rigorous catalog values — neither is ever
added to the other-axis mask, and neither is treated as inert. If a title or
description asserts two *distinct* `employment_type` values — "Seasonal,
Full-Time" (two comma-delimited title segments, each independently an exact
structural match) or an explicit description disjunction ("full-time or
part-time") — the result is `UNAVAILABLE`, identically to `remote.py`'s
existing `remote`/`hybrid` disagreement rule. This holds **even though both
values might be true of the real job** (e.g. a genuinely seasonal,
full-time position): `jobs.employment_type` is a single scalar text column,
not an array, so it has no way to hold two simultaneous values, and guessing
which one is "the" answer is exactly the false-confidence risk
docs/PHASE_RISK_CHECKLIST.md's Phase 3 section prohibits. This is a
documented **limitation of the existing scalar column**, not a defect in
the parser: a future schema change (an array column, or a
`contract_type`-style second column) would be a separate, reviewed decision,
not something this parser can route around unilaterally. Note the
asymmetry with title: `"Part-Time Internship"` (no delimiter at all) is one
undelimited 3-token segment that does not exactly equal either 2-token or
1-token catalog phrase, so it produces *no* structural title signal at all
— still `UNAVAILABLE`, but via "no exact segment match" rather than a
detected two-value conflict. Both routes are equally conservative (no
information is guessed either way) and neither masks or special-cases
`seasonal`/`internship`.

**Field-specific positive-evidence contract**, mirroring `remote.py`'s
already-proven title/description asymmetry (independently implemented here,
not imported — this module's needs are smaller: no comma-contrast rescue,
no title explicit-phrase-anywhere catalog, so no character-span tracking is
needed at all, only token-index tracking):

- **`title`** uses a **structural marker rule** (`_extract_title_signal`).
  A bare marker (`"full-time"`, `"part-time"`, `"seasonal"`,
  `"internship"`, `"intern"`) counts as signal only when, after cross-axis
  masking, the *entire* structural segment's remaining tokens equal exactly
  one catalog phrase — the complete title, a parenthesized/bracketed group
  (properly paired only — see below), or a comma/pipe/colon/whitespace-
  surrounded-dash-delimited segment. A leading bare word directly glued to
  an arbitrary occupational/domain word with no delimiter, parenthetical,
  or cross-axis-masked companion (e.g. `"Full-Time Equivalent Analyst"`,
  `"Seasonal Produce Manager"`) therefore never qualifies — "Analyst"/
  "Produce Manager" are not on the closed other-axis mask, so they still
  break exact-segment-equality, precisely as intended. **There is no
  "explicit phrase anywhere" mechanism for `title` in this slice** —
  unlike `remote.py`'s `_TITLE_EXPLICIT_PHRASES` (which recognizes
  inherently-unambiguous multi-word phrases like `"fully remote"`
  anywhere in a title, regardless of segment boundaries), no such catalog
  exists here. None of the four `employment_type` values had a compelling,
  safe multi-word phrase that needed to match outside the four structural
  forms above; the structural-marker rule alone, applied identically to
  all four values, is the complete title contract for this slice. The
  fixture corpus's `structural_matrix_*` cases exhaustively cover all four
  structural forms (whole-title, parenthesized, bracketed,
  delimiter-segment) for all four values.
- **`description`** matches only **arrangement-bearing phrases**
  (`_DESCRIPTION_QUALIFIED_PHRASES`): each bare prefix combined with one of
  `position`, `role`, `job`, `basis`, `employment` (plus `work` for
  `seasonal`; plus `program`/`opportunity` instead of `job`/`basis`/
  `employment` for `internship`, since "internship job"/"internship basis"
  do not read naturally). A **bare** marker in description prose (e.g.
  `"internship experience required"`, `"seasonal produce"`, `"full-time
  equivalent"`, `"part-time students"`, `"W2 reporting"`, `"1099 tax
  form"`) is never sufficient on its own — this positive catalog is the
  entire semantic gate for this slice; no additional context-exclusion cue
  list is layered on top, unlike `remote.py`'s belt-and-suspenders design,
  because the arrangement-noun requirement alone already structurally
  rejects every adversarial case discovered while designing this slice (see
  the fixture corpus). A future finding may still justify adding one.
  Matching is performed against the **cross-axis-masked, compacted** token
  sequence for the whole sentence (masked tokens removed entirely, not just
  flagged), so `"a full-time contract position"` still matches `"full-time
  position"` once the inert `"contract"` token is removed from between them.
- **No comma-contrast exception** — deliberately omitted for this slice
  (unlike `remote.py`), since no employment-type fixture demonstrates a
  need for it. If a genuine case is found, adding it is its own reviewed
  change.
- **Predicate-adjective phrasing is out of scope**, matching `remote.py`'s
  own established limit: `"This position is full-time"` (noun-then-adjective
  word order) is not recognized as a qualified phrase, only the attributive
  order `"full-time position"` is. The same string appearing in `title`
  (where a bare structural segment can match on its own, with no noun
  needed at all) versus `description` (which always requires an adjacent
  noun) can therefore legitimately produce different results in the two
  fields — this is an intentional asymmetry, not a bug, identical in kind to
  `remote.py`'s own title/description asymmetry.

**Pipeline (independently implemented — no cross-module private imports):**

1. NFKC-normalize, fold curly apostrophes (U+2018/U+2019) to the straight
   apostrophe, then case-fold.
2. `title`: split into structural segments (paired-parenthesis/bracket
   groups, then delimiter-split the remainder). `description`: split into
   sentences on `. ; : ! ?`.
3. A hyphen glued directly between two non-whitespace characters (as in
   `"full-time"`) is first normalized to a plain space during step 1
   (`_GLUED_HYPHEN_RE`), making it identical to the other
   explicitly-supported spelling, `"full time"`. Tokenize on whitespace and
   `,()[]{}"/&-–—`. Whitespace is the only remaining **transparent**
   separator. Comma, slash, ampersand, en-dash, em-dash, and any
   *surviving* hyphen (one with whitespace on at least one side — a prose
   dash, not a compound-word joiner) are **not** transparent: each becomes
   its own standalone one-character token, so `"Full/Time"`,
   `"full, time"`, `"full & time"`, `"full - time"`, and a glued
   `"full—time"` each produce a longer, non-matching token sequence
   instead of silently collapsing to the same phrase as the two accepted
   spellings. This applies uniformly to every catalog phrase, including
   multi-token cross-axis mask phrases (`"contract to hire"` still matches
   its hyphenated/spaced forms, but not `"contract/to/hire"`). Parens/
   brackets/braces/quote remain transparent — title's own structural
   extraction and segment-delimiter split already consume them before
   tokenization runs on a given segment.
4. **Cross-axis mask-and-compact**: find every `_OTHER_AXIS_MASK_PHRASES`
   span in the token list and remove those tokens entirely, producing a
   compacted sequence with no other-axis noise in it at all.
5. `title`: the compacted segment's tokens must equal exactly one bare
   catalog phrase. `description`: search the compacted sentence for
   contiguous arrangement-bearing phrase matches (qualified) and bare
   catalog matches (unqualified, tracked only to support negation
   coordination below — never counted as signal directly).
6. **Negation** (`description` only, `title` has none — same reasoning as
   `remote.py`: the structural rule is already conservative enough):
   for each negation cue (`not`, `no`, `neither`, `isn't`, `aren't`,
   `without`, `unavailable`), find its nearest surviving candidate(s)
   within a 3-token window and suppress them (a tie suppresses both).
   **Direction/clause-aware binding**: the search always tries the
   *forward* tier (candidates after the negator) first, and only falls
   back to the *backward* tier (candidates before the negator) when no
   forward candidate exists in-window at all — a negator overwhelmingly
   negates what grammatically follows it ("not X"), so a closer backward
   candidate, often sitting in an entirely separate clause, must never
   preempt an in-window forward candidate. This resolves the asymmetric
   matrix: `"This is a part-time role, not a full-time position."` ->
   `part_time` (forward `"full-time position"` is negated; backward
   `"part-time role"` is untouched since a forward candidate existed);
   the symmetric swap -> `full_time`; `"This is seasonal work, not a
   full-time position."` -> `seasonal`; `"Not internship, full-time
   position available."` -> `full_time` (both candidates are forward
   here — nearest-forward-only picks `"internship"`, leaving the farther
   forward `"full-time position"` untouched); and `"A full-time position
   is not available."` -> `UNAVAILABLE` (no forward candidate at all, so
   the backward-tier fallback still suppresses the qualified candidate,
   preserving `remote.py`-style trailing negation). Suppression propagates
   transitively to any candidate coordinated with an already-suppressed one
   via exactly one `"or"`/`"nor"` token between their spans — proven by
   `"This is not a full-time position or a part-time role."` (both
   qualified, only the first is within the negator's direct window; `"or"`
   propagates suppression to the second) and, degenerately, by `"This
   position is not full-time or part-time."` (neither is qualified at all
   in this word order, so both already contribute nothing regardless of
   suppression — included as an explicit regression, not because
   coordination changes its outcome here).
7. **Unresolved-negation poisoning**: a negation cue present in a sentence
   containing at least one candidate, whose own nearest-candidate search
   finds nothing within its window, discards that whole sentence's
   candidates rather than leaving them positive.
8. Distinct surviving qualified labels across all sentences/segments of one
   field: zero -> no signal; one -> that field's signal; two or more ->
   `"conflict"`.

**Cross-field precedence** (identical to `remote.py`, required to match by
the approved proposal): a conflict anywhere always yields
`(None, UNAVAILABLE)`; title-only evidence is `INFERRED`; description-only
evidence is `PARSED_DESCRIPTION`; title and description agreeing is
`PARSED_DESCRIPTION`; no evidence anywhere is `(None, UNAVAILABLE)`.

**Catalogs are exhaustive for this slice** — deliberately conservative,
listed in full above and in code. `per_diem` is **not** part of this
slice's vocabulary at all (per the approved proposal): it contributes no
signal under any circumstance, resolving to `UNAVAILABLE` exactly like any
other unrecognized phrase — not silently assigned to either axis.

**Fixed (was a known, discovered limitation in the prior iteration):** an
earlier draft's nearest-candidate negation window had no notion of
direction, so a closer *backward* candidate could win the "nearest" slot
over the actually-negated *forward* candidate in a separate clause —
`"This is a paid internship, not a full-time position."` incorrectly
returned `full_time`. Codex's review confirmed this generalized beyond the
originally-pinned example (also reproducing it with `"part-time role... not
a full-time position"`, its symmetric swap, and `"seasonal work... not a
full-time position"`) and required a real fix rather than a documented
limitation, since it let the parser confidently return a value the text
explicitly contradicts. Fixed via the direction/clause-aware binding
described in step 6 above; no cross-module comma-contrast/character-span
mechanism was needed — plain forward-tier-then-backward-tier-fallback
token-index comparison was sufficient, and was verified against the full
asymmetric matrix (see the `negation_direction_*` fixture cases) including
the two patterns that must still resolve the *other* way (`"Not
internship, full-time position available."` -> `full_time`; trailing
backward-only negation with no forward candidate at all -> `UNAVAILABLE`).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal, cast

from app.normalization.types import NormalizationResult, Provenance

EmploymentType = Literal["full_time", "part_time", "seasonal", "internship"]

_CONFLICT: Literal["conflict"] = "conflict"

_SENTENCE_SPLIT_RE = re.compile(r"[.;:!?]+")

# Two alternatives, deliberately asymmetric: a "word" run (first
# alternative) treats whitespace *and the plain ASCII hyphen* as
# invisible/transparent — the only two separators an explicitly-supported
# catalog spelling ("full-time" / "full time") ever uses — while comma,
# slash, ampersand, en-dash, and em-dash (second alternative) are matched
# as their own standalone one-character tokens, never silently discarded.
# This is what makes `"full-time"`/`"full time"` tokenize identically to
# `("full", "time")` while `"Full/Time"`, `"full, time"`, `"full & time"`,
# and a glued `"full—time"` each produce a *longer*, non-matching token
# sequence (e.g. `("full", "/", "time")`) instead of silently collapsing
# to the same two-token phrase. Parens/brackets/braces/quote remain
# transparent here too — title's own paren/bracket structural extraction
# and segment-delimiter split already consume them before tokenization
# ever runs on a given segment.
_TOKEN_RE = re.compile(r"[^\s,()\[\]{}\"/&\-–—]+|[,/&\-–—]")

# A hyphen glued directly between two non-whitespace characters ("full-
# time") is a compound-word joiner and normalizes to a plain space, making
# it identical to the other explicitly-supported spelling ("full time").
# A hyphen with whitespace on either side ("full - time", "full- time",
# "full -time") is *not* glued — it is being used as a prose dash, exactly
# like en-dash/em-dash — and is deliberately left alone here so `_TOKEN_RE`
# tokenizes it as its own hard, non-transparent token.
_GLUED_HYPHEN_RE = re.compile(r"(?<=\S)-(?=\S)")

_CURLY_APOSTROPHES = ("‘", "’")

_NEGATION_WINDOW = 3
_COORDINATING_CONJUNCTIONS = frozenset({"or", "nor"})

# Comma/pipe/colon anywhere, or a hyphen/en-dash/em-dash *surrounded by
# whitespace* (never glued inside a word) — same structural-segment
# definition as `remote.py`'s title rule, independently written here.
_TITLE_SEGMENT_DELIMITER_RE = re.compile(r"\s[-–—]\s|[,|:]")

# `(...)` and `[...]` as two entirely separate alternatives — never a mix
# of the two — so a crossed form like `"(Full-Time]"` matches neither
# alternative and is never treated as a structural marker.
_PAREN_BRACKET_RE = re.compile(r"\(([^()\[\]]*)\)|\[([^()\[\]]*)\]")


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    for curly in _CURLY_APOSTROPHES:
        normalized = normalized.replace(curly, "'")
    normalized = normalized.casefold()
    return _GLUED_HYPHEN_RE.sub(" ", normalized)


def _tokenize(sentence: str) -> list[str]:
    return _TOKEN_RE.findall(sentence)


def _compile_phrase(phrase: str) -> tuple[str, ...]:
    return tuple(_tokenize(_normalize_text(phrase)))


def _compile_all(phrases: frozenset[str]) -> frozenset[tuple[str, ...]]:
    return frozenset(_compile_phrase(p) for p in phrases)


# ---------------------------------------------------------------------------
# Bare marker catalog — title's structural-segment check, and description's
# negation-coordination bookkeeping (never counted as signal in description
# on its own, since there is no comma-contrast rescue in this slice).
# ---------------------------------------------------------------------------
_BARE_PHRASE_STRINGS: dict[EmploymentType, frozenset[str]] = {
    "full_time": frozenset({"full-time", "full time"}),
    "part_time": frozenset({"part-time", "part time"}),
    "seasonal": frozenset({"seasonal"}),
    "internship": frozenset({"internship", "intern"}),
}
_BARE_PHRASES: dict[EmploymentType, frozenset[tuple[str, ...]]] = {
    label: _compile_all(phrases) for label, phrases in _BARE_PHRASE_STRINGS.items()
}

# ---------------------------------------------------------------------------
# Description's positive catalog — arrangement-bearing phrases only, built
# from an explicit prefix and an explicit per-label noun set.
# ---------------------------------------------------------------------------
_ARRANGEMENT_PREFIX_STRINGS: dict[EmploymentType, str] = {
    "full_time": "full-time",
    "part_time": "part-time",
    "seasonal": "seasonal",
    "internship": "internship",
}
_ARRANGEMENT_NOUNS: dict[EmploymentType, frozenset[str]] = {
    "full_time": frozenset({"position", "role", "job", "basis", "employment"}),
    "part_time": frozenset({"position", "role", "job", "basis", "employment"}),
    "seasonal": frozenset({"position", "role", "job", "basis", "employment", "work"}),
    "internship": frozenset({"position", "role", "program", "opportunity"}),
}


def _build_description_qualified_phrases() -> dict[EmploymentType, frozenset[tuple[str, ...]]]:
    result: dict[EmploymentType, frozenset[tuple[str, ...]]] = {}
    for label in ("full_time", "part_time", "seasonal", "internship"):
        label_key = cast(EmploymentType, label)
        prefix_tokens = _compile_phrase(_ARRANGEMENT_PREFIX_STRINGS[label_key])
        result[label_key] = frozenset(
            prefix_tokens + _compile_phrase(noun) for noun in _ARRANGEMENT_NOUNS[label_key]
        )
    return result


_DESCRIPTION_QUALIFIED_PHRASES = _build_description_qualified_phrases()

# ---------------------------------------------------------------------------
# Cross-axis inert mask — the small, closed, currently-deferred
# `contract_type`/tax-classification/`per diem` vocabulary. Narrowly scoped:
# never an arbitrary occupational or domain word.
# ---------------------------------------------------------------------------
_OTHER_AXIS_MASK_PHRASE_STRINGS = frozenset(
    {
        "contract",
        "temporary",
        "temp",
        "contract to hire",
        "temp to perm",
        "1099",
        "w2",
        "w 2",
        "per diem",
    }
)
_OTHER_AXIS_MASK_PHRASES = _compile_all(_OTHER_AXIS_MASK_PHRASE_STRINGS)

_NEGATION_CUE_STRINGS = ("not", "no", "neither", "isn't", "aren't", "without", "unavailable")
_NEGATION_CUES = frozenset(_compile_phrase(p)[0] for p in _NEGATION_CUE_STRINGS)


def _find_spans(tokens: list[str], phrase: tuple[str, ...]) -> list[tuple[int, int]]:
    """Every contiguous (start, end-inclusive) span in `tokens` matching
    `phrase` exactly."""
    spans: list[tuple[int, int]] = []
    phrase_len = len(phrase)
    for start in range(len(tokens) - phrase_len + 1):
        end = start + phrase_len - 1
        if tuple(tokens[start : end + 1]) == phrase:
            spans.append((start, end))
    return spans


_OTHER_AXIS_MASK_PHRASES_BY_LENGTH = tuple(sorted(_OTHER_AXIS_MASK_PHRASES, key=len, reverse=True))


def _mask_other_axis_tokens(tokens: list[str]) -> list[bool]:
    """Longest-phrase-first, so a longer mask phrase (e.g. `"temp to
    perm"`) is never blocked by a shorter one that shares its leading token
    (`"temp"`) claiming that token first — `_OTHER_AXIS_MASK_PHRASES` is a
    `frozenset` with no defined iteration order, so this ordering must be
    explicit, not incidental."""
    masked = [False] * len(tokens)
    for phrase in _OTHER_AXIS_MASK_PHRASES_BY_LENGTH:
        for start, end in _find_spans(tokens, phrase):
            if any(masked[i] for i in range(start, end + 1)):
                continue
            for i in range(start, end + 1):
                masked[i] = True
    return masked


def _compact(tokens: list[str], masked: list[bool]) -> list[str]:
    """Cross-axis-masked tokens removed entirely (not merely flagged), so a
    phrase search can find e.g. `"full-time position"` immediately either
    side of a removed `"contract"` token."""
    return [token for token, is_masked in zip(tokens, masked, strict=True) if not is_masked]


def _distance(pivot: int, start: int, end: int) -> int:
    """Token distance from a single-token pivot index to a [start, end]
    span — the distance to the span's nearest edge."""
    if pivot < start:
        return start - pivot
    if pivot > end:
        return pivot - end
    return 0


def _is_coordinated(a_start: int, a_end: int, b_start: int, b_end: int, tokens: list[str]) -> bool:
    """True only if the two spans are joined by exactly one coordinating
    conjunction token ("or"/"nor") and nothing else between them."""
    if b_start > a_end:
        gap = tokens[a_end + 1 : b_start]
    elif a_start > b_end:
        gap = tokens[b_end + 1 : a_start]
    else:
        return False
    return len(gap) == 1 and gap[0] in _COORDINATING_CONJUNCTIONS


def _title_segments(text: str) -> list[str]:
    """Every structurally distinct segment of a title: each properly
    paired parenthesized `(...)` or bracketed `[...]` group's inner content,
    plus each delimiter-separated segment of the remainder. A crossed form
    like `"(Full-Time]"` matches neither paren/bracket alternative and stays
    in the plain delimiter-split remainder instead, same as any other stray
    punctuation."""
    segments = [
        match.group(1) if match.group(1) is not None else match.group(2)
        for match in _PAREN_BRACKET_RE.finditer(text)
    ]
    remainder = _PAREN_BRACKET_RE.sub(" ", text)
    segments.extend(_TITLE_SEGMENT_DELIMITER_RE.split(remainder))
    return segments


def _extract_title_signal(text: str | None) -> EmploymentType | Literal["conflict"] | None:
    """`title` uses a structural marker rule: the *entire* cross-axis-masked
    segment must equal exactly one bare catalog phrase. No negation support,
    same reasoning as `remote.py`."""
    if text is None or not text.strip():
        return None

    normalized = _normalize_text(text)
    survivors: set[str] = set()

    for segment in _title_segments(normalized):
        tokens = _tokenize(segment)
        if not tokens:
            continue
        masked = _mask_other_axis_tokens(tokens)
        compacted = tuple(_compact(tokens, masked))
        if not compacted:
            continue
        for label, phrases in _BARE_PHRASES.items():
            if compacted in phrases:
                survivors.add(label)

    if not survivors:
        return None
    if len(survivors) == 1:
        return cast(EmploymentType, next(iter(survivors)))
    return _CONFLICT


def _extract_description_signal(text: str | None) -> EmploymentType | Literal["conflict"] | None:
    """`description`'s positive catalog is arrangement-bearing phrases only,
    searched against the cross-axis-masked, compacted token sequence. Bare
    markers are still collected to support negation coordination, but never
    count as signal on their own."""
    if text is None or not text.strip():
        return None

    normalized = _normalize_text(text)
    survivors: set[str] = set()

    for sentence in _SENTENCE_SPLIT_RE.split(normalized):
        tokens = _tokenize(sentence)
        if not tokens:
            continue
        masked = _mask_other_axis_tokens(tokens)
        compacted = _compact(tokens, masked)
        if not compacted:
            continue

        qualified: list[tuple[int, int, EmploymentType]] = []
        for label, phrases in _DESCRIPTION_QUALIFIED_PHRASES.items():
            for phrase in phrases:
                for start, end in _find_spans(compacted, phrase):
                    qualified.append((start, end, label))

        bare: list[tuple[int, int, EmploymentType]] = []
        for label, phrases in _BARE_PHRASES.items():
            for phrase in phrases:
                for start, end in _find_spans(compacted, phrase):
                    bare.append((start, end, label))

        candidates: list[tuple[int, int, EmploymentType, bool]] = [
            (s, e, label, True) for s, e, label in qualified
        ] + [(s, e, label, False) for s, e, label in bare]

        suppressed: set[int] = set()
        unresolved_negation = False

        negation_positions = [i for i, token in enumerate(compacted) if token in _NEGATION_CUES]
        for neg_pos in negation_positions:
            # Direction/clause-aware binding: a negator overwhelmingly
            # negates what *follows* it ("not X") in English, not what
            # precedes it — so the forward tier is searched first, and a
            # backward candidate is only ever considered as a fallback
            # when no forward candidate exists within the window at all.
            # This prevents a closer *backward* candidate (often in an
            # entirely separate, comma-delimited clause) from stealing the
            # "nearest" slot from the actually-negated forward candidate —
            # see docs/LLM_HANDOFF.md's Iteration 2 review, finding 1.
            nearest_distance: int | None = None
            nearest_indices: list[int] = []
            for prefer_forward in (True, False):
                for idx, (start, end, _label, _qualified) in enumerate(candidates):
                    is_forward = neg_pos < start
                    if is_forward is not prefer_forward:
                        continue
                    distance = _distance(neg_pos, start, end)
                    if distance > _NEGATION_WINDOW:
                        continue
                    if nearest_distance is None or distance < nearest_distance:
                        nearest_distance = distance
                        nearest_indices = [idx]
                    elif distance == nearest_distance:
                        nearest_indices.append(idx)
                if nearest_indices:
                    break

            if not nearest_indices:
                if candidates:
                    unresolved_negation = True
                continue

            suppressed.update(nearest_indices)
            frontier = list(nearest_indices)
            while frontier:
                current = frontier.pop()
                c_start, c_end, _c_label, _c_q = candidates[current]
                for other_idx, (o_start, o_end, _o_label, _o_q) in enumerate(candidates):
                    if other_idx in suppressed:
                        continue
                    if _is_coordinated(c_start, c_end, o_start, o_end, compacted):
                        suppressed.add(other_idx)
                        frontier.append(other_idx)

        if unresolved_negation:
            continue

        for idx, (_start, _end, label, is_qualified) in enumerate(candidates):
            if idx in suppressed:
                continue
            if is_qualified:
                survivors.add(label)

    if not survivors:
        return None
    if len(survivors) == 1:
        return cast(EmploymentType, next(iter(survivors)))
    return _CONFLICT


def classify_employment_type(
    title: str | None,
    description: str | None,
) -> NormalizationResult[EmploymentType]:
    """Classifies a posting's employment-type schedule/commitment (full
    time / part time / seasonal / internship) from free text alone. Pure
    function — no I/O, no persistence, no `parser_version`. Never reads,
    writes, or reasons about `jobs.contract_type` or `jobs.shift`. See the
    module docstring for the full algorithm and the axis-boundary contract.
    """
    title_signal = _extract_title_signal(title)
    description_signal = _extract_description_signal(description)

    if title_signal == _CONFLICT or description_signal == _CONFLICT:
        return NormalizationResult(None, Provenance.UNAVAILABLE)
    if title_signal is None and description_signal is None:
        return NormalizationResult(None, Provenance.UNAVAILABLE)
    if title_signal is not None and description_signal is None:
        return NormalizationResult(cast(EmploymentType, title_signal), Provenance.INFERRED)
    if title_signal is None and description_signal is not None:
        return NormalizationResult(
            cast(EmploymentType, description_signal), Provenance.PARSED_DESCRIPTION
        )
    if title_signal == description_signal:
        return NormalizationResult(
            cast(EmploymentType, title_signal), Provenance.PARSED_DESCRIPTION
        )
    return NormalizationResult(None, Provenance.UNAVAILABLE)
