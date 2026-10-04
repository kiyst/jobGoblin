"""ADR 0011 D2 realistic-output protection at the pure `normalize_posting`
composition boundary (Phase 4 S2, docs/DECISIONS/0014-pure-posting-
composition-and-scoped-d2.md).

This module is the durable D2 contract. Every authoritative expectation
below is literal committed data; the module never reads or requires any
external manifest. The expectations were derived (and cross-checked) from
the gitignored review aid `.claude/runtime/phase4-s2-d2-expectation-
manifest.json` (SHA-256
`f480ed2ec0305a7a85987fb9cfca8e1763816c2cad7a50d13203d0893b104d65`, produced
by `.claude/runtime/phase4-s2-d2-manifest-generator.py`, SHA-256
`fff152a4dcd8055aec433191fc9eee4aecd79697656c26766aa414cb4195563c`); those
hashes are derivation/review evidence only, never a dependency.

Scope of the claim (ADR 0014): D2 is satisfied only at this composition
boundary, for the exact covered outputs demonstrated by the exposed
30-record corpus under the pinned corpus and taxonomy identities below.
Covered: `employment_type`, `seniority`, `location.country`, plus skills
recall. Every component in `UNPROVEN_COMPONENTS` receives only
no-crash/no-false-positive/no-confidently-wrong checks and is never
reported as covered. Title is outside the 28-label annotation schema: its
expectations are smoke/regression evidence only, never D2 accuracy, and it
is neither covered nor unproven in this accounting.

Exact-set failures are review triggers, not automatic regression or
improvement classifications: any change to an exact set fails with the
neutral message below, including an added correct value or a removed
abstention. The holdout is already exposed, so updating a literal requires
renewed review of the output change and its evidence.

The corpus and taxonomy identity pins are D2 evidence identities, not D1
parser-version implementation; D1 remains unsatisfied.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from app.normalization.employment import classify_employment_type
from app.normalization.experience import classify_experience
from app.normalization.location import classify_location
from app.normalization.posting import NormalizedPosting, PostingInputs, normalize_posting
from app.normalization.remote import classify_remote_type
from app.normalization.seniority import classify_seniority
from app.normalization.skills import classify_skills
from app.normalization.taxonomy import (
    DEFAULT_SKILLS_TAXONOMY_PATH,
    TaxonomyIndex,
    load_taxonomy,
)
from app.normalization.titles import classify_title
from app.normalization.types import NormalizationResult, Provenance
from scripts.evaluate_phase3_corpus import (
    CorpusRecord,
    SplitEvaluation,
    evaluate_corpus,
    load_corpus,
)

_CORPUS_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "evaluation" / "phase3_realistic_corpus.json"
)

CHANGED = "realistic-output contract changed; review required"

# --- identity pins (D2 evidence identities, not D1) ---

# sha256 of json.dumps(json.loads(corpus), sort_keys=True, ensure_ascii=True,
# separators=(",", ":")) -- independent of checkout line endings.
CORPUS_CANONICAL_JSON_SHA256 = "ca6e129110b71801e18d6bfba84d59376c689f67cb470f1335ab8805cd388f00"
# sha256 of the taxonomy file's UTF-8 bytes after replacing CRLF and lone CR
# with LF.
TAXONOMY_CANONICAL_LF_SHA256 = "926a2a46cb0c603b953d989f449551af2d1a82cb3b50084a4005e78d7730c67c"

# --- accounting ---

OUTCOMES = ("present_supported", "present_unsupported_form", "absent", "ambiguous")
FALSE_POSITIVE_CATEGORIES = {
    "absent": "false_positive_absent",
    "present_unsupported_form": "false_positive_unsupported_form",
    "ambiguous": "false_positive_ambiguous",
}
COMPOSED_COMPONENTS = (
    "remote_type",
    "employment_type",
    "seniority",
    "experience.minimum",
    "experience.maximum",
    "location.city",
    "location.state",
    "location.country",
    "location.postal_code",
)
SALARY_COMPONENTS = ("salary.minimum", "salary.maximum", "salary.currency", "salary.period")
ANNOTATED_COMPONENTS = COMPOSED_COMPONENTS + SALARY_COMPONENTS
COVERED_COMPONENTS = ("employment_type", "seniority", "location.country")
UNPROVEN_COMPONENTS = (
    "remote_type",
    "experience.minimum",
    "experience.maximum",
    "location.city",
    "location.state",
    "location.postal_code",
    "salary.minimum",
    "salary.maximum",
    "salary.currency",
    "salary.period",
)
ALLOWED_PROVENANCE = frozenset({"parsed_description", "derived", "inferred", "unavailable"})
EMITTED_PROVENANCE = frozenset({"inferred", "parsed_description", "unavailable"})
SKILLS_EMITTED_PROVENANCE = frozenset({"parsed_description"})

EXPECTED_TOTALS: dict[str, Any] = {
    "records": 30,
    "runtime_failures": 0,
    "confidently_wrong": 0,
    "false_positives": 0,
    "skills_false_positives": 0,
    "skills_recall": (37, 40),
    "skills_known_misses": 3,
    "supported_abstentions": 56,
    "missing_input_gap": 100,
    "correct_values": 33,
    "provenance_exceptions": 3,
    "evaluator_mismatches": 159,
}
TITLE_SMOKE_COUNTS = {"matched": 22, "unsupported": 6, "ambiguous": 2, "no_title": 0}

# Mutation-experiment M8's input predicate (ADR 0012 timing evidence only,
# never production special-casing).
M8_TITLE = "Strategic Finance"
M8_LOCATION = "San Francisco Bay Area"
M8_RECORD_ID = "discord:8575166002"

# --- literal expectations (derived at base 0c2c14b) ---

RECORD_IDS: frozenset[str] = frozenset(
    {
        "anthropic:4017331008",
        "anthropic:4020350008",
        "anthropic:4423394008",
        "anthropic:4461444008",
        "anthropic:4461450008",
        "anthropic:4502508008",
        "anthropic:4572744008",
        "anthropic:4593216008",
        "anthropic:4595463008",
        "anthropic:4610158008",
        "discord:8214127002",
        "discord:8369347002",
        "discord:8460791002",
        "discord:8464570002",
        "discord:8498984002",
        "discord:8537955002",
        "discord:8545675002",
        "discord:8571766002",
        "discord:8575166002",
        "discord:8581126002",
        "gitlab:8396674002",
        "gitlab:8451512002",
        "gitlab:8463922002",
        "gitlab:8476375002",
        "gitlab:8478405002",
        "gitlab:8490477002",
        "gitlab:8500014002",
        "gitlab:8512220002",
        "gitlab:8512432002",
        "gitlab:8514960002",
    }
)

ANNOTATION_PARTITIONS: dict[str, dict[str, frozenset[str]]] = {
    "remote_type": {
        "present_supported": frozenset(
            {
                "anthropic:4017331008",
                "anthropic:4020350008",
                "anthropic:4423394008",
                "anthropic:4461444008",
                "anthropic:4461450008",
                "anthropic:4502508008",
                "anthropic:4572744008",
                "anthropic:4593216008",
                "anthropic:4595463008",
                "anthropic:4610158008",
                "discord:8460791002",
                "discord:8498984002",
                "discord:8537955002",
                "gitlab:8396674002",
                "gitlab:8451512002",
                "gitlab:8463922002",
                "gitlab:8476375002",
                "gitlab:8478405002",
                "gitlab:8490477002",
                "gitlab:8500014002",
                "gitlab:8512220002",
                "gitlab:8512432002",
                "gitlab:8514960002",
            }
        ),
        "present_unsupported_form": frozenset(),
        "absent": frozenset(
            {
                "discord:8369347002",
                "discord:8464570002",
                "discord:8571766002",
                "discord:8575166002",
                "discord:8581126002",
            }
        ),
        "ambiguous": frozenset(
            {
                "discord:8214127002",
                "discord:8545675002",
            }
        ),
    },
    "employment_type": {
        "present_supported": frozenset(
            {
                "discord:8214127002",
                "discord:8369347002",
                "discord:8460791002",
                "discord:8464570002",
                "discord:8498984002",
                "discord:8537955002",
                "discord:8545675002",
                "discord:8571766002",
                "discord:8575166002",
                "discord:8581126002",
            }
        ),
        "present_unsupported_form": frozenset(),
        "absent": frozenset(
            {
                "anthropic:4017331008",
                "anthropic:4020350008",
                "anthropic:4423394008",
                "anthropic:4461444008",
                "anthropic:4461450008",
                "anthropic:4502508008",
                "anthropic:4572744008",
                "anthropic:4593216008",
                "anthropic:4595463008",
                "anthropic:4610158008",
                "gitlab:8396674002",
                "gitlab:8451512002",
                "gitlab:8463922002",
                "gitlab:8476375002",
                "gitlab:8478405002",
                "gitlab:8490477002",
                "gitlab:8500014002",
                "gitlab:8512220002",
                "gitlab:8512432002",
                "gitlab:8514960002",
            }
        ),
        "ambiguous": frozenset(),
    },
    "seniority": {
        "present_supported": frozenset(
            {
                "anthropic:4572744008",
                "anthropic:4593216008",
                "discord:8214127002",
                "discord:8369347002",
                "discord:8460791002",
                "discord:8464570002",
                "discord:8498984002",
                "discord:8545675002",
                "discord:8571766002",
                "discord:8581126002",
                "gitlab:8451512002",
                "gitlab:8463922002",
                "gitlab:8476375002",
                "gitlab:8490477002",
                "gitlab:8500014002",
                "gitlab:8512220002",
                "gitlab:8512432002",
                "gitlab:8514960002",
            }
        ),
        "present_unsupported_form": frozenset(
            {
                "discord:8537955002",
                "gitlab:8396674002",
                "gitlab:8478405002",
            }
        ),
        "absent": frozenset(
            {
                "anthropic:4017331008",
                "anthropic:4020350008",
                "anthropic:4423394008",
                "anthropic:4461444008",
                "anthropic:4461450008",
                "anthropic:4595463008",
                "anthropic:4610158008",
                "discord:8575166002",
            }
        ),
        "ambiguous": frozenset(
            {
                "anthropic:4502508008",
            }
        ),
    },
    "experience.minimum": {
        "present_supported": frozenset(
            {
                "anthropic:4423394008",
                "anthropic:4461444008",
                "anthropic:4461450008",
                "anthropic:4502508008",
                "anthropic:4593216008",
                "anthropic:4595463008",
                "discord:8369347002",
                "discord:8460791002",
                "discord:8464570002",
                "discord:8498984002",
                "discord:8545675002",
                "discord:8575166002",
                "discord:8581126002",
                "gitlab:8478405002",
            }
        ),
        "present_unsupported_form": frozenset(),
        "absent": frozenset(
            {
                "anthropic:4017331008",
                "anthropic:4020350008",
                "anthropic:4572744008",
                "anthropic:4610158008",
                "discord:8214127002",
                "gitlab:8396674002",
                "gitlab:8451512002",
                "gitlab:8463922002",
                "gitlab:8476375002",
                "gitlab:8490477002",
                "gitlab:8500014002",
                "gitlab:8512220002",
                "gitlab:8512432002",
                "gitlab:8514960002",
            }
        ),
        "ambiguous": frozenset(
            {
                "discord:8537955002",
                "discord:8571766002",
            }
        ),
    },
    "experience.maximum": {
        "present_supported": frozenset(),
        "present_unsupported_form": frozenset(),
        "absent": frozenset(
            {
                "anthropic:4017331008",
                "anthropic:4020350008",
                "anthropic:4423394008",
                "anthropic:4461444008",
                "anthropic:4461450008",
                "anthropic:4502508008",
                "anthropic:4572744008",
                "anthropic:4593216008",
                "anthropic:4595463008",
                "anthropic:4610158008",
                "discord:8214127002",
                "discord:8369347002",
                "discord:8460791002",
                "discord:8464570002",
                "discord:8498984002",
                "discord:8537955002",
                "discord:8545675002",
                "discord:8571766002",
                "discord:8575166002",
                "discord:8581126002",
                "gitlab:8396674002",
                "gitlab:8451512002",
                "gitlab:8463922002",
                "gitlab:8476375002",
                "gitlab:8478405002",
                "gitlab:8490477002",
                "gitlab:8500014002",
                "gitlab:8512220002",
                "gitlab:8512432002",
                "gitlab:8514960002",
            }
        ),
        "ambiguous": frozenset(),
    },
    "location.city": {
        "present_supported": frozenset(
            {
                "anthropic:4593216008",
                "anthropic:4610158008",
                "discord:8498984002",
                "gitlab:8396674002",
                "gitlab:8463922002",
                "gitlab:8478405002",
            }
        ),
        "present_unsupported_form": frozenset(),
        "absent": frozenset(
            {
                "discord:8214127002",
                "discord:8369347002",
                "discord:8460791002",
                "discord:8464570002",
                "discord:8537955002",
                "discord:8545675002",
                "discord:8571766002",
                "discord:8575166002",
                "discord:8581126002",
                "gitlab:8451512002",
                "gitlab:8476375002",
                "gitlab:8490477002",
                "gitlab:8500014002",
                "gitlab:8512220002",
                "gitlab:8512432002",
                "gitlab:8514960002",
            }
        ),
        "ambiguous": frozenset(
            {
                "anthropic:4017331008",
                "anthropic:4020350008",
                "anthropic:4423394008",
                "anthropic:4461444008",
                "anthropic:4461450008",
                "anthropic:4502508008",
                "anthropic:4572744008",
                "anthropic:4595463008",
            }
        ),
    },
    "location.state": {
        "present_supported": frozenset(
            {
                "anthropic:4593216008",
                "discord:8498984002",
                "gitlab:8396674002",
            }
        ),
        "present_unsupported_form": frozenset(),
        "absent": frozenset(
            {
                "anthropic:4610158008",
                "discord:8214127002",
                "discord:8369347002",
                "discord:8460791002",
                "discord:8464570002",
                "discord:8537955002",
                "discord:8545675002",
                "discord:8571766002",
                "discord:8575166002",
                "discord:8581126002",
                "gitlab:8451512002",
                "gitlab:8463922002",
                "gitlab:8476375002",
                "gitlab:8478405002",
                "gitlab:8490477002",
                "gitlab:8500014002",
                "gitlab:8512220002",
                "gitlab:8512432002",
                "gitlab:8514960002",
            }
        ),
        "ambiguous": frozenset(
            {
                "anthropic:4017331008",
                "anthropic:4020350008",
                "anthropic:4423394008",
                "anthropic:4461444008",
                "anthropic:4461450008",
                "anthropic:4502508008",
                "anthropic:4572744008",
                "anthropic:4595463008",
            }
        ),
    },
    "location.country": {
        "present_supported": frozenset(
            {
                "anthropic:4610158008",
                "discord:8214127002",
                "discord:8369347002",
                "discord:8460791002",
                "discord:8464570002",
                "discord:8498984002",
                "discord:8537955002",
                "discord:8545675002",
                "discord:8571766002",
                "discord:8575166002",
                "discord:8581126002",
                "gitlab:8396674002",
                "gitlab:8463922002",
                "gitlab:8478405002",
                "gitlab:8512432002",
            }
        ),
        "present_unsupported_form": frozenset(),
        "absent": frozenset(
            {
                "anthropic:4017331008",
                "anthropic:4020350008",
                "anthropic:4423394008",
                "anthropic:4461444008",
                "anthropic:4461450008",
                "anthropic:4502508008",
                "anthropic:4572744008",
                "anthropic:4593216008",
                "anthropic:4595463008",
            }
        ),
        "ambiguous": frozenset(
            {
                "gitlab:8451512002",
                "gitlab:8476375002",
                "gitlab:8490477002",
                "gitlab:8500014002",
                "gitlab:8512220002",
                "gitlab:8514960002",
            }
        ),
    },
    "location.postal_code": {
        "present_supported": frozenset(),
        "present_unsupported_form": frozenset(),
        "absent": frozenset(
            {
                "anthropic:4017331008",
                "anthropic:4020350008",
                "anthropic:4423394008",
                "anthropic:4461444008",
                "anthropic:4461450008",
                "anthropic:4502508008",
                "anthropic:4572744008",
                "anthropic:4593216008",
                "anthropic:4595463008",
                "anthropic:4610158008",
                "discord:8214127002",
                "discord:8369347002",
                "discord:8460791002",
                "discord:8464570002",
                "discord:8498984002",
                "discord:8537955002",
                "discord:8545675002",
                "discord:8571766002",
                "discord:8575166002",
                "discord:8581126002",
                "gitlab:8396674002",
                "gitlab:8451512002",
                "gitlab:8463922002",
                "gitlab:8476375002",
                "gitlab:8478405002",
                "gitlab:8490477002",
                "gitlab:8500014002",
                "gitlab:8512220002",
                "gitlab:8512432002",
                "gitlab:8514960002",
            }
        ),
        "ambiguous": frozenset(),
    },
    "salary.minimum": {
        "present_supported": frozenset(
            {
                "anthropic:4017331008",
                "anthropic:4020350008",
                "anthropic:4423394008",
                "anthropic:4461444008",
                "anthropic:4461450008",
                "anthropic:4502508008",
                "anthropic:4572744008",
                "anthropic:4593216008",
                "anthropic:4595463008",
                "anthropic:4610158008",
                "discord:8214127002",
                "discord:8369347002",
                "discord:8460791002",
                "discord:8464570002",
                "discord:8498984002",
                "discord:8537955002",
                "discord:8545675002",
                "discord:8571766002",
                "discord:8575166002",
                "discord:8581126002",
                "gitlab:8396674002",
                "gitlab:8451512002",
                "gitlab:8490477002",
                "gitlab:8512220002",
                "gitlab:8512432002",
            }
        ),
        "present_unsupported_form": frozenset(),
        "absent": frozenset(
            {
                "gitlab:8463922002",
                "gitlab:8476375002",
                "gitlab:8478405002",
                "gitlab:8500014002",
                "gitlab:8514960002",
            }
        ),
        "ambiguous": frozenset(),
    },
    "salary.maximum": {
        "present_supported": frozenset(
            {
                "anthropic:4017331008",
                "anthropic:4020350008",
                "anthropic:4423394008",
                "anthropic:4461444008",
                "anthropic:4461450008",
                "anthropic:4502508008",
                "anthropic:4572744008",
                "anthropic:4593216008",
                "anthropic:4595463008",
                "anthropic:4610158008",
                "discord:8214127002",
                "discord:8369347002",
                "discord:8460791002",
                "discord:8464570002",
                "discord:8498984002",
                "discord:8537955002",
                "discord:8545675002",
                "discord:8571766002",
                "discord:8575166002",
                "discord:8581126002",
                "gitlab:8396674002",
                "gitlab:8451512002",
                "gitlab:8490477002",
                "gitlab:8512220002",
                "gitlab:8512432002",
            }
        ),
        "present_unsupported_form": frozenset(),
        "absent": frozenset(
            {
                "gitlab:8463922002",
                "gitlab:8476375002",
                "gitlab:8478405002",
                "gitlab:8500014002",
                "gitlab:8514960002",
            }
        ),
        "ambiguous": frozenset(),
    },
    "salary.currency": {
        "present_supported": frozenset(
            {
                "anthropic:4017331008",
                "anthropic:4020350008",
                "anthropic:4423394008",
                "anthropic:4461444008",
                "anthropic:4461450008",
                "anthropic:4502508008",
                "anthropic:4572744008",
                "anthropic:4593216008",
                "anthropic:4595463008",
                "anthropic:4610158008",
                "discord:8214127002",
                "discord:8369347002",
                "discord:8460791002",
                "discord:8464570002",
                "discord:8498984002",
                "discord:8537955002",
                "discord:8545675002",
                "discord:8571766002",
                "discord:8575166002",
                "discord:8581126002",
                "gitlab:8396674002",
                "gitlab:8451512002",
                "gitlab:8490477002",
                "gitlab:8512220002",
                "gitlab:8512432002",
            }
        ),
        "present_unsupported_form": frozenset(),
        "absent": frozenset(
            {
                "gitlab:8463922002",
                "gitlab:8476375002",
                "gitlab:8478405002",
                "gitlab:8500014002",
                "gitlab:8514960002",
            }
        ),
        "ambiguous": frozenset(),
    },
    "salary.period": {
        "present_supported": frozenset(
            {
                "anthropic:4017331008",
                "anthropic:4020350008",
                "anthropic:4423394008",
                "anthropic:4461444008",
                "anthropic:4461450008",
                "anthropic:4502508008",
                "anthropic:4572744008",
                "anthropic:4593216008",
                "anthropic:4595463008",
                "anthropic:4610158008",
                "discord:8214127002",
                "discord:8369347002",
                "discord:8460791002",
                "discord:8464570002",
                "discord:8498984002",
                "discord:8537955002",
                "discord:8545675002",
                "discord:8571766002",
                "discord:8575166002",
                "discord:8581126002",
                "gitlab:8396674002",
                "gitlab:8451512002",
                "gitlab:8490477002",
                "gitlab:8512220002",
                "gitlab:8512432002",
            }
        ),
        "present_unsupported_form": frozenset(),
        "absent": frozenset(
            {
                "gitlab:8463922002",
                "gitlab:8476375002",
                "gitlab:8478405002",
                "gitlab:8500014002",
                "gitlab:8514960002",
            }
        ),
        "ambiguous": frozenset(),
    },
}

CORRECT: dict[str, dict[str, object]] = {
    "remote_type": {},
    "employment_type": {
        "discord:8214127002": "full_time",
        "discord:8369347002": "full_time",
        "discord:8460791002": "full_time",
        "discord:8464570002": "full_time",
        "discord:8498984002": "full_time",
        "discord:8537955002": "full_time",
        "discord:8545675002": "full_time",
        "discord:8571766002": "full_time",
        "discord:8575166002": "full_time",
        "discord:8581126002": "full_time",
    },
    "seniority": {
        "anthropic:4572744008": "staff",
        "anthropic:4593216008": "staff",
        "discord:8214127002": "staff",
        "discord:8369347002": "senior",
        "discord:8460791002": "senior",
        "discord:8464570002": "staff",
        "discord:8498984002": "staff",
        "discord:8545675002": "senior",
        "discord:8571766002": "director",
        "discord:8581126002": "senior",
        "gitlab:8451512002": "senior",
        "gitlab:8463922002": "staff",
        "gitlab:8476375002": "senior",
        "gitlab:8490477002": "staff",
        "gitlab:8500014002": "senior",
        "gitlab:8512220002": "senior",
        "gitlab:8512432002": "staff",
        "gitlab:8514960002": "staff",
    },
    "experience.minimum": {},
    "experience.maximum": {},
    "location.city": {},
    "location.state": {},
    "location.country": {
        "anthropic:4610158008": "United Kingdom",
        "gitlab:8396674002": "United States",
        "gitlab:8463922002": "India",
        "gitlab:8478405002": "India",
        "gitlab:8512432002": "United States",
    },
    "location.postal_code": {},
}

SUPPORTED_ABSTENTION: dict[str, frozenset[str]] = {
    "remote_type": frozenset(
        {
            "anthropic:4017331008",
            "anthropic:4020350008",
            "anthropic:4423394008",
            "anthropic:4461444008",
            "anthropic:4461450008",
            "anthropic:4502508008",
            "anthropic:4572744008",
            "anthropic:4593216008",
            "anthropic:4595463008",
            "anthropic:4610158008",
            "discord:8460791002",
            "discord:8498984002",
            "discord:8537955002",
            "gitlab:8396674002",
            "gitlab:8451512002",
            "gitlab:8463922002",
            "gitlab:8476375002",
            "gitlab:8478405002",
            "gitlab:8490477002",
            "gitlab:8500014002",
            "gitlab:8512220002",
            "gitlab:8512432002",
            "gitlab:8514960002",
        }
    ),
    "employment_type": frozenset(),
    "seniority": frozenset(),
    "experience.minimum": frozenset(
        {
            "anthropic:4423394008",
            "anthropic:4461444008",
            "anthropic:4461450008",
            "anthropic:4502508008",
            "anthropic:4593216008",
            "anthropic:4595463008",
            "discord:8369347002",
            "discord:8460791002",
            "discord:8464570002",
            "discord:8498984002",
            "discord:8545675002",
            "discord:8575166002",
            "discord:8581126002",
            "gitlab:8478405002",
        }
    ),
    "experience.maximum": frozenset(),
    "location.city": frozenset(
        {
            "anthropic:4593216008",
            "anthropic:4610158008",
            "discord:8498984002",
            "gitlab:8396674002",
            "gitlab:8463922002",
            "gitlab:8478405002",
        }
    ),
    "location.state": frozenset(
        {
            "anthropic:4593216008",
            "discord:8498984002",
            "gitlab:8396674002",
        }
    ),
    "location.country": frozenset(
        {
            "discord:8214127002",
            "discord:8369347002",
            "discord:8460791002",
            "discord:8464570002",
            "discord:8498984002",
            "discord:8537955002",
            "discord:8545675002",
            "discord:8571766002",
            "discord:8575166002",
            "discord:8581126002",
        }
    ),
    "location.postal_code": frozenset(),
}

CONFIDENTLY_WRONG: dict[str, dict[str, object]] = {
    "remote_type": {},
    "employment_type": {},
    "seniority": {},
    "experience.minimum": {},
    "experience.maximum": {},
    "location.city": {},
    "location.state": {},
    "location.country": {},
    "location.postal_code": {},
}

FALSE_POSITIVE_UNSUPPORTED_FORM: dict[str, dict[str, object]] = {
    "remote_type": {},
    "employment_type": {},
    "seniority": {},
    "experience.minimum": {},
    "experience.maximum": {},
    "location.city": {},
    "location.state": {},
    "location.country": {},
    "location.postal_code": {},
}

FALSE_POSITIVE_ABSENT: dict[str, dict[str, object]] = {
    "remote_type": {},
    "employment_type": {},
    "seniority": {},
    "experience.minimum": {},
    "experience.maximum": {},
    "location.city": {},
    "location.state": {},
    "location.country": {},
    "location.postal_code": {},
}

FALSE_POSITIVE_AMBIGUOUS: dict[str, dict[str, object]] = {
    "remote_type": {},
    "employment_type": {},
    "seniority": {},
    "experience.minimum": {},
    "experience.maximum": {},
    "location.city": {},
    "location.state": {},
    "location.country": {},
    "location.postal_code": {},
}

LOCATION_MISSING_INPUT_GAP: dict[str, frozenset[str]] = {
    "location.city": frozenset(),
    "location.state": frozenset(),
    "location.country": frozenset(),
    "location.postal_code": frozenset(),
}

SALARY_MISSING_INPUT_GAP: dict[str, frozenset[str]] = {
    "salary.minimum": frozenset(
        {
            "anthropic:4017331008",
            "anthropic:4020350008",
            "anthropic:4423394008",
            "anthropic:4461444008",
            "anthropic:4461450008",
            "anthropic:4502508008",
            "anthropic:4572744008",
            "anthropic:4593216008",
            "anthropic:4595463008",
            "anthropic:4610158008",
            "discord:8214127002",
            "discord:8369347002",
            "discord:8460791002",
            "discord:8464570002",
            "discord:8498984002",
            "discord:8537955002",
            "discord:8545675002",
            "discord:8571766002",
            "discord:8575166002",
            "discord:8581126002",
            "gitlab:8396674002",
            "gitlab:8451512002",
            "gitlab:8490477002",
            "gitlab:8512220002",
            "gitlab:8512432002",
        }
    ),
    "salary.maximum": frozenset(
        {
            "anthropic:4017331008",
            "anthropic:4020350008",
            "anthropic:4423394008",
            "anthropic:4461444008",
            "anthropic:4461450008",
            "anthropic:4502508008",
            "anthropic:4572744008",
            "anthropic:4593216008",
            "anthropic:4595463008",
            "anthropic:4610158008",
            "discord:8214127002",
            "discord:8369347002",
            "discord:8460791002",
            "discord:8464570002",
            "discord:8498984002",
            "discord:8537955002",
            "discord:8545675002",
            "discord:8571766002",
            "discord:8575166002",
            "discord:8581126002",
            "gitlab:8396674002",
            "gitlab:8451512002",
            "gitlab:8490477002",
            "gitlab:8512220002",
            "gitlab:8512432002",
        }
    ),
    "salary.currency": frozenset(
        {
            "anthropic:4017331008",
            "anthropic:4020350008",
            "anthropic:4423394008",
            "anthropic:4461444008",
            "anthropic:4461450008",
            "anthropic:4502508008",
            "anthropic:4572744008",
            "anthropic:4593216008",
            "anthropic:4595463008",
            "anthropic:4610158008",
            "discord:8214127002",
            "discord:8369347002",
            "discord:8460791002",
            "discord:8464570002",
            "discord:8498984002",
            "discord:8537955002",
            "discord:8545675002",
            "discord:8571766002",
            "discord:8575166002",
            "discord:8581126002",
            "gitlab:8396674002",
            "gitlab:8451512002",
            "gitlab:8490477002",
            "gitlab:8512220002",
            "gitlab:8512432002",
        }
    ),
    "salary.period": frozenset(
        {
            "anthropic:4017331008",
            "anthropic:4020350008",
            "anthropic:4423394008",
            "anthropic:4461444008",
            "anthropic:4461450008",
            "anthropic:4502508008",
            "anthropic:4572744008",
            "anthropic:4593216008",
            "anthropic:4595463008",
            "anthropic:4610158008",
            "discord:8214127002",
            "discord:8369347002",
            "discord:8460791002",
            "discord:8464570002",
            "discord:8498984002",
            "discord:8537955002",
            "discord:8545675002",
            "discord:8571766002",
            "discord:8575166002",
            "discord:8581126002",
            "gitlab:8396674002",
            "gitlab:8451512002",
            "gitlab:8490477002",
            "gitlab:8512220002",
            "gitlab:8512432002",
        }
    ),
}

SKILL_IDS: frozenset[str] = frozenset(
    {
        "c",
        "cpp",
        "csharp",
        "docker",
        "golang",
        "java",
        "javascript",
        "kubernetes",
        "mongodb",
        "mysql",
        "node.js",
        "postgresql",
        "python",
        "rlang",
        "typescript",
    }
)

SKILLS_PRESENT_SUPPORTED: frozenset[tuple[str, str]] = frozenset(
    {
        ("anthropic:4017331008", "python"),
        ("anthropic:4461444008", "python"),
        ("anthropic:4502508008", "golang"),
        ("anthropic:4502508008", "python"),
        ("anthropic:4502508008", "typescript"),
        ("anthropic:4593216008", "docker"),
        ("anthropic:4593216008", "kubernetes"),
        ("anthropic:4595463008", "python"),
        ("anthropic:4610158008", "kubernetes"),
        ("anthropic:4610158008", "python"),
        ("discord:8214127002", "javascript"),
        ("discord:8214127002", "python"),
        ("discord:8214127002", "typescript"),
        ("discord:8369347002", "python"),
        ("discord:8460791002", "python"),
        ("discord:8460791002", "typescript"),
        ("discord:8464570002", "python"),
        ("discord:8464570002", "typescript"),
        ("discord:8537955002", "kubernetes"),
        ("discord:8537955002", "python"),
        ("discord:8545675002", "python"),
        ("discord:8545675002", "typescript"),
        ("gitlab:8451512002", "golang"),
        ("gitlab:8451512002", "javascript"),
        ("gitlab:8451512002", "kubernetes"),
        ("gitlab:8451512002", "python"),
        ("gitlab:8463922002", "golang"),
        ("gitlab:8463922002", "kubernetes"),
        ("gitlab:8463922002", "postgresql"),
        ("gitlab:8490477002", "golang"),
        ("gitlab:8490477002", "kubernetes"),
        ("gitlab:8512432002", "docker"),
        ("gitlab:8512432002", "golang"),
        ("gitlab:8512432002", "kubernetes"),
        ("gitlab:8512432002", "postgresql"),
        ("gitlab:8512432002", "python"),
        ("gitlab:8512432002", "typescript"),
        ("gitlab:8514960002", "golang"),
        ("gitlab:8514960002", "kubernetes"),
        ("gitlab:8514960002", "python"),
    }
)

SKILLS_RECALL_HITS: frozenset[tuple[str, str]] = frozenset(
    {
        ("anthropic:4017331008", "python"),
        ("anthropic:4461444008", "python"),
        ("anthropic:4502508008", "golang"),
        ("anthropic:4502508008", "python"),
        ("anthropic:4502508008", "typescript"),
        ("anthropic:4593216008", "docker"),
        ("anthropic:4593216008", "kubernetes"),
        ("anthropic:4595463008", "python"),
        ("anthropic:4610158008", "kubernetes"),
        ("anthropic:4610158008", "python"),
        ("discord:8214127002", "javascript"),
        ("discord:8214127002", "python"),
        ("discord:8214127002", "typescript"),
        ("discord:8369347002", "python"),
        ("discord:8460791002", "python"),
        ("discord:8460791002", "typescript"),
        ("discord:8464570002", "python"),
        ("discord:8464570002", "typescript"),
        ("discord:8537955002", "kubernetes"),
        ("discord:8537955002", "python"),
        ("discord:8545675002", "python"),
        ("discord:8545675002", "typescript"),
        ("gitlab:8451512002", "golang"),
        ("gitlab:8451512002", "javascript"),
        ("gitlab:8451512002", "kubernetes"),
        ("gitlab:8451512002", "python"),
        ("gitlab:8463922002", "kubernetes"),
        ("gitlab:8463922002", "postgresql"),
        ("gitlab:8490477002", "kubernetes"),
        ("gitlab:8512432002", "docker"),
        ("gitlab:8512432002", "golang"),
        ("gitlab:8512432002", "kubernetes"),
        ("gitlab:8512432002", "postgresql"),
        ("gitlab:8512432002", "python"),
        ("gitlab:8512432002", "typescript"),
        ("gitlab:8514960002", "kubernetes"),
        ("gitlab:8514960002", "python"),
    }
)

SKILLS_KNOWN_MISSES: frozenset[tuple[str, str]] = frozenset(
    {
        ("gitlab:8463922002", "golang"),
        ("gitlab:8490477002", "golang"),
        ("gitlab:8514960002", "golang"),
    }
)

SKILLS_FALSE_POSITIVE_UNSUPPORTED_FORM: frozenset[tuple[str, str]] = frozenset()

SKILLS_FALSE_POSITIVE_ABSENT: frozenset[tuple[str, str]] = frozenset()

SKILLS_FALSE_POSITIVE_AMBIGUOUS: frozenset[tuple[str, str]] = frozenset()

TITLE_SMOKE: dict[str, tuple[str, str | None, str | None]] = {
    "anthropic:4017331008": ("matched", "research-engineer", "research"),
    "anthropic:4020350008": ("unsupported", None, None),
    "anthropic:4423394008": ("matched", "account-executive", "sales"),
    "anthropic:4461444008": ("unsupported", None, None),
    "anthropic:4461450008": ("matched", "account-executive", "sales"),
    "anthropic:4502508008": ("matched", "security-engineer", "security_engineering"),
    "anthropic:4572744008": ("matched", "software-engineer", "software_engineering"),
    "anthropic:4593216008": ("matched", "research-engineer", "research"),
    "anthropic:4595463008": ("ambiguous", None, None),
    "anthropic:4610158008": ("ambiguous", None, None),
    "discord:8214127002": ("matched", "software-engineer", "software_engineering"),
    "discord:8369347002": ("matched", "software-engineer", "software_engineering"),
    "discord:8460791002": ("matched", "software-engineer", "software_engineering"),
    "discord:8464570002": ("matched", "software-engineer", "software_engineering"),
    "discord:8498984002": ("matched", "software-engineer", "software_engineering"),
    "discord:8537955002": ("matched", "engineering-manager", "engineering_management"),
    "discord:8545675002": ("matched", "software-engineer", "software_engineering"),
    "discord:8571766002": ("matched", "engineering-director", "engineering_management"),
    "discord:8575166002": ("unsupported", None, None),
    "discord:8581126002": ("matched", "product-manager", "product_management"),
    "gitlab:8396674002": ("unsupported", None, None),
    "gitlab:8451512002": ("matched", "software-engineer", "software_engineering"),
    "gitlab:8463922002": ("matched", "software-engineer", "software_engineering"),
    "gitlab:8476375002": ("matched", "solutions-architect", "solutions_architecture"),
    "gitlab:8478405002": ("matched", "engineering-manager", "engineering_management"),
    "gitlab:8490477002": ("matched", "software-engineer", "software_engineering"),
    "gitlab:8500014002": ("unsupported", None, None),
    "gitlab:8512220002": ("matched", "product-manager", "product_management"),
    "gitlab:8512432002": ("unsupported", None, None),
    "gitlab:8514960002": ("matched", "security-engineer", "security_engineering"),
}

PROVENANCE_EXCEPTIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("anthropic:4610158008", "location.country"): ("inferred", "parsed_description"),
    ("gitlab:8396674002", "location.country"): ("inferred", "parsed_description"),
    ("gitlab:8512432002", "location.country"): ("inferred", "parsed_description"),
}


# --- independent minimal scorer ---


def _meaningful(value: str | None) -> bool:
    return value is not None and any(
        not char.isspace() and unicodedata.category(char) != "Cf" for char in value
    )


def _annotation(record: CorpusRecord, component: str) -> dict[str, Any]:
    annotations = record.annotations
    if "." in component:
        parser, part = component.split(".")
        return dict(annotations[parser][part])
    return dict(annotations[component])


def _component_result(posting: NormalizedPosting, component: str) -> NormalizationResult[Any]:
    if "." in component:
        parser, part = component.split(".")
        result: NormalizationResult[Any] = getattr(getattr(posting, parser), part)
        return result
    scalar: NormalizationResult[Any] = getattr(posting, component)
    return scalar


def _input_present(record: CorpusRecord, component: str) -> bool:
    if component.startswith("location."):
        return _meaningful(record.fields["location_raw"])
    return True


def _categorize(outcome: str, expected: Any, actual: Any, *, input_present: bool) -> str:
    if outcome == "present_supported":
        if not input_present:
            return "missing_input_gap"
        if actual is None:
            return "supported_abstention"
        if actual != expected:
            return "confidently_wrong"
        return "correct"
    if actual is None:
        return "true_negative"
    return FALSE_POSITIVE_CATEGORIES[outcome]


@pytest.fixture(scope="module")
def taxonomy() -> TaxonomyIndex:
    return load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)


@pytest.fixture(scope="module")
def records(taxonomy: TaxonomyIndex) -> dict[str, CorpusRecord]:
    loaded = load_corpus(_CORPUS_PATH, known_canonical_ids=taxonomy.canonical_ids())
    return {record.id: record for record in loaded}


@pytest.fixture(scope="module")
def composed(
    records: dict[str, CorpusRecord], taxonomy: TaxonomyIndex
) -> dict[str, NormalizedPosting]:
    """One `normalize_posting` call per record. A raised parser exception
    would fail every dependent test: zero runtime failures is a precondition
    of the whole module."""
    return {
        record_id: normalize_posting(
            PostingInputs(
                title=record.fields["title"],
                description=record.fields["description"],
                location=record.fields["location_raw"],
            ),
            taxonomy=taxonomy,
        )
        for record_id, record in records.items()
    }


@pytest.fixture(scope="module")
def scored(
    records: dict[str, CorpusRecord], composed: dict[str, NormalizedPosting]
) -> dict[str, dict[str, dict[str, Any]]]:
    """component -> category -> {record_id: actual value}."""
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for component in COMPOSED_COMPONENTS:
        by_category: dict[str, dict[str, Any]] = {}
        for record_id, record in records.items():
            annotation = _annotation(record, component)
            actual = _component_result(composed[record_id], component).value
            category = _categorize(
                annotation["outcome"],
                annotation["expected_value"],
                actual,
                input_present=_input_present(record, component),
            )
            by_category.setdefault(category, {})[record_id] = actual
        result[component] = by_category
    return result


@pytest.fixture(scope="module")
def skills_scored(
    records: dict[str, CorpusRecord], composed: dict[str, NormalizedPosting]
) -> dict[str, set[tuple[str, str]]]:
    result: dict[str, set[tuple[str, str]]] = {
        "hit": set(),
        "miss": set(),
        **{category: set() for category in FALSE_POSITIVE_CATEGORIES.values()},
    }
    for record_id, record in records.items():
        returned = {match.canonical_id for match in composed[record_id].skills}
        # Self-review finding P3-5: a returned id outside the frozen annotations
        # would otherwise be ignored by this scorer.
        assert returned <= SKILL_IDS, CHANGED
        for skill_id, annotation in record.annotations["skills"].items():
            outcome = annotation["outcome"]
            pair = (record_id, skill_id)
            if outcome == "present_supported":
                result["hit" if skill_id in returned else "miss"].add(pair)
            elif skill_id in returned:
                result[FALSE_POSITIVE_CATEGORIES[outcome]].add(pair)
    return result


@pytest.fixture(scope="module")
def evaluator_combined(
    records: dict[str, CorpusRecord], taxonomy: TaxonomyIndex
) -> SplitEvaluation:
    return evaluate_corpus(list(records.values()), taxonomy=taxonomy)["combined"]


# --- identity ---


def test_corpus_canonical_json_identity() -> None:
    data = json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode("ascii")).hexdigest() == CORPUS_CANONICAL_JSON_SHA256


def test_taxonomy_canonical_lf_identity() -> None:
    text = Path(DEFAULT_SKILLS_TAXONOMY_PATH).read_bytes().decode("utf-8")
    canonical = text.replace("\r\n", "\n").replace("\r", "\n")
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert digest == TAXONOMY_CANONICAL_LF_SHA256


# --- exhaustiveness ---


def test_record_id_universe_is_exact_with_no_duplicates() -> None:
    raw_ids = [record["id"] for record in json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))]
    assert len(raw_ids) == len(set(raw_ids)) == len(RECORD_IDS) == EXPECTED_TOTALS["records"]
    assert set(raw_ids) == RECORD_IDS


def test_loaded_records_match_the_universe(records: dict[str, CorpusRecord]) -> None:
    assert set(records) == RECORD_IDS


@pytest.mark.parametrize("component", ANNOTATED_COMPONENTS)
def test_annotation_outcomes_partition_the_records(
    component: str, records: dict[str, CorpusRecord]
) -> None:
    expected = ANNOTATION_PARTITIONS[component]
    assert set(expected) == set(OUTCOMES)
    assert sum(len(ids) for ids in expected.values()) == len(RECORD_IDS)
    assert frozenset().union(*expected.values()) == RECORD_IDS
    actual: dict[str, set[str]] = {outcome: set() for outcome in OUTCOMES}
    for record_id, record in records.items():
        actual[_annotation(record, component)["outcome"]].add(record_id)
    assert actual == {outcome: set(ids) for outcome, ids in expected.items()}, CHANGED


def test_annotation_partitions_cover_exactly_the_annotated_components() -> None:
    assert set(ANNOTATION_PARTITIONS) == set(ANNOTATED_COMPONENTS)


@pytest.mark.parametrize("component", COMPOSED_COMPONENTS)
def test_present_supported_records_partition_into_result_categories(component: str) -> None:
    present = ANNOTATION_PARTITIONS[component]["present_supported"]
    parts = [
        set(CORRECT[component]),
        set(SUPPORTED_ABSTENTION[component]),
        set(CONFIDENTLY_WRONG[component]),
        set(LOCATION_MISSING_INPUT_GAP.get(component, frozenset())),
    ]
    assert sum(len(part) for part in parts) == len(present)
    assert set().union(*parts) == present


@pytest.mark.parametrize("component", SALARY_COMPONENTS)
def test_salary_present_supported_records_are_exactly_the_missing_input_gap(
    component: str, records: dict[str, CorpusRecord]
) -> None:
    present = ANNOTATION_PARTITIONS[component]["present_supported"]
    assert SALARY_MISSING_INPUT_GAP[component] == present
    assert not any(_meaningful(record.fields["compensation_text"]) for record in records.values())


@pytest.mark.parametrize("component", COMPOSED_COMPONENTS)
def test_literal_result_categories_do_not_overlap(component: str) -> None:
    categories = [
        set(CORRECT[component]),
        set(SUPPORTED_ABSTENTION[component]),
        set(CONFIDENTLY_WRONG[component]),
        set(LOCATION_MISSING_INPUT_GAP.get(component, frozenset())),
        set(FALSE_POSITIVE_ABSENT[component]),
        set(FALSE_POSITIVE_UNSUPPORTED_FORM[component]),
        set(FALSE_POSITIVE_AMBIGUOUS[component]),
    ]
    for i, left in enumerate(categories):
        for right in categories[i + 1 :]:
            assert not left & right


@pytest.mark.parametrize("component", COMPOSED_COMPONENTS)
def test_scored_result_categories_are_exhaustive(
    component: str, scored: dict[str, dict[str, dict[str, Any]]]
) -> None:
    """Each record is placed in exactly one category by construction; this
    proves every record is placed."""
    by_category = scored[component]
    assert sum(len(ids) for ids in by_category.values()) == len(RECORD_IDS)
    assert set().union(*(set(ids) for ids in by_category.values())) == RECORD_IDS


def test_skills_annotations_are_exhaustive(records: dict[str, CorpusRecord]) -> None:
    present: set[tuple[str, str]] = set()
    absent = 0
    for record_id, record in records.items():
        assert set(record.annotations["skills"]) == SKILL_IDS, CHANGED
        for skill_id, annotation in record.annotations["skills"].items():
            if annotation["outcome"] == "present_supported":
                present.add((record_id, skill_id))
            else:
                assert annotation["outcome"] == "absent", CHANGED
                absent += 1
    assert present == SKILLS_PRESENT_SUPPORTED, CHANGED
    assert absent == len(RECORD_IDS) * len(SKILL_IDS) - len(SKILLS_PRESENT_SUPPORTED)
    assert SKILLS_RECALL_HITS | SKILLS_KNOWN_MISSES == SKILLS_PRESENT_SUPPORTED
    assert not SKILLS_RECALL_HITS & SKILLS_KNOWN_MISSES


# --- exact per-component output sets ---


@pytest.mark.parametrize("component", COMPOSED_COMPONENTS)
def test_correct_values_are_exact(
    component: str, scored: dict[str, dict[str, dict[str, Any]]]
) -> None:
    assert scored[component].get("correct", {}) == CORRECT[component], CHANGED


@pytest.mark.parametrize("component", COMPOSED_COMPONENTS)
def test_supported_abstentions_are_exact(
    component: str, scored: dict[str, dict[str, dict[str, Any]]]
) -> None:
    actual = set(scored[component].get("supported_abstention", {}))
    assert actual == SUPPORTED_ABSTENTION[component], CHANGED


@pytest.mark.parametrize("component", COMPOSED_COMPONENTS)
def test_confidently_wrong_values_are_exact(
    component: str, scored: dict[str, dict[str, dict[str, Any]]]
) -> None:
    assert scored[component].get("confidently_wrong", {}) == CONFIDENTLY_WRONG[component], CHANGED


@pytest.mark.parametrize(
    ("component", "category"),
    [
        (component, category)
        for component in COMPOSED_COMPONENTS
        for category in FALSE_POSITIVE_CATEGORIES.values()
    ],
)
def test_false_positive_sets_are_exact(
    component: str, category: str, scored: dict[str, dict[str, dict[str, Any]]]
) -> None:
    expected = {
        "false_positive_absent": FALSE_POSITIVE_ABSENT,
        "false_positive_unsupported_form": FALSE_POSITIVE_UNSUPPORTED_FORM,
        "false_positive_ambiguous": FALSE_POSITIVE_AMBIGUOUS,
    }[category][component]
    assert scored[component].get(category, {}) == expected, CHANGED


@pytest.mark.parametrize("component", sorted(LOCATION_MISSING_INPUT_GAP))
def test_location_missing_input_gap_is_exact(
    component: str, scored: dict[str, dict[str, dict[str, Any]]]
) -> None:
    actual = set(scored[component].get("missing_input_gap", {}))
    assert actual == LOCATION_MISSING_INPUT_GAP[component], CHANGED


# --- skills ---


def test_skills_recall_hits_are_exact(skills_scored: dict[str, set[tuple[str, str]]]) -> None:
    assert skills_scored["hit"] == SKILLS_RECALL_HITS, CHANGED


def test_skills_known_misses_are_exact(skills_scored: dict[str, set[tuple[str, str]]]) -> None:
    assert skills_scored["miss"] == SKILLS_KNOWN_MISSES, CHANGED


@pytest.mark.parametrize("category", sorted(FALSE_POSITIVE_CATEGORIES.values()))
def test_skills_false_positive_sets_are_exact(
    category: str, skills_scored: dict[str, set[tuple[str, str]]]
) -> None:
    expected = {
        "false_positive_absent": SKILLS_FALSE_POSITIVE_ABSENT,
        "false_positive_unsupported_form": SKILLS_FALSE_POSITIVE_UNSUPPORTED_FORM,
        "false_positive_ambiguous": SKILLS_FALSE_POSITIVE_AMBIGUOUS,
    }[category]
    assert skills_scored[category] == expected, CHANGED


# --- provenance, tested separately from value correctness ---


@pytest.mark.parametrize("component", COVERED_COMPONENTS)
def test_correct_value_provenance_matches_annotations_except_pinned_exceptions(
    component: str,
    records: dict[str, CorpusRecord],
    composed: dict[str, NormalizedPosting],
) -> None:
    assert CORRECT[component]
    for record_id in CORRECT[component]:
        expected = _annotation(records[record_id], component)["expected_provenance"]
        actual = _component_result(composed[record_id], component).provenance.value
        exception = PROVENANCE_EXCEPTIONS.get((record_id, component))
        if exception is None:
            assert actual == expected, CHANGED
        else:
            assert (expected, actual) == exception, CHANGED


def test_provenance_exceptions_are_exactly_the_three_accepted(
    records: dict[str, CorpusRecord], composed: dict[str, NormalizedPosting]
) -> None:
    actual: dict[tuple[str, str], tuple[str, str]] = {}
    for component in COMPOSED_COMPONENTS:
        for record_id, record in records.items():
            annotation = _annotation(record, component)
            result = _component_result(composed[record_id], component)
            if (
                annotation["outcome"] == "present_supported"
                and result.value is not None
                and result.value == annotation["expected_value"]
                and result.provenance.value != annotation["expected_provenance"]
            ):
                actual[(record_id, component)] = (
                    annotation["expected_provenance"],
                    result.provenance.value,
                )
    assert actual == PROVENANCE_EXCEPTIONS, CHANGED
    assert set(PROVENANCE_EXCEPTIONS) == {
        ("anthropic:4610158008", "location.country"),
        ("gitlab:8396674002", "location.country"),
        ("gitlab:8512432002", "location.country"),
    }


def _emitted_provenance(posting: NormalizedPosting) -> set[str]:
    results: list[NormalizationResult[Any]] = [
        posting.title.canonical_title,
        posting.title.role_family,
        posting.remote_type,
        posting.employment_type,
        posting.seniority,
        posting.experience.minimum,
        posting.experience.maximum,
        posting.location.city,
        posting.location.state,
        posting.location.country,
        posting.location.postal_code,
    ]
    return {result.provenance.value for result in results} | {
        match.provenance.value for match in posting.skills
    }


def test_emitted_provenance_never_claims_explicit_or_structured_sources(
    composed: dict[str, NormalizedPosting],
) -> None:
    emitted = set().union(*(_emitted_provenance(posting) for posting in composed.values()))
    assert emitted <= ALLOWED_PROVENANCE
    assert Provenance.EXPLICIT_SOURCE.value not in emitted
    assert Provenance.STRUCTURED_METADATA.value not in emitted
    assert emitted == EMITTED_PROVENANCE, CHANGED


def test_skills_provenance_is_parsed_description(composed: dict[str, NormalizedPosting]) -> None:
    emitted = {match.provenance.value for posting in composed.values() for match in posting.skills}
    assert emitted == SKILLS_EMITTED_PROVENANCE, CHANGED


# --- accounting ---


def test_covered_and_unproven_accounting(scored: dict[str, dict[str, dict[str, Any]]]) -> None:
    covered = tuple(c for c in COMPOSED_COMPONENTS if scored[c].get("correct"))
    zero_coverage = tuple(c for c in COMPOSED_COMPONENTS if not scored[c].get("correct"))
    assert covered == COVERED_COMPONENTS, CHANGED
    assert zero_coverage + SALARY_COMPONENTS == UNPROVEN_COMPONENTS, CHANGED
    assert not set(COVERED_COMPONENTS) & set(UNPROVEN_COMPONENTS)
    assert set(COVERED_COMPONENTS) | set(UNPROVEN_COMPONENTS) == set(ANNOTATED_COMPONENTS)
    assert "title" not in COVERED_COMPONENTS + UNPROVEN_COMPONENTS
    assert SKILLS_RECALL_HITS


def test_salary_is_not_composed_and_stays_unproven() -> None:
    assert "salary" not in {f for f in NormalizedPosting.__dataclass_fields__}
    assert set(SALARY_COMPONENTS) <= set(UNPROVEN_COMPONENTS)
    assert not set(SALARY_COMPONENTS) & set(CORRECT)


def test_headline_totals(
    scored: dict[str, dict[str, dict[str, Any]]],
    skills_scored: dict[str, set[tuple[str, str]]],
    composed: dict[str, NormalizedPosting],
    evaluator_combined: SplitEvaluation,
) -> None:
    def total(category: str) -> int:
        return sum(len(scored[c].get(category, {})) for c in COMPOSED_COMPONENTS)

    actual = {
        "records": len(composed),
        "runtime_failures": sum(
            counter.numerator for counter in evaluator_combined.runtime_failure.values()
        ),
        "confidently_wrong": total("confidently_wrong"),
        "false_positives": sum(total(c) for c in FALSE_POSITIVE_CATEGORIES.values()),
        "skills_false_positives": sum(
            len(skills_scored[c]) for c in FALSE_POSITIVE_CATEGORIES.values()
        ),
        "skills_recall": (
            len(skills_scored["hit"]),
            len(skills_scored["hit"]) + len(skills_scored["miss"]),
        ),
        "skills_known_misses": len(skills_scored["miss"]),
        "supported_abstentions": total("supported_abstention"),
        "missing_input_gap": total("missing_input_gap")
        + sum(len(ids) for ids in SALARY_MISSING_INPUT_GAP.values()),
        "correct_values": total("correct"),
        "provenance_exceptions": len(PROVENANCE_EXCEPTIONS),
        "evaluator_mismatches": len(evaluator_combined.mismatches),
    }
    assert actual == EXPECTED_TOTALS, CHANGED


# --- cross-check against the public evaluator result ---


def test_opportunity_matrices_match_the_evaluator(evaluator_combined: SplitEvaluation) -> None:
    for component in ANNOTATED_COMPONENTS:
        expected = {o: len(ids) for o, ids in ANNOTATION_PARTITIONS[component].items()}
        assert evaluator_combined.components[component].opportunity_matrix == expected
    skills_expected = {o: 0 for o in OUTCOMES}
    skills_expected["present_supported"] = len(SKILLS_PRESENT_SUPPORTED)
    skills_expected["absent"] = len(RECORD_IDS) * len(SKILL_IDS) - len(SKILLS_PRESENT_SUPPORTED)
    assert evaluator_combined.skills.opportunity_matrix == skills_expected


def test_runtime_failure_counts_match_the_evaluator(
    evaluator_combined: SplitEvaluation, composed: dict[str, NormalizedPosting]
) -> None:
    composed_parsers = {
        "remote_type",
        "employment_type",
        "seniority",
        "experience",
        "location",
        "skills",
    }
    assert composed_parsers <= set(evaluator_combined.runtime_failure)
    for parser in composed_parsers:
        counter = evaluator_combined.runtime_failure[parser]
        assert (counter.numerator, counter.denominator) == (0, len(composed))


def _evaluator_key(component: str) -> tuple[str, str | None]:
    if "." in component:
        parser, part = component.split(".")
        return parser, part
    return component, None


def test_mismatch_multiset_matches_the_evaluator_for_composed_components(
    scored: dict[str, dict[str, dict[str, Any]]],
    skills_scored: dict[str, set[tuple[str, str]]],
    evaluator_combined: SplitEvaluation,
) -> None:
    category_names = {
        "supported_abstention": "supported_abstention",
        "confidently_wrong": "confidently_wrong",
        "missing_input_gap": "missing_wired_input_gap",
        **{name: name for name in FALSE_POSITIVE_CATEGORIES.values()},
    }
    ours: Counter[tuple[str, str, str | None, str]] = Counter()
    for component in COMPOSED_COMPONENTS:
        parser, part = _evaluator_key(component)
        for category, ids in scored[component].items():
            if category in category_names:
                for record_id in ids:
                    ours[(record_id, parser, part, category_names[category])] += 1
    for record_id, skill_id in skills_scored["miss"]:
        ours[(record_id, "skills", skill_id, "recall_miss")] += 1
    for outcome, category in FALSE_POSITIVE_CATEGORIES.items():
        for record_id, skill_id in skills_scored[category]:
            ours[(record_id, "skills", skill_id, f"false_positive_{outcome}")] += 1
    theirs = Counter(
        (m.record_id, m.parser, m.component, m.category)
        for m in evaluator_combined.mismatches
        if m.parser != "salary"
    )
    assert ours == theirs


@pytest.mark.parametrize("component", SALARY_COMPONENTS)
def test_evaluator_salary_missing_input_sets_are_exact(
    component: str, evaluator_combined: SplitEvaluation
) -> None:
    parser, part = _evaluator_key(component)
    actual = {
        m.record_id
        for m in evaluator_combined.mismatches
        if (m.parser, m.component) == (parser, part) and m.category == "missing_wired_input_gap"
    }
    assert actual == SALARY_MISSING_INPUT_GAP[component], CHANGED


@pytest.mark.parametrize("record_id", sorted(RECORD_IDS))
def test_composition_equals_direct_parser_calls(
    record_id: str,
    records: dict[str, CorpusRecord],
    composed: dict[str, NormalizedPosting],
    taxonomy: TaxonomyIndex,
) -> None:
    fields = records[record_id].fields
    title, description, location = fields["title"], fields["description"], fields["location_raw"]
    posting = composed[record_id]
    assert posting.title == classify_title(title)
    assert posting.remote_type == classify_remote_type(title, description)
    assert posting.employment_type == classify_employment_type(title, description)
    assert posting.seniority == classify_seniority(title, description)
    assert posting.experience == classify_experience(title, description)
    assert posting.location == classify_location(location)
    assert posting.skills == tuple(classify_skills(title, description, taxonomy=taxonomy))


# --- title smoke boundary (not D2 accuracy evidence) ---


def test_title_smoke_expectations_are_exact(composed: dict[str, NormalizedPosting]) -> None:
    actual = {
        record_id: (
            posting.title.outcome.value,
            posting.title.canonical_title.value,
            posting.title.role_family.value,
        )
        for record_id, posting in composed.items()
    }
    assert actual == TITLE_SMOKE, CHANGED


def test_title_smoke_counts() -> None:
    counts = Counter(outcome for outcome, _, _ in TITLE_SMOKE.values())
    assert {o: counts.get(o, 0) for o in TITLE_SMOKE_COUNTS} == TITLE_SMOKE_COUNTS
    assert set(TITLE_SMOKE) == RECORD_IDS


# --- mutation-experiment predicate ---


def test_m8_input_predicate_matches_exactly_one_record(records: dict[str, CorpusRecord]) -> None:
    matches = [
        record_id
        for record_id, record in records.items()
        if record.fields["title"] == M8_TITLE and record.fields["location_raw"] == M8_LOCATION
    ]
    assert matches == [M8_RECORD_ID]
    assert M8_RECORD_ID in SUPPORTED_ABSTENTION["location.country"]
