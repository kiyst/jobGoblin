import re

# Same canonical-identifier grammar already enforced by every `provider`/
# `source` database CHECK in this schema (`job_occurrences`,
# `raw_job_ingestions`, `collection_run_provider_attempts`): lowercase,
# ASCII, starts with a letter/digit, otherwise letters/digits/`.`/`_`/`-`.
#
# Deliberately not exported: a caller reaching for this pattern directly
# would be one `.match()` away from silently reintroducing the exact bug
# `app/discovery/query_planner.py` once had — Python's `$` matches either
# true end-of-string or immediately before a single trailing `\n`, so
# `.match()` against this pattern wrongly accepts e.g. `"fixture_provider\n"`
# even though it is not a canonical slug. `is_canonical_slug()` below is the
# only supported entry point and always performs a genuine full-string
# match (`.fullmatch()`), closing that gap for every caller by construction.
_CANONICAL_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def is_canonical_slug(value: str) -> bool:
    """True if `value` is a canonical lowercase-ASCII identifier slug:
    starts with a lowercase letter or digit, followed by any number of
    lowercase letters, digits, `.`, `_`, or `-`. Matches the grammar every
    `provider`/`source` database `CHECK` in this schema already enforces.

    Always a genuine full-string match — a trailing newline (or any other
    trailing character) is rejected, never silently accepted.
    """
    return _CANONICAL_SLUG_PATTERN.fullmatch(value) is not None
