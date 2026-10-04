"""Offline tests for `app.providers.greenhouse_content` (Phase 4 S2b; ADR 0015).

Every input here is SYNTHETIC — not captured from Greenhouse. No captured raw
Greenhouse `content` HTML exists in this repository (ADR 0010 never retained raw
bodies), so these tests prove the extraction mechanism, not how the live list
endpoint encodes `content`.

`declared-double-escaped` is the compatibility name of the reviewed
one-predecode algorithm in `scripts/greenhouse_html_convert.py`. It also accepts
literal HTML that contains no escaped-angle reference; the tests below pin both
shapes. The frozen script and its tests are the differential oracle and are
pinned by canonical-LF SHA-256: if either changes, these pins fail and the
change needs review, so the application implementation and the oracle cannot
drift together unnoticed.

A socket guard makes any network attempt fail the test.
"""

from __future__ import annotations

import ast
import hashlib
import socket
import unicodedata
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from app.providers import greenhouse_content
from app.providers.greenhouse_content import (
    CONTENT_MODES,
    ERROR_INVALID_CONTENT_MODE,
    MAX_CONTENT_CHARS,
    MAX_DESCRIPTION_CHARS,
    ContentConversion,
    ContentOutcome,
    GreenhouseContentMode,
    convert_greenhouse_content,
)
from scripts.greenhouse_html_convert import (
    HtmlConversionError,
    HtmlDoubleEncodingError,
    convert_html_to_text,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
CONTENT_MODULE = BACKEND_DIR / "app" / "providers" / "greenhouse_content.py"
ORACLE_SCRIPT = BACKEND_DIR / "scripts" / "greenhouse_html_convert.py"
ORACLE_TESTS = BACKEND_DIR / "tests" / "test_greenhouse_html_convert.py"

# Canonical-LF SHA-256 (UTF-8 text with CRLF and lone CR replaced by LF).
ORACLE_SCRIPT_CANONICAL_LF_SHA256 = (
    "fff4b1c09765eb02def5f79c7b1b9bbfa58e20b1ed96edd2b96c5c852e2cd06f"
)
ORACLE_TESTS_CANONICAL_LF_SHA256 = (
    "2bdf301475fa79aad36ac84efa1ee73bc0959d2e376dcd6e49eb63084b89fcd1"
)

DECLARED: GreenhouseContentMode = "declared-double-escaped"
SENTINEL = "SENTINEL-4b1d-content-must-not-appear"

C = ContentOutcome


def convert(content: object) -> ContentConversion:
    return convert_greenhouse_content(content, mode=DECLARED)


def converted(content: object) -> str:
    result = convert(content)
    assert result.outcome is C.CONVERTED
    assert result.text is not None
    return result.text


def canonical_lf_sha256(path: Path) -> str:
    text = path.read_bytes().decode("utf-8")
    canonical = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@pytest.fixture(autouse=True)
def socket_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    calls: list[str] = []

    def hard_fail(name: str) -> Callable[..., Any]:
        def _blocked(*args: Any, **kwargs: Any) -> Any:
            calls.append(name)
            raise AssertionError(f"socket access attempted in an offline test: {name}")

        return _blocked

    with monkeypatch.context() as patch:
        patch.setattr(socket.socket, "connect", hard_fail("socket.connect"))
        patch.setattr(socket.socket, "connect_ex", hard_fail("socket.connect_ex"))
        patch.setattr(socket, "create_connection", hard_fail("socket.create_connection"))
        patch.setattr(socket, "getaddrinfo", hard_fail("socket.getaddrinfo"))
        yield calls
    assert calls == []


# ---------------------------------------------------------------------------
# Modes and configuration
# ---------------------------------------------------------------------------


def test_content_modes_are_exactly_the_two_declared_modes() -> None:
    assert frozenset({"disabled", "declared-double-escaped"}) == CONTENT_MODES


class _Hostile:
    """Raises on any ordinary operation: equality, hashing, truthiness,
    stringification, length, or attribute access."""

    def _fail(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("content value was inspected")

    __eq__ = __ne__ = __hash__ = __bool__ = __str__ = __repr__ = __len__ = _fail
    __format__ = __iter__ = __contains__ = _fail

    def __getattribute__(self, name: str) -> Any:
        raise AssertionError("content value was inspected")


def test_disabled_returns_not_requested_without_inspecting_content() -> None:
    result = convert_greenhouse_content(_Hostile(), mode="disabled")
    assert result == ContentConversion(text=None, outcome=C.NOT_REQUESTED)


@pytest.mark.parametrize("content", [None, "", "&lt;p&gt;Hello&lt;/p&gt;", "<p>Hi</p>", 7])
def test_disabled_never_converts(content: object) -> None:
    assert convert_greenhouse_content(content, mode="disabled").outcome is C.NOT_REQUESTED


class _StrSubclass(str):
    pass


@pytest.mark.parametrize(
    "mode",
    ["standard", "Disabled", "declared_double_escaped", "", None, 1, _StrSubclass("disabled")],
)
def test_unknown_mode_raises_fixed_non_interpolating_error(mode: Any) -> None:
    with pytest.raises(ValueError) as raised:
        convert_greenhouse_content("<p>Hi</p>", mode=mode)
    assert str(raised.value) == ERROR_INVALID_CONTENT_MODE
    assert ERROR_INVALID_CONTENT_MODE == (
        "content_mode must be 'disabled' or 'declared-double-escaped'"
    )


def test_unknown_mode_is_rejected_before_content_is_inspected() -> None:
    with pytest.raises(ValueError):
        convert_greenhouse_content(_Hostile(), mode="standard")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


def test_text_is_set_iff_converted() -> None:
    assert ContentConversion(text="x", outcome=C.CONVERTED).text == "x"
    for outcome in C:
        if outcome is C.CONVERTED:
            with pytest.raises(ValueError):
                ContentConversion(text=None, outcome=outcome)
        else:
            with pytest.raises(ValueError):
                ContentConversion(text="x", outcome=outcome)
            assert ContentConversion(text=None, outcome=outcome).text is None


def test_outcome_vocabulary_is_closed() -> None:
    assert {outcome.value for outcome in C} == {
        "converted",
        "not_requested",
        "absent",
        "blank",
        "invalid_type",
        "input_too_large",
        "output_too_large",
        "empty_after_conversion",
        "mixed_literal_and_escaped_markup",
        "unsupported_angle_reference",
        "residual_nested_encoding",
        "unclosed_suppressed_element",
        "malformed_truncated_markup",
        "parser_error",
    }


# ---------------------------------------------------------------------------
# Absent, type, and blank
# ---------------------------------------------------------------------------


def test_none_is_absent() -> None:
    assert convert(None) == ContentConversion(text=None, outcome=C.ABSENT)


@pytest.mark.parametrize(
    "content", [b"<p>Hi</p>", 1, 1.5, True, ["<p>Hi</p>"], {"html": "x"}, _StrSubclass("<p>Hi</p>")]
)
def test_only_exact_built_in_str_is_accepted(content: object) -> None:
    assert convert(content) == ContentConversion(text=None, outcome=C.INVALID_TYPE)


def test_hostile_object_is_invalid_type_without_being_inspected() -> None:
    assert convert(_Hostile()).outcome is C.INVALID_TYPE


@pytest.mark.parametrize("content", ["", " ", "\t", "\n", "\r", " \t\n\r \r\n"])
def test_covered_whitespace_only_is_blank(content: str) -> None:
    assert convert(content) == ContentConversion(text=None, outcome=C.BLANK)


# ---------------------------------------------------------------------------
# Declared-mode grammar (A8): exact predicates and precedence
# ---------------------------------------------------------------------------


def test_pure_declared_input_converts() -> None:
    assert converted("&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;") == "Hello world"


def test_literal_html_without_escaped_angles_is_accepted() -> None:
    """A4: the mode name does not mean every accepted input contains escaped
    tags. Literal HTML with no escaped-angle reference passes through the one
    no-op predecode."""
    assert converted("<p>Hello <b>world</b></p>") == "Hello world"


@pytest.mark.parametrize(
    "content",
    [
        "<p>Hello &lt;b&gt;world&lt;/b&gt;</p>",
        "<p>Hello &LT;b&GT;world&LT;/b&GT;</p>",
        "<p>a &#60;b&#62;</p>",
        "<p>a &#x3C;b&#x3e;</p>",
        "<p>Use &lt;script&gt; as text</p>",
        "<p>A &lt</p>",
    ],
)
def test_mixed_literal_and_escaped_rejected(content: str) -> None:
    assert convert(content) == ContentConversion(
        text=None, outcome=C.MIXED_LITERAL_AND_ESCAPED_MARKUP
    )


def test_single_layer_declared_input_converts() -> None:
    assert converted("&lt;div&gt;&lt;p&gt;One&lt;/p&gt;&lt;p&gt;Two&lt;/p&gt;&lt;/div&gt;") == (
        "One\nTwo"
    )


@pytest.mark.parametrize(
    "content",
    [
        "&amp;lt;p&amp;gt;Hello&amp;lt;/p&amp;gt;",
        "&amp;LT;p&amp;GT;Hello&amp;LT;/p&amp;GT;",
        "&amp;#60;p&amp;#62;Hello",
        "&lt;p&gt;Use &amp;lt;script&amp;gt; as text&lt;/p&gt;",
    ],
)
def test_residual_nested_encoding_rejected(content: str) -> None:
    assert convert(content) == ContentConversion(text=None, outcome=C.RESIDUAL_NESTED_ENCODING)


@pytest.mark.parametrize(
    "content",
    [
        # raw stage
        "&ltfoo",
        "&lt",
        "&GTfoo",
        "&LT",
        "&ltimes;",
        "A &gt B",
        # post-decode stage: the raw text has no angle form, the decoded text does
        "&amp;ltfoo",
        "&amp;gt",
        "&amp;LTx",
        "&amp;ltimes;",
    ],
)
def test_semicolonless_angle_reference_rejected(content: str) -> None:
    assert convert(content) == ContentConversion(text=None, outcome=C.UNSUPPORTED_ANGLE_REFERENCE)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("&lt;p&gt;A &Lt; B&lt;/p&gt;", "A ≪ B"),
        ("&lt;p&gt;A &Gt; B&lt;/p&gt;", "A ≫ B"),
        ("<p>A &Lt; B &Gt; C</p>", "A ≪ B ≫ C"),
    ],
)
def test_mixed_case_lt_gt_are_unrelated_entities(content: str, expected: str) -> None:
    assert converted(content) == expected


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("A &amp; B", "A & B"),
        ("A &amp;amp; B", "A & B"),
        ("caf&eacute; &copy;", "café ©"),
        ("&#233;&#xE9;&#XE9;", "ééé"),
        ("A&#13;B", "A\nB"),
        ("A&#13;&#10;B", "A\nB"),
        ("&lt;p&gt;A&lt;/p&gt;&amp;#13;&lt;p&gt;B&lt;/p&gt;", "A\n\nB"),
        ("&quot;x&quot; &apos;y&apos;", "\"x\" 'y'"),
    ],
)
def test_entities_decode_through_one_unescape_then_the_parser(content: str, expected: str) -> None:
    assert converted(content) == expected


