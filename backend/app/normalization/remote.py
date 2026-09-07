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

`title` and `description` use two *different* positive catalogs, and two
different matching strategies, because a job title and free-text
description prose fail in different ways.

- **`title`** uses a **structural marker rule**
  (`_extract_title_signal`), not "does this word appear anywhere in the
  title". A bare marker (`"remote"`, `"hybrid"`, `"onsite"`, `"on site"`,
  `"in office"`, `"in person"`, `"remotely"`, `"wfh"`) counts as signal
  only when it structurally stands alone as one of:
  1. **the complete title** (after trimming and normalizing);
  2. **parenthesized or bracketed** — `"Software Engineer (Remote)"`,
     `"Facilities Coordinator (In Office)"`;
  3. **its own delimiter-separated segment** — the title is split on a
     comma, pipe, colon, or a hyphen/en-dash/em-dash surrounded by
     whitespace (never a hyphen glued inside a word, like "on-site"), and
     the marker must exactly fill one whole segment, e.g.
     `"Product Designer - Fully Remote"`'s second segment is `"Fully
     Remote"` (an explicit phrase, case 4 below), while `"Remote Systems
     Administrator"` is one single undelimited segment containing three
     words, so the bare word "remote" filling only part of it never
     qualifies.
  Separately, **explicit multi-word arrangement phrases**
  (`_TITLE_EXPLICIT_PHRASES`: `"fully remote"`, `"100% remote"`, `"work
  remotely"`, `"work from home"`, `"work from anywhere"`, `"wfh"`, `"work
  in the office"`) count as signal *anywhere* in the title, regardless of
  segment boundaries — they are inherently unambiguous 2-4 word phrases,
  not a single generic word a domain noun could be modifying. A leading
  `Remote`/`Hybrid` directly attached to an occupational or domain noun,
  with no delimiter, parenthetical, or explicit phrase around it (e.g.
  `"Remote Infrastructure Engineer"`, `"Hybrid Network Specialist"`), is
  therefore **never** sufficient — it fails every one of the four cases
  above. `title` has no negation support: the structural rule above is
  already conservative enough that no title in this catalog's scope needs
  it, and adding it would reopen the same "matches anywhere" risk this
  redesign closes. Exclusion phrases (below) still apply, as defense in
  depth, not as the primary mechanism.
- **`description`** matches only **arrangement-bearing phrases**
  (`_DESCRIPTION_POSITIVE_PHRASES`): each of `remote`/`hybrid`/`onsite`
  (`onsite` also as `"on site"`) combined with one of `role`, `position`,
  `job`, `work arrangement`, `schedule`, `attendance`, `attendance
  requirement`, plus the self-sufficient phrases `"work remotely"`,
  `"work from home"`, `"work from anywhere"`, `"wfh"`, `"work in the
  office"`. A **bare** `remote`/`hybrid`/`onsite`/`"in person"` token in
  description prose is *not* sufficient on its own. This positive catalog
  is the primary semantic gate; the exclusion phrases and context-
  exclusion cues remain in place too, as defense in depth, not as the
  mechanism that does this job.
- **The narrow, separator-exact comma-contrast exception**: a bare,
  non-arrangement-bearing description candidate is allowed to count as
  signal in exactly one structurally explicit case — the *raw characters*
  between it and a negation-suppressed candidate in the same sentence are
  nothing but one comma, optionally surrounded by whitespace (`", "`,
  `" ,"`, `","`, ...). This is checked against the *original substring*,
  not the token stream — `_tokenize_with_spans` preserves each token's
  character offsets specifically so `_is_comma_contrast` can look at what
  is actually between two candidates, rather than the token list alone,
  which cannot otherwise distinguish a comma from a hyphen, a slash, an
  em-dash, or plain whitespace (all of those are ordinary token
  boundaries that produce the same "no token in between" gap). This is
  what preserves `"Not remote, onsite." -> onsite` while correctly
  rejecting `"Not remote onsite."`, `"Not remote - onsite."`, `"Not
  remote / onsite."`, and `"Not remote — onsite."` — none of those are a
  comma, so none of them rescue the bare "onsite" candidate.

