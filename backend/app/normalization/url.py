"""Job-occurrence URL normalization (ADR 0004; docs/DATA_MODEL.md's
`job_occurrences.canonical_url_normalized`/`source_url_normalized`).

`normalize_url()` is a pure function — no ORM, no provider, no I/O — so it
can be unit-tested in isolation. It is a narrowly scoped **identity
canonicalizer** required by the schema (see
docs/PHASE_RISK_CHECKLIST.md's Phase 1 clarification), not the broader
Phase 3 content-normalization pipeline (title/salary/location/skill, etc.).

Deliberately does **not** reuse `app.normalization.company.normalize_domain()`:
a URL's host is a click-through target, not a company-identity signal —
`www.` must be retained, and a valid IP-literal host remains a valid URL
host (both are rejected outright by `normalize_domain()`).

Malformed input never raises: it returns `None`, the same representation
"unknown"/"unparseable" already uses elsewhere in this schema.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import parse_qsl, urlencode, urlsplit

import idna

_DEFAULT_PORTS = {"http": 80, "https": 443}

# Matches the trim set the `*_normalized` columns' own DB CHECK constraints
# use (`trim(both E'\t\n\r ' from ...)`). `urlsplit()` only strips `\t`/`\n`/
# `\r` from the whole input already; a literal, unencoded space is not
# rejected by `urlsplit()` and can otherwise survive verbatim in `.path`.
_TRIM_CHARS = " \t\n\r"

# Stripped regardless of case: exact tracking-parameter names named in
# ADR 0004, plus every parameter whose name starts with "utm_" (checked
# separately in _should_strip_param, not just these five enumerated here).
_EXACT_STRIP_NAMES = frozenset(
    {
        "gh_src",
        "lever-source",
        "trk",
        "li_fat_id",
        "ref",
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
    }
)

# Per-(provider, source) query-parameter allow-list, overriding the deny-list
# above when a name is listed here. Deliberately empty in Phase 1 (ADR 0004:
# "starts empty/conservative", grows only with real Phase 4/7 adapter
# evidence) — never guess entries ahead of that evidence.
_PER_SOURCE_ALLOW_LIST: dict[tuple[str, str], frozenset[str]] = {}


def _should_strip_param(name: str, *, allowed: frozenset[str]) -> bool:
    lowered = name.lower()
    if lowered in allowed:
        return False
    return lowered.startswith("utm_") or lowered in _EXACT_STRIP_NAMES


def _canonicalize_host(hostname: str) -> str | None:
    """Returns the canonical host component (bracketed for IPv6), or `None`
    if `hostname` is neither a valid IP literal nor a validly-encodable
    domain name. Unlike `normalize_domain()`, a single-label host and an
    IP-literal host are both accepted — a URL's host is not being asked to
    prove company identity, only to be a stable, comparable target."""
    try:
        parsed_ip = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        return f"[{parsed_ip}]" if parsed_ip.version == 6 else str(parsed_ip)

    try:
        encoded = idna.encode(hostname, uts46=True, std3_rules=True)
    except (idna.IDNAError, UnicodeError, ValueError):
        return None
    return encoded.decode("ascii").lower()


def normalize_url(
    value: str | None, *, provider: str | None = None, source: str | None = None
) -> str | None:
    """Canonicalizes an absolute `http`/`https` URL for identity comparison
    (ADR 0004's match-precedence step 2/fallback natural key). Returns
    `None` for anything that isn't a syntactically valid, absolute
    http(s) URL with a hostname and no embedded credentials — relative
    URLs, protocol-relative URLs, a missing host, an invalid port, and
    `user:pass@host` userinfo are all rejected this way, never by raising.

    Steps: lowercase the scheme; canonicalize the host (IDNA/UTS #46 for a
    domain, preserved-as-valid for an IP literal — see `_canonicalize_host`);
    drop the fragment; drop the port only when it's the scheme's default;
    collapse an empty/root path and `/` to the same `/`, and strip trailing
    slashes from any other path (case preserved); drop every query
    parameter matching the tracking-parameter deny-list (case-insensitive
    `utm_*` prefix, plus a fixed exact-name list), *unless* the caller's
    `(provider, source)` has that name on its own allow-list; keep every
    other parameter, including repeated names and blank values, sorted
    deterministically; omit the `?` entirely when nothing is left.

    `provider`/`source` are optional context for the per-source allow-list
    (empty in this Phase 1 slice — see `_PER_SOURCE_ALLOW_LIST`), not part
    of the URL itself.
    """
    if value is None:
        return None

    try:
        parsed = urlsplit(value)
        port = parsed.port
        hostname = parsed.hostname
        username = parsed.username
        password = parsed.password
    except ValueError:
        return None

    scheme = parsed.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        return None
    if not hostname:
        return None
    if username is not None or password is not None:
        return None

    host = _canonicalize_host(hostname)
    if host is None:
        return None

    port_suffix = ""
    if port is not None and port != _DEFAULT_PORTS[scheme]:
        port_suffix = f":{port}"

    path = parsed.path.rstrip("/") or "/"

    allowed = (
        _PER_SOURCE_ALLOW_LIST.get((provider, source), frozenset())
        if provider and source
        else frozenset()
    )
    retained = [
        (name, param_value)
        for name, param_value in parse_qsl(parsed.query, keep_blank_values=True)
        if not _should_strip_param(name, allowed=allowed)
    ]
    retained.sort()
    query_suffix = f"?{urlencode(retained)}" if retained else ""

    result = f"{scheme}://{host}{port_suffix}{path}{query_suffix}"
    return result.strip(_TRIM_CHARS)
