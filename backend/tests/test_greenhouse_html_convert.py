import pytest

from scripts.greenhouse_html_convert import HtmlConversionError, convert_html_to_text


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
