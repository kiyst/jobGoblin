"""Company-domain normalization (docs/DATA_MODEL.md's `companies.domain`).

`normalize_domain()` is a pure function — no ORM, no provider, no I/O — so it
can be unit-tested in isolation and reused wherever a domain needs to be
normalized before it reaches `companies.domain`.

Malformed input never raises: it returns `None`, the same representation
"domain unknown" already uses elsewhere in this schema. This is an explicit
product decision (see docs/DATA_MODEL.md), not an oversight — a company
record with an unparseable domain is still a valid company, just one without
a usable domain-based identity signal.
"""

from __future__ import annotations

import ipaddress
import re

import idna

# Matches a URL scheme only when followed by "://" (an authority section) —
# `arbitrary scheme://` URLs are in scope, but a bare host with a port such
# as "acme.com:8080" must NOT be misread as scheme "acme.com" with path
# "8080", which is exactly what `urllib.parse.urlsplit` does for a
# colon-containing string with no "//". Detecting the scheme ourselves,
# only when "://" is actually present, avoids that misparse entirely.
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")
_PATH_START_RE = re.compile(r"[/?#]")
_MAX_PORT = 65535


def normalize_domain(value: str | None) -> str | None:
    """Canonicalizes a company-provided domain, bare host, or URL into the
    single ASCII hostname used for `companies.domain` identity matching.

    Steps: trim; lowercase; accept either a bare host or a `scheme://` URL;
    strip userinfo, port, path, query, and fragment; convert the remaining
    host through IDNA2008/UTS #46 into its canonical ASCII form; only then
    strip one leading `www.` and one trailing DNS root-label dot, and
    reject anything that isn't a syntactically valid multi-label hostname
    (single-label hosts, IP literals, empty labels, invalid ports, and
    oversized names all return `None`, never raise).

    IDNA/UTS #46 conversion must happen *before* the `www.`/trailing-dot/
    IP-literal/multi-label checks, not after: UTS #46 mapping can itself
    turn a Unicode look-alike into the exact ASCII form those checks are
    watching for (e.g. the ideographic full stop U+3002 or fullwidth
    U+FF0E both map to ASCII "."; fullwidth digits U+FF10-U+FF19 map to
    ASCII "0"-"9"). Checking the *pre-mapping* string lets a Unicode form
    that only becomes `www.`/a trailing dot/an IP literal *after* mapping
    bypass every one of those checks — confirmed at commit `7bd27a7`:
    `www。acme.com` failed to collide with `acme.com`, `acme.com。`
    kept a root-label separator, and full-width `127.0.0.1` was accepted as
    a hostname. Running the checks on the already-canonical, already-ASCII
    output closes all three.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    text = text.lower()

    scheme_match = _SCHEME_RE.match(text)
    remainder = text[scheme_match.end() :] if scheme_match else text

    path_match = _PATH_START_RE.search(remainder)
    authority = remainder[: path_match.start()] if path_match else remainder

    # Drop userinfo ("user:pass@") if present — a host can't itself contain
    # "@", so the last "@" is always the userinfo/host boundary.
    authority = authority.rsplit("@", 1)[-1]
    if not authority:
        return None

    if authority.startswith("["):
        # Bracketed IPv6 literal, e.g. "[::1]:8080" — RFC 3986 defines
        # bracket syntax only for an IP literal, never a hostname; the
        # bracketed content is extracted as "host" purely so IDNA encoding
        # below fails on it (colons are not valid hostname codepoints)
        # rather than on the surrounding bracket/port syntax.
        end = authority.find("]")
        if end == -1:
            return None
        host = authority[1:end]
        trailer = authority[end + 1 :]
        if trailer and not (trailer.startswith(":") and trailer[1:].isdigit()):
            return None
    elif authority.count(":") == 1:
        host, _, port = authority.partition(":")
        if not port.isdigit() or not (0 <= int(port) <= _MAX_PORT):
            return None
    else:
        # No colon (no port), or more than one colon (a bare, unbracketed
        # IPv6 literal) — treat the whole thing as the host either way; a
        # bare IPv6 literal fails IDNA encoding below (colons are not valid
        # hostname codepoints), as does any other multi-colon garbage.
        host = authority

    if not host:
        return None

    try:
        encoded = idna.encode(host, uts46=True, std3_rules=True)
    except (idna.IDNAError, UnicodeError, ValueError):
        return None
    canonical = encoded.decode("ascii").lower()

    if canonical.startswith("www."):
        canonical = canonical[4:]
    if canonical.endswith("."):
        canonical = canonical[:-1]
    if not canonical:
        return None

    try:
        ipaddress.ip_address(canonical)
    except ValueError:
        pass
    else:
        return None  # an IP literal is not a valid company domain

    if "." not in canonical:
        return None  # a single-label host is not a valid company domain

    return canonical
