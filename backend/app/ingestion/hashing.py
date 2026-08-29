import hashlib
import json
from typing import Any


def canonical_json_hash(payload: dict[str, Any]) -> str:
    """SHA-256 hex digest of `payload`'s canonical JSON encoding, used for
    `raw_job_ingestions.raw_content_hash`.

    `raw_payload` is a **value/structure-preserving** audit representation
    of `DiscoveredJob.raw` (this hash's own input) — not a byte-preserving
    one. Once a Python `dict` round-trips through JSONB, insertion order of
    equal-valued keys and any incidental raw-text whitespace from the
    original source payload are already gone; JSONB itself cannot restore
    them. `sort_keys=True` below is exactly what makes the hash agree with
    that reality: two dicts holding the same key/value pairs in different
    insertion order (including nested dicts) must hash identically, since
    that's the only distinction JSONB storage cannot preserve anyway.

    `allow_nan=False` rejects `NaN`/`Infinity`/`-Infinity` — `json.dumps`
    would otherwise silently emit the non-standard literals `NaN`/
    `Infinity`, which PostgreSQL's `jsonb` input function rejects outright.
    Hashing must fail exactly where storage would, not accept a payload
    JSONB can never actually persist.
    """
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
