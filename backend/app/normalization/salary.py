r"""Deterministic salary/base-pay classifier (Phase 3 -- fifth parser slice;
docs/ARCHITECTURE.md Section 4's `normalization/salary.py`,
docs/PHASE_RISK_CHECKLIST.md's Phase 3 exit gate -- Workflow v3.1 pilot
parser slice 2 of 3, reviewed by Astra across three proposal rounds before
implementation).

Pure function: `compensation_text` free text in, one `SalaryResult` out -- a
composite of four independently-provenanced `NormalizationResult` fields
(`minimum`/`maximum`: int; `currency`/`period`: str), per
`app.normalization.types`'s deferred composite-result-type case (already
anticipated there as "a future salary parser's min/max/currency/period").
No database, ORM, provider, network, or ingestion-pipeline dependency; no
`parser_version` threading. **`title`/`description` are deliberately never
read** -- `compensation_text` is the only source, an explicit, approved
scope boundary (not an oversight): unlike `experience.py`'s title+
description design, salary text is field-like/terse, not narrative, so
there is no cross-source reconciliation and no attribution-frame concept
in this module at all.

Explicitly out of scope (approved exclusions, unchanged across all three
proposal rounds): `annualized_salary_min`/`max` (DATA_MODEL.md calls this
"derived... not enforced/computed by this migration" -- an application-layer
concern), `compensation_explicit` (provider/source metadata, not derivable
from text), FX conversion, any taxonomy, any database/migration/ingestion
wiring.

**Provenance** (Astra round-4 correction): every successfully-extracted
field uses `Provenance.PARSED_DESCRIPTION` -- DATA_MODEL.md's own
definition is "extracted via regex/rules from free text," which is
literally what this module does to `compensation_text`. `INFERRED`
("a guess with a stated basis") does not apply -- there is no cross-field
guessing here, since the source is single-field. `EXPLICIT_SOURCE`/
`STRUCTURED_METADATA` are unavailable since this function receives no
source-origin metadata.

**Whole-field lexical/semantic split** (Astra round-4 correction). Two
strictly separated layers:

1. **Lexical envelope** -- after normalization (see below), the *entire*
   field must `re.fullmatch` exactly one of five finite productions (see
   `_PRODUCTIONS`). The numeric sub-pattern is deliberately *permissive* at
   this layer (any digit grouping shape, any decimal, an optional leading
   `-`, an optional trailing `k`/`K`) so that an otherwise-well-formed
   expression with an invalid numeric value still lexically matches --
   this is what lets `currency`/`period` survive a numeric failure per
   Table B below. If **no** production fullmatches (unknown leftover text,
   an unsupported digit system, a second candidate elsewhere in the text,
   a component-attribution word, ...) the result is fully unavailable in
   all four fields (Table D) -- there is no substring fallback. Because
   every production is anchored `^...$`, this "whole-field" behavior falls
   out of `fullmatch` itself: leftover, unconsumed text of *any* kind
   (`"$120,000 relocation assistance available"`, a second range, the word
   `"bonus"`) simply cannot be skipped over to reach a clean-looking
   substring elsewhere. This single mechanism is what implements the
   approved proposal's disqualifier list (bonus/commission/OTE/equity/
   stock/stipend/sign-on/total-compensation/multiple-range/multiple-
   component) without a separate keyword-poison scan: none of those words
   or a second amount can ever be consumed by the closed label/currency/
   amount/period grammar, so they always leave unconsumed leftover text.
2. **Semantic validation** -- given the lexically-matched groups, strict
   rules reject an invalid numeric operand (nonzero decimal, malformed
   digit grouping, a negative sign, overflow past PostgreSQL's 32-bit
   signed integer maximum, an inverted range) and resolve `currency`/
   `period` independently via the tables below. Numeric failure is
   **atomic across a composite (range) expression**: if either operand is
   invalid, *both* `minimum` and `maximum` become unavailable -- the
   clean-looking endpoint is never promoted to a standalone match.

**The five finite productions** (`_PRODUCTIONS`; no form beyond these is
implemented):

    [label]? [CODE]? <operand> [+]? [CODE]? [period]?        bare / open-lower
    [label]? [CODE]? up to <operand> [CODE]? [period]?       open-upper
    [label]? [CODE]? <operand> - <operand> [CODE]? [period]? hyphen range
    [label]? [CODE]? <operand> to <operand> [CODE]? [period]? "to" range
    [label]? [CODE]? between <operand> and <operand> [CODE]? [period]?

`<operand>` is `-?(symbol)?<digits>`, where `<digits>` lexically accepts
any comma-grouped or ungrouped ASCII-digit run, an optional decimal
fraction, and an optional trailing `k`/`K`. `label` is one of `salary`,
`base salary`, `base pay`, `pay rate`, `pay`, each with an optional
trailing colon (recommended, closed catalog -- unchanged since round 2).
`CODE` is one of `USD`/`CAD`/`AUD`/`GBP`/`EUR` and may appear before
and/or after the amount-expression (both may be present at once, e.g. to
exercise a currency conflict). `symbol` is one of `$`/`GBP-pound-sign`/
`euro-sign`, attached per-operand.

**Numeric grammar is ASCII-only** (Astra round-4 correction): every digit
class is the literal `[0-9]`, never bare `\d` (which is Unicode-digit-aware
in Python without `re.ASCII`). Normalization applies NFKC first (see
`_normalize_field`), so a fullwidth digit (`１２０`) folds into
ASCII range before matching, while a genuinely different digit system
(e.g. Arabic-Indic) does not fold under NFKC and is correctly rejected by
the explicit `[0-9]` classes -- never silently accepted the way a bare
`\d` would accept it. A digit-system rejection is a *lexical* mismatch
(the production simply does not fullmatch), landing in Table D, not a
semantic numeric failure landing in Table B.

**Normalization order** (Astra round-4 correction), applied once before
any grammar match, in this exact sequence:

    1. NFKC-normalize the raw text (`unicodedata.normalize("NFKC", text)`).
    2. Strip the project's established covered-whitespace set --
       tab/newline/CR/space (`"\t\n\r "`, matching the exact set used by
       every trim-only text column in this schema, e.g.
       `candidate_skills.skill`/`saved_search_titles.title`) -- from both
       ends. This is *not* Python's unrestricted `str.strip()`, which
       would also remove other Unicode whitespace characters this project
       does not treat as trimmable.
    3. If the result ends with exactly one literal `.` (the sole
       enumerated harmless-punctuation allowance -- a run of two or more
       periods is deliberately left alone and will simply fail to
       fullmatch), remove that single trailing `.`, then repeat step 2's
       whitespace strip once more (to clean up whitespace exposed between
       the removed period and the preceding content, e.g. `"$120,000 ."`
       -> strip -> `"$120,000 ."` unchanged by step 2 alone since `.` is
       not in the whitespace set -> period removed -> `"$120,000 "` ->
       final strip -> `"$120,000"`).

**Currency compatibility** (Astra round-4 correction; see `_resolve_currency`):

| Signals found in one candidate                  | Result                    |
|---------------------------------------------------|---------------------------|
| No symbol, no code                                 | unavailable (no signal)   |
| Bare `$` only, no code                             | unavailable (ambiguous)   |
| `$` + one of `USD`/`CAD`/`AUD`                     | that code (compatible)    |
| `$` + `GBP` or `EUR`                               | unavailable (conflicting) |
| `£` (GBP pound sign) alone, or + `GBP`        | `GBP`                     |
| `£` + any other code                          | unavailable (conflicting) |
| `€` (euro sign) alone, or + `EUR`             | `EUR`                     |
| `€` + any other code                          | unavailable (conflicting) |
| Exactly one explicit code, no symbol               | that code                 |
| Two different explicit codes                       | unavailable (conflicting) |
| Two different symbol types (e.g. `$` and `£`) | unavailable (conflicting) |

A currency conflict is a *local* failure of the `currency` field alone --
`minimum`/`maximum`/`period` are unaffected by it (Table B).

**Period grammar** -- a closed synonym catalog mapping to the exact four
database literals (`docs/DATA_MODEL.md`'s `salary_period` CHECK):

| DB literal | Synonyms                                                      |
|---|---|
| `hourly`   | `hour`, `hourly`, `hr`, `/hr`, `per hour`                     |
| `daily`    | `day`, `daily`, `/day`, `per day`                             |
| `monthly`  | `month`, `monthly`, `mo`, `/mo`, `per month`                  |
| `annual`   | `year`, `yearly`, `annual`, `annually`, `yr`, `/yr`, `/year`, `per year` |

No period marker at all leaves `period` unavailable without affecting
`minimum`/`maximum` (Table A -- absence, not failure). An *explicit but
unsupported* period-shaped token -- an enumerated closed set (`week`,
`weekly`, `biweekly`, `bi-weekly`, `fortnight`, `fortnightly`, `per week`,
`/wk`, `semi-monthly`, `semimonthly`) plus a generic structural fallback
(any other `/word` or `per word` suffix) -- is lexically recognized (so
the production still fullmatches) but semantically invalidates **both**
`period` and `minimum`/`maximum` together (Table B); this is the one
approved cross-field contamination rule in this module, carried unchanged
from the round-3 proposal.

**Tables B/D summary** (see the module-level comments above each table's
originating rule for the full rationale):

- Table A (absence, no failure): no currency signal -> `currency`
  unavailable; no period marker -> `period` unavailable. Never affects
  the other fields.
- Table B (recognized production, invalid slot value -- partial results
  survive): nonzero decimal, malformed grouping, negative sign, overflow,
  or an inverted range -> `minimum`/`maximum` unavailable, `currency`/
  `period` resolve independently. An unsupported-but-recognized period ->
  `period` and `minimum`/`maximum` unavailable, `currency` independent.
  A currency conflict -> `currency` unavailable, `minimum`/`maximum`/
  `period` independent.
- Table D (no production fullmatches, or no anchor found even though one
  fullmatched): all four fields unavailable.

**Confidently-wrong blockers directly implemented here**: a bare,
unanchored number is never extracted (see the explicit anchor check in
`classify_salary` -- label, currency code, or currency symbol must be
present on at least one signal even though the lexical grammar alone
would otherwise let an all-optional wrapper match a bare number); a
malformed or overflowing number is never rounded, truncated, or silently
accepted; a range is never silently reordered; an ambiguous or
conflicting currency is never guessed; a missing period is never defaulted
to `annual`.

**Evidence limitation (disclosed, not treated as satisfied)**: every
fixture in `tests/fixtures/normalization/salary_cases.json` is a
hand-constructed synthetic example built to isolate one grammar mechanism.
No real, sanitized job-posting salary-text captures have been collected or
reviewed for this slice -- this falls short of
`docs/PHASE_RISK_CHECKLIST.md`'s Phase 3 aspiration to "build a regression
corpus from realistic captured payloads," the same disclosed limitation
`classify_experience` already carries ("corpus is synthetic").
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.normalization.types import NormalizationResult, Provenance

_INT32_MAX = 2_147_483_647

# The project's established covered-whitespace set (matches the exact
# four characters used by every trim-only text column's CHECK constraint
# in this schema, e.g. candidate_skills.skill / saved_search_titles.title).
_WHITESPACE = "\t\n\r "

_INVERTED_RANGE_ERROR = (
    "SalaryResult invariant violated: both bounds resolved but minimum > maximum."
)


@dataclass(frozen=True)
class SalaryResult:
    """Composite result: four independently-provenanced fields. Never
    persisted directly -- see the module docstring. `__post_init__` is
    defense-in-depth against a future internal bug constructing a
    self-contradictory object directly; `classify_salary` itself is
    responsible for detecting an inverted reconciled range and choosing
    double-`UNAVAILABLE` before construction (mirroring
    `experience.py`'s `ExperienceRange` precedent exactly) -- this is
    never the mechanism by which that coercion happens."""

    minimum: NormalizationResult[int]
    maximum: NormalizationResult[int]
    currency: NormalizationResult[str]
    period: NormalizationResult[str]

    def __post_init__(self) -> None:
        if (
            self.minimum.provenance is not Provenance.UNAVAILABLE
            and self.maximum.provenance is not Provenance.UNAVAILABLE
            and self.minimum.value is not None
            and self.maximum.value is not None
            and self.minimum.value > self.maximum.value
        ):
            raise ValueError(_INVERTED_RANGE_ERROR)


_UNAVAILABLE_INT: NormalizationResult[int] = NormalizationResult(None, Provenance.UNAVAILABLE)
_UNAVAILABLE_STR: NormalizationResult[str] = NormalizationResult(None, Provenance.UNAVAILABLE)
_UNAVAILABLE_RESULT = SalaryResult(
    _UNAVAILABLE_INT, _UNAVAILABLE_INT, _UNAVAILABLE_STR, _UNAVAILABLE_STR
)


def _normalize_field(text: str) -> str:
    """Exact three-step order (Astra round-4 correction) -- see the module
    docstring's "Normalization order" section for the full rationale."""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.strip(_WHITESPACE)
    if normalized.endswith(".") and not normalized.endswith(".."):
        normalized = normalized[:-1].strip(_WHITESPACE)
    return normalized


# ---------------------------------------------------------------------------
# Closed catalogs
# ---------------------------------------------------------------------------

_LABEL = r"(?:salary|base\s+salary|base\s+pay|pay\s+rate|pay)"
_LABEL_PREFIX = rf"(?:(?P<label>{_LABEL})\s*:?\s*)?"

_CODE = r"(?:USD|CAD|AUD|GBP|EUR)"
_CODE_PREFIX = rf"(?:(?P<code_prefix>{_CODE})\s*)?"
_CODE_SUFFIX = rf"(?:\s*(?P<code_suffix>{_CODE}))?"

_SYMBOL = r"[$£€]"  # $, GBP pound sign, euro sign

_SUPPORTED_PERIOD_SYNONYMS: dict[str, str] = {
    "hour": "hourly",
    "hourly": "hourly",
    "hr": "hourly",
    "/hr": "hourly",
    "per hour": "hourly",
    "day": "daily",
    "daily": "daily",
    "/day": "daily",
    "per day": "daily",
    "month": "monthly",
    "monthly": "monthly",
    "mo": "monthly",
    "/mo": "monthly",
    "per month": "monthly",
    "year": "annual",
    "yearly": "annual",
    "annual": "annual",
    "annually": "annual",
    "yr": "annual",
    "/yr": "annual",
    "/year": "annual",
    "per year": "annual",
}
_UNSUPPORTED_PERIOD_ENUMERATED = {
    "week",
    "weekly",
    "biweekly",
    "bi-weekly",
    "fortnight",
    "fortnightly",
    "per week",
    "/wk",
    "semi-monthly",
    "semimonthly",
}
_SUPPORTED_PERIOD_WORDS_RE = "|".join(re.escape(w) for w in _SUPPORTED_PERIOD_SYNONYMS)
_UNSUPPORTED_PERIOD_WORDS_RE = "|".join(re.escape(w) for w in _UNSUPPORTED_PERIOD_ENUMERATED)
_GENERIC_PERIOD_FALLBACK = r"(?:/[A-Za-z]+|per\s+[A-Za-z]+)"
_PERIOD_TOKEN = (
    rf"(?:{_SUPPORTED_PERIOD_WORDS_RE}|{_UNSUPPORTED_PERIOD_WORDS_RE}|{_GENERIC_PERIOD_FALLBACK})"
)
_PERIOD_SUFFIX = rf"(?:\s*(?P<period>{_PERIOD_TOKEN}))?"

# Lexically permissive numeric body -- any digit grouping shape, any
# decimal, an optional k/K scale suffix. Grouping/decimal-exactness/
# overflow/sign validity are all semantic-layer concerns (_parse_operand).
_NUMBER_BODY = r"[0-9]+(?:,[0-9]+)*(?:\.[0-9]+)?[kK]?"
_NUMBER_BODY_PARSE_RE = re.compile(
    r"(?P<int_part>[0-9]+(?:,[0-9]+)*)(?:\.(?P<frac_part>[0-9]+))?(?P<k>[kK])?"
)


def _operand(idx: int) -> str:
    return rf"(?P<sign{idx}>-)?(?P<sym{idx}>{_SYMBOL})?\s*(?P<num{idx}>{_NUMBER_BODY})"


_UP_TO = r"up[\s-]+to\s+"

_PRODUCTIONS: dict[str, re.Pattern[str]] = {
    "single_or_open_lower": re.compile(
        rf"^{_LABEL_PREFIX}{_CODE_PREFIX}{_operand(1)}(?P<plus>\+)?{_CODE_SUFFIX}{_PERIOD_SUFFIX}$",
        re.IGNORECASE,
    ),
    "open_upper": re.compile(
        rf"^{_LABEL_PREFIX}{_CODE_PREFIX}{_UP_TO}{_operand(1)}{_CODE_SUFFIX}{_PERIOD_SUFFIX}$",
        re.IGNORECASE,
    ),
    "hyphen_range": re.compile(
        rf"^{_LABEL_PREFIX}{_CODE_PREFIX}{_operand(1)}\s*-\s*{_operand(2)}{_CODE_SUFFIX}{_PERIOD_SUFFIX}$",
        re.IGNORECASE,
    ),
    "to_range": re.compile(
        rf"^{_LABEL_PREFIX}{_CODE_PREFIX}{_operand(1)}\s+to\s+{_operand(2)}{_CODE_SUFFIX}{_PERIOD_SUFFIX}$",
        re.IGNORECASE,
    ),
    "between_and_range": re.compile(
        rf"^{_LABEL_PREFIX}{_CODE_PREFIX}between\s+{_operand(1)}\s+and\s+{_operand(2)}"
        rf"{_CODE_SUFFIX}{_PERIOD_SUFFIX}$",
        re.IGNORECASE,
    ),
}

# Symbols compatible with each explicit code, and vice versa -- the
# currency-compatibility table in the module docstring, expressed as data.
_DOLLAR_COMPATIBLE_CODES = {"USD", "CAD", "AUD"}
_SYMBOL_COMPATIBLE_CODES = {
    "$": _DOLLAR_COMPATIBLE_CODES,
    "£": {"GBP"},
    "€": {"EUR"},
}
_SYMBOL_UNIQUE_CODE = {"£": "GBP", "€": "EUR"}


def _parse_operand(sign: str | None, num_text: str) -> int | None:
    """Semantic validation of one operand's numeric text. Returns `None`
    for any invalid shape (negative, malformed grouping, nonzero decimal,
    overflow) -- callers collapse all of these to the same "operand
    invalid" outcome, since Table B treats them identically."""
    if sign is not None:
        return None
    match = _NUMBER_BODY_PARSE_RE.fullmatch(num_text)
    if match is None:
        return None
    int_part = match.group("int_part")
    frac_part = match.group("frac_part")
    has_k = match.group("k") is not None
    if frac_part is not None and frac_part != "00":
        return None
    if "," in int_part:
        groups = int_part.split(",")
        if not (1 <= len(groups[0]) <= 3):
            return None
        if any(len(g) != 3 for g in groups[1:]):
            return None
    value = int(int_part.replace(",", ""))
    if has_k:
        value *= 1000
    if value > _INT32_MAX:
        return None
    return value


def _resolve_currency(
    code_prefix: str | None, code_suffix: str | None, symbols: list[str]
) -> str | None:
    """Table C. Returns the resolved ISO code, or `None` if unavailable
    (no signal, ambiguous bare `$`, or a conflict)."""
    codes = {c.upper() for c in (code_prefix, code_suffix) if c is not None}
    distinct_symbols = set(symbols)

    if len(codes) > 1:
        return None
    if len(distinct_symbols) > 1:
        return None

    explicit_code = next(iter(codes)) if codes else None
    symbol = next(iter(distinct_symbols)) if distinct_symbols else None

    if explicit_code is not None:
        if symbol is not None and explicit_code not in _SYMBOL_COMPATIBLE_CODES[symbol]:
            return None
        return explicit_code

    if symbol is None:
        return None
    if symbol in _SYMBOL_UNIQUE_CODE:
        return _SYMBOL_UNIQUE_CODE[symbol]
    return None  # bare "$": ambiguous, never establishes currency alone


def _resolve_period(period_text: str | None) -> tuple[str | None, bool]:
    """Returns (canonical_db_literal_or_None, numeric_should_be_invalidated).
    The second element is True only for the "explicit but unsupported"
    case (Table B) -- absence of a marker is not a failure (Table A)."""
    if period_text is None:
        return None, False
    normalized = period_text.lower()
    canonical = _SUPPORTED_PERIOD_SYNONYMS.get(normalized)
    if canonical is not None:
        return canonical, False
    return None, True  # recognized (enumerated or generic fallback) but unsupported


def _has_k_suffix(num_text: str) -> bool:
    return num_text[-1:].lower() == "k"


def _apply_shared_trailing_k(op1: int | None, num1_text: str, num2_text: str) -> int | None:
    """A trailing k/K on only the *last* operand of a range shares
    backward onto an unmarked first operand (e.g. `"$120-150k"` ->
    120000-150000), per the approved proposal. No form beyond this exact,
    literal case is implemented -- a k on only the first operand does not
    share forward (absent from the approved proposal)."""
    if op1 is None:
        return None
    if _has_k_suffix(num1_text) or not _has_k_suffix(num2_text):
        return op1
    scaled = op1 * 1000
    if scaled > _INT32_MAX:
        return None
    return scaled


def _wrap_int(value: int | None) -> NormalizationResult[int]:
    if value is None:
        return _UNAVAILABLE_INT
    return NormalizationResult(value, Provenance.PARSED_DESCRIPTION)


def _wrap_str(value: str | None) -> NormalizationResult[str]:
    if value is None:
        return _UNAVAILABLE_STR
    return NormalizationResult(value, Provenance.PARSED_DESCRIPTION)


def classify_salary(compensation_text: str | None) -> SalaryResult:
    """Pure function: `compensation_text` in, one `SalaryResult` out. See
    the module docstring for the full grammar, tables, and rationale."""
    if compensation_text is None:
        return _UNAVAILABLE_RESULT

    normalized = _normalize_field(compensation_text)
    if not normalized:
        return _UNAVAILABLE_RESULT

    match: re.Match[str] | None = None
    shape = ""
    for name, pattern in _PRODUCTIONS.items():
        candidate = pattern.fullmatch(normalized)
        if candidate is not None:
            match = candidate
            shape = name
            break

    if match is None:
        return _UNAVAILABLE_RESULT

    groups = match.groupdict()
    label = groups.get("label")
    code_prefix = groups.get("code_prefix")
    code_suffix = groups.get("code_suffix")
    symbols = [groups[f"sym{i}"] for i in (1, 2) if groups.get(f"sym{i}") is not None]

    has_anchor = (
        label is not None or code_prefix is not None or code_suffix is not None or len(symbols) > 0
    )
    if not has_anchor:
        return _UNAVAILABLE_RESULT

    currency = _resolve_currency(code_prefix, code_suffix, symbols)
    period, period_invalidates_numeric = _resolve_period(groups.get("period"))

    op1 = _parse_operand(groups.get("sign1"), groups["num1"])
    op2 = _parse_operand(groups.get("sign2"), groups["num2"]) if "num2" in groups else None

    minimum: int | None
    maximum: int | None

    if shape == "single_or_open_lower":
        if groups.get("plus") is not None:
            minimum, maximum = op1, None
        else:
            minimum, maximum = op1, op1
    elif shape == "open_upper":
        minimum, maximum = None, op1
    else:  # hyphen_range, to_range, between_and_range -- two operands, atomic
        op1 = _apply_shared_trailing_k(op1, groups["num1"], groups["num2"])
        if op1 is None or op2 is None:
            minimum, maximum = None, None
        elif op1 > op2:
            minimum, maximum = None, None  # inverted range: never silently reordered
        else:
            minimum, maximum = op1, op2

    if period_invalidates_numeric:
        minimum, maximum = None, None

    return SalaryResult(
        minimum=_wrap_int(minimum),
        maximum=_wrap_int(maximum),
        currency=_wrap_str(currency),
        period=_wrap_str(period),
    )
