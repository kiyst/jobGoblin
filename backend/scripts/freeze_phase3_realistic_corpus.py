"""Deterministic corpus-freeze builder for the realistic Phase 3 evaluation
corpus (Class H tooling slice; Sol-approved freeze/evaluation contract,
2026-09-27). Pure, read-only apart from its one create-only output write --
no network, no database, no parser-semantic change.

**Canonical `source_packet_hash`** (`compute_source_packet_hash`): both
annotation passes must be run against the exact same triple -- the reviewed
salvage file, the committed skills taxonomy, and the frozen rubric --
identified by this one manifest, serialized canonically (`json.dumps` with
`sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, no trailing
newline) and SHA-256 hashed:

    {
      "schema_version": "1",
      "salvage_path": "backend/.evaluation-staging/greenhouse_candidates_second_pass_review.json",
      "salvage_sha256": "<sha256 of that file>",
      "taxonomy_path": "backend/app/taxonomy/skills.yaml",
      "taxonomy_sha256": "<sha256 of that file>",
      "rubric_path": "docs/evaluation/phase3-realistic-annotation-rubric.md",
      "rubric_sha256": "<sha256 of that file>",
      "rubric_version": "<the rubric's declared version>"
    }

**Annotation-pass schema** (`load_annotation_pass`), one file per pass,
exactly these top-level keys:

    {
      "schema_version": "1",
      "annotator_role": "claude" | "sol",
      "rubric_version": "...",
      "source_packet_hash": "<sha256 hex, recomputed and compared, never trusted>",
      "frozen_at": "<aware ISO8601>",
      "records": {
        "<record id>": {
          "remote_type": {"outcome": ..., "expected_value": ..., "expected_provenance": ...},
          "employment_type": {...}, "seniority": {...},
          "experience": {"minimum": {...}, "maximum": {...}},
          "salary": {"minimum": {...}, "maximum": {...}, "currency": {...}, "period": {...}},
          "location": {"city": {...}, "state": {...}, "country": {...}, "postal_code": {...}},
          "skills": {"<canonical id>": {"outcome": ...}, ...every known id...}
        },
        ... exactly the salvage batch's record ids ...
      }
    }

Every scalar/composite label is a closed 3-key object (`outcome`,
`expected_value`, `expected_provenance`); every skill label is a closed
1-key object (`outcome`) -- no other key is ever accepted, which is what
rules out a smuggled-in parser-output field. Exactly 3 + 10 + (taxonomy
size) labels are required per record, no more, no fewer.

Blindness (one annotator never seeing the other's pass, reasoning, or any
parser output) is **procedural** -- guaranteed by how the two annotation
tasks are run, never by anything this file's schema can itself cryptographically
prove. This module does not and cannot verify blindness; it only verifies
that a pass file is internally well-formed and cites the correct shared
source packet.

**Adjudication/audit schema** (`load_adjudication_audit`): records every
disagreement between the two passes (each resolved by a complete
`adjudication`) and every required agreement audit (every `present_supported`
agreement, plus -- for every other outcome, per parser/component-or-skill
label and per employer stratum containing at least one agreement -- the
agreement at the lexicographically smallest stable record id). An audited
agreement found wrong ("overturned") must also appear as a disagreement with
a complete adjudication; this module cross-validates that pairing rather
than trusting either half in isolation.

**`build_corpus`** merges the validated salvage batch, both validated passes,
and the validated adjudication/audit evidence into
`evaluate_phase3_corpus.py`'s own committed corpus schema, assigns the
deterministic employer-disjoint dev/holdout split (employers sorted
ascending; the lexicographically last employer is `holdout`, the rest are
`dev`), copies reviewed `fields` text unmodified, and writes the result
atomically -- create-only, refusing to overwrite an existing corpus file.
Before that write is made durable, the freshly built corpus is validated by
actually calling `evaluate_phase3_corpus.load_corpus` against it (the real,
authoritative validator -- never a shadow reimplementation of its rules), so
an invalid corpus is never left on disk even transiently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPTS_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.normalization.taxonomy import load_taxonomy  # noqa: E402
from scripts.evaluate_phase3_corpus import CorpusValidationError, load_corpus  # noqa: E402

DEFAULT_SALVAGE_PATH = (
    BACKEND_DIR / ".evaluation-staging" / "greenhouse_candidates_second_pass_review.json"
)
DEFAULT_TAXONOMY_PATH = BACKEND_DIR / "app" / "taxonomy" / "skills.yaml"
DEFAULT_RUBRIC_PATH = REPO_ROOT / "docs" / "evaluation" / "phase3-realistic-annotation-rubric.md"
DEFAULT_CORPUS_OUTPUT_PATH = (
    BACKEND_DIR / "tests" / "fixtures" / "evaluation" / "phase3_realistic_corpus.json"
)

RUBRIC_VERSION = "1.0.0"
EXPECTED_SALVAGE_SHA256 = "1273b6eafd42d05898520a783ad94f063da4507e8c00f3c4da86a3273b36fd6a"
EXPECTED_RECORD_COUNT = 30

_SCALAR_PARSERS: tuple[str, ...] = ("remote_type", "employment_type", "seniority")
_COMPOSITE_PARSER_COMPONENTS: dict[str, tuple[str, ...]] = {
    "experience": ("minimum", "maximum"),
    "salary": ("minimum", "maximum", "currency", "period"),
    "location": ("city", "state", "country", "postal_code"),
}
_FIXED_LABEL_COUNT = len(_SCALAR_PARSERS) + sum(
    len(components) for components in _COMPOSITE_PARSER_COMPONENTS.values()
)  # 3 + 10 == 13, independent of taxonomy size

_VALID_OUTCOMES = frozenset(
    {"present_supported", "present_unsupported_form", "absent", "ambiguous"}
)
_RAW_SCALAR_LABEL_FIELDS = frozenset({"outcome", "expected_value", "expected_provenance"})
_RAW_SKILL_LABEL_FIELDS = frozenset({"outcome"})

_REQUIRED_PASS_TOP_FIELDS = frozenset(
    {
        "schema_version",
        "annotator_role",
        "rubric_version",
        "source_packet_hash",
        "frozen_at",
        "records",
    }
)
_VALID_ANNOTATOR_ROLES = frozenset({"claude", "sol"})


class FreezeBuilderError(Exception):
    """The salvage batch, an annotation pass, or the adjudication/audit
    artifact fails a required invariant -- always fails closed, never a
    warning or a silently-repaired value."""


# ---------------------------------------------------------------------------
# Canonical source-packet hash
# ---------------------------------------------------------------------------
def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _repo_relative(path: Path) -> str:
    """Repo-relative POSIX path when `path` is actually inside this
    repository (the real, committed inputs always are); otherwise the
    resolved absolute POSIX path -- still deterministic and still hashable,
    just not repo-relative. Lets synthetic test fixtures outside the repo
    (e.g. under `tmp_path`) exercise this function without special-casing."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def compute_source_packet_hash(
    *, salvage_path: Path, taxonomy_path: Path, rubric_path: Path, rubric_version: str
) -> tuple[dict[str, str], str]:
    """Returns `(manifest, source_packet_hash)`. `manifest` is the exact
    binding schema (`schema_version`, `*_path`, `*_sha256`, `rubric_version`);
    `source_packet_hash` is its canonical-JSON SHA-256, recomputed fresh from
    the three files on disk every time -- never read from a caller-supplied
    value, so a stale or hand-edited hash can never silently pass."""
    manifest = {
        "schema_version": "1",
        "salvage_path": _repo_relative(salvage_path),
        "salvage_sha256": _sha256_file(salvage_path),
        "taxonomy_path": _repo_relative(taxonomy_path),
        "taxonomy_sha256": _sha256_file(taxonomy_path),
        "rubric_path": _repo_relative(rubric_path),
        "rubric_sha256": _sha256_file(rubric_path),
        "rubric_version": rubric_version,
    }
    digest = _sha256_bytes(_canonical_json_bytes(manifest))
    return manifest, digest