def test_output_is_never_re_escaped() -> None:
    assert converted("&lt;p&gt;5 &amp;amp; 6&lt;/p&gt;") == "5 & 6"


# ---------------------------------------------------------------------------
# Boundaries, whitespace, suppression, and dropped markup
# ---------------------------------------------------------------------------


def test_list_items_get_line_boundaries() -> None:
    assert converted("<ul><li>Python</li><li>Go</li></ul>") == "Python\nGo"
    assert converted("&lt;ol&gt;&lt;li&gt;A&lt;/li&gt;&lt;li&gt;B&lt;/li&gt;&lt;/ol&gt;") == "A\nB"


def test_lists_get_no_markers() -> None:
    result = converted("<ol><li>First</li><li>Second</li></ol>")
    assert result == "First\nSecond"
    assert "1" not in result and "•" not in result and "-" not in result


def test_paragraph_boundaries() -> None:
    assert converted("<p>Skills:</p><p>Python, Go</p>") == "Skills:\nPython, Go"


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("A<br>B", "A\nB"),
        ("A<br/>B", "A\nB"),
        ("A<br />B", "A\nB"),
        ("<h1>T</h1><h6>U</h6>body", "T\nU\nbody"),
        ("<div><p>Hello</p></div><div><p>World</p></div>", "Hello\nWorld"),
        ("<p>A</p><p></p><p></p><p>B</p>", "A\nB"),
        ("<p>A</p>\n\n\n<p>B</p>", "A\n\nB"),
        ("<p>A</p>\r\n<p>B</p>", "A\n\nB"),
        ("<p>Hello <strong>World</strong> <em>x</em><a>y</a><span>z</span></p>", "Hello World xyz"),
        ("Hello  \t  World", "Hello World"),
        ("<div><p>A</p></div>", "A"),
    ],
)
def test_block_inline_and_whitespace_rules(content: str, expected: str) -> None:
    assert converted(content) == expected


