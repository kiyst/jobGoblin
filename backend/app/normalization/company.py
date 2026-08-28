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
    strip userinfo, port, path, query, and fragment; strip one leading
    `www.` and one trailing DNS root-label dot; convert through IDNA2008/
    UTS #46 (rejecting anything that isn't a syntactically valid multi-label
    hostname — single-label hosts, IP literals, empty labels, invalid ports,
    and oversized names all return `None`, never raise).
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
        # Bracketed IPv6 literal, e.g. "[::1]:8080" — the bracketed content
        # is the host; it is rejected as an IP literal below regardless.
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
        # bare IPv6 literal is rejected as an IP literal below, and any
        # other multi-colon garbage fails IDNA encoding below.
        host = authority

    if host.startswith("www."):
        host = host[4:]
    if host.endswith("."):
        host = host[:-1]
    if not host:
        return None

    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return None  # an IP literal is not a valid company domain

    if "." not in host:
        return None  # a single-label host is not a valid company domain

    try:
        encoded = idna.encode(host, uts46=True, std3_rules=True)
    except (idna.IDNAError, UnicodeError, ValueError):
        return None

    return encoded.decode("ascii").lower()
