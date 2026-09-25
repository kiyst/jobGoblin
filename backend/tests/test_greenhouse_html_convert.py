import pytest

from scripts.greenhouse_html_convert import (
    _ESCAPED_ANGLE_REFERENCE_RE,
    _UNTERMINATED_NAMED_ANGLE_RE,
    HtmlConversionError,
    HtmlDoubleEncodingError,
    convert_html_to_text,
)


def test_adjacent_list_items_do_not_concatenate() -> None:
    assert convert_html_to_text("<li>A</li><li>B</li>") == "A\nB"


def test_block_boundary_preserves_terminal_punctuation() -> None:
    assert convert_html_to_text("<p>Skills:</p><p>Python, Go</p>") == "Skills:\nPython, Go"


def test_script_content_is_suppressed() -> None:
    assert convert_html_to_text("<script>alert('x')</script>Hello") == "Hello"


def test_style_content_is_suppressed() -> None:
    assert convert_html_to_text("<style>.a{color:red}</style>Hello") == "Hello"


def test_named_entity_is_decoded() -> None:
    assert convert_html_to_text("A &amp; B") == "A & B"


def test_nbsp_entity_is_preserved_not_collapsed() -> None:
    result = convert_html_to_text("A&nbsp;B")
    assert result == "A B"
    assert " " in result


def test_crlf_line_endings_are_normalized() -> None:
    """The `\r\n` between the tags is itself a source whitespace text
    node (like the blank-line-collapse case below), not tag-boundary
    insertion -- normalized to one `\n`, contributing one blank line."""
    assert convert_html_to_text("<p>A</p>\r\n<p>B</p>") == "A\n\nB"


def test_bare_cr_line_endings_are_normalized() -> None:
    assert convert_html_to_text("<p>A</p>\r<p>B</p>") == "A\n\nB"


def test_nested_block_tags_do_not_accumulate_blank_lines() -> None:
    html = "<div><p>Hello</p></div><div><p>World</p></div>"
    assert convert_html_to_text(html) == "Hello\nWorld"


def test_horizontal_space_run_collapses_to_one_space() -> None:
    assert convert_html_to_text("Hello     World") == "Hello World"


def test_horizontal_tab_run_collapses_to_one_space() -> None:
    assert convert_html_to_text("Hello\t\tWorld") == "Hello World"


def test_inline_tags_insert_no_boundary() -> None:
    assert convert_html_to_text("<p>Hello <strong>World</strong></p>") == "Hello World"


def test_empty_paragraph_contributes_no_extra_boundary() -> None:
    """An empty `<p></p>` sits between two boundaries already inserted by
    its neighbors' own close/open tags -- boundary insertion dedupes at
    the source, so this never produces a visible blank line, consistent
    with the nested-block-tags case above."""
    assert convert_html_to_text("<p>A</p><p></p><p>B</p>") == "A\nB"


def test_multiple_consecutive_empty_paragraphs_contribute_no_extra_boundary() -> None:
    assert convert_html_to_text("<p>A</p><p></p><p></p><p></p><p>B</p>") == "A\nB"


def test_source_whitespace_text_nodes_collapse_to_one_blank_line() -> None:
    """Unlike tag-boundary insertion (deduped at the source), literal
    whitespace *text* between sibling tags in the raw HTML is ordinary
    `handle_data` content and can genuinely produce several blank lines
    -- this is what `_collapse_blank_lines` exists to reduce to one."""
    assert convert_html_to_text("<p>A</p>\n\n\n<p>B</p>") == "A\n\nB"


def test_line_of_only_nbsp_is_not_treated_as_blank() -> None:
    html = "<p>A</p><p>&nbsp;</p><p>B</p>"
    result = convert_html_to_text(html)
    assert result == "A\n \nB"


def test_br_inserts_a_boundary() -> None:
    assert convert_html_to_text("A<br>B") == "A\nB"


def test_leading_and_trailing_newlines_are_stripped() -> None:
    assert convert_html_to_text("<div><p>A</p></div>") == "A"


def test_zero_width_space_entity_is_preserved() -> None:
    result = convert_html_to_text("A&#8203;B")
    assert result == "A​B"


def test_malformed_html_does_not_raise() -> None:
    convert_html_to_text("<p>Unclosed <strong>tag")