def test_table_cells_merge_disclosed_limitation() -> None:
    """Limitation: table and sectioning tags are inline, so adjacent cells or
    sections run together."""
    assert converted("<table><tr><td>Python</td><td>Go</td></tr></table>") == "PythonGo"
    assert converted("<section>A</section><blockquote>B</blockquote><pre>C</pre><hr>D") == "ABCD"


def test_noscript_and_template_text_is_kept_disclosed_limitation() -> None:
    assert converted("<noscript>A</noscript><template>B</template>") == "AB"


def test_script_style_content_dropped() -> None:
    assert converted(f"<script>{SENTINEL}</script><p>Hello</p>") == "Hello"
    assert converted(f"<style>{SENTINEL}</style><p>Hello</p>") == "Hello"
    assert converted(f"&lt;script&gt;{SENTINEL}&lt;/script&gt;&lt;p&gt;Hello&lt;/p&gt;") == "Hello"


def test_inline_text_kept() -> None:
    assert converted("<p>Plain <i>inline</i> text</p>") == "Plain inline text"


@pytest.mark.parametrize(
    "content",
    [
        "<script>never closed<p>fake para</p>",
        "<style>never closed<p>Real text</p>",
        "&lt;p&gt;Before&lt;/p&gt;&lt;script&gt;never closed",
    ],
)
def test_unclosed_suppressed_element_abstains(content: str) -> None:
    assert convert(content) == ContentConversion(text=None, outcome=C.UNCLOSED_SUPPRESSED_ELEMENT)


