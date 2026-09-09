r"""Deterministic location-geography classifier (Phase 3 -- sixth parser
slice; docs/ARCHITECTURE.md Section 4's `normalization/location.py`,
docs/PHASE_RISK_CHECKLIST.md's Phase 3 exit gate -- Workflow v3.1 pilot
parser slice 3 of 3, following four proposal-review rounds before
implementation).

Pure function: `location` free text in, one `LocationResult` out -- a
composite of four independently-provenanced `NormalizationResult` fields
(`city`/`state`/`country`/`postal_code`, all `str`), matching the `jobs`
table's location-related columns exactly. No database, ORM, provider,
network, or ingestion-pipeline dependency; no `parser_version` threading.
`title`/`description` are never read -- `location` is the only source,
since `DiscoveredJob.location` is always a dedicated schema field, never
something to fish out of narrative text.

**Explicit separation from `remote.py`**: this module never reads
title/description and never produces a `remote_type`-shaped value --
`remote.py` owns `jobs.remote_type` exclusively. A recognized work-
arrangement marker (`remote`/`hybrid`/`onsite`/`on-site`/`on site`)
appearing inside a `location` string is consumed and discarded here,
never asserted as a geography fact and never fed back into any
remote/hybrid/onsite classification.

**City resolution is deferred, not implemented, in this slice.** `city`
is unconditionally `Provenance.UNAVAILABLE` for every input this function
returns. This is a deliberate scope boundary, not a defect: no positive
city catalog/gazetteer exists in this repository, and a denylist-based
approach (reject a closed list of known-generic phrases, otherwise treat
any city-shaped span as a real city) was considered and rejected during
proposal review -- it cannot establish a positive correctness guarantee,
since any city-shaped span not on the denylist (`"Headquarters, United
States"`, `"Flexible, Canada"`, `"Anywhere, France"`, `"Distributed,
US"`) would otherwise be confidently, and wrongly, emitted as a city.
The fix is structural: every production below still requires a
city/region-shaped span to be present (so a bare, contextless state code
alone is never confidently resolved either), but that span's captured
text is always discarded, never wired into any output field. `state`,
`country`, and `postal_code` remain independently extractable, since
each is validated against a closed catalog or a strict structural
pattern -- never free text.

**The generic/non-geographic sentinel catalog remains as defense-in-
depth only** (`_SENTINEL_PHRASES`) -- it is not, and never was, the
mechanism that makes discarding the city span safe (nothing needs to
make it safe; it is never read). When a discarded geo/region span
exactly matches a sentinel phrase, the *whole* result is rejected (all
four fields unavailable, including `country`, even when the country is
otherwise literally stated) as an extra conservative layer treating a
small set of known placeholder-shaped prefixes as a signal the entire
location description is unreliable. This catalog is deliberately small
and reviewable, not exhaustive: a generic phrase not in it is not
rejected by this layer, but it was never going to populate `city`
regardless, since `city` is never populated at all in v1.

**Five finite productions** (`_PRODUCTIONS`; no form beyond these is
implemented), each wrapped in an identical, independently-optional
marker prefix/suffix (see below):

    <COUNTRY>                                   country-alone
    <geo> , <STATE>                             state (geo discarded)
    <geo> , <STATE> <ZIP>                       state+zip (geo discarded)
    <geo> , <COUNTRY>                           country (geo discarded)
    <geo> , <region> , <COUNTRY>                dispatch (geo AND region discarded)

**Marker wrapper** -- exactly two independent optional slots (never both
present in one match; rejected if so):

    MARKER , <production>              prefix-comma, e.g. "Remote, Austin, TX"
    MARKER - <production>              prefix-hyphen, mandatory whitespace both
                                        sides of the hyphen (unlike a numeric
                                        range separator, a word-to-word hyphen
                                        boundary is made strict from the start,
                                        applying the salary-classifier
                                        correction's lesson proactively)
    <production> (MARKER)              suffix-parenthesized, literal matched
                                        parentheses only

`MARKER` is the closed catalog `{remote, hybrid, onsite, on-site, on
site}`, case-insensitive, applied uniformly across both wrapper slots.
A marker word embedded inside a discarded geo/region span (`"Austin
Remote, TX"`) is rejected the same way a coordinator word is (see
below) -- markers are consumed but never populate geography or
`remote_type`.

**Discarded-span validation** (`_geo_span_is_rejected`) -- a captured
geo/region span, though never read into an output field, still gates
whether the *whole* result may be confidently produced at all. The span
is rejected (whole result -> all four fields unavailable) if it
contains, as a standalone word (case-insensitive, not a substring --
`"Andover"` is not rejected for containing `"and"`), `"or"` or `"and"`;
contains any of the literal characters `/`, `;`, `|`; contains a
standalone marker word; or, trimmed and with internal covered-whitespace
runs collapsed to a single space, exactly equals a sentinel phrase. The
`or`/`and`/delimiter check exists specifically because `state`/`country`
are closed-catalog-anchored and reject junk "for free" via a failed
catalog lookup, but `geo`/`region` are open-ended, permissive tokens --
without this explicit check, `"London or Paris, France"` would lexically
match `geo="London or Paris"` (three space-separated words, no comma
inside) + `country=France`, silently treating a multi-location listing
as if it were one place. `"Austin, TX or Boston, MA"` fails for a
different, structural reason -- the closed state catalog cannot match
`"TX or Boston, MA"` as a literal 2-letter code -- demonstrating that the
open-ended-token risk and the closed-catalog risk are genuinely
different failure modes, not redundant checks.

**Three-part dispatch** (`region_country_form`) -- `region` is matched
by the same permissive geo-shaped pattern as `geo`, then semantically
classified as "a recognized US state code" or not:

| `region`                   | `country`   | Result                          |
|-----------------------------|-------------|----------------------------------|
| Recognized US state (any)  | Explicit US | `state`/`country=United States`  |
| Recognized US state        | Non-US      | All four unavailable             |
| Not a recognized US state  | Non-US      | `country` only (state unavailable) |
| Not a recognized US state  | Explicit US | All four unavailable             |

This makes `"Austin, TX, Canada"` fail (state=TX real, country=Canada
non-US) while preserving `"Toronto, ON, Canada"` (region=ON not a
recognized state, country=Canada non-US).

**Collision-bearing US state abbreviations** (`_COLLISION_STATES`) --
a USPS Appendix B state abbreviation that is also a current ISO 3166-1
alpha-2 country code:

    AL=Albania, AR=Argentina, AZ=Azerbaijan, CA=Canada, CO=Colombia,
    DE=Germany, GA=Gabon, ID=Indonesia, IL=Israel, IN=India,
    KY=Cayman Islands, LA=Laos, MA=Morocco, MD=Moldova, ME=Montenegro,
    MN=Mongolia, MO=Macao, MS=Montserrat, MT=Malta, NC=New Caledonia,
    NE=Niger, PA=Panama, SC=Seychelles, SD=Sudan, TN=Tunisia,
    VA=Holy See (Vatican City State).

This 26-code set was independently derived (walked all 51 USPS codes
against the ISO 3166-1 alpha-2 list one at a time) during proposal
review, converged with an independently-proposed candidate set, and was
confirmed via a live-source check against USPS Appendix B and the ISO
3166 authority on 2026-09-09 -- frozen, not re-verified at every
implementation. A collision-bearing state code appearing in the plain
`geo, STATE` form (no ZIP, no explicit country) has no US-only anchor
and fails closed (`"Toronto, CA"`, `"Bangalore, IN"`, `"Berlin, DE"` all
return all four fields unavailable). It is disambiguated only by a
trailing US ZIP (`"Sacramento, CA 95814"`, anchored regardless of
collision-set membership) or an explicit US country in the three-part
form (`"Sacramento, CA, United States"`, via the dispatch table above).
`DC` is never a collision-set member (not an ISO country code) and
always resolves via the plain two-part form, in either its bare (`DC`)
or dotted (`D.C.`/`D.C`) spelling.

**Country catalog** (`_COUNTRY_CANONICAL`), canonicalized to the full
English name on output: `United States` (aliases `US`/`U.S.`/`U.S.A.`/
`USA`), `United Kingdom` (alias `UK`), `Canada`, `Australia`, `Ireland`,
`Germany`, `France`, `India`, `Singapore`, `Netherlands`. Deliberately
narrow and closed -- no other country or 2/3-letter code is recognized
(`country` stays unavailable). No 2-letter code besides the `US`/`UK`
aliases is accepted, specifically to avoid reintroducing the collision
risk `_COLLISION_STATES` exists to bound (`CA`/`IN`/`DE` are state
codes here, never country codes).

**Normalization order**, identical to `salary.py`'s established
precedent: NFKC-normalize, strip the project's covered-whitespace set
(`_WHITESPACE = "\t\n\r "`) from both ends, then -- if the result ends
with exactly one literal `.` -- remove it and re-strip. Every grammar
boundary uses `_WS = r"[\t\n\r ]"` only, never unrestricted `\s`.

**Confidently-wrong blockers directly implemented here**: a discarded
geo/region span never populates `city` (structural, not denylist-
dependent); a collision-bearing state code is never resolved without a
US-only anchor; `CA` never resolves to Canada in the state/country slot;
a multi-location or coordinator-bearing string never confidently
extracts `state`/`country`/`postal_code` either; a three-part
state-vs-country conflict is never silently resolved to either side;
the sentinel catalog's silence is never read as proof a discarded span
is a genuine, validated location.

**Evidence limitation (disclosed, not treated as satisfied)**: every
fixture in `tests/fixtures/normalization/location_cases.json` is a
hand-constructed synthetic example. Exactly one real sanitized location
string exists in this repository --
`backend/tests/fixtures/discovery/greenhouse_live_canary.json`'s
`job.location.name` (`"Remote, US"`) -- exercised by its own dedicated
test (`test_real_sanitized_greenhouse_fixture_classifies_correctly`)
that loads the actual fixture file and asserts the source value before
asserting the classification, so the claim cannot silently drift out of
sync with the committed fixture.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.normalization.types import NormalizationResult, Provenance

# The project's established covered-whitespace set (matches salary.py's
# and experience.py's own `_WHITESPACE`/normalization precedent).
_WHITESPACE = "\t\n\r "
_WS = r"[\t\n\r ]"


@dataclass(frozen=True)
class LocationResult:
    """Composite result: four independently-provenanced fields, matching
    the `jobs` table's location-related columns exactly. Never persisted
    directly -- see the module docstring. No `__post_init__` invariant is
    needed (unlike `ExperienceRange`/`SalaryResult`) -- there is no
    ordering/range concept for geography to defend against."""

    city: NormalizationResult[str]
    state: NormalizationResult[str]
    country: NormalizationResult[str]
    postal_code: NormalizationResult[str]


_UNAVAILABLE_STR: NormalizationResult[str] = NormalizationResult(None, Provenance.UNAVAILABLE)
_UNAVAILABLE_RESULT = LocationResult(
    _UNAVAILABLE_STR, _UNAVAILABLE_STR, _UNAVAILABLE_STR, _UNAVAILABLE_STR
)


def _normalize_field(text: str) -> str:
    """Identical three-step order to `salary.py`'s `_normalize_field`."""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.strip(_WHITESPACE)
    if normalized.endswith(".") and not normalized.endswith(".."):
        normalized = normalized[:-1].strip(_WHITESPACE)
    return normalized


