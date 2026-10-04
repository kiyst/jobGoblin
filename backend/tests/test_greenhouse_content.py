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


@pytest.mark.parametrize(
    ("content", "outcome", "text"),
    [
        ("<p>Intro</p><!-- note <p>Requirements: Python</p>", C.CONVERTED, "Intro"),
        (
            '<p>Intro</p><a href="x>More</a><p>Requirements: Python</p>',
            C.CONVERTED,
            "Intro",
        ),
        ("A<B rest", C.CONVERTED, "A"),
        ("<p>Intro</p><!", C.CONVERTED, "Intro"),
        ("A</", C.CONVERTED, "A</"),
        ("A<", C.CONVERTED, "A<"),
        ("<![ x", C.EMPTY_AFTER_CONVERSION, None),
        ("<!x", C.EMPTY_AFTER_CONVERSION, None),
        ("<!-- unterminated", C.EMPTY_AFTER_CONVERSION, None),
        ("<![foo[x]]>after", C.CONVERTED, "after"),
        ("<![CDATA[x]]>after", C.CONVERTED, "after"),
    ],
)
def test_parser_sensitive_golden_expectations_disclosed_limitation(
    content: str, outcome: ContentOutcome, text: str | None
) -> None:
    """Literal golden pins, verified on CPython 3.12.13. An unterminated comment,
    quoted attribute, or `<letter` silently truncates the rest while the outcome
    stays CONVERTED (inherited from `html.parser` and the oracle). The oracle
    shares the parser, so these literals, not the differential test, catch a
    standard-library behavior change; a failure here requires review."""
    assert convert(content) == ContentConversion(text=text, outcome=outcome)


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
    else:
        # The oracle has no blank/meaningfulness abstention; it returns text
        # that carries no meaning, which this module abstains on.
        assert mine.outcome in (C.BLANK, C.EMPTY_AFTER_CONVERSION)
        assert not _meaningful(expected)


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