def test_closed_suppressed_element_converts() -> None:
    assert converted("<script>alert(1)</script><p>Real text</p>") == "Real text"


def test_attributes_are_never_emitted() -> None:
    content = f'<a href="https://example.invalid/{SENTINEL}" title="{SENTINEL}">link</a>'
    assert converted(content) == "link"
    assert converted(f'<img alt="{SENTINEL}" src="x">after') == "after"


def test_comments_declarations_instructions_and_cdata_are_dropped() -> None:
    content = (
        f"<!DOCTYPE html><!-- {SENTINEL} --><?pi {SENTINEL} ?>" f"<![CDATA[{SENTINEL}]]><p>Body</p>"
    )
    assert converted(content) == "Body"


# ---------------------------------------------------------------------------
# End-of-input integrity marker: malformed truncation fails closed
# ---------------------------------------------------------------------------

# Sol's three reproductions. Before the integrity check each returned a
# truncated CONVERTED result: "Intro", "Intro", and "A" respectively.
SOL_TRUNCATION_REPRODUCTIONS = [
    "<p>Intro</p><!-- note <p>Requirements: Python</p>",
    '<p>Intro</p><a href="x>More</a><p>Requirements: Python</p>',
    "A<B rest",
]


@pytest.mark.parametrize("content", SOL_TRUNCATION_REPRODUCTIONS)
def test_malformed_truncated_markup_abstains(content: str) -> None:
    assert convert(content) == ContentConversion(text=None, outcome=C.MALFORMED_TRUNCATED_MARKUP)


@pytest.mark.parametrize(
    "content",
    [
        "<p>Intro</p><!",
        "A</",
        "x</p",
        "A<p",
        "A <b",
        "<!-- unterminated",
        "<!x",
        "<![ x",
        "<p>A</p><p title='unterminated>B</p>",
        "&lt;p&gt;Intro&lt;/p&gt;&lt;!-- note &lt;p&gt;Requirements&lt;/p&gt;",
    ],
)
def test_other_unfinished_trailing_constructs_abstain(content: str) -> None:
    assert convert(content) == ContentConversion(text=None, outcome=C.MALFORMED_TRUNCATED_MARKUP)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("A<", "A<"),
        ("A < B", "A < B"),
        ("5 < 6 and 7 > 3", "5 < 6 and 7 > 3"),
        ("<![foo[x]]>after", "after"),
        ("<![CDATA[x]]>after", "after"),
        ("<p>Intro</p><!-- closed --><p>Requirements: Python</p>", "Intro\nRequirements: Python"),
        (
            '<p>Intro</p><a href="x">More</a><p>Requirements: Python</p>',
            "Intro\nMore\nRequirements: Python",
        ),
    ],
)
def test_parser_sensitive_golden_expectations(content: str, expected: str) -> None:
    """Literal golden pins, verified on CPython 3.12.13. The oracle shares the
    parser, so these literals, not the differential test, catch a standard-library
    behavior change; a failure here requires review."""
    assert converted(content) == expected


def test_integrity_marker_name_is_absent_from_the_source() -> None:
    marker = greenhouse_content._integrity_marker
    assert marker("") == "ghintegrity-z"
    assert marker("plain text") == "ghintegrity-z"
    assert marker("ghintegrity-") == "ghintegrity-z"
    assert marker("<ghintegrity-z>") == "ghintegrity-zz"
    assert marker("GHINTEGRITY-ZZZ and ghintegrity-z") == "ghintegrity-zzzz"
    for source in ("x ghintegrity-zzzzzz y", "<GhIntegrity-ZZ></gHiNtEgRiTy-zz>"):
        assert marker(source) not in source.lower()


def test_integrity_marker_selection_is_linear_on_adversarial_input() -> None:
    source = "ghintegrity-" * 15_000 + "ghintegrity-" + "z" * 10_000
    assert greenhouse_content._integrity_marker(source) == "ghintegrity-" + "z" * 10_001


@pytest.mark.parametrize(
    "content",
    [
        "<p>Intro</p><!-- note <ghintegrity-z></ghintegrity-z>",
        # A complete source pair before the truncation: forgeable by a fixed-name or
        # last-two-events check, rejected because the real marker name differs.
        "<p>Intro</p><ghintegrity-z></ghintegrity-z><!-- note <p>Requirements</p>",
        'A<B rest="<ghintegrity-z></ghintegrity-z>',
        "<p>Intro</p><!-- <GHINTEGRITY-Z></GHINTEGRITY-Z> <p>Requirements</p>",
        "&lt;p&gt;Intro&lt;/p&gt;&lt;!-- &lt;ghintegrity-z&gt;&lt;/ghintegrity-z&gt;",
        '<a href="x><ghintegrity-zz></ghintegrity-zz>',
    ],
)
def test_marker_like_source_cannot_forge_the_integrity_check(content: str) -> None:
    assert convert(content).outcome is C.MALFORMED_TRUNCATED_MARKUP


