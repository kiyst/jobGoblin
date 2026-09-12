"""Committed, replayable mutation selectors for every active guard
(Workflow v3.2 Slice 2, binding clarifications 3/4/8). Two mutation
kinds:

- **Simple**: swaps a module-level constant/compiled-pattern object (or
  a small, atomic, single-purpose helper function) on the *live*
  imported module via monkeypatch, then restores the original. Never
  touches the shared checkout or any file on disk.
- **Structural**: reads the real source file's text from disk (never
  writing it back), asserts an exact anchor substring occurs exactly
  once, builds mutated source text, and loads it as a freshly-named,
  fully isolated module via `importlib` -- the already-imported
  `app.normalization.*` module object and the file on disk are never
  touched.

Every entry carries deterministic fingerprints of the *whole* production
source file, the corresponding contract record, and the *whole* adapter
file -- file-level granularity, not a narrower anchor/region hash. This
is a disclosed limitation, not region-level precision: an unrelated
edit anywhere in a parser's file (e.g. a docstring fix) will trip every
guard's staleness check for that parser, which is over-broad but never
under-broad. These fingerprints are committed baseline values (see
`_FROZEN_SOURCE_FP`/`_FROZEN_ADAPTER_FP`/`_FROZEN_RECORD_FP` below),
frozen at the time this correction was authored -- never recomputed
from current files at import time, which would make the staleness
check compare a file against itself and could never detect drift. The
mutation runner recomputes each fingerprint fresh, from whatever is
actually on disk when it runs, and compares against these frozen
values, so real drift since this baseline was committed is detected.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from tests.contracts.schema import ContractRecordError

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_RECORDS_DIR = Path(__file__).resolve().parent / "records"


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def fingerprint_file(relative_path: str) -> str:
    return _fingerprint((_BACKEND_ROOT / relative_path).read_text(encoding="utf-8"))


def fingerprint_record(record_id: str, parser: str) -> str:
    data = json.loads((_RECORDS_DIR / f"{parser}.json").read_text(encoding="utf-8"))
    for raw in data["records"]:
        if raw["record_id"] == record_id:
            return _fingerprint(json.dumps(raw, sort_keys=True))
    raise ContractRecordError(f"fingerprint_record: {record_id!r} not found in {parser}.json")


@dataclass(frozen=True)
class SimpleMutation:
    kind: Literal["simple"]
    guard_ref: str
    record_id: str
    parser: str
    module_path: str
    mutate: Callable[[Any], dict[str, object]]
    input_: dict[str, str | None]
    erroneous_output: dict[str, tuple[object, str]]
    source_fingerprint: str = field(default="")
    record_fingerprint: str = field(default="")
    adapter_fingerprint: str = field(default="")


@dataclass(frozen=True)
class StructuralMutation:
    kind: Literal["structural"]
    guard_ref: str
    record_id: str
    parser: str
    module_path: str
    source_file: str
    anchor: str
    replacement: str
    input_: dict[str, str | None]
    erroneous_output: dict[str, tuple[object, str]]
    source_fingerprint: str = field(default="")
    record_fingerprint: str = field(default="")
    adapter_fingerprint: str = field(default="")


Mutation = SimpleMutation | StructuralMutation

_SOURCE_FILE = {
    "location": "app/normalization/location.py",
    "salary": "app/normalization/salary.py",
    "experience": "app/normalization/experience.py",
}
_ADAPTER_FILE = {
    "location": "tests/contracts/adapters/location.py",
    "salary": "tests/contracts/adapters/salary.py",
    "experience": "tests/contracts/adapters/experience.py",
}

# ---------------------------------------------------------------------------
# Committed baseline fingerprints (Workflow v3.2 Slice 2, binding
# clarification 4 -- corrected). These are FROZEN values, computed once
# against the exact source/record/adapter content this correction
# commit ships, and never recomputed at import time. The witness script
# (`scripts/contract_mutation_witnesses.py`) recomputes each fingerprint
# fresh from whatever is on disk *when it runs* and compares against
# these committed values -- a real staleness check, since the two
# computations happen at genuinely different times (commit time here,
# vs. run time there), unlike an earlier draft of this file that
# recomputed both sides from the same current files in the same import
# and could never detect drift. Regenerate these three tables (never by
# hand) whenever a covered guard's production source, adapter, or
# contract record changes -- see the module docstring.
# ---------------------------------------------------------------------------

_FROZEN_SOURCE_FP: dict[str, str] = {
    "location": "acc97c36b99434d7",
    "salary": "e15a6180dd122f1e",
    "experience": "f0668c3a76a1b29a",
}
_FROZEN_ADAPTER_FP: dict[str, str] = {
    "location": "274c19eaa69a138b",
    "salary": "1daba92cc73415d3",
    "experience": "dfa142423607a5a3",
}
_FROZEN_RECORD_FP: dict[str, str] = {
    "experience/g01-attribution-frame": "443242f08d541811",
    "experience/g02-continuation-boundary": "258262363c124b21",
    "experience/g03-individual-number-redaction": "7c2e007b2628d5e3",
    "experience/g04-positional-preference-suppression": "5a30869352ef6d1d",
    "experience/g05-internal-conflict-precedence": "1e984335cd9cd752",
    "experience/g06-original-unicode-hyphen-disambiguation": "6aefe28e459b1ab9",
    "experience/g08-title-leading-preference": "beadf8c28e9682bd",
    "experience/g09-cross-segment-qualifier-following": "c18bcc33a6ae41cd",
    "experience/g10-trailing-bound-marker": "f334513523c4a2a0",
    "experience/g11-unsupported-prefix-poison": "d6ef7fd9a55a2cf6",
    "experience/g12-fraction-slash-normalization": "d1770da42c102fa1",
    "experience/g13-unicode-dash-poison": "231ef9c108ead5e5",
    "experience/g14-multi-candidate-collection": "4983de8b1d4f9a0a",
    "experience/g15-title-segment-order-preservation": "b17efdcc3c2a0139",
    "experience/g16-bidirectional-adjacency": "89212d1673a0058c",
    "experience/g17-composite-range-poison-decimal-fraction": "cc116ed2254db73b",
    "experience/g18-description-label-value-scope-removed": "f28bb6322e35a423",
    "experience/g19-title-label-value-whole-anchor": "6e42700649b47992",
    "experience/g20-empty-segment-adjacency": "32751e6c0cb3af0b",
    "experience/g21-composite-range-poison-negative": "47fd63f7b58431a2",
    "experience/g22-composite-poison-casefold": "2da41be2d919f50b",
    "location/g01-alias-trailing-period": "d1e09be3152020ee",
    "location/g02-state-zip-provenance": "60197ea3aab09753",
    "location/g03-region-whitespace-trim": "9346a33e1de16442",
    "location/g04-negation-standalone-word": "5d5b344dec6af6a5",
    "location/g05-country-conflict-discarded-span": "52294cefdd3a52df",
    "location/g06-ascii-only-casefold": "04dfc26dd1089acb",
    "location/g07-state-precedence-over-coordinator": "49ee461c6003ff8d",
    "location/g08-exact-state-token-grammar": "f04e71cc735d438d",
    "salary/g01-covered-whitespace-class": "cb24070a3e5463ab",
    "salary/g02-label-boundary-strictness": "296a623056b82cb7",
    "salary/g03-currency-code-boundary-strictness": "a111ee905075950c",
    "salary/g04-period-boundary-by-shape": "9090c750c0be5b39",
    "salary/g05-up-to-narrowed-forms": "66bd5ac4130fe212",
}


def _finalize(entries: list[Mutation]) -> dict[str, Mutation]:
    """Fills in every entry's three fingerprints from the committed
    baseline tables above (never recomputed from current files here),
    then returns the guard_ref-keyed registry. Staleness is detected
    later, at witness-run time, by recomputing each fingerprint fresh
    from whatever is on disk *then* and comparing against these frozen
    values."""
    out: dict[str, Mutation] = {}
    for entry in entries:
        source_fp = _FROZEN_SOURCE_FP[entry.parser]
        record_fp = _FROZEN_RECORD_FP[entry.guard_ref]
        adapter_fp = _FROZEN_ADAPTER_FP[entry.parser]
        if isinstance(entry, SimpleMutation):
            filled: Mutation = SimpleMutation(
                kind="simple",
                guard_ref=entry.guard_ref,
                record_id=entry.record_id,
                parser=entry.parser,
                module_path=entry.module_path,
                mutate=entry.mutate,
                input_=entry.input_,
                erroneous_output=entry.erroneous_output,
                source_fingerprint=source_fp,
                record_fingerprint=record_fp,
                adapter_fingerprint=adapter_fp,
            )
        else:
            filled = StructuralMutation(
                kind="structural",
                guard_ref=entry.guard_ref,
                record_id=entry.record_id,
                parser=entry.parser,
                module_path=entry.module_path,
                source_file=entry.source_file,
                anchor=entry.anchor,
                replacement=entry.replacement,
                input_=entry.input_,
                erroneous_output=entry.erroneous_output,
                source_fingerprint=source_fp,
                record_fingerprint=record_fp,
                adapter_fingerprint=adapter_fp,
            )
        if out.setdefault(entry.guard_ref, filled) is not filled:
            raise ContractRecordError(
                f"duplicate mutation-registry selector for {entry.guard_ref!r}"
            )
    return out


# ---------------------------------------------------------------------------
# location.py -- 8 active guards.
# ---------------------------------------------------------------------------


def _rebuild_location_productions(
    module: Any, *, country_token: str | None = None, ascii_flag: bool = True
) -> dict[str, re.Pattern[str]]:
    ct = country_token if country_token is not None else module._COUNTRY_TOKEN
    ws = module._WS
    marker_prefix = module._MARKER_PREFIX
    marker_suffix = module._MARKER_SUFFIX
    geo = module._GEO_TOKEN
    state_token = module._STATE_TOKEN
    zip_ = module._ZIP
    flags = re.IGNORECASE | re.ASCII if ascii_flag else re.IGNORECASE
    return {
        "country_alone": re.compile(rf"^{marker_prefix}(?P<country>{ct}){marker_suffix}$", flags),
        "state_form": re.compile(
            rf"^{marker_prefix}(?P<geo>{geo}){ws}*,{ws}*(?P<state>{state_token}){marker_suffix}$",
            flags,
        ),
        "state_zip_form": re.compile(
            rf"^{marker_prefix}(?P<geo>{geo}){ws}*,{ws}*(?P<state>{state_token}){ws}+"
            rf"(?P<zip>{zip_}){marker_suffix}$",
            flags,
        ),
        "country_form": re.compile(
            rf"^{marker_prefix}(?P<geo>{geo}){ws}*,{ws}*(?P<country>{ct}){marker_suffix}$", flags
        ),
        "region_country_form": re.compile(
            rf"^{marker_prefix}(?P<geo>{geo}){ws}*,{ws}*(?P<region>{geo}){ws}*,{ws}*"
            rf"(?P<country>{ct}){marker_suffix}$",
            flags,
        ),
    }


def _mutate_location_g01(module: Any) -> dict[str, object]:
    original = module._PRODUCTIONS
    mutated_token = module._COUNTRY_TOKEN.replace(r"U\.S\.A\.?", r"U\.S\.A\.").replace(
        r"U\.S\.?", r"U\.S\."
    )
    module._PRODUCTIONS = _rebuild_location_productions(module, country_token=mutated_token)
    return {"_PRODUCTIONS": original}


def _mutate_location_g06(module: Any) -> dict[str, object]:
    original_productions = module._PRODUCTIONS
    original_state_token_re = module._STATE_TOKEN_RE
    module._PRODUCTIONS = _rebuild_location_productions(module, ascii_flag=False)
    module._STATE_TOKEN_RE = re.compile(
        rf"^{module._STATE_TOKEN}$",
        re.IGNORECASE,
    )
    return {"_PRODUCTIONS": original_productions, "_STATE_TOKEN_RE": original_state_token_re}


def _is_recognized_state_no_trim(module: Any) -> Callable[[str], str | None]:
    def _replacement(raw: str) -> str | None:
        if module._STATE_TOKEN_RE.fullmatch(raw) is None:
            return None
        return str(module._canonicalize_state(raw))

    return _replacement


def _mutate_location_g03(module: Any) -> dict[str, object]:
    original = module._is_recognized_state
    module._is_recognized_state = _is_recognized_state_no_trim(module)
    return {"_is_recognized_state": original}


def _is_recognized_state_loose_grammar(module: Any) -> Callable[[str], str | None]:
    def _replacement(raw: str) -> str | None:
        trimmed = raw.strip(module._WHITESPACE)
        candidate = trimmed.replace(".", "").upper()
        if candidate not in module._STATES:
            return None
        return candidate

    return _replacement


def _mutate_location_g08(module: Any) -> dict[str, object]:
    original = module._is_recognized_state
    module._is_recognized_state = _is_recognized_state_loose_grammar(module)
    return {"_is_recognized_state": original}


def _geo_span_is_rejected_no_negation(module: Any) -> Callable[[str], bool]:
    def _replacement(span: str) -> bool:
        if module._OR_AND_RE.search(span):
            return True
        if any(ch in module._DELIMITER_CHARS for ch in span):
            return True
        if module._MARKER_WORD_RE.search(span):
            return True
        trimmed = span.strip(module._WHITESPACE)
        collapsed = re.sub(rf"{module._WS}+", " ", trimmed).lower()
        if collapsed in module._SENTINEL_PHRASES:
            return True
        return module._canonicalize_country(trimmed) is not None

    return _replacement


def _mutate_location_g04(module: Any) -> dict[str, object]:
    original = module._geo_span_is_rejected
    module._geo_span_is_rejected = _geo_span_is_rejected_no_negation(module)
    return {"_geo_span_is_rejected": original}


def _geo_span_is_rejected_no_country_conflict(module: Any) -> Callable[[str], bool]:
    def _replacement(span: str) -> bool:
        if module._OR_AND_RE.search(span):
            return True
        if module._NEGATION_WORDS_RE.search(span):
            return True
        if any(ch in module._DELIMITER_CHARS for ch in span):
            return True
        if module._MARKER_WORD_RE.search(span):
            return True
        trimmed = span.strip(module._WHITESPACE)
        collapsed = re.sub(rf"{module._WS}+", " ", trimmed).lower()
        return collapsed in module._SENTINEL_PHRASES

    return _replacement


def _mutate_location_g05(module: Any) -> dict[str, object]:
    original = module._geo_span_is_rejected
    module._geo_span_is_rejected = _geo_span_is_rejected_no_country_conflict(module)
    return {"_geo_span_is_rejected": original}


_LOCATION_MUTATIONS: list[Mutation] = [
    SimpleMutation(
        "simple",
        "location/g01-alias-trailing-period",
        "location-alias-trailing-period--transform-none--target-location--boundary-country_token--variant-base",
        "location",
        "app.normalization.location",
        _mutate_location_g01,
        {"location": "Remote, U.S."},
        {
            "city": (None, "unavailable"),
            "state": (None, "unavailable"),
            "country": (None, "unavailable"),
            "postal_code": (None, "unavailable"),
        },
    ),
    StructuralMutation(
        "structural",
        "location/g02-state-zip-provenance",
        "location-state-zip-provenance--transform-none--target-location--boundary-whole_field--variant-base",
        "location",
        "app.normalization.location",
        "app/normalization/location.py",
        (
            "        return _build_result(\n"
            "            state=state,\n"
            '            country="United States",\n'
            '            postal_code=groups["zip"],\n'
            "            country_provenance=Provenance.INFERRED,\n"
            "        )"
        ),
        (
            "        return _build_result(\n"
            "            state=state,\n"
            '            country="United States",\n'
            '            postal_code=groups["zip"],\n'
            "            country_provenance=Provenance.PARSED_DESCRIPTION,\n"
            "        )"
        ),
        {"location": "Austin, TX 78701"},
        {
            "city": (None, "unavailable"),
            "state": ("TX", "parsed_description"),
            "country": ("United States", "parsed_description"),
            "postal_code": ("78701", "parsed_description"),
        },
    ),
    SimpleMutation(
        "simple",
        "location/g03-region-whitespace-trim",
        "location-region-whitespace-trim--transform-none--target-location--boundary-region_span--variant-base",
        "location",
        "app.normalization.location",
        _mutate_location_g03,
        {"location": "Toronto, TX , United States"},
        {
            "city": (None, "unavailable"),
            "state": (None, "unavailable"),
            "country": (None, "unavailable"),
            "postal_code": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "location/g04-negation-standalone-word",
        "location-negation-standalone-word--transform-none--target-location--boundary-geo_span--variant-base",
        "location",
        "app.normalization.location",
        _mutate_location_g04,
        {"location": "All countries except, Canada"},
        {
            "city": (None, "unavailable"),
            "state": (None, "unavailable"),
            "country": ("Canada", "parsed_description"),
            "postal_code": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "location/g05-country-conflict-discarded-span",
        "location-country-conflict-discarded-span--transform-none--target-location--boundary-geo_span--variant-base",
        "location",
        "app.normalization.location",
        _mutate_location_g05,
        {"location": "Canada, France"},
        {
            "city": (None, "unavailable"),
            "state": (None, "unavailable"),
            "country": ("France", "parsed_description"),
            "postal_code": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "location/g06-ascii-only-casefold",
        "location-ascii-only-casefold--transform-none--target-location--boundary-state_token--variant-base",
        "location",
        "app.normalization.location",
        _mutate_location_g06,
        {"location": "Austin, Wİ"},
        {
            "city": (None, "unavailable"),
            "state": ("Wİ", "parsed_description"),
            "country": ("United States", "inferred"),
            "postal_code": (None, "unavailable"),
        },
    ),
    StructuralMutation(
        "structural",
        "location/g07-state-precedence-over-coordinator",
        "location-state-precedence-over-coordinator--transform-none--target-location--boundary-region_span--variant-base",
        "location",
        "app.normalization.location",
        "app/normalization/location.py",
        (
            '    region = groups.get("region")\n'
            "    region_state = _is_recognized_state(region) if region is not None else None\n"
            "    if region is not None and region_state is None and "
            "_geo_span_is_rejected(region):\n"
            "        return _UNAVAILABLE_RESULT"
        ),
        (
            '    region = groups.get("region")\n'
            "    if region is not None and _geo_span_is_rejected(region):\n"
            "        return _UNAVAILABLE_RESULT\n"
            "    region_state = _is_recognized_state(region) if region is not None else None"
        ),
        {"location": "Austin, OR, United States"},
        {
            "city": (None, "unavailable"),
            "state": (None, "unavailable"),
            "country": (None, "unavailable"),
            "postal_code": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "location/g08-exact-state-token-grammar",
        "location-exact-state-token-grammar--transform-none--target-location--boundary-region_span--variant-base",
        "location",
        "app.normalization.location",
        _mutate_location_g08,
        {"location": "Toronto, T...X, Canada"},
        {
            "city": (None, "unavailable"),
            "state": (None, "unavailable"),
            "country": (None, "unavailable"),
            "postal_code": (None, "unavailable"),
        },
    ),
]

# ---------------------------------------------------------------------------
# salary.py -- 5 active guards. All expressible as rebuilding the
# `_PRODUCTIONS` dict from a modified building-block string.
# ---------------------------------------------------------------------------


def _rebuild_salary_productions(
    module: Any,
    *,
    label_prefix: str | None = None,
    code_prefix: str | None = None,
    code_suffix: str | None = None,
    period_suffix: str | None = None,
    up_to: str | None = None,
) -> dict[str, re.Pattern[str]]:
    lp = label_prefix if label_prefix is not None else module._LABEL_PREFIX
    cp = code_prefix if code_prefix is not None else module._CODE_PREFIX
    cs = code_suffix if code_suffix is not None else module._CODE_SUFFIX
    ps = period_suffix if period_suffix is not None else module._PERIOD_SUFFIX
    ut = up_to if up_to is not None else module._UP_TO
    ws = module._WS

    def operand(idx: int) -> str:
        return str(module._operand(idx))

    return {
        "single_or_open_lower": re.compile(
            rf"^{lp}{cp}{operand(1)}(?P<plus>\+)?{cs}{ps}$", re.IGNORECASE
        ),
        "open_upper": re.compile(rf"^{lp}{cp}{ut}{operand(1)}{cs}{ps}$", re.IGNORECASE),
        "hyphen_range": re.compile(
            rf"^{lp}{cp}{operand(1)}{ws}*-{ws}*{operand(2)}{cs}{ps}$", re.IGNORECASE
        ),
        "to_range": re.compile(
            rf"^{lp}{cp}{operand(1)}{ws}+to{ws}+{operand(2)}{cs}{ps}$", re.IGNORECASE
        ),
        "between_and_range": re.compile(
            rf"^{lp}{cp}between{ws}+{operand(1)}{ws}+and{ws}+{operand(2)}{cs}{ps}$",
            re.IGNORECASE,
        ),
    }


def _mutate_salary_g01(module: Any) -> dict[str, object]:
    """Widens every covered-whitespace boundary back to bare `\\s`."""
    original = module._PRODUCTIONS
    bare = r"\s"
    ws_pattern = re.escape(module._WS)

    def widen(text: str) -> str:
        return text.replace(module._WS, bare)

    module._PRODUCTIONS = _rebuild_salary_productions(
        module,
        label_prefix=widen(module._LABEL_PREFIX),
        code_prefix=widen(module._CODE_PREFIX),
        code_suffix=widen(module._CODE_SUFFIX),
        period_suffix=widen(module._PERIOD_SUFFIX),
        up_to=widen(module._UP_TO),
    )
    del ws_pattern
    return {"_PRODUCTIONS": original}


def _mutate_salary_g02(module: Any) -> dict[str, object]:
    original = module._PRODUCTIONS
    label = module._LABEL
    weakened = rf"(?:(?P<label>{label})(?::{module._WS}*|{module._WS}*))?"
    module._PRODUCTIONS = _rebuild_salary_productions(module, label_prefix=weakened)
    return {"_PRODUCTIONS": original}


def _mutate_salary_g03(module: Any) -> dict[str, object]:
    original = module._PRODUCTIONS
    code = module._CODE
    ws = module._WS
    weakened_prefix = rf"(?:(?P<code_prefix>{code}){ws}*)?"
    weakened_suffix = rf"(?:{ws}*(?P<code_suffix>{code}))?"
    module._PRODUCTIONS = _rebuild_salary_productions(
        module, code_prefix=weakened_prefix, code_suffix=weakened_suffix
    )
    return {"_PRODUCTIONS": original}


def _mutate_salary_g04(module: Any) -> dict[str, object]:
    original = module._PRODUCTIONS
    ws = module._WS
    slash_token = module._SLASH_PERIOD_TOKEN
    word_token = module._WORD_PERIOD_TOKEN
    weakened = rf"(?:{ws}*(?P<period_slash>{slash_token})|{ws}*(?P<period_word>{word_token}))?"
    module._PRODUCTIONS = _rebuild_salary_productions(module, period_suffix=weakened)
    return {"_PRODUCTIONS": original}


def _mutate_salary_g05(module: Any) -> dict[str, object]:
    original = module._PRODUCTIONS
    ws = module._WS
    old_permissive = rf"up[{ws[1:-1]}-]+to{ws}+"
    module._PRODUCTIONS = _rebuild_salary_productions(module, up_to=old_permissive)
    return {"_PRODUCTIONS": original}


_SALARY_MUTATIONS: list[Mutation] = [
    SimpleMutation(
        "simple",
        "salary/g01-covered-whitespace-class",
        "salary-covered-whitespace-line-separator--transform-none--target-compensation_text--boundary-label_boundary--variant-base",
        "salary",
        "app.normalization.salary",
        _mutate_salary_g01,
        {"compensation_text": "Salary: $120,000"},
        {
            "minimum": (120000, "parsed_description"),
            "maximum": (120000, "parsed_description"),
            "currency": (None, "unavailable"),
            "period": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "salary/g02-label-boundary-strictness",
        "salary-label-boundary-strictness--transform-none--target-compensation_text--boundary-label_boundary--variant-base",
        "salary",
        "app.normalization.salary",
        _mutate_salary_g02,
        {"compensation_text": "salary120000"},
        {
            "minimum": (120000, "parsed_description"),
            "maximum": (120000, "parsed_description"),
            "currency": (None, "unavailable"),
            "period": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "salary/g03-currency-code-boundary-strictness",
        "salary-currency-code-boundary-strictness--transform-none--target-compensation_text--boundary-code_boundary--variant-base",
        "salary",
        "app.normalization.salary",
        _mutate_salary_g03,
        {"compensation_text": "USD120000"},
        {
            "minimum": (120000, "parsed_description"),
            "maximum": (120000, "parsed_description"),
            "currency": ("USD", "parsed_description"),
            "period": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "salary/g04-period-boundary-by-shape",
        "salary-period-boundary-by-shape--transform-none--target-compensation_text--boundary-period_boundary--variant-base",
        "salary",
        "app.normalization.salary",
        _mutate_salary_g04,
        {"compensation_text": "$120000year"},
        {
            "minimum": (120000, "parsed_description"),
            "maximum": (120000, "parsed_description"),
            "currency": (None, "unavailable"),
            "period": ("annual", "parsed_description"),
        },
    ),
    SimpleMutation(
        "simple",
        "salary/g05-up-to-narrowed-forms",
        "salary-up-to-narrowed-forms--transform-none--target-compensation_text--boundary-range_separator--variant-base",
        "salary",
        "app.normalization.salary",
        _mutate_salary_g05,
        {"compensation_text": "up--to $150,000"},
        {
            "minimum": (None, "unavailable"),
            "maximum": (150000, "parsed_description"),
            "currency": (None, "unavailable"),
            "period": (None, "unavailable"),
        },
    ),
]

# ---------------------------------------------------------------------------
# experience.py -- 21 active guards (g07 is superseded; see taxonomy.py).
# ---------------------------------------------------------------------------


def _drop_from_poison_patterns(module: Any, *names: str) -> dict[str, object]:
    original = module._POISON_PATTERNS
    dropped = {getattr(module, name) for name in names}
    module._POISON_PATTERNS = tuple(p for p in original if p not in dropped)
    return {"_POISON_PATTERNS": original}


def _mutate_experience_g02(module: Any) -> dict[str, object]:
    original = module._remainder_is_acceptable
    module._remainder_is_acceptable = lambda remainder: True
    return {"_remainder_is_acceptable": original}


def _mutate_experience_g03(module: Any) -> dict[str, object]:
    return _drop_from_poison_patterns(module, "_DECIMAL_RE")


def _mutate_experience_g05(module: Any) -> dict[str, object]:
    """Checks cross-source agreement *before* the internal-conflict
    check, the reverted precedence this guard fixed."""
    original = module._reconcile_bound

    def _replacement(title_signal: object, description_signal: object) -> object:
        if title_signal == description_signal and title_signal is not None:
            return module.NormalizationResult(
                description_signal, module.Provenance.PARSED_DESCRIPTION
            )
        if title_signal is None and description_signal is None:
            return module._UNAVAILABLE_RESULT
        if (
            title_signal is not None
            and title_signal != module._CONFLICT
            and description_signal is None
        ):
            return module.NormalizationResult(title_signal, module.Provenance.INFERRED)
        if description_signal is not None and description_signal != module._CONFLICT:
            return module.NormalizationResult(
                description_signal, module.Provenance.PARSED_DESCRIPTION
            )
        return module._UNAVAILABLE_RESULT

    module._reconcile_bound = _replacement
    return {"_reconcile_bound": original}


def _mutate_experience_g11(module: Any) -> dict[str, object]:
    return _drop_from_poison_patterns(module, "_UNSUPPORTED_PREFIX_RE")


def _mutate_experience_g12(module: Any) -> dict[str, object]:
    """Removes the U+2044 FRACTION SLASH -> ASCII '/' substitution from
    `_normalize_text`, keeping NFKC normalization and curly-apostrophe
    replacement intact."""
    import unicodedata

    original = module._normalize_text

    def _replacement(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text)
        for curly in module._CURLY_APOSTROPHES:
            normalized = normalized.replace(curly, "'")
        return normalized

    module._normalize_text = _replacement
    return {"_normalize_text": original}


def _mutate_experience_g13(module: Any) -> dict[str, object]:
    return _drop_from_poison_patterns(module, "_UNICODE_DASH_NUMERIC_RE")


def _mutate_experience_g17(module: Any) -> dict[str, object]:
    return _drop_from_poison_patterns(
        module, "_DECIMAL_COMPOSITE_RANGE_RE", "_FRACTION_COMPOSITE_RANGE_RE"
    )


def _mutate_experience_g21(module: Any) -> dict[str, object]:
    return _drop_from_poison_patterns(module, "_NEGATIVE_COMPOSITE_RANGE_RE")


def _mutate_experience_g22(module: Any) -> dict[str, object]:
    original_patterns = module._POISON_PATTERNS
    original_decimal = module._DECIMAL_COMPOSITE_RANGE_RE
    original_fraction = module._FRACTION_COMPOSITE_RANGE_RE
    original_negative = module._NEGATIVE_COMPOSITE_RANGE_RE
    range_sep = module._RANGE_SEPARATOR
    new_decimal = re.compile(rf"\d+\.\d+{range_sep}\d+|\d+{range_sep}\d+\.\d+")  # no re.IGNORECASE
    new_fraction = re.compile(rf"\d+\s*/\s*\d+{range_sep}\d+|\d+{range_sep}\d+\s*/\s*\d+")
    new_negative = re.compile(rf"(?<!\d)-\d+{range_sep}\d+|\d+{range_sep}(?<!\d)-\d+")
    module._DECIMAL_COMPOSITE_RANGE_RE = new_decimal
    module._FRACTION_COMPOSITE_RANGE_RE = new_fraction
    module._NEGATIVE_COMPOSITE_RANGE_RE = new_negative
    module._POISON_PATTERNS = tuple(
        {
            id(original_decimal): new_decimal,
            id(original_fraction): new_fraction,
            id(original_negative): new_negative,
        }.get(id(p), p)
        for p in original_patterns
    )
    return {
        "_POISON_PATTERNS": original_patterns,
        "_DECIMAL_COMPOSITE_RANGE_RE": original_decimal,
        "_FRACTION_COMPOSITE_RANGE_RE": original_fraction,
        "_NEGATIVE_COMPOSITE_RANGE_RE": original_negative,
    }


def _mutate_experience_g06(module: Any) -> dict[str, object]:
    original = module._TITLE_SEGMENT_DELIMITER_RE
    module._TITLE_SEGMENT_DELIMITER_RE = re.compile(r"\s[-–—]\s|-|[,|:]")
    return {"_TITLE_SEGMENT_DELIMITER_RE": original}


def _mutate_experience_g08(module: Any) -> dict[str, object]:
    original = module._TITLE_LEADING_PREFERENCE_RE
    module._TITLE_LEADING_PREFERENCE_RE = re.compile(r"(?!x)x")
    return {"_TITLE_LEADING_PREFERENCE_RE": original}


def _neighbor_ignore_step(module: Any, ignored_step: int) -> Callable[..., bool]:
    real = module._nearest_meaningful_neighbor_is_qualifier

    def _replacement(
        raw_segments: list[str], qualifier_only: list[bool], index: int, step: int
    ) -> bool:
        if step == ignored_step:
            return False
        return real(raw_segments, qualifier_only, index, step)  # type: ignore[no-any-return]

    return _replacement


def _mutate_experience_g09(module: Any) -> dict[str, object]:
    original = module._nearest_meaningful_neighbor_is_qualifier
    module._nearest_meaningful_neighbor_is_qualifier = _neighbor_ignore_step(module, 1)
    return {"_nearest_meaningful_neighbor_is_qualifier": original}


def _mutate_experience_g16(module: Any) -> dict[str, object]:
    original = module._nearest_meaningful_neighbor_is_qualifier
    module._nearest_meaningful_neighbor_is_qualifier = _neighbor_ignore_step(module, -1)
    return {"_nearest_meaningful_neighbor_is_qualifier": original}


def _neighbor_no_blank_skip(
    raw_segments: list[str], qualifier_only: list[bool], index: int, step: int
) -> bool:
    i = index + step
    if not (0 <= i < len(raw_segments)):
        return False
    return qualifier_only[i]


def _mutate_experience_g20(module: Any) -> dict[str, object]:
    original = module._nearest_meaningful_neighbor_is_qualifier
    module._nearest_meaningful_neighbor_is_qualifier = _neighbor_no_blank_skip
    return {"_nearest_meaningful_neighbor_is_qualifier": original}


def _mutate_experience_g10(module: Any) -> dict[str, object]:
    original = module._FORWARD_PHRASE_RE
    unit = module._UNIT
    of_experience = module._OF_EXPERIENCE
    pattern = "".join(
        [
            r"between\s+(?P<between_lo>\d+)\s+and\s+(?P<between_hi>\d+)\s*" + unit + of_experience,
            r"|(?P<to_lo>\d+)\s+to\s+(?P<to_hi>\d+)\s*" + unit + of_experience,
            r"|(?P<hy_lo>\d+)-(?P<hy_hi>\d+)\s*" + unit + of_experience,
            r"|(?:at least|minimum of|minimum)\s+(?P<open_lo_prefix>\d+)\s*" + unit + of_experience,
            r"|(?:up to|no more than|maximum of)\s+(?P<open_hi_prefix>\d+)\s*"
            + unit
            + of_experience,
            r"|(?P<open_lo_suffix>\d+)\s*(?:or more|or above|plus)\s*" + unit + of_experience,
            r"|(?P<open_hi_suffix>\d+)\s*(?:or less|or fewer|or under)\s*" + unit + of_experience,
            r"|(?P<plus_lo>\d+)\+\s*" + unit + of_experience,
            # bare_trail_hi/bare_trail_lo group *names* are kept (so
            # `_phrase_from_forward_match`'s hardcoded groups[...] lookups
            # don't KeyError), but their bodies are made unmatchable --
            # this is the mutation.
            r"|(?P<bare_trail_hi>(?!)\d+)\s*"
            + unit
            + of_experience
            + r"\s+(?:or less|or fewer|or under)\b",
            r"|(?P<bare_trail_lo>(?!)\d+)\s*"
            + unit
            + of_experience
            + r"\s+(?:or more|or above|plus)\b",
            r"|(?P<bare>\d+)\s*" + unit + of_experience,
        ]
    )
    module._FORWARD_PHRASE_RE = re.compile(pattern, re.IGNORECASE)
    return {"_FORWARD_PHRASE_RE": original}


def _mutate_experience_g14(module: Any) -> dict[str, object]:
    original = module._iter_forward_phrases

    def _replacement(text: str) -> list[object]:
        result = module._match_forward_phrase(text, 0)
        if result is None:
            return []
        phrase, _match = result
        return [phrase]

    module._iter_forward_phrases = _replacement
    return {"_iter_forward_phrases": original}


def _mutate_experience_g15(module: Any) -> dict[str, object]:
    original = module._title_segments

    def _replacement(text: str) -> list[str]:
        paren_re = module._PAREN_BRACKET_RE
        delim_re = module._TITLE_SEGMENT_DELIMITER_RE
        paren_segments: list[str] = []
        for match in paren_re.finditer(text):
            content = match.group(1) if match.group(1) is not None else match.group(2)
            paren_segments.append(content)
        remainder_segments: list[str] = delim_re.split(paren_re.sub("", text))
        return paren_segments + remainder_segments

    module._title_segments = _replacement
    return {"_title_segments": original}


def _mutate_experience_g19(module: Any) -> dict[str, object]:
    original = module._LABEL_VALUE_RE
    unit = module._UNIT
    pattern = "".join(
        [
            r"experience\s*:?\s*",
            r"(?:(?P<lv_hy_lo>\d+)-(?P<lv_hy_hi>\d+)",
            r"|(?P<lv_plus>\d+)\+",
            r"|(?P<lv_bare>\d+))",
            r"\s*(?:" + unit + r")?\b",
        ]
    )
    module._LABEL_VALUE_RE = re.compile(pattern, re.IGNORECASE)
    return {"_LABEL_VALUE_RE": original}


_EXPERIENCE_MUTATIONS: list[Mutation] = [
    StructuralMutation(
        "structural",
        "experience/g01-attribution-frame",
        "experience-attribution-frame--transform-none--target-description--boundary-attribution_frame--variant-base",
        "experience",
        "app.normalization.experience",
        "app/normalization/experience.py",
        (
            "        phrase, match = forward\n"
            "        if match.start() != 0:\n"
            "            # The number-phrase must begin the frame's remainder directly\n"
            "            # (only an approved ATTRIBUTION_OBJECT may precede it) — a gap\n"
            "            # here means unsupported intervening text, same fail-closed\n"
            "            # rule as an unsupported trailing remainder.\n"
            "            continue"
        ),
        ("        phrase, match = forward"),
        {"title": None, "description": "We require vendors with 5 years of experience."},
        {
            "minimum": (5, "parsed_description"),
            "maximum": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "experience/g02-continuation-boundary",
        "experience-continuation-boundary--transform-none--target-description--boundary-continuation_boundary--variant-base",
        "experience",
        "app.normalization.experience",
        _mutate_experience_g02,
        {
            "title": None,
            "description": "This role requires 5 years of experience, however this is negotiable.",
        },
        {
            "minimum": (5, "parsed_description"),
            "maximum": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "experience/g03-individual-number-redaction",
        "experience-individual-number-redaction--transform-none--target-title--boundary-numeric_redaction--variant-base",
        "experience",
        "app.normalization.experience",
        _mutate_experience_g03,
        {"title": "3.5 years experience", "description": None},
        {
            "minimum": (5, "inferred"),
            "maximum": (None, "unavailable"),
        },
    ),
    StructuralMutation(
        "structural",
        "experience/g04-positional-preference-suppression",
        "experience-positional-preference-suppression--transform-none--target-description--boundary-preference_suppression--variant-base",
        "experience",
        "app.normalization.experience",
        "app/normalization/experience.py",
        (
            "        # Leading preference marker suppresses the whole sentence outright.\n"
            '        if re.match(r"^ideally\\s*,", stripped, re.IGNORECASE):\n'
            "            continue"
        ),
        (
            "        # Leading preference marker suppresses the whole sentence outright.\n"
            '        if re.match(r"^ideally\\s*,", stripped, re.IGNORECASE):\n'
            "            continue\n"
            '        if "ideal" in stripped.lower():\n'
            "            continue"
        ),
        {"title": None, "description": "The ideal candidate must have 5 years of experience."},
        {
            "minimum": (None, "unavailable"),
            "maximum": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "experience/g05-internal-conflict-precedence",
        "experience-internal-conflict-precedence--transform-none--target-title--boundary-numeric_redaction--variant-base",
        "experience",
        "app.normalization.experience",
        _mutate_experience_g05,
        {
            "title": "3 years experience and 5 years experience",
            "description": "This role requires 5 years of experience.",
        },
        {
            "minimum": (5, "parsed_description"),
            "maximum": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "experience/g06-original-unicode-hyphen-disambiguation",
        "experience-original-unicode-hyphen-disambiguation--transform-none--target-title--boundary-title_segment_adjacency--variant-base",
        "experience",
        "app.normalization.experience",
        _mutate_experience_g06,
        {"title": "Software Engineer - 3-5 years experience", "description": None},
        {
            "minimum": (5, "inferred"),
            "maximum": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "experience/g08-title-leading-preference",
        "experience-title-leading-preference--transform-none--target-title--boundary-preference_suppression--variant-base",
        "experience",
        "app.normalization.experience",
        _mutate_experience_g08,
        {"title": "Preferred 3-5 years experience", "description": None},
        {
            "minimum": (3, "inferred"),
            "maximum": (5, "inferred"),
        },
    ),
    SimpleMutation(
        "simple",
        "experience/g09-cross-segment-qualifier-following",
        "experience-cross-segment-qualifier-following--transform-none--target-title--boundary-title_segment_adjacency--variant-base",
        "experience",
        "app.normalization.experience",
        _mutate_experience_g09,
        {"title": "5 years experience, not required", "description": None},
        {
            "minimum": (5, "inferred"),
            "maximum": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "experience/g10-trailing-bound-marker",
        "experience-trailing-bound-marker--transform-none--target-description--boundary-attribution_frame--variant-base",
        "experience",
        "app.normalization.experience",
        _mutate_experience_g10,
        {"title": None, "description": "This role requires 5 years of experience or fewer."},
        {
            "minimum": (None, "unavailable"),
            "maximum": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "experience/g11-unsupported-prefix-poison",
        "experience-unsupported-prefix-poison--transform-none--target-title--boundary-numeric_redaction--variant-base",
        "experience",
        "app.normalization.experience",
        _mutate_experience_g11,
        {"title": "less than 5 years of experience", "description": None},
        {
            "minimum": (5, "inferred"),
            "maximum": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "experience/g12-fraction-slash-normalization",
        "experience-fraction-slash-normalization--transform-none--target-title--boundary-numeric_redaction--variant-base",
        "experience",
        "app.normalization.experience",
        _mutate_experience_g12,
        {"title": "½ years experience", "description": None},
        {
            "minimum": (2, "inferred"),
            "maximum": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "experience/g13-unicode-dash-poison",
        "experience-unicode-dash-poison--transform-none--target-title--boundary-numeric_redaction--variant-base",
        "experience",
        "app.normalization.experience",
        _mutate_experience_g13,
        {"title": "−5 years experience", "description": None},
        {
            "minimum": (5, "inferred"),
            "maximum": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "experience/g14-multi-candidate-collection",
        "experience-multi-candidate-collection--transform-none--target-title--boundary-title_segment_adjacency--variant-base",
        "experience",
        "app.normalization.experience",
        _mutate_experience_g14,
        {"title": "3 years experience and 5 years experience", "description": None},
        {
            "minimum": (3, "inferred"),
            "maximum": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "experience/g15-title-segment-order-preservation",
        "experience-title-segment-order-preservation--transform-none--target-title--boundary-title_segment_adjacency--variant-base",
        "experience",
        "app.normalization.experience",
        _mutate_experience_g15,
        {"title": "Junior Developer, 5 years experience (not required)", "description": None},
        {
            "minimum": (5, "inferred"),
            "maximum": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "experience/g16-bidirectional-adjacency",
        "experience-bidirectional-adjacency--transform-none--target-title--boundary-title_segment_adjacency--variant-base",
        "experience",
        "app.normalization.experience",
        _mutate_experience_g16,
        {"title": "Ideally, 5 years of experience", "description": None},
        {
            "minimum": (5, "inferred"),
            "maximum": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "experience/g17-composite-range-poison-decimal-fraction",
        "experience-composite-range-poison-decimal-fraction--transform-none--target-title--boundary-numeric_redaction--variant-base",
        "experience",
        "app.normalization.experience",
        _mutate_experience_g17,
        {"title": "3.5 to 5 years experience", "description": None},
        {
            "minimum": (5, "inferred"),
            "maximum": (None, "unavailable"),
        },
    ),
    StructuralMutation(
        "structural",
        "experience/g18-description-label-value-scope-removed",
        "experience-description-label-value-scope-removed--transform-none--target-description--boundary-attribution_frame--variant-base",
        "experience",
        "app.normalization.experience",
        "app/normalization/experience.py",
        (
            "        frame_match = _FRAME_RE.match(stripped)\n"
            "        if frame_match is None:\n"
            "            continue"
        ),
        (
            "        label_phrase = _match_label_value_phrase(stripped)\n"
            "        if label_phrase is not None:\n"
            "            remainder = stripped[label_phrase.end :]\n"
            "            if _remainder_is_acceptable(remainder):\n"
            "                if label_phrase.minimum is not None:\n"
            "                    minimums.append(label_phrase.minimum)\n"
            "                if label_phrase.maximum is not None:\n"
            "                    maximums.append(label_phrase.maximum)\n"
            "            continue\n"
            "        frame_match = _FRAME_RE.match(stripped)\n"
            "        if frame_match is None:\n"
            "            continue"
        ),
        {"title": None, "description": "Experience: 5+ years."},
        {
            "minimum": (5, "parsed_description"),
            "maximum": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "experience/g19-title-label-value-whole-anchor",
        "experience-title-label-value-whole-anchor--transform-none--target-title--boundary-attribution_frame--variant-base",
        "experience",
        "app.normalization.experience",
        _mutate_experience_g19,
        {"title": "Experience: 5", "description": None},
        {
            "minimum": (5, "inferred"),
            "maximum": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "experience/g20-empty-segment-adjacency",
        "experience-empty-segment-adjacency--transform-none--target-title--boundary-title_segment_adjacency--variant-base",
        "experience",
        "app.normalization.experience",
        _mutate_experience_g20,
        {"title": "(Preferred), 5 years experience", "description": None},
        {
            "minimum": (5, "inferred"),
            "maximum": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "experience/g21-composite-range-poison-negative",
        "experience-composite-range-poison-negative--transform-none--target-title--boundary-numeric_redaction--variant-base",
        "experience",
        "app.normalization.experience",
        _mutate_experience_g21,
        {"title": "-3 to 5 years experience", "description": None},
        {
            "minimum": (5, "inferred"),
            "maximum": (None, "unavailable"),
        },
    ),
    SimpleMutation(
        "simple",
        "experience/g22-composite-poison-casefold",
        "experience-composite-poison-casefold--transform-none--target-title--boundary-numeric_redaction--variant-base",
        "experience",
        "app.normalization.experience",
        _mutate_experience_g22,
        {"title": "3.5 TO 5 years experience", "description": None},
        {
            "minimum": (5, "inferred"),
            "maximum": (None, "unavailable"),
        },
    ),
]

MUTATION_REGISTRY: dict[str, Mutation] = _finalize(
    [*_LOCATION_MUTATIONS, *_SALARY_MUTATIONS, *_EXPERIENCE_MUTATIONS]
)