def test_unclosed_script_raises_instead_of_silently_truncating() -> None:
    """`HTMLParser` treats `<script>` as CDATA and only exits on a
    literal matching end tag -- an unclosed one would otherwise discard
    every character after it, including real description text, with no
    signal that the result is truncated rather than genuinely short."""
    with pytest.raises(HtmlConversionError):
        convert_html_to_text("<script>never closed<p>fake para</p>")


def test_unclosed_style_raises_instead_of_silently_truncating() -> None:
    with pytest.raises(HtmlConversionError):
        convert_html_to_text("<style>never closed<p>fake para</p>")


def test_properly_closed_script_does_not_raise() -> None:
    assert convert_html_to_text("<script>alert(1)</script><p>Real text</p>") == "Real text"


def test_entity_encoded_cr_is_normalized() -> None:
    """`_normalize_line_endings` runs on the raw markup before parsing,
    which only catches a *literal* `\\r` byte in the source. A character
    reference like `&#13;` is decoded by `HTMLParser` *during* parsing,
    after that first pass already ran -- normalizing the fully extracted
    text again afterward is what actually catches this."""
    result = convert_html_to_text("A&#13;B")
    assert "\r" not in result
    assert result == "A\nB"


def test_entity_encoded_crlf_is_normalized() -> None:
    result = convert_html_to_text("A&#13;&#10;B")
    assert "\r" not in result
    assert result == "A\nB"


def test_entity_encoded_cr_between_block_tags_is_normalized() -> None:
    result = convert_html_to_text("<p>A</p>&#13;<p>B</p>")
    assert "\r" not in result


# ---------------------------------------------------------------------------
# Input-mode contract
# ---------------------------------------------------------------------------
def test_standard_is_the_default_mode() -> None:
    assert convert_html_to_text("<p>Hello</p>") == convert_html_to_text(
        "<p>Hello</p>", mode="standard"
    )


def test_unknown_mode_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unknown content mode"):
        convert_html_to_text("<p>Hello</p>", mode="not-a-real-mode")  # type: ignore[arg-type]


def test_html_double_encoding_error_is_an_html_conversion_error() -> None:
    assert issubclass(HtmlDoubleEncodingError, HtmlConversionError)


# ---------------------------------------------------------------------------
# declared-double-escaped mode -- success cases
# ---------------------------------------------------------------------------
def test_declared_mode_decodes_named_entity_form() -> None:
    assert (
        convert_html_to_text("&lt;p&gt;Hello&lt;/p&gt;", mode="declared-double-escaped") == "Hello"
    )


def test_declared_mode_decodes_decimal_numeric_form() -> None:
    assert (
        convert_html_to_text("&#60;p&#62;Hello&#60;/p&#62;", mode="declared-double-escaped")
        == "Hello"
    )


def test_declared_mode_decodes_hex_numeric_form() -> None:
    assert (
        convert_html_to_text("&#x3c;p&#x3e;Hello&#x3c;/p&#x3e;", mode="declared-double-escaped")
        == "Hello"
    )


def test_declared_mode_on_already_real_markup_passes_through() -> None:
    """No escaped form at all -- stage 1 finds nothing to reject, the one
    permitted `html.unescape()` call is a no-op, and conversion proceeds
    normally."""
    assert convert_html_to_text("<p>Hello</p>", mode="declared-double-escaped") == "Hello"


# ---------------------------------------------------------------------------
# declared-double-escaped mode -- nested-encoding rejection
# ---------------------------------------------------------------------------
def test_declared_mode_rejects_nested_named_encoding() -> None:
    with pytest.raises(HtmlDoubleEncodingError) as exc_info:
        convert_html_to_text(
            "&amp;lt;p&amp;gt;Hello&amp;lt;/p&amp;gt;", mode="declared-double-escaped"
        )
    assert exc_info.value.category == "residual-nested-encoding"


# ---------------------------------------------------------------------------
# declared-double-escaped mode -- mixed-content rejection
# ---------------------------------------------------------------------------
def test_declared_mode_rejects_mixed_literal_and_escaped_markup() -> None:
    with pytest.raises(HtmlDoubleEncodingError) as exc_info:
        convert_html_to_text(
            "<p>Hello &lt;b&gt;world&lt;/b&gt;</p>", mode="declared-double-escaped"
        )
    assert exc_info.value.category == "mixed-literal-and-escaped-markup"


