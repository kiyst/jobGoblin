"""Deterministic HTML-to-plain-text conversion for the realistic Phase 3
evaluation corpus (Class H realistic-corpus evaluation slice).

Pure function, no I/O, no network. Converts a Greenhouse job posting's
`content` field (HTML) into plain text suitable for feeding directly into
the seven merged Phase 3 classifiers, so the evaluation corpus exercises
the same character-level realism (entity decoding, block-boundary
whitespace, stray Unicode format characters) that real HTML-authored
descriptions actually contain.

**Input-mode contract.** `convert_html_to_text` never inspects its input
to guess an encoding shape -- the caller always explicitly selects one of
exactly two modes:

- `"standard"` (default): today's behavior, byte-for-behavior unchanged.
  No outer decode, no residual validation of any kind, at any stage --
  including inert tag-looking text produced by an intentional
  escaped-code example (e.g. `<p>Use &lt;script&gt; as text</p>` ->
  `"Use <script> as text"`, unchanged and never flagged).
- `"declared-double-escaped"`: the caller has separately determined
  (never inferred by this module) that the whole input is HTML-escaped
  once more than standard HTML -- exactly one additional
  `html.unescape()` pass is permitted before ordinary conversion.

**Processing stages, in order, for `"declared-double-escaped"` mode**
(stages 1 and 3 share one fixed pair of regex constants,
`_ESCAPED_ANGLE_REFERENCE_RE` and `_UNTERMINATED_NAMED_ANGLE_RE`; none of
this applies under `"standard"` mode, which has no stage 1/3 checks at
all):

1. Raw input validation: reject (`HtmlDoubleEncodingError`,
   `"mixed-literal-and-escaped-markup"`) if the raw input contains a
   literal `<`/`>` character *and* an escaped-angle-reference-shaped
   substring simultaneously -- never guessed at; also reject
   (`"unsupported-angle-reference"`) if a semicolonless named
   `&lt`/`&gt`/`&LT`/`&GT` form is present anywhere -- exactly the four
   spellings `html.unescape()` itself decodes to `<`/`>` (confirmed
   empirically; the mixed-case `&Lt`/`&Gt` are separate, unrelated named
   references and are never treated as angle references at all) -- since
   its interaction with `html.unescape()`'s own legacy matching against a
   longer entity name sharing the same prefix (e.g. `&ltimes;`, a real,
   distinct, unrelated named reference) is not trusted to be safe --
   every such form is rejected regardless of what follows it.
2. Exactly one `html.unescape()` call -- the stdlib's own well-defined
   semantics for named, decimal, and hexadecimal character references,
   including its legacy semicolon-optional behavior. No hand-rolled
   decoding logic.
3. Validation of the decoded HTML: the same two checks as stage 1,
   applied to the stage-2 output -- a decoded document containing a
   semicolonless named form is `"unsupported-angle-reference"`; one
   still containing a fully-terminated escaped-angle-reference-shaped
   substring is `"residual-nested-encoding"` (more than one extra layer
   of encoding was actually present).
4. Existing HTML-to-text conversion (unchanged in either mode).
5. No further validation; never a re-parse.

**Accepted limitation**: stage 3's residual check cannot distinguish a
genuine unresolved second encoding layer from a legitimate escaped-code
example that happens to still contain an escaped-angle-reference-shaped
substring after exactly one correct decode -- the two are structurally
identical. For example, `"declared-double-escaped"` input
`&lt;p&gt;Use &amp;lt;script&amp;gt; as text&lt;/p&gt;` decodes at stage 2
to the perfectly legitimate `<p>Use &lt;script&gt; as text</p>` (exactly
the intentional-escaped-code-example document from the `"standard"`-mode
example above), but stage 3 still rejects it as
`"residual-nested-encoding"`, since it cannot tell this case apart from a
genuine unresolved second layer. This is an accepted limitation of
`"declared-double-escaped"` mode only -- never applied to `"standard"`
mode, where the identical content decodes and displays correctly with no
rejection at all. A caller whose content is known to contain such
examples, and is not actually double-encoded, must declare `"standard"`.

**Covered whitespace is exactly `" \\t\\n\\r"`** (space, tab, LF, CR) --
the same class already used by `app/normalization/taxonomy.py` and
`app/normalization/skills.py`, declared independently here per this
project's own-implementation convention.

**Algorithm:**

1. Normalize line endings in the *raw* HTML before parsing: `"\\r\\n"` and
   bare `"\\r"` both become `"\\n"`. This runs before block-boundary
   insertion so a source file's own line-ending style never doubles up
   with an inserted boundary.
2. Parse with `html.parser.HTMLParser(convert_charrefs=True)` (Python's
   own default) -- character references are decoded as text is extracted,
   never as a separate regex pass that could double-decode a literal
   `"&amp;amp;"`.
3. `<script>`/`<style>` element *content* is suppressed entirely (tracked
   via a start/end-tag depth flag) -- their text is never extracted.
4. Block tags (`p`, `div`, `br`, `li`, `h1`-`h6`, `ul`, `ol`) each ensure
   exactly one `"\\n"` boundary at that point; inline tags (`span`,
   `strong`, `em`, `b`, `i`, `a`) insert none -- their text is kept inline.
5. Post-processing, applied per extracted line: runs of literal ASCII
   space/tab (`[ \\t]+`) collapse to one ASCII space. A line whose
   collapsed form is empty (was entirely space/tab) is a blank line for
   step 6 -- **never** a line that is merely a no-break space or another
   Unicode whitespace/format character, which is preserved unchanged and
   counts as content.
6. A run of two or more consecutive blank lines collapses to exactly one
   blank line -- never zero (a single blank line is a real, meaningful
   paragraph break) and never left to accumulate from nested/adjacent
   block tags.
7. Leading/trailing `"\\n"` is stripped from the final result.

NBSP (`\\u00a0`) and every other Unicode whitespace or format character
(`\\u200b`, `\\ufeff`, `\\u180e`, ...) are never touched by steps 5-6 --
deliberately, since the corpus exists partly to exercise the exact
Unicode-whitespace/format-character handling `app/normalization/skills.py`
already implements.
"""