# ---------------------------------------------------------------------------
# Closed catalogs
# ---------------------------------------------------------------------------

_STATES = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        "DC",
    }
)  # USPS Appendix B: 50 states + DC.

_COLLISION_STATES = frozenset(
    {
        "AL",
        "AR",
        "AZ",
        "CA",
        "CO",
        "DE",
        "GA",
        "ID",
        "IL",
        "IN",
        "KY",
        "LA",
        "MA",
        "MD",
        "ME",
        "MN",
        "MO",
        "MS",
        "MT",
        "NC",
        "NE",
        "PA",
        "SC",
        "SD",
        "TN",
        "VA",
    }
)  # Frozen, independently derived and live-source-confirmed 2026-09-09
# (see module docstring) -- USPS state abbreviations that collide with a
# current ISO 3166-1 alpha-2 country code.

_STATE_ALTERNATION = "|".join(sorted(_STATES - {"DC"}))
_STATE_TOKEN = rf"(?:{_STATE_ALTERNATION}|DC|D\.C\.?)"

_ZIP = r"[0-9]{5}(?:-[0-9]{4})?"

_COUNTRY_CANONICAL: dict[str, str] = {
    "united states": "United States",
    "us": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "usa": "United States",
    "united kingdom": "United Kingdom",
    "uk": "United Kingdom",
    "canada": "Canada",
    "australia": "Australia",
    "ireland": "Ireland",
    "germany": "Germany",
    "france": "France",
    "india": "India",
    "singapore": "Singapore",
    "netherlands": "Netherlands",
}
_COUNTRY_TOKEN = (
    rf"(?:United{_WS}+Kingdom|United{_WS}+States|U\.S\.A\.|U\.S\.|USA|US|UK|"
    rf"Canada|Australia|Ireland|Germany|France|India|Singapore|Netherlands)"
)