def _is_valid_aware_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# Label-path helpers -- one shared vocabulary of "where a label lives" used
# by pass-file validation, adjudication/audit validation, and the merge step.
# ---------------------------------------------------------------------------
def _label_paths(known_canonical_ids: frozenset[str]) -> list[tuple[str, ...]]:
    paths: list[tuple[str, ...]] = [(parser,) for parser in _SCALAR_PARSERS]
    for parser, components in _COMPOSITE_PARSER_COMPONENTS.items():
        paths.extend((parser, component) for component in components)
    paths.extend(("skills", canonical_id) for canonical_id in sorted(known_canonical_ids))
    return paths


def _is_skill_path(label_path: tuple[str, ...]) -> bool:
    return label_path[0] == "skills"


def _artifact_key(record_id: str, label_path: tuple[str, ...]) -> str:
    return f"{record_id}|{'.'.join(label_path)}"


def _get_raw_label(record_annotations: Any, label_path: tuple[str, ...]) -> dict[str, Any]:
    node = record_annotations
    for part in label_path:
        if not isinstance(node, dict) or part not in node:
            raise FreezeBuilderError(f"annotation path {'.'.join(label_path)} is missing")
        node = node[part]
    if not isinstance(node, dict):
        raise FreezeBuilderError(f"annotation path {'.'.join(label_path)} must be an object")
    return node


# ---------------------------------------------------------------------------
# Annotation-pass loading and validation
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AnnotationPass:
    annotator_role: str
    rubric_version: str
    source_packet_hash: str
    frozen_at: str
    records: dict[str, dict[str, Any]]