@pytest.mark.parametrize(
    "content",
    [
        "<p>Text <ghintegrity-z>x</ghintegrity-z> end</p>",
        "<p>A</p><ghintegrity-z><ghintegrity-z/></ghintegrity-z><p>B</p>",
        "<GHINTEGRITY-Z></GHINTEGRITY-Z>Hello",
        "&lt;ghintegrity-z&gt;&lt;/ghintegrity-z&gt;&lt;p&gt;Hello&lt;/p&gt;",
        "</ghintegrity-z>Hello<ghintegrity-z>",
    ],
)
def test_marker_like_source_cannot_suppress_valid_conversion(content: str) -> None:
    result = convert(content)
    assert result.outcome is C.CONVERTED
    assert result.text == convert_html_to_text(content, mode="declared-double-escaped")


def test_marker_emits_no_text_or_boundary() -> None:
    assert converted("Hello") == "Hello"
    assert converted("A<b>B</b>") == "AB"
    assert converted("<p>A</p>") == "A"
    assert converted("A&nbsp;") == "A "


def test_caps_measure_source_and_output_text_only() -> None:
    """The marker grows with marker-like runs in the source, but neither cap counts
    marker material: an at-cap source and an at-cap output both still convert."""
    head = "<p>Hello</p><!--"
    run = "ghintegrity-" + "z" * 50_000
    tail = "-->"
    content = head + run + "x" * (MAX_CONTENT_CHARS - len(head) - len(run) - len(tail)) + tail
    assert len(content) == MAX_CONTENT_CHARS
    assert converted(content) == "Hello"
    text = "ghintegrity-" + "z" * (MAX_DESCRIPTION_CHARS - len("ghintegrity-"))
    assert len(text) == MAX_DESCRIPTION_CHARS
    assert converted(text) == text
    assert convert(text + "z").outcome is C.OUTPUT_TOO_LARGE


def test_parser_error_precedes_truncated_markup(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(self: Any) -> None:
        raise RecursionError

    monkeypatch.setattr(greenhouse_content._BlockAwareTextExtractor, "close", explode)
    assert convert("A<B rest").outcome is C.PARSER_ERROR


def test_open_script_or_style_precedes_truncated_markup() -> None:
    assert convert("<p>A</p><script>x").outcome is C.UNCLOSED_SUPPRESSED_ELEMENT
    assert convert("<p>A</p><style>x <!-- y").outcome is C.UNCLOSED_SUPPRESSED_ELEMENT
    # A comment that swallows a would-be script tag is generic truncation.
    assert convert("<p>A</p><!-- <script>").outcome is C.MALFORMED_TRUNCATED_MARKUP


@pytest.mark.parametrize(
    "content",
    [
        "<style>x</style/",
        "<style>B\n</style\r",
        "<style>A</style\t<!-",
        "<p>A</p><style>x</style ",
        "<p>A</p><script>x</script",
    ],
)
def test_dangling_suppressed_end_tag_stays_unclosed(content: str) -> None:
    """The marker's own `<`/`>` would complete a dangling `</style`/`</script` end
    tag; the open element is recorded before the marker is fed."""
    assert convert(content) == ContentConversion(text=None, outcome=C.UNCLOSED_SUPPRESSED_ELEMENT)


@pytest.mark.parametrize(
    "content",
    [
        "A<title>B",
        "A<textarea>B",
        "A<xmp>B",
        "A<iframe>B",
        "A<noembed>B",
        "A<noframes>B",
        "A<p>B</p><plaintext>C",
    ],
)
def test_unclosed_raw_text_element_abstains_disclosed(content: str) -> None:
    """Disclosed behavior change: CPython 3.12.13's `html.parser` treats these
    elements' content as literal text, so an unclosed one swallows the marker (and
    in the oracle turns all later markup into literal text)."""
    assert convert(content) == ContentConversion(text=None, outcome=C.MALFORMED_TRUNCATED_MARKUP)


@pytest.mark.parametrize(
    ("content", "expected"),
    [("A<title>B</title>C", "ABC"), ("A<textarea>B</textarea>C", "ABC")],
)
def test_closed_raw_text_element_converts(content: str, expected: str) -> None:
    assert converted(content) == expected


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (
            '<p>Intro</p><a href="x>More</a><p>Requirements: Python</p><p>Say "hi"</p>',
            "Intro",
        ),
        ("<p>Intro</p><!-- note <p>Req</p><p>x --> y</p>", "Intro\n y"),
    ],
)
def test_mid_input_swallowing_closed_later_is_not_detected_disclosed_limitation(
    content: str, expected: str
) -> None:
    """Disclosed limitation: only end-of-input swallowing is detected. When a later
    quote or `-->` closes the swallowing construct, the lost text is not detected."""
    assert converted(content) == expected