_MARKER = r"(?:remote|hybrid|on-site|on site|onsite)"

_SENTINEL_PHRASES = frozenset(
    {
        "multiple locations",
        "various locations",
        "worldwide",
        "various",
        "multiple",
        "nationwide",
        "global",
    }
)

# Permissive: letters, internal spaces/hyphens/apostrophes/periods --
# never anchored to a catalog. Validity is a semantic-layer concern
# (_geo_span_is_rejected), mirroring salary.py's lexical/semantic split.
_GEO_TOKEN = r"[A-Za-z][A-Za-z .'\-]*"

_MARKER_PREFIX = (
    rf"(?:(?P<marker_prefix_comma>{_MARKER}){_WS}*,{_WS}*"
    rf"|(?P<marker_prefix_hyphen>{_MARKER}){_WS}+-{_WS}+)?"
)
_MARKER_SUFFIX = rf"(?:{_WS}+\({_WS}*(?P<marker_suffix>{_MARKER}){_WS}*\))?"

_PRODUCTIONS: dict[str, re.Pattern[str]] = {
    "country_alone": re.compile(
        rf"^{_MARKER_PREFIX}(?P<country>{_COUNTRY_TOKEN}){_MARKER_SUFFIX}$", re.IGNORECASE
    ),
    "state_form": re.compile(
        rf"^{_MARKER_PREFIX}(?P<geo>{_GEO_TOKEN}){_WS}*,{_WS}*(?P<state>{_STATE_TOKEN})"
        rf"{_MARKER_SUFFIX}$",
        re.IGNORECASE,
    ),
    "state_zip_form": re.compile(
        rf"^{_MARKER_PREFIX}(?P<geo>{_GEO_TOKEN}){_WS}*,{_WS}*(?P<state>{_STATE_TOKEN})"
        rf"{_WS}+(?P<zip>{_ZIP}){_MARKER_SUFFIX}$",
        re.IGNORECASE,
    ),
    "country_form": re.compile(
        rf"^{_MARKER_PREFIX}(?P<geo>{_GEO_TOKEN}){_WS}*,{_WS}*(?P<country>{_COUNTRY_TOKEN})"
        rf"{_MARKER_SUFFIX}$",
        re.IGNORECASE,
    ),
    "region_country_form": re.compile(
        rf"^{_MARKER_PREFIX}(?P<geo>{_GEO_TOKEN}){_WS}*,{_WS}*(?P<region>{_GEO_TOKEN})"
        rf"{_WS}*,{_WS}*(?P<country>{_COUNTRY_TOKEN}){_MARKER_SUFFIX}$",
        re.IGNORECASE,
    ),
}

