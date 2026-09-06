"""Deterministic remote/hybrid/onsite classifier (Phase 3 — first parser
slice; docs/ARCHITECTURE.md §4's `normalization/remote.py`,
docs/PHASE_RISK_CHECKLIST.md's Phase 3 exit gate).

Pure function: `title`/`description` free text in, one
`NormalizationResult` out. No database, ORM, provider, network, or
ingestion-pipeline dependency — `test_normalization_remote.py`'s
`test_import_boundary_allow_list` proves this by AST inspection against an
exact, fail-closed permitted-import allow-list (not a deny-list). Writing
the result into `jobs.remote_type`/`jobs.field_provenance` and threading
`parser_version` are both Phase 4+ ingestion-layer concerns, out of scope
here.

**Field-specific positive-evidence contract (the actual current design):**

`title` and `description` use two *different* positive catalogs, because a
job title is inherently a claim about the position itself, while free-text
description prose routinely mentions "remote"/"hybrid"/"in person" about
something *other than* this job's own arrangement (a managed team, a piece
of equipment, a one-time event) — the exact failure mode two prior review
rounds found.

- **`title`** matches the bare marker catalog (`_BARE_TOKEN_PHRASES`):
  `"remote"`, `"remotely"`, `"work from home"`, `"work from anywhere"`,
  `"wfh"`, `"hybrid"`, `"onsite"`, `"on site"`, `"in office"`, `"in
  person"`. A bare marker in a title (e.g. "Senior Backend Engineer
  (Remote)") already describes the position, by construction of what a
  job title is. A small set of domain/subject exclusion phrases (below)
  catches the ambiguous cases where a title's generic noun, not the
  position's arrangement, is what "remote"/"hybrid" is modifying (e.g.
  "Remote Systems Administrator", "Remote Team Manager").
- **`description`** matches only **arrangement-bearing phrases**
  (`_DESCRIPTION_POSITIVE_PHRASES`): each of `remote`/`hybrid`/`onsite`
  (`onsite` also as `"on site"`) combined with one of `role`, `position`,
  `job`, `work arrangement`, `schedule`, `attendance`, `attendance
  requirement` (e.g. "remote role", "hybrid position", "onsite
  attendance", "onsite attendance requirement"),
  plus the self-sufficient phrases `"work remotely"`, `"work from home"`,
  `"work from anywhere"`, `"wfh"`, and `"work in the office"`. A **bare**
  `remote`/`hybrid`/`onsite`/`"in person"` token in description prose is
  *not* sufficient on its own — "Serve remote customers across several
  regions" or "Design and operate hybrid databases" must not read as a
  work-arrangement fact merely because the word appears. This positive
  catalog is the primary semantic gate; the exclusion phrases and
  context-exclusion cues below remain in place too, as defense in depth,
  not as the mechanism that does this job.
- **The narrow comma-contrast exception**: a bare, non-arrangement-bearing
  description candidate is allowed to count as signal in exactly one
  structurally explicit case — it sits immediately after (separated only
  by a comma, i.e. a zero-token gap) another candidate that a negation cue
  suppressed in the same sentence. This is what preserves `"Not remote,
  onsite."` -> `onsite`: "onsite" is bare and would otherwise not qualify,
  but it directly contrasts with the negated "remote" right before it.
  This is a narrow, explicitly tested exception, not a general allowance
  for bare description tokens — see `_is_comma_contrast`.

**Pipeline (applied independently to `title` and `description`, each using
its own catalog above):**

1. NFKC-normalize, fold curly apostrophes (U+2018/U+2019) to the straight
   apostrophe, then case-fold. Zero-width/format characters (U+200B ZWSP,
   U+200C ZWNJ, U+200D ZWJ, U+FEFF BOM, ...) are never stripped and are
   never treated as a boundary — a token containing one can therefore never
   equal a clean catalog token, so a zero-width-obfuscated keyword fails to
   match rather than being silently repaired.
2. Split into sentences on `. ; : ! ?` (one or more, collapsed). All
   subsequent matching is scoped to one sentence at a time.
3. Tokenize each sentence on whitespace and `,()[]{}"/&-` (en/em dash
   included) — a phrase may cross whitespace or a hyphen but never a
   sentence-ending mark. The apostrophe is deliberately excluded from this
   boundary set, so a contraction survives as one token (`"isn't"`).
4. Catalog phrases (positive, exclusion, negation, context-exclusion) are
   compiled through this identical normalize+tokenize pipeline
   (`_compile_phrase`), never hand-written as separate regexes.
5. **Exclusion-span masking**: every `_EXCLUSION_TOKEN_PHRASES` match
   (e.g. "remote sensing", "hybrid cloud", "remote systems", "remote
   team") masks every token in its span from all later consideration.
   Applies identically to `title` and `description`.
6. Positive-candidate collection using the field's own catalog (title:
   bare markers; description: arrangement-bearing phrases, plus the bare
   catalog collected *separately* only to feed negation/the comma-contrast
   rule below — never counted as signal on its own).
7. **Context-exclusion suppression** (defense in depth, not the primary
   gate): a universal cue set ("stipend", "vpn", ...) applies to both
   fields; a larger set ("team(s)", "system(s)", "device(s)", "interview",
   "meeting(s)") applies only in `description`. Each suppresses every
   candidate within a 3-token same-sentence window.
8. **Negation suppression**: for each negation cue, find its *nearest*
   surviving candidate(s) within a 3-token same-sentence window (a tie
   suppresses both, never neither). Suppression propagates transitively to
   any candidate directly coordinated with an already-suppressed one via
   exactly one "or"/"nor" token between their spans (never a bare
   comma-adjacent gap, which is contrast, not coordination — see above).
9. **Unresolved-negation poisoning**: if a negation cue is present in a
   sentence containing at least one candidate, but that cue's own
   nearest-candidate search finds nothing within its window, the entire
   sentence's candidates are discarded rather than left positive.
10. In `description` only: apply the comma-contrast exception (above) to
    any surviving bare candidate; every other bare candidate is discarded
    (contributes nothing) unless it was an arrangement-bearing match.
11. Distinct surviving labels across all sentences of this one field: zero
    -> no signal; one -> that field's signal; two or more -> `"conflict"`.

**Cross-field precedence** (docs/DATA_MODEL.md's Provenance vocabulary):
a conflict anywhere (within a field or between fields) always yields
`(None, UNAVAILABLE)`; title-only evidence is `INFERRED`; description-only
evidence is `PARSED_DESCRIPTION`; title and description agreeing is
`PARSED_DESCRIPTION`; no evidence anywhere is `(None, UNAVAILABLE)`.
Absence of remote language never implies onsite.

**Catalogs are exhaustive for this slice** — deliberately conservative,
listed in full above and below. A phrase not on these lists (e.g.
"telecommute") contributes no signal at all; adding one requires its own
reviewed change, not silent expansion here.

**Known, accepted limitation**: the negation window only reaches 3 tokens
in either direction within the same sentence; an unresolved negator still
poisons its whole sentence (step 9), so this is not silently ignored. The
narrower unhandled case is two separate, unconnected negators/candidates
coincidentally sharing one sentence, which could still cross-poison each
other — an intentionally narrow, fail-closed design over a general
negation-scope parser.

**Known, accepted limitation — `title` still uses an enumerated exclusion
list, not a positive catalog.** Unlike `description`, `title` was not
redesigned around a positive-evidence requirement (the review's own
guidance sanctions "title markers may remain narrowly supported with
domain exclusions"). Adversarial testing beyond the two reproduced titles
found this genuinely does not generalize: `"Remote Infrastructure
Engineer"`, `"Remote Client Success Manager"`, and `"Hybrid Network
Specialist"` all still return a confident positive today, for the same
underlying reason `description` needed a full redesign rather than a
larger deny-list — a job title's generic noun can be modified by
`remote`/`hybrid` in ways this bounded exclusion list cannot exhaustively
anticipate. Documented here rather than silently left implicit; closing it
fully (mirroring `description`'s positive-catalog approach, or another
mechanism) is out of scope for this correction and would need its own
reviewed change.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal, cast

from app.normalization.types import NormalizationResult, Provenance

RemoteType = Literal["remote", "hybrid", "onsite"]

_CONFLICT: Literal["conflict"] = "conflict"

_SENTENCE_SPLIT_RE = re.compile(r"[.;:!?]+")
_TOKEN_SPLIT_RE = re.compile(r"[\s,()\[\]{}\"/&\-–—]+")

_CURLY_APOSTROPHES = ("‘", "’")

_NEGATION_WINDOW = 3
_CONTEXT_WINDOW = 3

_COORDINATING_CONJUNCTIONS = frozenset({"or", "nor"})


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    for curly in _CURLY_APOSTROPHES:
        normalized = normalized.replace(curly, "'")
    return normalized.casefold()


def _tokenize(sentence: str) -> list[str]:
    return [token for token in _TOKEN_SPLIT_RE.split(sentence) if token]


def _compile_phrase(phrase: str) -> tuple[str, ...]:
    """Tokenizes one catalog phrase through the identical normalize+
    tokenize pipeline used on input text — never a hand-maintained
    separate regex."""
    return tuple(_tokenize(_normalize_text(phrase)))


def _compile_all(phrases: set[str]) -> frozenset[tuple[str, ...]]:
    return frozenset(_compile_phrase(p) for p in phrases)


# ---------------------------------------------------------------------------
# Bare marker catalog — used directly as `title`'s positive catalog, and
# collected (but never counted as signal on its own) in `description` to
# feed negation and the narrow comma-contrast rule.
# ---------------------------------------------------------------------------
_BARE_REMOTE_PHRASES = {"remote", "remotely", "work from home", "work from anywhere", "wfh"}
_BARE_HYBRID_PHRASES = {"hybrid"}
_BARE_ONSITE_PHRASES = {"onsite", "on site", "in office", "in person"}

_BARE_TOKEN_PHRASES: dict[RemoteType, frozenset[tuple[str, ...]]] = {
    "remote": _compile_all(_BARE_REMOTE_PHRASES),
    "hybrid": _compile_all(_BARE_HYBRID_PHRASES),
    "onsite": _compile_all(_BARE_ONSITE_PHRASES),
}

# ---------------------------------------------------------------------------
# Description's positive catalog — arrangement-bearing phrases only. Built
# from an explicit prefix set per label and an explicit noun set, so every
# generated phrase is a deliberate, reviewable combination, not a bare word.
# ---------------------------------------------------------------------------
_ARRANGEMENT_PREFIXES: dict[RemoteType, frozenset[str]] = {
    "remote": frozenset({"remote"}),
    "hybrid": frozenset({"hybrid"}),
    "onsite": frozenset({"onsite", "on site"}),
}
_ARRANGEMENT_NOUNS = frozenset(
    {
        "role",
        "position",
        "job",
        "work arrangement",
        "schedule",
        "attendance",
        "attendance requirement",
    }
)
_SELF_SUFFICIENT_DESCRIPTION_PHRASES: dict[RemoteType, frozenset[str]] = {
    "remote": frozenset({"work remotely", "work from home", "work from anywhere", "wfh"}),
    "hybrid": frozenset(),
    "onsite": frozenset({"work in the office"}),
}


def _build_description_positive_phrases() -> dict[RemoteType, frozenset[tuple[str, ...]]]:
    result: dict[RemoteType, frozenset[tuple[str, ...]]] = {}
    for label in ("remote", "hybrid", "onsite"):
        label_key = cast(RemoteType, label)
        combined = {
            f"{prefix} {noun}"
            for prefix in _ARRANGEMENT_PREFIXES[label_key]
            for noun in _ARRANGEMENT_NOUNS
        }
        combined |= _SELF_SUFFICIENT_DESCRIPTION_PHRASES[label_key]
        result[label_key] = _compile_all(combined)
    return result


_DESCRIPTION_POSITIVE_PHRASES = _build_description_positive_phrases()

# ---------------------------------------------------------------------------
# Exclusion phrases — domain-collision terms masked entirely (positive or
# negative signal), in both title and description. "remote systems"/"remote
# team" cover ambiguous subject/domain titles ("Remote Systems
# Administrator", "Remote Team Manager") without touching an explicit
# marker like "Software Engineer (Remote)".
# ---------------------------------------------------------------------------
_EXCLUSION_PHRASES = {
    "remote sensing",
    "remote desktop",
    "remote location",
    "hybrid cloud",
    "remote systems",
    "remote team",
}
_EXCLUSION_TOKEN_PHRASES = _compile_all(_EXCLUSION_PHRASES)

# Universal context-exclusion cues (defense in depth, both fields).
_EXCLUSION_CONTEXT_CUES = frozenset(
    _compile_phrase(p)[0] for p in ("stipend", "collaboration", "vpn", "protocol", "allowance")
)

# Description-only context-exclusion cues (defense in depth, description
# only — never applied to title).
_DESCRIPTION_ONLY_CONTEXT_CUES = frozenset(
    _compile_phrase(p)[0]
    for p in (
        "team",
        "teams",
        "system",
        "systems",
        "device",
        "devices",
        "interview",
        "meeting",
        "meetings",
    )
)

_NEGATION_CUES = frozenset(
    _compile_phrase(p)[0] for p in ("not", "no", "isn't", "aren't", "without", "unavailable")
)


def _find_spans(
    tokens: list[str], phrase: tuple[str, ...], masked: list[bool]
) -> list[tuple[int, int]]:
    """Every contiguous (start, end-inclusive) span in `tokens` matching
    `phrase` exactly, skipping any span overlapping a masked token."""
    spans: list[tuple[int, int]] = []
    phrase_len = len(phrase)
    for start in range(len(tokens) - phrase_len + 1):
        end = start + phrase_len - 1
        if any(masked[i] for i in range(start, end + 1)):
            continue
        if tuple(tokens[start : end + 1]) == phrase:
            spans.append((start, end))
    return spans


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
    conjunction token ("or"/"nor") and nothing else between them — never
    for a bare comma-adjacent gap, which is contrast (see
    `_is_comma_contrast`), not coordination."""
    if b_start > a_end:
        gap = tokens[a_end + 1 : b_start]
    elif a_start > b_end:
        gap = tokens[b_end + 1 : a_start]
    else:
        return False
    return len(gap) == 1 and gap[0] in _COORDINATING_CONJUNCTIONS