def _validate_raw_label(label: Any, *, is_skill: bool, context: str) -> None:
    if not isinstance(label, dict):
        raise FreezeBuilderError(f"{context} must be a JSON object")
    allowed = _RAW_SKILL_LABEL_FIELDS if is_skill else _RAW_SCALAR_LABEL_FIELDS
    if set(label) != allowed:
        raise FreezeBuilderError(f"{context} must declare exactly {sorted(allowed)}")
    if label["outcome"] not in _VALID_OUTCOMES:
        raise FreezeBuilderError(
            f"{context}.outcome must be one of {sorted(_VALID_OUTCOMES)}, got {label['outcome']!r}"
        )
    if not is_skill:
        has_value = label["expected_value"] is not None
        is_supported = label["outcome"] == "present_supported"
        if has_value != is_supported:
            raise FreezeBuilderError(
                f"{context}: expected_value must be non-null iff outcome is 'present_supported'"
            )
        if is_supported and label["expected_provenance"] not in ("parsed_description", "inferred"):
            raise FreezeBuilderError(
                f"{context}.expected_provenance must be 'parsed_description' or 'inferred' "
                "when outcome is 'present_supported' (see the rubric's provenance rules)"
            )
        if not is_supported and label["expected_provenance"] != "unavailable":
            raise FreezeBuilderError(
                f"{context}.expected_provenance must be 'unavailable' when expected_value is null"
            )


