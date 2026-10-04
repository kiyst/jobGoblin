"""Strict Greenhouse `DiscoveredJob` -> `PostingInputs` mapping (Phase 4 S2b, Class H;
`docs/DECISIONS/0015-greenhouse-content-conversion-and-posting-input-mapping.md`).

The provider-to-normalization bridge. Exactly three Greenhouse-derived values may
become parser inputs:

| Greenhouse source | `DiscoveredJob` (adapter) | `PostingInputs` |
|---|---|---|
| `title` | `title`, verbatim | `title` |
| `location.name` | `location`, verbatim | `location` |
| `content` | `description`, converted under a declared content mode | `description` |

Nothing else reaches a parser: not `raw`, `company`, URLs, IDs, timestamps,
`compensation_text`, or any other payload field. Each value is passed through
unchanged (no strip, case-fold, or fallback), so whitespace, Unicode, and the
empty/`None` distinction are preserved exactly.

The mapping reads only `provider`, `source`, `title`, `description`, and
`location`, by direct attribute access. It does not call `normalize_posting`,
and nothing at runtime calls it: neither it nor the adapter is registered or
wired anywhere.
"""

from __future__ import annotations

from app.normalization.posting import PostingInputs
from app.schemas.discovered_job import DiscoveredJob

_ERROR_JOB_TYPE = "greenhouse_posting_inputs requires a DiscoveredJob instance"
_ERROR_NOT_GREENHOUSE = "greenhouse_posting_inputs accepts only greenhouse provider/source jobs"


def greenhouse_posting_inputs(job: DiscoveredJob) -> PostingInputs:
    """Maps one Greenhouse job to parser inputs. Raises a fixed `TypeError` for a
    non-`DiscoveredJob` argument and a fixed `ValueError` unless both `provider`
    and `source` are `"greenhouse"`; neither message contains a runtime value."""
    if not isinstance(job, DiscoveredJob):
        raise TypeError(_ERROR_JOB_TYPE)
    if job.provider != "greenhouse" or job.source != "greenhouse":
        raise ValueError(_ERROR_NOT_GREENHOUSE)
    return PostingInputs(
        title=job.title,
        description=job.description,
        location=job.location,
    )
