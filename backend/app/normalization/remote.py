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

**Pipeline (applied independently to `title` and `description`):**

1. NFKC-normalize, fold curly apostrophes (U+2018/U+2019) to the straight
   apostrophe, then case-fold. Zero-width/format characters (U+200B ZWSP,
   U+200C ZWNJ, U+200D ZWJ, U+FEFF BOM, ...) are never stripped and are
   never treated as a boundary — a token containing one can therefore never
   equal a clean catalog token, so a zero-width-obfuscated keyword fails to
   match rather than being silently repaired.
2. Split into sentences on `. ; : ! ?` (one or more, collapsed). All
   subsequent matching is scoped to one sentence at a time — this is what
   guarantees a multi-token phrase, a negation window, and a
   context-exclusion window can never cross a sentence boundary, without
   any separate punctuation-scanning logic.
3. Tokenize each sentence on whitespace and `,()[]{}"/&-` (en/em dash
   included) — a phrase may cross whitespace or a hyphen (both are
   ordinary token boundaries) but never a sentence-ending mark, since
   sentence-ending marks aren't present inside a sentence's own token
   list at all. The apostrophe is deliberately excluded from this
   boundary set, so a contraction survives as one token (`"isn't"`).
4. Catalog phrases (positive, exclusion, negation, context-exclusion) are
   compiled through this identical normalize+tokenize pipeline
   (`_compile_phrase`), never hand-written as separate regexes — so
   catalog and input text can never disagree on apostrophe/hyphen/
   whitespace handling.
5. **Exclusion-span masking**: every `_EXCLUSION_TOKEN_PHRASES` match
   (e.g. "remote sensing", "hybrid cloud") marks every token in its span as
   masked; masked tokens are invisible to every later step, including the
   standalone "remote"/"hybrid" phrase — this is what stops "remote
   sensing"'s embedded "remote", or "hybrid cloud"'s embedded "hybrid",
   from also registering as its own positive candidate. Exclusion phrases
   apply identically to both `title` and `description`.
6. Positive-candidate collection over the unmasked tokens.
7. **Context-exclusion suppression**: for each context cue, suppress every
   candidate within a 3-token same-sentence window. Two cue sets apply:
   a small universal set (benefit/tooling mentions — "stipend", "vpn",
   ... — checked in both fields) and a larger set checked only in
   `description` (generic collocates that mean the surrounding sentence is
   *not* describing this position's own arrangement — "team(s)",
   "system(s)", "device(s)", "interview", "meeting(s)" — e.g. "manage
   remote teams", "troubleshoot remote systems", "an in-person interview").
   `title` does not get this second, description-only set: a bare marker
   in a title (e.g. "Senior Backend Engineer (Remote)") already describes
   the position itself, by construction of what a job title is — the
   review's approved distinction between "title markers may remain
   narrowly supported with domain exclusions" (the universal exclusion
   phrases/cues, which do apply to titles) and "description matches must
   express an arrangement, not merely mention" a team/system/event (the
   description-only cues, which do not apply to titles).
8. **Negation suppression**: for each negation cue, find its *nearest*
   surviving candidate(s) within a 3-token same-sentence window (a tie
   suppresses both, never neither; a cue never suppresses every candidate
   in its window indiscriminately, only the nearest). Suppression then
   propagates transitively to any candidate directly coordinated with an
   already-suppressed one via exactly one "or"/"nor" token between their
   spans (never a bare comma-adjacent gap, which is plain juxtaposition,
   not coordination) — so "not remote or hybrid" cannot leave "hybrid"
   unnegated, while "not remote, onsite" still correctly leaves "onsite"
   untouched (comma-adjacency alone never coordinates).