def test_truncated_markup_precedes_meaningfulness_and_output_cap() -> None:
    assert convert("<!-- unterminated").outcome is C.MALFORMED_TRUNCATED_MARKUP
    too_long = "a" * (MAX_DESCRIPTION_CHARS + 1) + "<!--"
    assert convert(too_long).outcome is C.MALFORMED_TRUNCATED_MARKUP


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("<p>Unclosed <strong>tag", "Unclosed tag"),
        ("<p>A</b></i>B</p>", "AB"),
        ("<div><p>A<div>B</p>C", "A\nB\nC"),
        ("<p>A <unknown-tag>B</unknown-tag></p>", "A B"),
    ],
)
def test_malformed_ordinary_tags_are_tolerated(content: str, expected: str) -> None:
    assert converted(content) == expected


# ---------------------------------------------------------------------------
# Unicode whitespace and meaningful text
# ---------------------------------------------------------------------------


def test_nbsp_inside_real_text_is_kept() -> None:
    assert converted("A&nbsp;B") == "A B"
    assert converted("<p>A</p><p>&nbsp;</p><p>B</p>") == "A\n \nB"


def test_unicode_whitespace_and_format_characters_are_preserved() -> None:
    assert converted("A​B C﻿D᠎E") == "A​B C﻿D᠎E"


@pytest.mark.parametrize(
    "content",
    [
        " ",
        "&nbsp;",
        "​",
        "<p> ​ </p>",
        "&lt;p&gt;&amp;nbsp;&amp;#8203;&lt;/p&gt;",
        "﻿ ",
        "<p></p>",
        "<br>",
        f"<script>{SENTINEL}</script>",
    ],
)
def test_nbsp_or_format_only_output_abstains(content: str) -> None:
    assert convert(content) == ContentConversion(text=None, outcome=C.EMPTY_AFTER_CONVERSION)


# ---------------------------------------------------------------------------
# Caps (A7): code points, not bytes; exact cap accepted; cap+1 abstains;
# nothing is truncated.
# ---------------------------------------------------------------------------


def test_caps_are_the_frozen_values() -> None:
    assert MAX_CONTENT_CHARS == 200_000
    assert MAX_DESCRIPTION_CHARS == 100_000


def _padded_to(length: int) -> str:
    head = "<p>Hello</p><!--"
    tail = "-->"
    return head + "x" * (length - len(head) - len(tail)) + tail


def test_input_exactly_at_cap_converts() -> None:
    content = _padded_to(MAX_CONTENT_CHARS)
    assert len(content) == MAX_CONTENT_CHARS
    assert converted(content) == "Hello"


def test_input_cap_plus_one_abstains() -> None:
    assert convert("a" * (MAX_CONTENT_CHARS + 1)) == ContentConversion(
        text=None, outcome=C.INPUT_TOO_LARGE
    )
    assert convert(_padded_to(MAX_CONTENT_CHARS + 1)).outcome is C.INPUT_TOO_LARGE


def test_input_cap_counts_code_points_not_bytes() -> None:
    euro = "€"  # three UTF-8 bytes
    emoji = "\U0001f600"  # four UTF-8 bytes
    at_cap = "<p>Hi</p><!--" + emoji * (MAX_CONTENT_CHARS - 16) + "-->"
    assert len(at_cap) == MAX_CONTENT_CHARS
    assert len(at_cap.encode("utf-8")) > 3 * MAX_CONTENT_CHARS
    assert converted(at_cap) == "Hi"
    assert convert(euro * (MAX_CONTENT_CHARS + 1)).outcome is C.INPUT_TOO_LARGE


def test_output_exactly_at_cap_is_exact() -> None:
    euro = "€"
    assert converted("a" * MAX_DESCRIPTION_CHARS) == "a" * MAX_DESCRIPTION_CHARS
    assert converted(euro * MAX_DESCRIPTION_CHARS) == euro * MAX_DESCRIPTION_CHARS


def test_output_over_cap_abstains_without_truncation() -> None:
    for text in ("a" * (MAX_DESCRIPTION_CHARS + 1), "€" * (MAX_DESCRIPTION_CHARS + 1)):
        assert convert(text) == ContentConversion(text=None, outcome=C.OUTPUT_TOO_LARGE)


def test_validation_order_input_length_precedes_blank_and_encoding() -> None:
    assert convert(" " * (MAX_CONTENT_CHARS + 1)).outcome is C.INPUT_TOO_LARGE
    assert convert("&ltfoo" + "a" * MAX_CONTENT_CHARS).outcome is C.INPUT_TOO_LARGE