from __future__ import annotations

import re
from html import unescape as _html_unescape
from html.parser import HTMLParser
from typing import Literal

_COVERED_WHITESPACE = " \t\n\r"

_BLOCK_TAGS = frozenset({"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol"})
_SUPPRESSED_TAGS = frozenset({"script", "style"})

_HORIZONTAL_RUN_RE = re.compile(r"[ \t]+")

ContentMode = Literal["standard", "declared-double-escaped"]
_VALID_CONTENT_MODES = frozenset({"standard", "declared-double-escaped"})

# Shared by stages 1 and 3 -- see the module docstring's "Processing
# stages" section. Fixed exactly as specified; never modified ad hoc.
# `lt`/`gt`/`LT`/`GT` are exactly the four named-reference spellings
# Python's `html.unescape()` decodes to `<`/`>` (confirmed empirically);
# the mixed-case spellings `Lt`/`Gt` are separate, unrelated HTML5 named
# references (`&Lt;` -> U+226A, `&Gt;` -> U+226B) and must never be
# treated as angle references.
_ESCAPED_ANGLE_REFERENCE_RE = re.compile(
    r"(?:"
    r"&(?:lt|gt|LT|GT);"
    r"|&#(?:0*60|0*62)(?:;|(?=[^0-9]|$))"
    r"|&#[xX](?:0*3[cC]|0*3[eE])(?:;|(?=[^0-9A-Fa-f]|$))"
    r")"
)
_UNTERMINATED_NAMED_ANGLE_RE = re.compile(r"&(?:lt|gt|LT|GT)(?!;)")


class _BlockAwareTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self.suppress_depth = 0

    def _ends_with_boundary(self) -> bool:
        return not self._parts or self._parts[-1].endswith("\n")

    def _insert_boundary(self) -> None:
        if not self._ends_with_boundary():
            self._parts.append("\n")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SUPPRESSED_TAGS:
            self.suppress_depth += 1
            return
        if tag in _BLOCK_TAGS:
            self._insert_boundary()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Void/self-closing elements (e.g. `<br/>`) -- no matching end tag
        # will ever arrive, so handle the boundary here directly.
        if tag in _BLOCK_TAGS:
            self._insert_boundary()

    def handle_endtag(self, tag: str) -> None:
        if tag in _SUPPRESSED_TAGS:
            if self.suppress_depth > 0:
                self.suppress_depth -= 1
            return
        if tag in _BLOCK_TAGS:
            self._insert_boundary()

    def handle_data(self, data: str) -> None:
        if self.suppress_depth > 0:
            return
        self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


def _normalize_line_endings(html: str) -> str:
    return html.replace("\r\n", "\n").replace("\r", "\n")


def _collapse_horizontal_whitespace(line: str) -> str:
    return _HORIZONTAL_RUN_RE.sub(" ", line)


def _collapse_blank_lines(lines: list[str]) -> list[str]:
    """A line is blank if it contains only ASCII space/tab after horizontal
    collapsing -- checked with `.strip(" \t")`, never a bare `.strip()`,
    so a line that is only a no-break space or another Unicode whitespace/
    format character is never mistaken for blank. A blank line is
    normalized to `""` when kept (never left as the single stray space
    horizontal collapsing may have produced for an all-space/tab line)."""
    collapsed: list[str] = []
    previous_was_blank = False
    for line in lines:
        is_blank = line.strip(" \t") == ""
        if is_blank:
            if previous_was_blank:
                continue
            collapsed.append("")
        else:
            collapsed.append(line)
        previous_was_blank = is_blank
    return collapsed