def load_annotation_pass(
    path: Path,
    *,
    expected_annotator_role: str,
    expected_record_ids: frozenset[str],
    known_canonical_ids: frozenset[str],
    expected_rubric_version: str,
    expected_source_packet_hash: str,
) -> AnnotationPass:
    """Loads and fully validates one annotation-pass file. Fails closed on
    any structural defect, any declared-metadata mismatch, or an incomplete
    inventory -- never silently accepts a partial or malformed pass."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FreezeBuilderError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != _REQUIRED_PASS_TOP_FIELDS:
        raise FreezeBuilderError(f"{path} must declare exactly {sorted(_REQUIRED_PASS_TOP_FIELDS)}")

    if raw["schema_version"] != "1":
        raise FreezeBuilderError(f"{path}: unsupported schema_version {raw['schema_version']!r}")
    if raw["annotator_role"] != expected_annotator_role:
        raise FreezeBuilderError(
            f"{path}: annotator_role must be {expected_annotator_role!r}, "
            f"got {raw['annotator_role']!r}"
        )
    if raw["annotator_role"] not in _VALID_ANNOTATOR_ROLES:
        raise FreezeBuilderError(f"{path}: annotator_role not in {sorted(_VALID_ANNOTATOR_ROLES)}")
    if raw["rubric_version"] != expected_rubric_version:
        raise FreezeBuilderError(
            f"{path}: rubric_version must be {expected_rubric_version!r}, "
            f"got {raw['rubric_version']!r}"
        )
    if raw["source_packet_hash"] != expected_source_packet_hash:
        raise FreezeBuilderError(
            f"{path}: source_packet_hash does not match the freshly recomputed canonical hash -- "
            "this pass was not run against the declared common source packet"
        )
    if not _is_valid_aware_timestamp(raw["frozen_at"]):
        raise FreezeBuilderError(f"{path}: frozen_at must be a timezone-aware ISO8601 timestamp")

    records = raw["records"]
    if not isinstance(records, dict) or set(records) != expected_record_ids:
        missing = expected_record_ids - set(records) if isinstance(records, dict) else None
        extra = set(records) - expected_record_ids if isinstance(records, dict) else None
        raise FreezeBuilderError(
            f"{path}: records must declare exactly the {len(expected_record_ids)} salvage "
            f"record ids (missing={sorted(missing) if missing else []}, "
            f"extra={sorted(extra) if extra else []})"
        )

    label_paths = _label_paths(known_canonical_ids)
    for record_id, record_annotations in records.items():
        if not isinstance(record_annotations, dict):
            raise FreezeBuilderError(f"{path}: records[{record_id!r}] must be a JSON object")
        for label_path in label_paths:
            label = _get_raw_label(record_annotations, label_path)
            _validate_raw_label(
                label,
                is_skill=_is_skill_path(label_path),
                context=f"{path}: records[{record_id!r}].{'.'.join(label_path)}",
            )
        # Exhaustiveness: exactly the expected leaf-label count, no more.
        leaf_count = len(_SCALAR_PARSERS)
        for parser, components in _COMPOSITE_PARSER_COMPONENTS.items():
            group = record_annotations.get(parser)
            if not isinstance(group, dict) or set(group) != set(components):
                raise FreezeBuilderError(
                    f"{path}: records[{record_id!r}].{parser} must declare exactly "
                    f"{sorted(components)}"
                )
            leaf_count += len(components)
        skills_group = record_annotations.get("skills")
        if not isinstance(skills_group, dict) or set(skills_group) != known_canonical_ids:
            raise FreezeBuilderError(
                f"{path}: records[{record_id!r}].skills must declare exactly the "
                f"{len(known_canonical_ids)} known canonical id(s), no more, no fewer"
            )
        leaf_count += len(known_canonical_ids)
        expected_leaf_count = _FIXED_LABEL_COUNT + len(known_canonical_ids)
        if leaf_count != expected_leaf_count:
            raise FreezeBuilderError(
                f"{path}: records[{record_id!r}] has {leaf_count} labels, "
                f"expected exactly {expected_leaf_count}"
            )
        unknown_top_keys = set(record_annotations) - (
            set(_SCALAR_PARSERS) | set(_COMPOSITE_PARSER_COMPONENTS) | {"skills"}
        )
        if unknown_top_keys:
            raise FreezeBuilderError(
                f"{path}: records[{record_id!r}] declares unrecognized annotation "
                f"group(s): {sorted(unknown_top_keys)}"
            )

    return AnnotationPass(
        annotator_role=raw["annotator_role"],
        rubric_version=raw["rubric_version"],
        source_packet_hash=raw["source_packet_hash"],
        frozen_at=raw["frozen_at"],
        records=records,
    )


# ---------------------------------------------------------------------------
# Adjudication/audit artifact loading and validation
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AdjudicationAudit:
    disagreements: dict[str, dict[str, Any]]
    audited_agreements: dict[str, dict[str, Any]]


_REQUIRED_ADJUDICATION_AUDIT_TOP_FIELDS = frozenset(
    {"schema_version", "completed_at", "disagreements", "audited_agreements"}
)
_REQUIRED_SCALAR_ADJUDICATION_FIELDS = frozenset(
    {"final_outcome", "final_value", "final_provenance", "adjudicated_by", "adjudicated_at"}
)
_REQUIRED_SKILL_ADJUDICATION_FIELDS = frozenset(
    {"final_outcome", "adjudicated_by", "adjudicated_at"}
)
_REQUIRED_AUDIT_ENTRY_FIELDS = frozenset({"audited_by", "audited_at", "result"})
_VALID_AUDIT_RESULTS = frozenset({"confirmed", "overturned"})


def _final_label_from_adjudication(
    adjudication: Any, *, is_skill: bool, context: str
) -> dict[str, Any]:
    required = (
        _REQUIRED_SKILL_ADJUDICATION_FIELDS if is_skill else _REQUIRED_SCALAR_ADJUDICATION_FIELDS
    )
    if not isinstance(adjudication, dict) or set(adjudication) != required:
        raise FreezeBuilderError(f"{context}.adjudication must declare exactly {sorted(required)}")
    if not isinstance(adjudication["adjudicated_by"], str) or not adjudication["adjudicated_by"]:
        raise FreezeBuilderError(
            f"{context}.adjudication.adjudicated_by must be a non-empty string"
        )
    if not _is_valid_aware_timestamp(adjudication["adjudicated_at"]):
        raise FreezeBuilderError(
            f"{context}.adjudication.adjudicated_at must be a timezone-aware ISO8601 timestamp"
        )
    final_outcome = adjudication["final_outcome"]
    if final_outcome not in _VALID_OUTCOMES:
        raise FreezeBuilderError(f"{context}.adjudication.final_outcome is not a known outcome")
    if is_skill:
        return {"outcome": final_outcome}
    final_value = adjudication["final_value"]
    final_provenance = adjudication["final_provenance"]
    has_value = final_value is not None
    is_supported = final_outcome == "present_supported"
    if has_value != is_supported:
        raise FreezeBuilderError(
            f"{context}.adjudication: final_value must be non-null iff final_outcome is "
            "'present_supported'"
        )
    if is_supported and final_provenance not in ("parsed_description", "inferred"):
        raise FreezeBuilderError(
            f"{context}.adjudication.final_provenance must be 'parsed_description' or 'inferred' "
            "when final_outcome is 'present_supported'"
        )
    if not is_supported and final_provenance != "unavailable":
        raise FreezeBuilderError(
            f"{context}.adjudication.final_provenance must be 'unavailable' when "
            "final_value is null"
        )
    return {
        "outcome": final_outcome,
        "expected_value": final_value,
        "expected_provenance": final_provenance,
    }


def _compute_required_audit_keys(
    *,
    expected_record_ids: frozenset[str],
    employer_by_record_id: dict[str, str],
    claude_pass: AnnotationPass,
    sol_pass: AnnotationPass,
    label_paths: list[tuple[str, ...]],
) -> tuple[set[str], dict[str, tuple[dict[str, Any], dict[str, Any]]]]:
    """Returns `(required_audit_keys, agreements)`. `agreements` maps every
    agreeing (record, label) key to its shared `(claude_label, sol_label)`
    pair. The deterministic rule (frozen before any label exists): audit
    every `present_supported` agreement; for every other outcome, audit
    exactly the agreement at the lexicographically smallest record id within
    each (label path, outcome, employer) stratum that contains at least one
    agreement."""
    agreements: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    strata: dict[tuple[str, str, str], list[str]] = {}
    required: set[str] = set()

    for record_id in sorted(expected_record_ids):
        employer = employer_by_record_id[record_id]
        for label_path in label_paths:
            claude_label = _get_raw_label(claude_pass.records[record_id], label_path)
            sol_label = _get_raw_label(sol_pass.records[record_id], label_path)
            if claude_label != sol_label:
                continue
            key = _artifact_key(record_id, label_path)
            agreements[key] = (claude_label, sol_label)
            if claude_label["outcome"] == "present_supported":
                required.add(key)
            else:
                stratum = (".".join(label_path), claude_label["outcome"], employer)
                strata.setdefault(stratum, []).append(record_id)

    for (label_path_str, _outcome, _employer), record_ids in strata.items():
        smallest = min(record_ids)
        required.add(_artifact_key(smallest, tuple(label_path_str.split("."))))

    return required, agreements


def load_adjudication_audit(
    path: Path,
    *,
    expected_record_ids: frozenset[str],
    employer_by_record_id: dict[str, str],
    claude_pass: AnnotationPass,
    sol_pass: AnnotationPass,
    known_canonical_ids: frozenset[str],
) -> AdjudicationAudit:
    """Loads and fully validates the adjudication/audit artifact against
    both already-validated passes: every genuine disagreement between the
    two passes must have a complete adjudication; every required agreement
    audit (per the deterministic rule) must be present; an `overturned`
    audit entry must have a matching disagreement whose adjudication
    actually differs from the previously agreed label; a `confirmed` entry
    must not also be recorded as a disagreement."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FreezeBuilderError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != _REQUIRED_ADJUDICATION_AUDIT_TOP_FIELDS:
        raise FreezeBuilderError(
            f"{path} must declare exactly {sorted(_REQUIRED_ADJUDICATION_AUDIT_TOP_FIELDS)}"
        )
    if raw["schema_version"] != "1":
        raise FreezeBuilderError(f"{path}: unsupported schema_version {raw['schema_version']!r}")
    if not _is_valid_aware_timestamp(raw["completed_at"]):
        raise FreezeBuilderError(f"{path}: completed_at must be a timezone-aware ISO8601 timestamp")

    disagreements = raw["disagreements"]
    audited_agreements = raw["audited_agreements"]
    if not isinstance(disagreements, dict):
        raise FreezeBuilderError(f"{path}: disagreements must be a JSON object")
    if not isinstance(audited_agreements, dict):
        raise FreezeBuilderError(f"{path}: audited_agreements must be a JSON object")

    label_paths = _label_paths(known_canonical_ids)
    required_keys, agreements = _compute_required_audit_keys(
        expected_record_ids=expected_record_ids,
        employer_by_record_id=employer_by_record_id,
        claude_pass=claude_pass,
        sol_pass=sol_pass,
        label_paths=label_paths,
    )
    all_keys = {_artifact_key(rid, lp) for rid in expected_record_ids for lp in label_paths}
    disagreement_expected_keys = all_keys - set(agreements)

    unknown_disagreement_keys = set(disagreements) - all_keys
    if unknown_disagreement_keys:
        raise FreezeBuilderError(
            f"{path}: disagreements cites unknown record/label key(s): "
            f"{sorted(unknown_disagreement_keys)}"
        )
    missing_disagreement_keys = disagreement_expected_keys - set(disagreements)
    if missing_disagreement_keys:
        raise FreezeBuilderError(
            f"{path}: {len(missing_disagreement_keys)} genuine pass disagreement(s) have no "
            f"recorded adjudication, e.g. {sorted(missing_disagreement_keys)[:3]}"
        )
    spurious_disagreement_keys = set(disagreements) & set(agreements)

    for key, entry in disagreements.items():
        if not isinstance(entry, dict) or set(entry) != {"adjudication"}:
            raise FreezeBuilderError(
                f"{path}: disagreements[{key!r}] must declare exactly 'adjudication'"
            )
        record_id, label_path_str = key.split("|", 1)
        label_path = tuple(label_path_str.split("."))
        is_skill = _is_skill_path(label_path)
        final_label = _final_label_from_adjudication(
            entry["adjudication"], is_skill=is_skill, context=f"{path}: disagreements[{key!r}]"
        )
        if key in spurious_disagreement_keys:
            claude_label, sol_label = agreements[key]
            if final_label == claude_label:
                raise FreezeBuilderError(
                    f"{path}: disagreements[{key!r}] resolves to the same label the two passes "
                    "already agreed on -- an overturned agreement must actually change the label"
                )

    unknown_audit_keys = set(audited_agreements) - set(agreements)
    if unknown_audit_keys:
        raise FreezeBuilderError(
            f"{path}: audited_agreements cites key(s) that are not agreements between the two "
            f"passes: {sorted(unknown_audit_keys)}"
        )
    missing_audit_keys = required_keys - set(audited_agreements)
    if missing_audit_keys:
        raise FreezeBuilderError(
            f"{path}: {len(missing_audit_keys)} required agreement audit(s) are missing, e.g. "
            f"{sorted(missing_audit_keys)[:3]}"
        )

    for key, entry in audited_agreements.items():
        if not isinstance(entry, dict) or set(entry) != _REQUIRED_AUDIT_ENTRY_FIELDS:
            raise FreezeBuilderError(
                f"{path}: audited_agreements[{key!r}] must declare exactly "
                f"{sorted(_REQUIRED_AUDIT_ENTRY_FIELDS)}"
            )
        if not isinstance(entry["audited_by"], str) or not entry["audited_by"]:
            raise FreezeBuilderError(
                f"{path}: audited_agreements[{key!r}].audited_by must be non-empty"
            )
        if not _is_valid_aware_timestamp(entry["audited_at"]):
            raise FreezeBuilderError(
                f"{path}: audited_agreements[{key!r}].audited_at must be a timezone-aware "
                "ISO8601 timestamp"
            )
        if entry["result"] not in _VALID_AUDIT_RESULTS:
            raise FreezeBuilderError(
                f"{path}: audited_agreements[{key!r}].result must be one of "
                f"{sorted(_VALID_AUDIT_RESULTS)}"
            )
        is_overturned = entry["result"] == "overturned"
        is_recorded_as_disagreement = key in disagreements
        if is_overturned and not is_recorded_as_disagreement:
            raise FreezeBuilderError(
                f"{path}: audited_agreements[{key!r}] is 'overturned' but has no matching "
                "disagreements[...] adjudication"
            )
        if not is_overturned and is_recorded_as_disagreement:
            raise FreezeBuilderError(
                f"{path}: audited_agreements[{key!r}] is 'confirmed' but is also recorded as a "
                "disagreement -- a confirmed agreement must not be adjudicated away"
            )

    return AdjudicationAudit(disagreements=disagreements, audited_agreements=audited_agreements)