**Pipeline (`description`; `title` uses its own structural pass above):**

1. NFKC-normalize, fold curly apostrophes (U+2018/U+2019) to the straight
   apostrophe, then case-fold. Zero-width/format characters (U+200B ZWSP,
   U+200C ZWNJ, U+200D ZWJ, U+FEFF BOM, ...) are never stripped and are
   never treated as a boundary — a token containing one can therefore never
   equal a clean catalog token, so a zero-width-obfuscated keyword fails to
   match rather than being silently repaired.
2. Split into sentences on `. ; : ! ?` (one or more, collapsed). All
   subsequent matching is scoped to one sentence at a time.
3. Tokenize each sentence on whitespace and `,()[]{}"/&-` (en/em dash
   included), preserving each token's character span within the sentence
   — a phrase may cross whitespace or a hyphen but never a sentence-ending
   mark. The apostrophe is deliberately excluded from this boundary set,
   so a contraction survives as one token (`"isn't"`).
4. Catalog phrases (positive, exclusion, negation, context-exclusion) are
   compiled through this identical normalize+tokenize pipeline
   (`_compile_phrase`), never hand-written as separate regexes.
5. **Exclusion-span masking**: every `_EXCLUSION_TOKEN_PHRASES` match
   masks every token in its span from all later consideration.
6. Positive-candidate collection: arrangement-bearing phrases (qualified),
   plus the bare catalog collected *separately* only to feed negation and
   the comma-contrast rule — never counted as signal on its own.
7. **Context-exclusion suppression** (defense in depth, not the primary
   gate): a universal cue set ("stipend", "vpn", ...) plus a
   description-only set ("team(s)", "system(s)", "device(s)",
   "interview", "meeting(s)"). Each suppresses every candidate within a
   3-token same-sentence window.
8. **Negation suppression**: for each negation cue, find its *nearest*
   surviving candidate(s) within a 3-token same-sentence window (a tie
   suppresses both, never neither). Suppression propagates transitively to
   any candidate directly coordinated with an already-suppressed one via
   exactly one "or"/"nor" token between their spans.
9. **Unresolved-negation poisoning**: if a negation cue is present in a
   sentence containing at least one candidate, but that cue's own
   nearest-candidate search finds nothing within its window, the entire
   sentence's candidates are discarded rather than left positive.
10. Apply the separator-exact comma-contrast exception (above) to any
    surviving bare candidate; every other bare candidate is discarded
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
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal, cast

from app.normalization.types import NormalizationResult, Provenance

RemoteType = Literal["remote", "hybrid", "onsite"]

_CONFLICT: Literal["conflict"] = "conflict"

_SENTENCE_SPLIT_RE = re.compile(r"[.;:!?]+")
_TOKEN_RE = re.compile(r"[^\s,()\[\]{}\"/&\-–—]+")

_CURLY_APOSTROPHES = ("‘", "’")

_NEGATION_WINDOW = 3
_CONTEXT_WINDOW = 3

_COORDINATING_CONJUNCTIONS = frozenset({"or", "nor"})

# The exact separator-exact comma-contrast rule: the raw substring between
# two candidates must be nothing but one comma, optionally surrounded by
# whitespace — never a hyphen, slash, dash, or bare whitespace.
_EXACT_COMMA_GAP_RE = re.compile(r"\A\s*,\s*\Z")


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    for curly in _CURLY_APOSTROPHES:
        normalized = normalized.replace(curly, "'")
    return normalized.casefold()


def _tokenize_with_spans(sentence: str) -> list[tuple[str, int, int]]:
    """Every token in `sentence` as `(text, char_start, char_end)`, so a
    caller can inspect the *raw substring* between two tokens rather than
    only their token identities — needed to tell a comma apart from every
    other separator this tokenizer otherwise treats identically."""
    return [(m.group(), m.start(), m.end()) for m in _TOKEN_RE.finditer(sentence)]