# ---------------------------------------------------------------------------
# Intentional escaped-code example -- preserved under standard mode,
# rejected under declared mode (accepted limitation).
# ---------------------------------------------------------------------------
def test_standard_mode_preserves_intentional_escaped_code_example() -> None:
    assert convert_html_to_text("<p>Use &lt;script&gt; as text</p>") == "Use <script> as text"


def test_declared_mode_rejects_escaped_code_example_as_mixed_content() -> None:
    """This single-encoded document has a real `<p>` tag *and* an
    escaped-looking `&lt;script&gt;` example -- explicit mode cannot
    tell this apart from genuinely mixed encoding, so it rejects it. A
    caller with content like this should have declared `"standard"`."""
    with pytest.raises(HtmlDoubleEncodingError) as exc_info:
        convert_html_to_text("<p>Use &lt;script&gt; as text</p>", mode="declared-double-escaped")
    assert exc_info.value.category == "mixed-literal-and-escaped-markup"


def test_declared_mode_accepted_limitation_false_positive_on_one_outer_layer() -> None:
    """The documented accepted limitation: this is the *correct*
    one-outer-layer-escaped equivalent of the previous test's legitimate
    document -- it decodes at stage 2 to exactly that legitimate
    document, but stage 3 cannot distinguish the surviving
    `&lt;script&gt;` example from a genuine unresolved second layer, so
    it is rejected too."""
    with pytest.raises(HtmlDoubleEncodingError) as exc_info:
        convert_html_to_text(
            "&lt;p&gt;Use &amp;lt;script&amp;gt; as text&lt;/p&gt;",
            mode="declared-double-escaped",
        )
    assert exc_info.value.category == "residual-nested-encoding"


# ---------------------------------------------------------------------------
# Missing-semicolon legacy forms
# ---------------------------------------------------------------------------
def test_standard_mode_decodes_missing_semicolon_legacy_form() -> None:
    assert convert_html_to_text("A&ltB") == "A<B"


def test_standard_mode_decodes_truncated_fragment_followed_by_text() -> None:
    assert convert_html_to_text("&ltfoo") == "<foo"


def test_declared_mode_rejects_semicolonless_named_form() -> None:
    with pytest.raises(HtmlDoubleEncodingError) as exc_info:
        convert_html_to_text("&ltfoo", mode="declared-double-escaped")
    assert exc_info.value.category == "unsupported-angle-reference"


def test_declared_mode_rejects_bare_semicolonless_lt() -> None:
    with pytest.raises(HtmlDoubleEncodingError) as exc_info:
        convert_html_to_text("&lt", mode="declared-double-escaped")
    assert exc_info.value.category == "unsupported-angle-reference"


# ---------------------------------------------------------------------------
# Forms that must NOT be classified as an escaped angle reference by
# `_ESCAPED_ANGLE_REFERENCE_RE` -- a distinct, unrelated named entity, or
# a numeric reference whose value is not 0x3C/0x3E.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    ["&ltimes;", "&#600;", "&#0600;", "&#x3cafe;", "&#x03c0;"],
)
def test_not_classified_as_an_escaped_angle_reference(text: str) -> None:
    assert _ESCAPED_ANGLE_REFERENCE_RE.search(text) is None


def test_ltimes_is_a_real_distinct_entity_under_standard_mode() -> None:
    """`&ltimes;` decodes to U+22C9 ('LESS-THAN WITH TIMES'), a real,
    unrelated named HTML5 entity -- nothing to do with `<`. Standard
    mode is completely unaffected by the declared-mode grammar."""
    assert convert_html_to_text("&ltimes;") == "⋉"


def test_ltimes_is_rejected_under_declared_mode_via_the_unterminated_check() -> None:
    """Even though `&ltimes;` is not classified as an escaped angle
    reference by `_ESCAPED_ANGLE_REFERENCE_RE` (previous test), it *is*
    caught by the separate, deliberately blunt
    `_UNTERMINATED_NAMED_ANGLE_RE` check: `&lt` immediately followed by a
    non-`;` character ('i') matches, regardless of what the rest of the
    string spells out. `declared-double-escaped` mode does not attempt
    to look ahead for a longer, different, valid entity name -- every
    semicolonless-looking `&lt`/`&gt` prefix is rejected uniformly."""
    assert _UNTERMINATED_NAMED_ANGLE_RE.search("&ltimes;") is not None
    with pytest.raises(HtmlDoubleEncodingError) as exc_info:
        convert_html_to_text("&ltimes;", mode="declared-double-escaped")
    assert exc_info.value.category == "unsupported-angle-reference"