class HtmlConversionError(RuntimeError):
    """Raised when a `<script>`/`<style>` element is never closed. Python's
    `HTMLParser` treats both as CDATA and only exits on a literal matching
    end tag, so a truncated/malformed open tag anywhere would otherwise
    silently discard every character after it -- including real
    description text -- with no signal that the result is truncated
    rather than genuinely short. Raising here is the fail-closed choice,
    consistent with the rest of this slice: a caller must not treat
    unreliable output as a real (if short) description."""


class HtmlDoubleEncodingError(HtmlConversionError):
    """Raised only under `mode="declared-double-escaped"`, for input this
    bounded, single-extra-decode contract cannot safely process.
    `category` is one of a fixed closed set:

    - `"mixed-literal-and-escaped-markup"` -- the raw input contains a
      literal angle bracket *and* an escaped-angle-reference-shaped
      substring simultaneously; ambiguous, never guessed at.
    - `"unsupported-angle-reference"` -- a semicolonless named
      `&lt`/`&gt`/`&LT`/`&GT` form is present (raw or post-decode); its
      interaction with `html.unescape()`'s own legacy matching against a
      longer entity name sharing the same prefix is not trusted to be
      safe, so every such form is rejected regardless of what follows
      it.
    - `"residual-nested-encoding"` -- the one permitted decode still left
      a fully-terminated escaped-angle-reference-shaped substring behind
      (see the module docstring's accepted-limitation note).

    Never carries posting content -- the fixed category string is the
    entire message."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(f"declared-double-escaped mode rejected input: {category}")


def _validate_raw_for_declared_mode(raw: str) -> None:
    has_literal_angle = "<" in raw or ">" in raw
    has_escaped_form = bool(_ESCAPED_ANGLE_REFERENCE_RE.search(raw)) or bool(
        _UNTERMINATED_NAMED_ANGLE_RE.search(raw)
    )
    if has_literal_angle and has_escaped_form:
        raise HtmlDoubleEncodingError("mixed-literal-and-escaped-markup")
    if _UNTERMINATED_NAMED_ANGLE_RE.search(raw):
        raise HtmlDoubleEncodingError("unsupported-angle-reference")


def _validate_decoded_for_declared_mode(decoded: str) -> None:
    if _UNTERMINATED_NAMED_ANGLE_RE.search(decoded):
        raise HtmlDoubleEncodingError("unsupported-angle-reference")
    if _ESCAPED_ANGLE_REFERENCE_RE.search(decoded):
        raise HtmlDoubleEncodingError("residual-nested-encoding")


def convert_html_to_text(html: str, *, mode: ContentMode = "standard") -> str:
    """Converts one Greenhouse job posting's HTML `content` field into
    plain text per this module's algorithm. Tolerates ordinary malformed
    HTML (unclosed/mismatched ordinary tags) -- `html.parser.HTMLParser`
    recovers from those rather than failing closed, since a job-posting
    HTML fragment is never validated against a strict grammar upstream.
    Raises `HtmlConversionError` only for an unclosed `<script>`/
    `<style>`, where silently returning truncated text would be worse
    than failing closed.

    Line-ending normalization runs *twice*, deliberately: once on the
    raw markup before parsing (covers a literal `\\r\\n`/`\\r` in the
    source), and once more on the fully extracted text afterward (covers
    a decoded character reference -- e.g. `&#13;` -- which `HTMLParser`
    only resolves *during* parsing, after the first pass already ran, so
    a decoded CR/LF would otherwise reach the output completely
    unnormalized).

    `mode="declared-double-escaped"` additionally runs stages 1-3 from
    the module docstring's "Processing stages" section before this
    normalization -- exactly one `html.unescape()` call, bracketed by the
    fixed validation predicates -- and may raise `HtmlDoubleEncodingError`
    (a subclass of `HtmlConversionError`). `mode="standard"` (the
    default) is completely unaffected by any of that: byte-for-behavior
    identical to this function's behavior before the mode contract
    existed."""
    if mode not in _VALID_CONTENT_MODES:
        raise ValueError(f"unknown content mode: {mode!r}")

    working = html
    if mode == "declared-double-escaped":
        _validate_raw_for_declared_mode(working)
        working = _html_unescape(working)
        _validate_decoded_for_declared_mode(working)

    normalized = _normalize_line_endings(working)
    extractor = _BlockAwareTextExtractor()
    extractor.feed(normalized)
    extractor.close()
    if extractor.suppress_depth > 0:
        raise HtmlConversionError(
            "unclosed <script>/<style> element -- refusing to return text that may be "
            "silently truncated"
        )
    raw_text = _normalize_line_endings(extractor.get_text())

    lines = [_collapse_horizontal_whitespace(line) for line in raw_text.split("\n")]
    lines = _collapse_blank_lines(lines)
    return "\n".join(lines).strip("\n")