def _tokenize(sentence: str) -> list[str]:
    return [token for token, _start, _end in _tokenize_with_spans(sentence)]


def _compile_phrase(phrase: str) -> tuple[str, ...]:
    """Tokenizes one catalog phrase through the identical normalize+
    tokenize pipeline used on input text — never a hand-maintained
    separate regex."""
    return tuple(_tokenize(_normalize_text(phrase)))


def _compile_all(phrases: set[str]) -> frozenset[tuple[str, ...]]:
    return frozenset(_compile_phrase(p) for p in phrases)


# ---------------------------------------------------------------------------
# Bare marker catalog. Used by `title`'s structural-segment check and
# collected (but never counted as signal on its own) in `description` to
# feed negation and the comma-contrast rule.
# ---------------------------------------------------------------------------
_BARE_REMOTE_PHRASES = {"remote", "remotely", "work from home", "work from anywhere", "wfh"}
_BARE_HYBRID_PHRASES = {"hybrid"}
_BARE_ONSITE_PHRASES = {"onsite", "on site", "in office", "in person"}

_BARE_TOKEN_PHRASES: dict[RemoteType, frozenset[tuple[str, ...]]] = {
    "remote": _compile_all(_BARE_REMOTE_PHRASES),
    "hybrid": _compile_all(_BARE_HYBRID_PHRASES),
    "onsite": _compile_all(_BARE_ONSITE_PHRASES),
}

# Explicit multi-word arrangement phrases recognized anywhere in a title,
# regardless of segment boundaries — inherently unambiguous, unlike a bare
# single word a domain/occupational noun could be modifying.
_TITLE_EXPLICIT_REMOTE_PHRASES = {
    "fully remote",
    "100% remote",
    "work remotely",
    "work from home",
    "work from anywhere",
    "wfh",
}
_TITLE_EXPLICIT_ONSITE_PHRASES = {"work in the office"}

_TITLE_EXPLICIT_PHRASES: dict[RemoteType, frozenset[tuple[str, ...]]] = {
    "remote": _compile_all(_TITLE_EXPLICIT_REMOTE_PHRASES),
    "hybrid": frozenset(),
    "onsite": _compile_all(_TITLE_EXPLICIT_ONSITE_PHRASES),
}

# Delimiters that split a title into structurally distinct segments: a
# comma/pipe/colon anywhere, or a hyphen/en-dash/em-dash *surrounded by
# whitespace* (never one glued inside a word, like "on-site" or "100%-
# remote", which must stay a single token).
_TITLE_SEGMENT_DELIMITER_RE = re.compile(r"\s[-–—]\s|[,|:]")
_PAREN_BRACKET_RE = re.compile(r"[(\[]([^()\[\]]*)[)\]]")

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
# negative signal), in both title and description, as defense in depth on
# top of title's structural-segment rule and description's positive
# catalog (neither of which strictly needs these to close the reproduced
# false positives, since e.g. "remote systems administrator" already fails
# title's segment-exactness check on its own).
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


def _mask_exclusions(tokens: list[str]) -> list[bool]:
    masked = [False] * len(tokens)
    for exclusion_phrase in _EXCLUSION_TOKEN_PHRASES:
        for start, end in _find_spans(tokens, exclusion_phrase, masked):
            for i in range(start, end + 1):
                masked[i] = True
    return masked


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