_OR_AND_RE = re.compile(r"(?<![A-Za-z])(?:or|and)(?![A-Za-z])", re.IGNORECASE)
_MARKER_WORD_RE = re.compile(rf"(?<![A-Za-z])(?:{_MARKER})(?![A-Za-z])", re.IGNORECASE)
_DELIMITER_CHARS = frozenset("/;|")


def _geo_span_is_rejected(span: str) -> bool:
    """Semantic validation of a discarded geo/region span -- see the
    module docstring's "Discarded-span validation" section."""
    if _OR_AND_RE.search(span):
        return True
    if any(ch in _DELIMITER_CHARS for ch in span):
        return True
    if _MARKER_WORD_RE.search(span):
        return True
    collapsed = re.sub(rf"{_WS}+", " ", span.strip(_WHITESPACE)).lower()
    return collapsed in _SENTINEL_PHRASES


def _canonicalize_country(raw: str) -> str | None:
    collapsed = re.sub(rf"{_WS}+", " ", raw.strip(_WHITESPACE)).lower()
    return _COUNTRY_CANONICAL.get(collapsed)


def _canonicalize_state(raw: str) -> str:
    return raw.replace(".", "").upper()


def _wrap_str(
    value: str | None, provenance: Provenance = Provenance.PARSED_DESCRIPTION
) -> NormalizationResult[str]:
    if value is None:
        return _UNAVAILABLE_STR
    return NormalizationResult(value, provenance)


