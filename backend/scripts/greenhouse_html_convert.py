"""Deterministic HTML-to-plain-text conversion for the realistic Phase 3
evaluation corpus (Class H realistic-corpus evaluation slice).

Pure function, no I/O, no network. Converts a Greenhouse job posting's
`content` field (HTML) into plain text suitable for feeding directly into
the seven merged Phase 3 classifiers, so the evaluation corpus exercises
the same character-level realism (entity decoding, block-boundary
whitespace, stray Unicode format characters) that real HTML-authored
descriptions actually contain.

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
from html.parser import HTMLParser

_COVERED_WHITESPACE = " \t\n\r"

_BLOCK_TAGS = frozenset({"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol"})
_SUPPRESSED_TAGS = frozenset({"script", "style"})

_HORIZONTAL_RUN_RE = re.compile(r"[ \t]+")


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


def convert_html_to_text(html: str) -> str:
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
    unnormalized)."""
    normalized = _normalize_line_endings(html)
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