def _gap_between(
    a_start: int, a_end: int, b_start: int, b_end: int, tokens: list[str]
) -> list[str] | None:
    """The tokens strictly between the two spans, in whichever order they
    appear; `None` if the spans are not disjoint (should not happen for
    candidates drawn from disjoint catalogs, but defensive nonetheless)."""
    if b_start > a_end:
        return tokens[a_end + 1 : b_start]
    if a_start > b_end:
        return tokens[b_end + 1 : a_start]
    return None


def _is_comma_contrast(
    idx: int,
    candidates: list[tuple[int, int, RemoteType, bool]],
    negation_suppressed: set[int],
    tokens: list[str],
) -> bool:
    """True if candidate `idx` sits immediately adjacent (a zero-token gap
    — separated only by a comma, since a comma produces no token of its
    own) to some *other* candidate that was suppressed specifically by
    negation (never by a context-exclusion cue) — the narrow "not X, Y"
    contrastive construction this module explicitly supports, and the only
    circumstance in which a bare, non-arrangement-bearing description
    candidate is ever allowed to count as signal."""
    start, end, _label, _qualified = candidates[idx]
    for other_idx in negation_suppressed:
        if other_idx == idx:
            continue
        o_start, o_end, _o_label, _o_qualified = candidates[other_idx]
        gap = _gap_between(start, end, o_start, o_end, tokens)
        if gap is not None and len(gap) == 0:
            return True
    return False