def _build_result(
    *,
    state: str | None = None,
    country: str | None = None,
    postal_code: str | None = None,
    country_provenance: Provenance = Provenance.PARSED_DESCRIPTION,
) -> LocationResult:
    """`city` is unconditionally unavailable -- see the module docstring's
    "City resolution is deferred" section. Hardcoded here so no call site
    can accidentally populate it."""
    return LocationResult(
        city=_UNAVAILABLE_STR,
        state=_wrap_str(state),
        country=_wrap_str(country, country_provenance),
        postal_code=_wrap_str(postal_code),
    )


def classify_location(location: str | None) -> LocationResult:
    """Pure function: `location` in, one `LocationResult` out. See the
    module docstring for the full grammar, tables, and rationale."""
    if location is None:
        return _UNAVAILABLE_RESULT

    normalized = _normalize_field(location)
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

    has_prefix_marker = (
        groups.get("marker_prefix_comma") is not None
        or groups.get("marker_prefix_hyphen") is not None
    )
    has_suffix_marker = groups.get("marker_suffix") is not None
    if has_prefix_marker and has_suffix_marker:
        return _UNAVAILABLE_RESULT

    geo = groups.get("geo")
    if geo is not None and _geo_span_is_rejected(geo):
        return _UNAVAILABLE_RESULT

    region = groups.get("region")
    if region is not None and _geo_span_is_rejected(region):
        return _UNAVAILABLE_RESULT

    if shape == "country_alone":
        country = _canonicalize_country(groups["country"])
        if country is None:
            return _UNAVAILABLE_RESULT
        return _build_result(country=country)

    if shape == "state_form":
        state = _canonicalize_state(groups["state"])
        if state in _COLLISION_STATES:
            return _UNAVAILABLE_RESULT  # no anchor beyond a bare state code
        return _build_result(
            state=state, country="United States", country_provenance=Provenance.INFERRED
        )

    if shape == "state_zip_form":
        state = _canonicalize_state(groups["state"])
        return _build_result(state=state, country="United States", postal_code=groups["zip"])

    if shape == "country_form":
        country = _canonicalize_country(groups["country"])
        if country is None:
            return _UNAVAILABLE_RESULT
        return _build_result(country=country)

    # region_country_form
    country = _canonicalize_country(groups["country"])
    if country is None:
        return _UNAVAILABLE_RESULT
    region_state = _canonicalize_state(groups["region"])
    region_is_state = region_state in _STATES
    is_us = country == "United States"
    if region_is_state and is_us:
        return _build_result(state=region_state, country="United States")
    if region_is_state and not is_us:
        return _UNAVAILABLE_RESULT
    if not region_is_state and not is_us:
        return _build_result(country=country)
    return _UNAVAILABLE_RESULT  # not region_is_state and is_us