# ---------------------------------------------------------------------------
# Deterministic split and merge
# ---------------------------------------------------------------------------
def deterministic_split(employers: frozenset[str]) -> tuple[frozenset[str], str]:
    """Returns `(dev_employers, holdout_employer)`. Employers sorted
    ascending; the lexicographically last one is `holdout`, every other
    employer is `dev` -- fixed, requires no per-record judgment call."""
    ordered = sorted(employers)
    if len(ordered) < 2:
        raise FreezeBuilderError(
            "at least two distinct employers are required for a disjoint split"
        )
    holdout_employer = ordered[-1]
    dev_employers = frozenset(ordered[:-1])
    return dev_employers, holdout_employer


def _merge_agreed_label(
    shared_raw: dict[str, Any], *, rubric_version: str, frozen_at: str
) -> dict[str, Any]:
    label = dict(shared_raw)
    label.update(
        {
            "annotator_role": "claude+sol:agreed",
            "rubric_version": rubric_version,
            "annotation_provenance": (
                "phase3_realistic_corpus freeze: independent two-pass agreement"
            ),
            "frozen": True,
            "frozen_at": frozen_at,
        }
    )
    return label


def _merge_adjudicated_label(
    *,
    claude_raw: dict[str, Any],
    sol_raw: dict[str, Any],
    final_raw: dict[str, Any],
    rubric_version: str,
    claude_frozen_at: str,
    sol_frozen_at: str,
    adjudicated_by: str,
    adjudicated_at: str,
) -> dict[str, Any]:
    """`final_raw` is the user's resolved label. `second_annotation` is
    whichever of the two raw passes differs from `final_raw` -- guaranteed
    to exist and to actually differ, since a genuine two-way disagreement
    has `claude_raw != sol_raw`, and an overturned agreement's adjudication
    is required (above) to differ from the previously agreed value. This
    keeps `evaluate_phase3_corpus.py`'s own "a disagreement must reflect an
    actual difference" invariant satisfiable in every case, including one
    where the final answer happens to exactly match one raw pass."""
    if final_raw == sol_raw:
        second_raw, second_role, second_frozen_at = claude_raw, "claude", claude_frozen_at
    else:
        second_raw, second_role, second_frozen_at = sol_raw, "sol", sol_frozen_at

    is_skill = "expected_value" not in final_raw
    adjudication: dict[str, Any] = {
        "adjudicated_by": adjudicated_by,
        "adjudicated_at": adjudicated_at,
    }
    if is_skill:
        adjudication["final_outcome"] = final_raw["outcome"]
    else:
        adjudication["final_outcome"] = final_raw["outcome"]
        adjudication["final_value"] = final_raw["expected_value"]
        adjudication["final_provenance"] = final_raw["expected_provenance"]

    primary = dict(final_raw)
    primary.update(
        {
            "annotator_role": "adjudicated:user",
            "rubric_version": rubric_version,
            "annotation_provenance": (
                "phase3_realistic_corpus freeze: user-adjudicated disagreement"
            ),
            "frozen": True,
            "frozen_at": adjudicated_at,
            "disagreement": {
                "second_annotation": {
                    **second_raw,
                    "annotator_role": second_role,
                    "rubric_version": rubric_version,
                    "annotation_provenance": (
                        f"phase3_realistic_corpus freeze: {second_role} pass (raw)"
                    ),
                    "frozen": True,
                    "frozen_at": second_frozen_at,
                },
                "adjudication": adjudication,
            },
        }
    )
    return primary