def test_validation_order_meaningfulness_precedes_output_length() -> None:
    assert convert(" " * (MAX_DESCRIPTION_CHARS + 1)).outcome is C.EMPTY_AFTER_CONVERSION


# ---------------------------------------------------------------------------
# Parser errors (A6)
# ---------------------------------------------------------------------------


def test_recursion_error_from_parser_is_parser_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(self: Any, data: str) -> None:
        raise RecursionError

    monkeypatch.setattr(greenhouse_content._BlockAwareTextExtractor, "feed", explode)
    assert convert("<p>Hi</p>") == ContentConversion(text=None, outcome=C.PARSER_ERROR)


def test_recursion_error_from_parser_close_is_parser_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(self: Any) -> None:
        raise RecursionError

    monkeypatch.setattr(greenhouse_content._BlockAwareTextExtractor, "close", explode)
    assert convert("<p>Hi</p>").outcome is C.PARSER_ERROR


def test_other_parser_exceptions_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(self: Any, data: str) -> None:
        raise RuntimeError("defect")

    monkeypatch.setattr(greenhouse_content._BlockAwareTextExtractor, "feed", explode)
    with pytest.raises(RuntimeError, match="defect"):
        convert("<p>Hi</p>")


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_conversion_is_deterministic_across_repeated_and_interleaved_calls() -> None:
    inputs = [
        "&lt;p&gt;A&lt;/p&gt;&lt;li&gt;B&lt;/li&gt;",
        "<script>x",
        "<p>C&nbsp;D</p>",
        "&ltfoo",
        "a" * (MAX_DESCRIPTION_CHARS + 1),
    ]
    first = [convert(content) for content in inputs]
    for _ in range(3):
        assert [convert(content) for content in reversed(inputs)] == list(reversed(first))
        assert [convert(content) for content in inputs] == first


# ---------------------------------------------------------------------------
# Differential oracle (A14)
# ---------------------------------------------------------------------------


def test_oracle_script_is_pinned() -> None:
    assert canonical_lf_sha256(ORACLE_SCRIPT) == ORACLE_SCRIPT_CANONICAL_LF_SHA256


def test_oracle_tests_are_pinned() -> None:
    assert canonical_lf_sha256(ORACLE_TESTS) == ORACLE_TESTS_CANONICAL_LF_SHA256


ORACLE_CATEGORIES = {
    "mixed-literal-and-escaped-markup": C.MIXED_LITERAL_AND_ESCAPED_MARKUP,
    "unsupported-angle-reference": C.UNSUPPORTED_ANGLE_REFERENCE,
    "residual-nested-encoding": C.RESIDUAL_NESTED_ENCODING,
}

# Every input literal from the frozen oracle test module, applied under the
# declared mode, plus numeric-reference boundary cases and this module's own
# synthetic inputs.
ORACLE_TEST_VECTORS = [
    "<li>A</li><li>B</li>",
    "<p>Skills:</p><p>Python, Go</p>",
    "<script>alert('x')</script>Hello",
    "<style>.a{color:red}</style>Hello",
    "A &amp; B",
    "A&nbsp;B",
    "<p>A</p>\r\n<p>B</p>",
    "<p>A</p>\r<p>B</p>",
    "<div><p>Hello</p></div><div><p>World</p></div>",
    "Hello     World",
    "Hello\t\tWorld",
    "<p>Hello <strong>World</strong></p>",
    "<p>A</p><p></p><p>B</p>",
    "<p>A</p><p></p><p></p><p></p><p>B</p>",
    "<p>A</p>\n\n\n<p>B</p>",
    "<p>A</p><p>&nbsp;</p><p>B</p>",
    "A<br>B",
    "<div><p>A</p></div>",
    "A&#8203;B",
    "<p>Unclosed <strong>tag",
    "<script>never closed<p>fake para</p>",
    "<style>never closed<p>fake para</p>",
    "<script>alert(1)</script><p>Real text</p>",
    "A&#13;B",
    "A&#13;&#10;B",
    "<p>A</p>&#13;<p>B</p>",
    "<p>Hello</p>",
    "&lt;p&gt;Hello&lt;/p&gt;",
    "&#60;p&#62;Hello&#60;/p&#62;",
    "&#x3c;p&#x3e;Hello&#x3c;/p&#x3e;",
    "&amp;lt;p&amp;gt;Hello&amp;lt;/p&amp;gt;",
    "<p>Hello &lt;b&gt;world&lt;/b&gt;</p>",
    "<p>Use &lt;script&gt; as text</p>",
    "&lt;p&gt;Use &amp;lt;script&amp;gt; as text&lt;/p&gt;",
    "A&ltB",
    "&ltfoo",
    "&lt",
    "&ltimes;",
    "&#600;",
    "&#0600;",
    "&#x3cafe;",
    "&#x03c0;",
    "&LT;p&GT;Hello&LT;/p&GT;",
    "<p>Hello &LT;b&GT;world&LT;/b&GT;</p>",
    "&LTfoo",
    "&GTfoo",
    "&LT",
    "&GT",
    "&amp;LT;p&amp;GT;Hello&amp;LT;/p&amp;GT;",
    "&Lt;",
    "&Gt;",
]