9. **Unresolved-negation poisoning**: if a negation cue is present in a
   sentence that contains at least one candidate anywhere, but that cue's
   own nearest-candidate search finds nothing within its 3-token window
   (an "unresolved" negator — a negation clearly present in the sentence,
   just structurally out of the algorithm's reach), the *entire sentence's*
   candidates are discarded rather than left as an unsuppressed positive
   match. This is what makes "This is not, under any circumstances, a
   remote position" resolve to no signal instead of a confident "remote":
   the negator exists, but can't be proven to have successfully attached to
   anything, so nothing from that sentence is trusted.
10. Distinct surviving labels across all sentences of this one field: zero
    -> no signal; one -> that field's signal; two or more -> `"conflict"`.

**Cross-field precedence** (docs/DATA_MODEL.md's Provenance vocabulary):
a conflict anywhere (within a field or between fields) always yields
`(None, UNAVAILABLE)`; title-only evidence is `INFERRED`; description-only
evidence is `PARSED_DESCRIPTION`; title and description agreeing is
`PARSED_DESCRIPTION` (two independent free-text sources corroborating is
stronger than either alone); no evidence anywhere is
`(None, UNAVAILABLE)`. Absence of remote language never implies onsite —
onsite is only ever returned from a positive onsite-phrase match.

**Catalogs are exhaustive for this slice** — deliberately conservative,
listed in full below. A phrase not on these lists (e.g. "telecommute")
contributes no signal at all; adding one requires its own reviewed change,
not silent expansion here.

**Known, accepted limitation**: the negation window itself only reaches 3
tokens in either direction within the same sentence — but unlike an
earlier version of this module, a negator that exists just outside that
window is never silently ignored (see step 9 above): its sentence's
candidates are discarded, not left positive. The genuinely unhandled case
is different and narrower: two *separate*, unconnected negators and
candidates that both happen to sit in the same sentence purely by
coincidence (not a realistic job-posting construction this catalog is
tuned for) could still poison each other's sentence. This is an
intentionally narrow, fail-closed design (a simple, fully-specified,
easily-tested rule over a general negation-scope parser), not a special
case silently handled elsewhere.
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
    tokenize pipeline used on input text (point 4 of the approved
    proposal) — never a hand-maintained separate regex."""
    return tuple(_tokenize(_normalize_text(phrase)))


# Deliberately minimal/conservative — see the module docstring. Every
# surface variant not listed here (e.g. "telecommute") is unsupported and
# returns no signal until added in its own reviewed change.
_REMOTE_PHRASES = {"remote", "remotely", "work from home", "work from anywhere", "wfh"}
_HYBRID_PHRASES = {"hybrid"}
_ONSITE_PHRASES = {"onsite", "on site", "in office", "in person"}

_POSITIVE_TOKEN_PHRASES: dict[RemoteType, frozenset[tuple[str, ...]]] = {
    "remote": frozenset(_compile_phrase(p) for p in _REMOTE_PHRASES),
    "hybrid": frozenset(_compile_phrase(p) for p in _HYBRID_PHRASES),
    "onsite": frozenset(_compile_phrase(p) for p in _ONSITE_PHRASES),
}

# Domain-collision phrases — masked entirely, contributing no signal
# (positive or negative), in both title and description. "hybrid cloud" is
# a cloud-computing infrastructure term (a mix of on-prem and cloud
# infrastructure), not a work-arrangement claim — e.g. "Hybrid Cloud
# Engineer" as a job title, or "Build hybrid cloud infrastructure" in a
# description.
_EXCLUSION_PHRASES = {"remote sensing", "remote desktop", "remote location", "hybrid cloud"}
_EXCLUSION_TOKEN_PHRASES = frozenset(_compile_phrase(p) for p in _EXCLUSION_PHRASES)

# Benefit/tooling context cues — a nearby positive match is suppressed
# (e.g. "remote work stipend", "remote collaboration protocol"). Applies to
# both title and description. Kept deliberately narrow: generic words like
# "software"/"tool"/"equipment"/"access" were considered and rejected —
# each collides with ordinary job titles/descriptions having nothing to do
# with remote-work benefits (e.g. "Software Engineer (Remote)", "Equipment
# Operator", "Access Control Specialist"), which would silently suppress a
# genuine positive signal. Every cue kept here is unambiguous in this
# context.
_EXCLUSION_CONTEXT_CUES = frozenset(
    _compile_phrase(p)[0] for p in ("stipend", "collaboration", "vpn", "protocol", "allowance")
)

# Description-only context cues (never applied to title — see the module
# docstring's step 7): a nearby positive match is suppressed because the
# surrounding sentence is describing something *other than* this position's
# own arrangement — managing a remote team, troubleshooting remote
# equipment, or an in-person interview/meeting event, not a remote/hybrid/
# onsite role. Each pairs a singular and plural surface form deliberately
# (no stemming anywhere in this module).
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
    span — the distance to the span's nearest edge, 0 if the pivot were
    (impossibly, since cue and candidate token sets are disjoint) inside
    the span itself."""
    if pivot < start:
        return start - pivot
    if pivot > end:
        return pivot - end
    return 0


def _is_coordinated(a_start: int, a_end: int, b_start: int, b_end: int, tokens: list[str]) -> bool:
    """True only if the two spans are joined by exactly one coordinating
    conjunction token ("or"/"nor") and nothing else between them — never
    for a bare comma-adjacent gap (that's plain juxtaposition, already
    handled by the nearest-only negation rule, not coordination that should
    propagate a negation)."""
    if b_start > a_end:
        gap = tokens[a_end + 1 : b_start]
    elif a_start > b_end:
        gap = tokens[b_end + 1 : a_start]
    else:
        return False
    return len(gap) == 1 and gap[0] in _COORDINATING_CONJUNCTIONS


def _extract_signal(
    text: str | None, *, extra_context_cues: frozenset[str] = frozenset()
) -> RemoteType | Literal["conflict"] | None:
    """Returns this one field's local classification: a single label, the
    `"conflict"` sentinel when more than one distinct label survives
    anywhere in the field, or `None` when no signal survives at all.
    `extra_context_cues` is the description-only cue set (empty for
    title)."""
    if text is None or not text.strip():
        return None

    normalized = _normalize_text(text)
    context_cues = _EXCLUSION_CONTEXT_CUES | extra_context_cues
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
        for label, phrases in _POSITIVE_TOKEN_PHRASES.items():
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

            # Only the nearest candidate(s) to this cue are suppressed —
            # never every candidate in its window indiscriminately. A tie
            # suppresses both, failing closed rather than guessing.
            suppressed.update(nearest_indices)

            # Propagate transitively to any candidate directly coordinated
            # with an already-suppressed one, so "not remote or hybrid"
            # cannot leave "hybrid" unnegated.
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
            i for i, token in enumerate(tokens) if not masked[i] and token in context_cues
        ]
        for ctx_pos in context_positions:
            for idx, (start, end, _label) in enumerate(candidates):
                if _distance(ctx_pos, start, end) <= _CONTEXT_WINDOW:
                    suppressed.add(idx)

        if unresolved_negation:
            # A negation cue exists in this sentence, alongside at least
            # one candidate, but could not be proven to have attached to
            # anything within its window — discard the whole sentence's
            # contribution rather than leave an unsuppressed candidate
            # looking like a confident positive match.
            continue

        survivors.update(
            label for idx, (_start, _end, label) in enumerate(candidates) if idx not in suppressed
        )

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
    precedence rules."""
    title_signal = _extract_signal(title)
    description_signal = _extract_signal(
        description, extra_context_cues=_DESCRIPTION_ONLY_CONTEXT_CUES
    )

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
