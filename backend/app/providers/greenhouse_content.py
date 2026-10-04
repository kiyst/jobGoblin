"""Deterministic, bounded text extraction for a Greenhouse job's HTML `content`
field (Phase 4 S2b, Class H;
`docs/DECISIONS/0015-greenhouse-content-conversion-and-posting-input-mapping.md`).

Provider-specific and standard-library-only. No I/O, logging, network, global
mutable state, or import-time work. `convert_greenhouse_content` returns a
`ContentConversion`; it never raises for any `content` value. Only an unknown
`mode`, a programmer error, raises.

**Content modes.** The caller declares one of exactly two modes, which this module
never infers from the content, a board token, or anything else:

- `"disabled"`: returns `NOT_REQUESTED` before `content` is inspected in any way.
- `"declared-double-escaped"`: the compatibility name of the reviewed
  one-predecode algorithm in `scripts/greenhouse_html_convert.py` (ADR 0010). It is
  **not** a claim that every accepted input contains escaped tags. Literal HTML with
  no escaped-angle reference is also accepted (the single `html.unescape()` pass is
  then a no-op). Input this mode rejects stays rejected; there is no fallback to
  another mode and no retry.

This module reimplements that script's `declared-double-escaped` path exactly: its
two angle-reference predicates, their precedence, the single `html.unescape()`
followed by `HTMLParser(convert_charrefs=True)`, the block-tag set, script/style
suppression, line-ending normalization, and whitespace collapsing. The script and
its tests stay frozen; `tests/test_greenhouse_content.py` pins both by hash and
checks that the two implementations agree wherever this module converts.

**End-of-input integrity marker.** Unlike the script, this module fails closed when
an unfinished construct silently swallows the rest of the input. After decoding,
the parser is fed the decoded text followed by one internal marker element,
`<NAME></NAME>`, whose `NAME` is `ghintegrity-` plus one more `z` than the longest
`ghintegrity-z…` run anywhere in the decoded text (case-insensitive). That name is
therefore absent from the source, so source text can neither forge nor suppress it;
selection is a pure, linear-time function of the decoded text. The marker emits no
text and no block boundary. After the parser closes, exactly one ordered
start/end pair of the marker must have been seen; otherwise an unterminated
comment, quoted attribute, tag-like fragment, or equivalent unfinished construct
consumed it, and the result is `MALFORMED_TRUNCATED_MARKUP` with no text. Caps
measure only source and output text, never marker material. Whether a
`script`/`style` element is still open is recorded before the marker is fed, so the
marker cannot complete a dangling `</style` end tag and hide it. An unclosed
raw-text element (`title`, `textarea`, `xmp`, `iframe`, `noembed`, `noframes`,
`plaintext` on CPython 3.12.13) also swallows the marker and abstains. Only
end-of-input swallowing is detected: when a later quote or `-->` closes a
swallowing construct mid-input, the lost text is not detected.

**Validation order** (the first failing check decides the outcome): mode; absent
or type; input length; covered-whitespace blank; raw encoding checks; one decode
plus decoded encoding checks; extraction, where `PARSER_ERROR` precedes
`UNCLOSED_SUPPRESSED_ELEMENT` (an open `script`/`style`), which precedes
`MALFORMED_TRUNCATED_MARKUP`; meaningfulness; output length.

**Caps.** `MAX_CONTENT_CHARS` and `MAX_DESCRIPTION_CHARS` count Python Unicode code
points, not bytes. Content is never truncated: exactly at a cap is accepted, and
one past it abstains. The byte boundary is the adapter's: S1 caps a complete HTTP
response at five megabytes before any record exists, and the character cap
bounds a direct call.

**Extraction only.** This is deterministic text extraction, not sanitization or
security cleaning. The output can still contain contact details or any other
text the source contained.

Disclosed limitations (pinned by tests):

- only `p div br li h1-h6 ul ol` are block tags, so adjacent table cells and
  `section`/`blockquote`/`pre`/`hr` content run together;
- `noscript` and `template` text is kept;
- a legitimate escaped code example (`&lt;script&gt;` meant as text) is rejected as
  mixed or residual encoding;
- no-break space and every other Unicode whitespace or format character is kept,
  but output made only of such characters abstains;
- extraction rides on the running interpreter's standard-library `html.parser`,
  whose handling of comments, declarations, CDATA, and unterminated markup has
  changed between CPython patch releases. Determinism and the never-raises
  guarantee were verified on CPython 3.12.13; the oracle shares the same parser, so
  literal golden expectations for those parser-sensitive inputs are pinned
  separately in the tests.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from html import unescape as _html_unescape
from html.parser import HTMLParser
from typing import Final, Literal

GreenhouseContentMode = Literal["disabled", "declared-double-escaped"]
CONTENT_MODES: Final = frozenset({"disabled", "declared-double-escaped"})

MAX_CONTENT_CHARS: Final = 200_000
MAX_DESCRIPTION_CHARS: Final = 100_000

ERROR_INVALID_CONTENT_MODE: Final = "content_mode must be 'disabled' or 'declared-double-escaped'"
_ERROR_INVALID_CONVERSION = "ContentConversion text must be set iff the outcome is converted"

_COVERED_WHITESPACE = " \t\n\r"

_BLOCK_TAGS = frozenset({"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol"})
_SUPPRESSED_TAGS = frozenset({"script", "style"})

_HORIZONTAL_RUN_RE = re.compile(r"[ \t]+")

# Copied exactly from `scripts/greenhouse_html_convert.py`. `lt`/`gt`/`LT`/`GT` are
# the four named spellings `html.unescape()` decodes to `<`/`>`; the mixed-case
# `&Lt;`/`&Gt;` are unrelated entities (U+226A/U+226B) and never angle references.
_ESCAPED_ANGLE_REFERENCE_RE = re.compile(
    r"(?:"
    r"&(?:lt|gt|LT|GT);"
    r"|&#(?:0*60|0*62)(?:;|(?=[^0-9]|$))"
    r"|&#[xX](?:0*3[cC]|0*3[eE])(?:;|(?=[^0-9A-Fa-f]|$))"
    r")"
)
# Deliberately blunt: any `&lt`/`&gt`/`&LT`/`&GT` not followed by `;`, so the
# unrelated `&ltimes;` is rejected too.
_UNTERMINATED_NAMED_ANGLE_RE = re.compile(r"&(?:lt|gt|LT|GT)(?!;)")

_MARKER_PREFIX = "ghintegrity-"
_MARKER_RUN_RE = re.compile(re.escape(_MARKER_PREFIX) + "(z*)")
_MARKER_COMPLETE = ("start", "end")


class ContentOutcome(StrEnum):
    """Closed outcome set. Only `CONVERTED` carries text."""

    CONVERTED = "converted"
    NOT_REQUESTED = "not_requested"
    ABSENT = "absent"
    BLANK = "blank"
    INVALID_TYPE = "invalid_type"
    INPUT_TOO_LARGE = "input_too_large"
    OUTPUT_TOO_LARGE = "output_too_large"
    EMPTY_AFTER_CONVERSION = "empty_after_conversion"
    MIXED_LITERAL_AND_ESCAPED_MARKUP = "mixed_literal_and_escaped_markup"
    UNSUPPORTED_ANGLE_REFERENCE = "unsupported_angle_reference"
    RESIDUAL_NESTED_ENCODING = "residual_nested_encoding"
    UNCLOSED_SUPPRESSED_ELEMENT = "unclosed_suppressed_element"
    MALFORMED_TRUNCATED_MARKUP = "malformed_truncated_markup"
    PARSER_ERROR = "parser_error"


@dataclass(frozen=True)
class ContentConversion:
    """`text` is non-`None` iff `outcome` is `CONVERTED`."""

    text: str | None
    outcome: ContentOutcome

    def __post_init__(self) -> None:
        if (self.text is not None) != (self.outcome is ContentOutcome.CONVERTED):
            raise ValueError(_ERROR_INVALID_CONVERSION)


def _abstain(outcome: ContentOutcome) -> ContentConversion:
    return ContentConversion(text=None, outcome=outcome)


class _BlockAwareTextExtractor(HTMLParser):
    """Collects text data. Each block tag (start, end, or self-closing) ensures one
    `\\n` boundary; every other tag inserts nothing. Attributes, comments,
    declarations, processing instructions, and CDATA sections are never emitted
    (`HTMLParser`'s default handlers drop them). Tags named `marker` are recorded in
    `marker_events` and otherwise ignored: no text, no boundary."""

    def __init__(self, marker: str) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._marker = marker
        self.marker_events: list[str] = []
        self.suppress_depth = 0

    def _ends_with_boundary(self) -> bool:
        return not self._parts or self._parts[-1].endswith("\n")

    def _insert_boundary(self) -> None:
        if not self._ends_with_boundary():
            self._parts.append("\n")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == self._marker:
            self.marker_events.append("start")
            return
        if tag in _SUPPRESSED_TAGS:
            self.suppress_depth += 1
            return
        if tag in _BLOCK_TAGS:
            self._insert_boundary()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == self._marker:
            self.marker_events.append("self-closing")
            return
        if tag in _BLOCK_TAGS:
            self._insert_boundary()

    def handle_endtag(self, tag: str) -> None:
        if tag == self._marker:
            self.marker_events.append("end")
            return
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


def _normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _collapse_blank_lines(lines: list[str]) -> list[str]:
    """A line is blank only when `.strip(" \\t")` leaves nothing; a run of blank
    lines becomes one `""` line. A line of no-break space or another Unicode
    whitespace or format character is content, not blank."""
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


def _has_semicolonless_angle_reference(text: str) -> bool:
    """The single semicolonless-angle predicate, shared by the raw and the
    decoded checks."""
    return _UNTERMINATED_NAMED_ANGLE_RE.search(text) is not None


def _raw_encoding_problem(raw: str) -> ContentOutcome | None:
    has_literal_angle = "<" in raw or ">" in raw
    has_escaped_form = bool(_ESCAPED_ANGLE_REFERENCE_RE.search(raw)) or (
        _has_semicolonless_angle_reference(raw)
    )
    if has_literal_angle and has_escaped_form:
        return ContentOutcome.MIXED_LITERAL_AND_ESCAPED_MARKUP
    if _has_semicolonless_angle_reference(raw):
        return ContentOutcome.UNSUPPORTED_ANGLE_REFERENCE
    return None


def _decoded_encoding_problem(decoded: str) -> ContentOutcome | None:
    if _has_semicolonless_angle_reference(decoded):
        return ContentOutcome.UNSUPPORTED_ANGLE_REFERENCE
    if _ESCAPED_ANGLE_REFERENCE_RE.search(decoded):
        return ContentOutcome.RESIDUAL_NESTED_ENCODING
    return None


def _integrity_marker(decoded: str) -> str:
    """`ghintegrity-` plus one more `z` than the longest `ghintegrity-z…` run in the
    decoded text (compared case-insensitively, as `HTMLParser` lowercases tag names),
    so the name occurs nowhere in the source."""
    longest = max(
        (len(match.group(1)) for match in _MARKER_RUN_RE.finditer(decoded.lower())),
        default=0,
    )
    return _MARKER_PREFIX + "z" * (longest + 1)


def _is_meaningful(text: str) -> bool:
    """True when at least one character is neither whitespace nor a Unicode
    format (`Cf`) character."""
    return any(not (char.isspace() or unicodedata.category(char) == "Cf") for char in text)


def convert_greenhouse_content(
    content: object, *, mode: GreenhouseContentMode
) -> ContentConversion:
    """Converts one Greenhouse `content` value under the declared `mode`.

    Raises only `ValueError(ERROR_INVALID_CONTENT_MODE)` for a mode outside
    `CONTENT_MODES` (exact built-in `str` required). In declared mode only an
    exact built-in `str` is converted; `None` is `ABSENT` and anything else,
    including a `str` subclass, is `INVALID_TYPE`. Only a `RecursionError` from
    `HTMLParser.feed()`/`close()` becomes `PARSER_ERROR`; any other exception is
    a defect and propagates."""
    if type(mode) is not str or mode not in CONTENT_MODES:
        raise ValueError(ERROR_INVALID_CONTENT_MODE)
    if mode == "disabled":
        return _abstain(ContentOutcome.NOT_REQUESTED)

    if content is None:
        return _abstain(ContentOutcome.ABSENT)
    if type(content) is not str:
        return _abstain(ContentOutcome.INVALID_TYPE)
    if len(content) > MAX_CONTENT_CHARS:
        return _abstain(ContentOutcome.INPUT_TOO_LARGE)
    if not content.strip(_COVERED_WHITESPACE):
        return _abstain(ContentOutcome.BLANK)

    raw_problem = _raw_encoding_problem(content)
    if raw_problem is not None:
        return _abstain(raw_problem)
    decoded = _html_unescape(content)
    decoded_problem = _decoded_encoding_problem(decoded)
    if decoded_problem is not None:
        return _abstain(decoded_problem)

    marker = _integrity_marker(decoded)
    extractor = _BlockAwareTextExtractor(marker)
    try:
        extractor.feed(_normalize_line_endings(decoded))
        # Recorded before the marker is fed: the marker's own `<`/`>` could finish a
        # dangling `</style`/`</script` end tag and hide the open element.
        open_suppressed_at_end_of_source = extractor.suppress_depth > 0
        extractor.feed(f"<{marker}></{marker}>")
        extractor.close()
    except RecursionError:
        return _abstain(ContentOutcome.PARSER_ERROR)
    if open_suppressed_at_end_of_source or extractor.suppress_depth > 0:
        return _abstain(ContentOutcome.UNCLOSED_SUPPRESSED_ELEMENT)
    # The integrity-completeness decision: anything other than one ordered
    # start/end pair means an unfinished construct swallowed the end of the input.
    if tuple(extractor.marker_events) != _MARKER_COMPLETE:
        return _abstain(ContentOutcome.MALFORMED_TRUNCATED_MARKUP)

    # Normalized again: `HTMLParser` decodes references such as `&#13;` only while
    # parsing, after the first normalization.
    extracted = _normalize_line_endings(extractor.get_text())
    lines = [_HORIZONTAL_RUN_RE.sub(" ", line) for line in extracted.split("\n")]
    text = "\n".join(_collapse_blank_lines(lines)).strip("\n")

    if not _is_meaningful(text):
        return _abstain(ContentOutcome.EMPTY_AFTER_CONVERSION)
    if len(text) > MAX_DESCRIPTION_CHARS:
        return _abstain(ContentOutcome.OUTPUT_TOO_LARGE)
    return ContentConversion(text=text, outcome=ContentOutcome.CONVERTED)