NUMERIC_BOUNDARY_VECTORS = [
    "&#60",
    "&#60x",
    "&#060;p&#062;A",
    "&#00060;",
    "&#601;",
    "&#6;",
    "&#600",
    "a&#60b",
    "&#x3c",
    "&#x3C;p&#X3E;A",
    "&#x003c;",
    "&#x3cg",
    "&#x3ca;",
    "&#x3e0;",
    "&#x3E",
    "<p>&#60</p>",
    "<p>&#600;</p>",
    "<p>&#x3c0;</p>",
    "&amp;#60;",
    "&amp;#x3c;",
    "&amp;#600;",
]

SYNTHETIC_VECTORS = [
    "&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;",
    "<p>Hello <b>world</b></p>",
    "&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;li&gt;Go&lt;/li&gt;&lt;/ul&gt;",
    "&lt;p&gt;A &Lt; B&lt;/p&gt;",
    "A &amp;amp; B",
    "<table><tr><td>Python</td><td>Go</td></tr></table>",
    "<noscript>A</noscript><template>B</template>",
    f"<!DOCTYPE html><!-- {SENTINEL} --><p>Body</p>",
    "A​B C﻿D",
    "&amp;ltfoo",
    "<p> </p>",
    "<p></p>",
    "   ",
]


def _meaningful(text: str) -> bool:
    return any(not (char.isspace() or unicodedata.category(char) == "Cf") for char in text)


@pytest.mark.parametrize(
    "content", ORACLE_TEST_VECTORS + NUMERIC_BOUNDARY_VECTORS + SYNTHETIC_VECTORS
)
def test_agrees_with_the_frozen_oracle(content: str) -> None:
    mine = convert(content)
    try:
        expected = convert_html_to_text(content, mode="declared-double-escaped")
    except HtmlDoubleEncodingError as error:
        assert mine.outcome is ORACLE_CATEGORIES[error.category]
        return
    except HtmlConversionError:
        assert mine.outcome is C.UNCLOSED_SUPPRESSED_ELEMENT
        return
    if mine.outcome is C.CONVERTED:
        assert mine.text == expected
    elif mine.outcome is C.MALFORMED_TRUNCATED_MARKUP:
        # The oracle has no end-of-input integrity check: for these inputs it
        # returns whatever text preceded the unfinished construct.
        assert isinstance(expected, str)
    else:
        # The oracle has no blank/meaningfulness abstention; it returns text
        # that carries no meaning, which this module abstains on.
        assert mine.outcome in (C.BLANK, C.EMPTY_AFTER_CONVERSION)
        assert not _meaningful(expected)


@pytest.mark.parametrize("content", ["&#60x", "a&#60b", "&#x3cg"])
def test_oracle_numeric_fragments_now_abstain_as_truncated(content: str) -> None:
    """Each decodes to a `<letter` fragment that swallows the end of the input;
    the oracle silently drops it, this module abstains."""
    assert convert(content) == ContentConversion(text=None, outcome=C.MALFORMED_TRUNCATED_MARKUP)


def test_oracle_vectors_exercise_every_shared_category() -> None:
    outcomes = {
        convert(content).outcome
        for content in ORACLE_TEST_VECTORS + NUMERIC_BOUNDARY_VECTORS + SYNTHETIC_VECTORS
    }
    assert outcomes >= {
        C.CONVERTED,
        C.BLANK,
        C.EMPTY_AFTER_CONVERSION,
        C.MIXED_LITERAL_AND_ESCAPED_MARKUP,
        C.UNSUPPORTED_ANGLE_REFERENCE,
        C.RESIDUAL_NESTED_ENCODING,
        C.UNCLOSED_SUPPRESSED_ELEMENT,
        C.MALFORMED_TRUNCATED_MARKUP,
    }


# ---------------------------------------------------------------------------
# Import boundary (A19)
# ---------------------------------------------------------------------------


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module is not None
            names.add(node.module)
    return names


def test_content_module_import_allow_list() -> None:
    assert _imported_modules(CONTENT_MODULE) == {
        "__future__",
        "dataclasses",
        "enum",
        "html",
        "html.parser",
        "re",
        "typing",
        "unicodedata",
    }


def test_content_module_has_no_dynamic_import_execution_io_or_logging() -> None:
    tree = ast.parse(CONTENT_MODULE.read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    # `compile` is checked as a bare builtin name only: `re.compile` is expected.
    assert not names & {"__import__", "importlib", "exec", "eval", "compile", "open", "print"}
    assert not attributes & {"__import__", "import_module", "system", "popen"}