def _set_at_path(
    annotations: dict[str, Any], label_path: tuple[str, ...], value: dict[str, Any]
) -> None:
    node = annotations
    for part in label_path[:-1]:
        node = node.setdefault(part, {})
    node[label_path[-1]] = value


def build_corpus(
    *,
    salvage_path: Path = DEFAULT_SALVAGE_PATH,
    expected_salvage_sha256: str = EXPECTED_SALVAGE_SHA256,
    taxonomy_path: Path = DEFAULT_TAXONOMY_PATH,
    rubric_path: Path = DEFAULT_RUBRIC_PATH,
    rubric_version: str = RUBRIC_VERSION,
    pass_claude_path: Path,
    pass_sol_path: Path,
    adjudication_audit_path: Path,
    output_path: Path = DEFAULT_CORPUS_OUTPUT_PATH,
) -> Path:
    """Verifies every input, merges validated evidence into the committed
    corpus schema, and atomically create-only writes it to `output_path`.
    Raises `FreezeBuilderError` (or lets a `CorpusValidationError` from the
    authoritative self-check propagate) on any failure -- never leaves a
    partially-written or invalid corpus file behind."""
    if output_path.exists():
        raise FreezeBuilderError(f"{output_path} already exists -- refusing to overwrite")

    actual_salvage_sha256 = _sha256_file(salvage_path)
    if actual_salvage_sha256 != expected_salvage_sha256:
        raise FreezeBuilderError(
            f"{salvage_path}: sha256 {actual_salvage_sha256} does not match the expected "
            f"{expected_salvage_sha256} -- refusing to freeze against an unverified salvage batch"
        )

    salvage = json.loads(salvage_path.read_text(encoding="utf-8"))
    candidates = salvage["candidates"]
    human_review_record = salvage["human_review_record"]

    record_ids: list[str] = []
    salvage_by_id: dict[str, dict[str, Any]] = {}
    employer_by_record_id: dict[str, str] = {}
    for candidate in candidates:
        if candidate["human_decision"]["status"] != "retain":
            raise FreezeBuilderError(
                f"candidate {candidate['board_token']}/{candidate['job_id']} is not retained -- "
                "only retained candidates may enter the corpus"
            )
        record_id = f"{candidate['board_token']}:{candidate['job_id']}"
        if record_id in salvage_by_id:
            raise FreezeBuilderError(f"duplicate salvage record id {record_id!r}")
        record_ids.append(record_id)
        salvage_by_id[record_id] = candidate
        employer_by_record_id[record_id] = candidate["employer"]

    expected_record_ids = frozenset(record_ids)

    taxonomy = load_taxonomy(taxonomy_path)
    known_canonical_ids = taxonomy.canonical_ids()

    _manifest, source_packet_hash = compute_source_packet_hash(
        salvage_path=salvage_path,
        taxonomy_path=taxonomy_path,
        rubric_path=rubric_path,
        rubric_version=rubric_version,
    )

    claude_pass = load_annotation_pass(
        pass_claude_path,
        expected_annotator_role="claude",
        expected_record_ids=expected_record_ids,
        known_canonical_ids=known_canonical_ids,
        expected_rubric_version=rubric_version,
        expected_source_packet_hash=source_packet_hash,
    )
    sol_pass = load_annotation_pass(
        pass_sol_path,
        expected_annotator_role="sol",
        expected_record_ids=expected_record_ids,
        known_canonical_ids=known_canonical_ids,
        expected_rubric_version=rubric_version,
        expected_source_packet_hash=source_packet_hash,
    )
    adjudication_audit = load_adjudication_audit(
        adjudication_audit_path,
        expected_record_ids=expected_record_ids,
        employer_by_record_id=employer_by_record_id,
        claude_pass=claude_pass,
        sol_pass=sol_pass,
        known_canonical_ids=known_canonical_ids,
    )

    dev_employers, holdout_employer = deterministic_split(frozenset(employer_by_record_id.values()))

    label_paths = _label_paths(known_canonical_ids)
    corpus_records: list[dict[str, Any]] = []
    for record_id in record_ids:
        candidate = salvage_by_id[record_id]
        employer = employer_by_record_id[record_id]
        split = "holdout" if employer == holdout_employer else "dev"
        if employer not in dev_employers and split == "dev":
            raise FreezeBuilderError(f"internal split inconsistency for {record_id!r}")

        annotations: dict[str, Any] = {}
        for label_path in label_paths:
            key = _artifact_key(record_id, label_path)
            claude_label = _get_raw_label(claude_pass.records[record_id], label_path)
            sol_label = _get_raw_label(sol_pass.records[record_id], label_path)
            if key in adjudication_audit.disagreements:
                final_label = _final_label_from_adjudication(
                    adjudication_audit.disagreements[key]["adjudication"],
                    is_skill=_is_skill_path(label_path),
                    context=f"disagreements[{key!r}]",
                )
                merged = _merge_adjudicated_label(
                    claude_raw=claude_label,
                    sol_raw=sol_label,
                    final_raw=final_label,
                    rubric_version=rubric_version,
                    claude_frozen_at=claude_pass.frozen_at,
                    sol_frozen_at=sol_pass.frozen_at,
                    adjudicated_by=adjudication_audit.disagreements[key]["adjudication"][
                        "adjudicated_by"
                    ],
                    adjudicated_at=adjudication_audit.disagreements[key]["adjudication"][
                        "adjudicated_at"
                    ],
                )
            else:
                if claude_label != sol_label:
                    raise FreezeBuilderError(
                        f"internal inconsistency: {key!r} is a pass disagreement with no "
                        "adjudication (should already have been rejected by "
                        "load_adjudication_audit)"
                    )
                frozen_at = max(
                    datetime.fromisoformat(claude_pass.frozen_at),
                    datetime.fromisoformat(sol_pass.frozen_at),
                ).isoformat()
                merged = _merge_agreed_label(
                    claude_label, rubric_version=rubric_version, frozen_at=frozen_at
                )
            _set_at_path(annotations, label_path, merged)

        corpus_records.append(
            {
                "id": record_id,
                "provenance": {
                    **candidate["provenance"],
                    "manual_review": {
                        "reviewer": human_review_record["reviewer"],
                        "reviewed_at": human_review_record["reviewed_at"],
                        "notes": (
                            f"packet {human_review_record['packet_reviewed_path']} "
                            f"(sha256 {human_review_record['packet_reviewed_sha256']})"
                        ),
                    },
                },
                "split": split,
                "fields": dict(candidate["fields"]),
                "annotations": annotations,
            }
        )

    tmp_output_path = output_path.with_name(output_path.name + ".tmp")
    if tmp_output_path.exists():
        raise FreezeBuilderError(f"{tmp_output_path} already exists -- remove it before retrying")
    tmp_output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_output_path.write_text(
        json.dumps(corpus_records, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    try:
        load_corpus(tmp_output_path, known_canonical_ids=known_canonical_ids)
    except CorpusValidationError:
        tmp_output_path.unlink()
        raise
    if output_path.exists():
        tmp_output_path.unlink()
        raise FreezeBuilderError(f"{output_path} already exists -- refusing to overwrite")
    tmp_output_path.rename(output_path)
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest_parser = subparsers.add_parser(
        "manifest", help="print the canonical common-source-packet manifest and hash"
    )
    manifest_parser.add_argument("--salvage-path", type=Path, default=DEFAULT_SALVAGE_PATH)
    manifest_parser.add_argument("--taxonomy-path", type=Path, default=DEFAULT_TAXONOMY_PATH)
    manifest_parser.add_argument("--rubric-path", type=Path, default=DEFAULT_RUBRIC_PATH)
    manifest_parser.add_argument("--rubric-version", default=RUBRIC_VERSION)

    build_parser = subparsers.add_parser("build", help="freeze the corpus from validated evidence")
    build_parser.add_argument("--salvage-path", type=Path, default=DEFAULT_SALVAGE_PATH)
    build_parser.add_argument("--taxonomy-path", type=Path, default=DEFAULT_TAXONOMY_PATH)
    build_parser.add_argument("--rubric-path", type=Path, default=DEFAULT_RUBRIC_PATH)
    build_parser.add_argument("--rubric-version", default=RUBRIC_VERSION)
    build_parser.add_argument("--pass-claude-path", type=Path, required=True)
    build_parser.add_argument("--pass-sol-path", type=Path, required=True)
    build_parser.add_argument("--adjudication-audit-path", type=Path, required=True)
    build_parser.add_argument("--output-path", type=Path, default=DEFAULT_CORPUS_OUTPUT_PATH)

    args = parser.parse_args(argv)
    if args.command == "manifest":
        manifest, digest = compute_source_packet_hash(
            salvage_path=args.salvage_path,
            taxonomy_path=args.taxonomy_path,
            rubric_path=args.rubric_path,
            rubric_version=args.rubric_version,
        )
        print(json.dumps({**manifest, "source_packet_hash": digest}, indent=2, sort_keys=True))
        return 0

    try:
        output_path = build_corpus(
            salvage_path=args.salvage_path,
            taxonomy_path=args.taxonomy_path,
            rubric_path=args.rubric_path,
            rubric_version=args.rubric_version,
            pass_claude_path=args.pass_claude_path,
            pass_sol_path=args.pass_sol_path,
            adjudication_audit_path=args.adjudication_audit_path,
            output_path=args.output_path,
        )
    except (FreezeBuilderError, CorpusValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"corpus written: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