def _extract_title_signal(text: str | None) -> RemoteType | Literal["conflict"] | None:
    """`title`'s positive catalog is the bare marker set — a bare marker in
    a title already describes the position, by construction of what a job
    title is. Only exclusion phrases and universal context cues apply."""
    if text is None or not text.strip():
        return None

    normalized = _normalize_text(text)
    survivors: set[str] = set()

    for sentence in _SENTENCE_SPLIT_RE.split(normalized):
        tokens = _tokenize(sentence)
        if not tokens:
            continue

        masked = [False] * len(tokens)
        for exclusion_phrase in _EXCLUSION_TOKEN_PHRASES:
            for start, end in _find_spans(tokens, exclusion_phrase, masked):
                for i in range(start, end + 1):
                    masked[i] = True

        candidates: list[tuple[int, int, RemoteType]] = []
        for label, phrases in _BARE_TOKEN_PHRASES.items():
            for phrase in phrases:
                for start, end in _find_spans(tokens, phrase, masked):
                    candidates.append((start, end, label))

        suppressed: set[int] = set()
        unresolved_negation = False

        negation_positions = [
            i for i, token in enumerate(tokens) if not masked[i] and token in _NEGATION_CUES
        ]
        for neg_pos in negation_positions:
            nearest_distance: int | None = None
            nearest_indices: list[int] = []
            for idx, (start, end, _label) in enumerate(candidates):
                distance = _distance(neg_pos, start, end)
                if distance > _NEGATION_WINDOW:
                    continue
                if nearest_distance is None or distance < nearest_distance:
                    nearest_distance = distance
                    nearest_indices = [idx]
                elif distance == nearest_distance:
                    nearest_indices.append(idx)

            if not nearest_indices:
                if candidates:
                    unresolved_negation = True
                continue

            suppressed.update(nearest_indices)
            frontier = list(nearest_indices)
            while frontier:
                current = frontier.pop()
                c_start, c_end, _c_label = candidates[current]
                for other_idx, (o_start, o_end, _o_label) in enumerate(candidates):
                    if other_idx in suppressed:
                        continue
                    if _is_coordinated(c_start, c_end, o_start, o_end, tokens):
                        suppressed.add(other_idx)
                        frontier.append(other_idx)

        context_positions = [
            i
            for i, token in enumerate(tokens)
            if not masked[i] and token in _EXCLUSION_CONTEXT_CUES
        ]
        for ctx_pos in context_positions:
            for idx, (start, end, _label) in enumerate(candidates):
                if _distance(ctx_pos, start, end) <= _CONTEXT_WINDOW:
                    suppressed.add(idx)

        if unresolved_negation:
            continue

        survivors.update(
            label for idx, (_start, _end, label) in enumerate(candidates) if idx not in suppressed
        )

    if not survivors:
        return None
    if len(survivors) == 1:
        return cast(RemoteType, next(iter(survivors)))
    return _CONFLICT


