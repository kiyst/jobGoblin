"""Mechanical, parser-independent string transforms (Workflow v3.2 Slice
2). Every function here is a pure `str -> str` mutator taking explicit,
deterministic parameters. None of these functions makes any claim about
what a parser should do with its output -- that applicability claim is
stated per case record, never attached to a transform's identity (see
`docs/DECISIONS/` Slice 2 proposal, binding decision 1).

All offsets are Python Unicode code-point indices (an ordinary Python
`str` index), not byte offsets -- Python strings are already sequences
of code points. Transformed-input validation elsewhere in this harness
uses exact Python string equality (`==`), never a byte-level comparison.
"""

from __future__ import annotations

import string
import unicodedata

from tests.contracts.schema import ContractRecordError

_ASCII_LETTERS = frozenset(string.ascii_letters)

_FULLWIDTH_DIGIT_OFFSET = 0xFF10 - ord("0")
_FULLWIDTH_UPPER_OFFSET = 0xFF21 - ord("A")
_FULLWIDTH_LOWER_OFFSET = 0xFF41 - ord("a")


def ascii_recase(text: str, mode: str) -> str:
    """Re-cases ASCII letters in `text` per `mode`; every other character
    is left untouched. `mode="mixed"` alternates upper/lower
    deterministically by ordinal position **among ASCII letters only**
    (a non-letter character does not advance the alternation counter)."""
    if mode not in ("upper", "lower", "mixed"):
        raise ContractRecordError(f"unsupported ascii_recase mode: {mode!r}")
    if mode == "upper":
        return "".join(c.upper() if c in _ASCII_LETTERS else c for c in text)
    if mode == "lower":
        return "".join(c.lower() if c in _ASCII_LETTERS else c for c in text)
    result: list[str] = []
    letter_index = 0
    for c in text:
        if c in _ASCII_LETTERS:
            result.append(c.upper() if letter_index % 2 == 0 else c.lower())
            letter_index += 1
        else:
            result.append(c)
    return "".join(result)


def _fullwidth_char(c: str) -> str:
    if c.isdigit() and c in string.digits:
        return chr(ord(c) + _FULLWIDTH_DIGIT_OFFSET)
    if c in string.ascii_uppercase:
        return chr(ord(c) + _FULLWIDTH_UPPER_OFFSET)
    if c in string.ascii_lowercase:
        return chr(ord(c) + _FULLWIDTH_LOWER_OFFSET)
    return c


def nfkc_fullwidth_substitute(text: str, start: int, end: int) -> str:
    """Replaces the ASCII digits/letters in `text[start:end]` (a
    code-point-index span) with their NFKC-compatible fullwidth code
    points. Every character in the span that is not an ASCII digit or
    letter is left unchanged."""
    if not (0 <= start <= end <= len(text)):
        raise ContractRecordError(
            f"nfkc_fullwidth_substitute span out of range: start={start}, end={end}, "
            f"len(text)={len(text)}"
        )
    span = "".join(_fullwidth_char(c) for c in text[start:end])
    result = text[:start] + span + text[end:]
    # Sanity: the substituted span must genuinely NFKC-fold back to the
    # original ASCII span, or this transform's own safety claim (used
    # only where a case record states it) would be self-contradictory.
    if unicodedata.normalize("NFKC", span) != text[start:end]:
        raise ContractRecordError(
            "nfkc_fullwidth_substitute produced a span that does not "
            "NFKC-fold back to the original text"
        )
    return result


def insert_codepoint(text: str, codepoint: str, position: int) -> str:
    """Inserts exactly one Unicode code point at a code-point-index
    position."""
    if len(codepoint) != 1:
        raise ContractRecordError(
            f"insert_codepoint requires a single code point, got {codepoint!r}"
        )
    if not (0 <= position <= len(text)):
        raise ContractRecordError(
            f"insert_codepoint position out of range: position={position}, len(text)={len(text)}"
        )
    return text[:position] + codepoint + text[position:]


def append_codepoints(text: str, codepoints: str) -> str:
    """Appends `codepoints` verbatim to the end of `text`."""
    return text + codepoints


def remove_boundary(text: str, start: int, end: int) -> str:
    """Deletes `text[start:end]` (a code-point-index span) verbatim --
    used to construct 'glued' variants by deleting a separator."""
    if not (0 <= start <= end <= len(text)):
        raise ContractRecordError(
            f"remove_boundary span out of range: start={start}, end={end}, len(text)={len(text)}"
        )
    return text[:start] + text[end:]


def apply_transform(text: str, name: str, parameters: dict[str, object]) -> str:
    """Dispatches to the named mechanical transform. `name="none"`
    (identity) is handled directly; every other name must match one of
    this module's functions exactly, with `parameters` matching that
    function's own declared arguments -- an unrecognized name or a
    malformed parameter set raises `ContractRecordError` rather than
    silently doing nothing."""
    if name == "none":
        if parameters:
            raise ContractRecordError(f"transform 'none' takes no parameters, got {parameters!r}")
        return text
    if name == "ascii_recase":
        return ascii_recase(text, _require_str(parameters, "mode"))
    if name == "nfkc_fullwidth_substitute":
        return nfkc_fullwidth_substitute(
            text, _require_int(parameters, "start"), _require_int(parameters, "end")
        )
    if name == "insert_codepoint":
        return insert_codepoint(
            text, _require_str(parameters, "codepoint"), _require_int(parameters, "position")
        )
    if name == "append_codepoints":
        return append_codepoints(text, _require_str(parameters, "codepoints"))
    if name == "remove_boundary":
        return remove_boundary(
            text, _require_int(parameters, "start"), _require_int(parameters, "end")
        )
    raise ContractRecordError(f"unrecognized transform name: {name!r}")


def _require_int(parameters: dict[str, object], key: str) -> int:
    if key not in parameters:
        raise ContractRecordError(f"transform parameter {key!r} is required")
    value = parameters[key]
    # Explicitly reject bool (a subclass of int in Python) and float
    # (even an integral one, e.g. 3.0) posing as an int parameter.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractRecordError(
            f"transform parameter {key!r} must be an int, got {type(value).__name__}: {value!r}"
        )
    return value


def _require_str(parameters: dict[str, object], key: str) -> str:
    if key not in parameters:
        raise ContractRecordError(f"transform parameter {key!r} is required")
    value = parameters[key]
    if not isinstance(value, str):
        raise ContractRecordError(
            f"transform parameter {key!r} must be a str, got {type(value).__name__}: {value!r}"
        )
    return value