def _is_comma_contrast(
    idx: int,
    candidates: list[tuple[int, int, RemoteType, bool]],
    negation_suppressed: set[int],
    token_spans: list[tuple[str, int, int]],
    sentence: str,
) -> bool:
    """True if candidate `idx` is separated from some *other* candidate
    that negation suppressed in this sentence by nothing but a comma
    (optionally surrounded by whitespace) in the *original substring* —
    never a hyphen, slash, dash, or bare whitespace, all of which this
    tokenizer otherwise discards identically. The only circumstance in
    which a bare, non-arrangement-bearing description candidate is ever
    allowed to count as signal."""
    start, end, _label, _qualified = candidates[idx]
    for other_idx in negation_suppressed:
        if other_idx == idx:
            continue
        o_start, o_end, _o_label, _o_qualified = candidates[other_idx]
        if o_start > end:
            raw_gap = sentence[token_spans[end][2] : token_spans[o_start][1]]
        elif start > o_end:
            raw_gap = sentence[token_spans[o_end][2] : token_spans[start][1]]
        else:
            continue
        if _EXACT_COMMA_GAP_RE.match(raw_gap):
            return True
    return False


def _title_segments(text: str) -> list[str]:
    """Every structurally distinct segment of a title: each parenthesized
    or bracketed group's inner content, plus each delimiter-separated
    segment of the remaining text (with those groups removed first). With
    no parentheses/brackets/delimiters at all, this returns exactly one
    segment — the complete title."""
    segments = [match.group(1) for match in _PAREN_BRACKET_RE.finditer(text)]
    remainder = _PAREN_BRACKET_RE.sub(" ", text)
    segments.extend(_TITLE_SEGMENT_DELIMITER_RE.split(remainder))
    return segments


def _extract_title_signal(text: str | None) -> RemoteType | Literal["conflict"] | None:
    """`title` uses a structural marker rule, not "matches anywhere": see
    the module docstring for the four accepted structural cases. No
    negation support — the structural rule is conservative enough not to
    need it, and adding it would reopen a "matches anywhere" risk."""
    if text is None or not text.strip():
        return None

    normalized = _normalize_text(text)
    survivors: set[str] = set()

    # Explicit multi-word arrangement phrases count anywhere in the title.
    whole_tokens = _tokenize(normalized)
    whole_masked = _mask_exclusions(whole_tokens)
    for label, phrases in _TITLE_EXPLICIT_PHRASES.items():
        for phrase in phrases:
            if _find_spans(whole_tokens, phrase, whole_masked):
                survivors.add(label)

    # A bare marker counts only when it exactly fills one whole structural
    # segment (the complete title, a parenthetical/bracketed group, or a
    # delimiter-separated segment) — never as one word within a longer,
    # undelimited phrase.
    for segment in _title_segments(normalized):
        segment_tokens = _tokenize(segment)
        if not segment_tokens:
            continue
        segment_masked = _mask_exclusions(segment_tokens)
        unmasked_tokens = tuple(
            token
            for token, masked in zip(segment_tokens, segment_masked, strict=True)
            if not masked
        )
        if not unmasked_tokens:
            continue
        for label, phrases in _BARE_TOKEN_PHRASES.items():
            if unmasked_tokens in phrases:
                survivors.add(label)

    if not survivors:
        return None
    if len(survivors) == 1:
        return cast(RemoteType, next(iter(survivors)))
    return _CONFLICT


def _extract_description_signal(text: str | None) -> RemoteType | Literal["conflict"] | None:
    """`description`'s positive catalog is arrangement-bearing phrases only.
    Bare markers are still collected (so negation has something to attach
    to), but they count as signal only via the narrow, separator-exact
    comma-contrast rule — never on their own."""
    if text is None or not text.strip():
        return None

    normalized = _normalize_text(text)
    survivors: set[str] = set()
    context_cues = _EXCLUSION_CONTEXT_CUES | _DESCRIPTION_ONLY_CONTEXT_CUES

    for sentence in _SENTENCE_SPLIT_RE.split(normalized):
        token_spans = _tokenize_with_spans(sentence)
        tokens = [token for token, _start, _end in token_spans]
        if not tokens:
            continue

        masked = _mask_exclusions(tokens)

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
            if is_qualified or _is_comma_contrast(
                idx, candidates, negation_suppressed, token_spans, sentence
            ):
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