def _extract_description_signal(text: str | None) -> RemoteType | Literal["conflict"] | None:
    """`description`'s positive catalog is arrangement-bearing phrases only.
    Bare markers are still collected (so negation has something to attach
    to), but they count as signal only via the narrow comma-contrast rule
    — never on their own."""
    if text is None or not text.strip():
        return None

    normalized = _normalize_text(text)
    survivors: set[str] = set()
    context_cues = _EXCLUSION_CONTEXT_CUES | _DESCRIPTION_ONLY_CONTEXT_CUES

    for sentence in _SENTENCE_SPLIT_RE.split(normalized):
        tokens = _tokenize(sentence)
        if not tokens:
            continue

        masked = [False] * len(tokens)
        for exclusion_phrase in _EXCLUSION_TOKEN_PHRASES:
            for start, end in _find_spans(tokens, exclusion_phrase, masked):
                for i in range(start, end + 1):
                    masked[i] = True

        qualified: list[tuple[int, int, RemoteType]] = []
        for label, phrases in _DESCRIPTION_POSITIVE_PHRASES.items():
            for phrase in phrases:
                for start, end in _find_spans(tokens, phrase, masked):
                    qualified.append((start, end, label))

        bare: list[tuple[int, int, RemoteType]] = []
        for label, phrases in _BARE_TOKEN_PHRASES.items():
            for phrase in phrases:
                for start, end in _find_spans(tokens, phrase, masked):
                    bare.append((start, end, label))

        candidates: list[tuple[int, int, RemoteType, bool]] = [
            (s, e, label, True) for s, e, label in qualified
        ] + [(s, e, label, False) for s, e, label in bare]

        suppressed: set[int] = set()
        negation_suppressed: set[int] = set()
        unresolved_negation = False

        negation_positions = [
            i for i, token in enumerate(tokens) if not masked[i] and token in _NEGATION_CUES
        ]
        for neg_pos in negation_positions:
            nearest_distance: int | None = None
            nearest_indices: list[int] = []
            for idx, (start, end, _label, _qualified) in enumerate(candidates):
                distance = _distance(neg_pos, start, end)
                if distance > _NEGATION_WINDOW:
                    continue
                if nearest_distance is None or distance < nearest_distance:
                    nearest_distance = distance
                    nearest_indices = [idx]
                elif distance == nearest_distance:
                    nearest_indices.append(idx)

            if not nearest_indices:
                if candidates:
                    unresolved_negation = True
                continue

            suppressed.update(nearest_indices)
            negation_suppressed.update(nearest_indices)
            frontier = list(nearest_indices)
            while frontier:
                current = frontier.pop()
                c_start, c_end, _c_label, _c_q = candidates[current]
                for other_idx, (o_start, o_end, _o_label, _o_q) in enumerate(candidates):
                    if other_idx in suppressed:
                        continue
                    if _is_coordinated(c_start, c_end, o_start, o_end, tokens):
                        suppressed.add(other_idx)
                        negation_suppressed.add(other_idx)
                        frontier.append(other_idx)

        context_positions = [
            i for i, token in enumerate(tokens) if not masked[i] and token in context_cues
        ]
        for ctx_pos in context_positions:
            for idx, (start, end, _label, _qualified) in enumerate(candidates):
                if _distance(ctx_pos, start, end) <= _CONTEXT_WINDOW:
                    suppressed.add(idx)

        if unresolved_negation:
            continue

        for idx, (_start, _end, label, is_qualified) in enumerate(candidates):
            if idx in suppressed:
                continue
            # A bare, unqualified candidate with no comma-contrast rescue
            # contributes nothing — this is the actual semantic gate.
            if is_qualified or _is_comma_contrast(idx, candidates, negation_suppressed, tokens):
                survivors.add(label)

    if not survivors:
        return None
    if len(survivors) == 1:
        return cast(RemoteType, next(iter(survivors)))
    return _CONFLICT


def classify_remote_type(
    title: str | None,
    description: str | None,
) -> NormalizationResult[RemoteType]:
    """Classifies a posting's remote/hybrid/onsite work arrangement from
    free text alone. Pure function — no I/O, no persistence, no
    `parser_version`. See the module docstring for the full algorithm and
    the field-specific positive-evidence contract."""
    title_signal = _extract_title_signal(title)
    description_signal = _extract_description_signal(description)

    if title_signal == _CONFLICT or description_signal == _CONFLICT:
        return NormalizationResult(None, Provenance.UNAVAILABLE)
    if title_signal is None and description_signal is None:
        return NormalizationResult(None, Provenance.UNAVAILABLE)
    if title_signal is not None and description_signal is None:
        return NormalizationResult(cast(RemoteType, title_signal), Provenance.INFERRED)
    if title_signal is None and description_signal is not None:
        return NormalizationResult(
            cast(RemoteType, description_signal), Provenance.PARSED_DESCRIPTION
        )
    if title_signal == description_signal:
        return NormalizationResult(cast(RemoteType, title_signal), Provenance.PARSED_DESCRIPTION)
    return NormalizationResult(None, Provenance.UNAVAILABLE)
