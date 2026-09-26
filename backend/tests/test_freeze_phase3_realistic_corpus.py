from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.freeze_phase3_realistic_corpus import (
    AnnotationPass,
    FreezeBuilderError,
    _artifact_key,
    _compute_required_audit_keys,
    _label_paths,
    build_corpus,
    compute_source_packet_hash,
    deterministic_split,
    load_adjudication_audit,
    load_annotation_pass,
)

_TS = "2026-09-27T00:00:00+00:00"
_TS_LATER = "2026-09-27T01:00:00+00:00"
_CANONICAL_IDS = frozenset({"alpha", "beta"})


# ---------------------------------------------------------------------------
# Synthetic fixture builders -- no real posting text anywhere in this file.
# ---------------------------------------------------------------------------
def _write_taxonomy(tmp_path: Path) -> Path:
    path = tmp_path / "skills.yaml"
    path.write_text(
        "schema_version: 1\n"
        "entries:\n"
        "  - canonical_id: alpha\n"
        "    display_name: Alpha\n"
        "    aliases: []\n"
        "  - canonical_id: beta\n"
        "    display_name: Beta\n"
        "    aliases: []\n",
        encoding="utf-8",
    )
    return path


def _write_rubric(tmp_path: Path, *, version: str = "1.0.0", name: str = "rubric.md") -> Path:
    path = tmp_path / name
    path.write_text(f"rubric_version: {version}\nsynthetic test rubric\n", encoding="utf-8")
    return path


def _candidate(
    *, board_token: str, job_id: str, employer: str, status: str = "retain"
) -> dict[str, Any]:
    return {
        "review_number": 1,
        "board_token": board_token,
        "job_id": job_id,
        "employer": employer,
        "proposed_disposition": "retain",
        "proposed_disposition_notes": "synthetic",
        "provenance": {
            "provider": "greenhouse",
            "employer": employer,
            "template_family": "unknown",
            "capture": {
                "board_token": board_token,
                "job_id": job_id,
                "accessed_at": _TS,
                "capture_method": "fetch_greenhouse_evaluation_postings.py",
            },
            "sanitization_lineage": "manually reviewed",
            "origin": "sanitized_capture",
        },
        "fields": {
            "title": "Synthetic Engineer",
            "description": "A synthetic description.",
            "location_raw": "Remote",
            "compensation_text": None,
        },
        "human_decision": {"status": status, "notes": "synthetic"},
    }


def _write_salvage(
    tmp_path: Path, candidates: list[dict[str, Any]], *, name: str = "salvage.json"
) -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps(
            {
                "derivation": {"synthetic": True},
                "candidates": candidates,
                "human_review_record": {
                    "reviewer": "user",
                    "reviewed_at": _TS,
                    "packet_reviewed_path": "synthetic/packet.md",
                    "packet_reviewed_sha256": "0" * 64,
                    "summary": "synthetic",
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _scalar_label(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "outcome": "absent",
        "expected_value": None,
        "expected_provenance": "unavailable",
    }
    base.update(overrides)
    return base


def _skill_label(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"outcome": "absent"}
    base.update(overrides)
    return base


def _record_annotations(
    overrides: dict[tuple[str, ...], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    overrides = overrides or {}

    def get(path: tuple[str, ...], default: dict[str, Any]) -> dict[str, Any]:
        return overrides.get(path, default)

    return {
        "remote_type": get(("remote_type",), _scalar_label()),
        "employment_type": get(("employment_type",), _scalar_label()),
        "seniority": get(("seniority",), _scalar_label()),
        "experience": {
            "minimum": get(("experience", "minimum"), _scalar_label()),
            "maximum": get(("experience", "maximum"), _scalar_label()),
        },
        "salary": {
            "minimum": get(("salary", "minimum"), _scalar_label()),
            "maximum": get(("salary", "maximum"), _scalar_label()),
            "currency": get(("salary", "currency"), _scalar_label()),
            "period": get(("salary", "period"), _scalar_label()),
        },
        "location": {
            "city": get(("location", "city"), _scalar_label()),
            "state": get(("location", "state"), _scalar_label()),
            "country": get(("location", "country"), _scalar_label()),
            "postal_code": get(("location", "postal_code"), _scalar_label()),
        },
        "skills": {
            "alpha": get(("skills", "alpha"), _skill_label()),
            "beta": get(("skills", "beta"), _skill_label()),
        },
    }


def _write_pass(
    tmp_path: Path,
    name: str,
    *,
    annotator_role: str,
    source_packet_hash: str,
    records: dict[str, Any],
    rubric_version: str = "1.0.0",
    frozen_at: str = _TS,
    schema_version: str = "1",
) -> Path:
    path = tmp_path / f"pass-{name}.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": schema_version,
                "annotator_role": annotator_role,
                "rubric_version": rubric_version,
                "source_packet_hash": source_packet_hash,
                "frozen_at": frozen_at,
                "records": records,
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_adjudication_audit(
    tmp_path: Path,
    *,
    disagreements: dict[str, Any],
    audited_agreements: dict[str, Any],
    completed_at: str = _TS,
    name: str = "adjudication-audit.json",
) -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "completed_at": completed_at,
                "disagreements": disagreements,
                "audited_agreements": audited_agreements,
            }
        ),
        encoding="utf-8",
    )
    return path


def _auto_audited_agreements(
    required_keys: set[str], *, audited_by: str = "user", audited_at: str = _TS
) -> dict[str, Any]:
    return {
        key: {"audited_by": audited_by, "audited_at": audited_at, "result": "confirmed"}
        for key in required_keys
    }


# ---------------------------------------------------------------------------
# compute_source_packet_hash
# ---------------------------------------------------------------------------
def test_compute_source_packet_hash_is_deterministic(tmp_path: Path) -> None:
    salvage_path = _write_salvage(tmp_path, [_candidate(board_token="a", job_id="1", employer="A")])
    taxonomy_path = _write_taxonomy(tmp_path)
    rubric_path = _write_rubric(tmp_path)
    manifest_1, digest_1 = compute_source_packet_hash(
        salvage_path=salvage_path,
        taxonomy_path=taxonomy_path,
        rubric_path=rubric_path,
        rubric_version="1.0.0",
    )
    manifest_2, digest_2 = compute_source_packet_hash(
        salvage_path=salvage_path,
        taxonomy_path=taxonomy_path,
        rubric_path=rubric_path,
        rubric_version="1.0.0",
    )
    assert digest_1 == digest_2
    assert manifest_1 == manifest_2
    assert len(digest_1) == 64


def test_compute_source_packet_hash_changes_if_rubric_content_changes(tmp_path: Path) -> None:
    salvage_path = _write_salvage(tmp_path, [_candidate(board_token="a", job_id="1", employer="A")])
    taxonomy_path = _write_taxonomy(tmp_path)
    rubric_path = _write_rubric(tmp_path)
    _, digest_before = compute_source_packet_hash(
        salvage_path=salvage_path,
        taxonomy_path=taxonomy_path,
        rubric_path=rubric_path,
        rubric_version="1.0.0",
    )
    rubric_path.write_text("rubric_version: 1.0.0\nchanged\n", encoding="utf-8")
    _, digest_after = compute_source_packet_hash(
        salvage_path=salvage_path,
        taxonomy_path=taxonomy_path,
        rubric_path=rubric_path,
        rubric_version="1.0.0",
    )
    assert digest_before != digest_after


def test_compute_source_packet_hash_changes_if_rubric_version_changes(tmp_path: Path) -> None:
    salvage_path = _write_salvage(tmp_path, [_candidate(board_token="a", job_id="1", employer="A")])
    taxonomy_path = _write_taxonomy(tmp_path)
    rubric_path = _write_rubric(tmp_path)
    _, digest_v1 = compute_source_packet_hash(
        salvage_path=salvage_path,
        taxonomy_path=taxonomy_path,
        rubric_path=rubric_path,
        rubric_version="1.0.0",
    )
    _, digest_v2 = compute_source_packet_hash(
        salvage_path=salvage_path,
        taxonomy_path=taxonomy_path,
        rubric_path=rubric_path,
        rubric_version="1.1.0",
    )
    assert digest_v1 != digest_v2


# ---------------------------------------------------------------------------
# load_annotation_pass
# ---------------------------------------------------------------------------
def _base_pass_kwargs(source_packet_hash: str) -> dict[str, Any]:
    return dict(
        expected_annotator_role="claude",
        expected_record_ids=frozenset({"a:1"}),
        known_canonical_ids=_CANONICAL_IDS,
        expected_rubric_version="1.0.0",
        expected_source_packet_hash=source_packet_hash,
    )


def test_load_annotation_pass_accepts_a_well_formed_pass(tmp_path: Path) -> None:
    path = _write_pass(
        tmp_path,
        "claude",
        annotator_role="claude",
        source_packet_hash="h",
        records={"a:1": _record_annotations()},
    )
    loaded = load_annotation_pass(path, **_base_pass_kwargs("h"))
    assert loaded.annotator_role == "claude"
    assert set(loaded.records) == {"a:1"}


def test_load_annotation_pass_rejects_wrong_annotator_role(tmp_path: Path) -> None:
    path = _write_pass(
        tmp_path,
        "sol",
        annotator_role="sol",
        source_packet_hash="h",
        records={"a:1": _record_annotations()},
    )
    with pytest.raises(FreezeBuilderError, match="annotator_role must be"):
        load_annotation_pass(path, **_base_pass_kwargs("h"))


def test_load_annotation_pass_rejects_wrong_source_packet_hash(tmp_path: Path) -> None:
    path = _write_pass(
        tmp_path,
        "claude",
        annotator_role="claude",
        source_packet_hash="wrong",
        records={"a:1": _record_annotations()},
    )
    with pytest.raises(FreezeBuilderError, match="source_packet_hash"):
        load_annotation_pass(path, **_base_pass_kwargs("h"))


def test_load_annotation_pass_rejects_wrong_rubric_version(tmp_path: Path) -> None:
    path = _write_pass(
        tmp_path,
        "claude",
        annotator_role="claude",
        source_packet_hash="h",
        records={"a:1": _record_annotations()},
        rubric_version="0.9.0",
    )
    with pytest.raises(FreezeBuilderError, match="rubric_version"):
        load_annotation_pass(path, **_base_pass_kwargs("h"))


def test_load_annotation_pass_rejects_missing_record_id(tmp_path: Path) -> None:
    path = _write_pass(
        tmp_path, "claude", annotator_role="claude", source_packet_hash="h", records={}
    )
    with pytest.raises(FreezeBuilderError, match="records must declare exactly"):
        load_annotation_pass(path, **_base_pass_kwargs("h"))


def test_load_annotation_pass_rejects_extra_record_id(tmp_path: Path) -> None:
    path = _write_pass(
        tmp_path,
        "claude",
        annotator_role="claude",
        source_packet_hash="h",
        records={"a:1": _record_annotations(), "a:2": _record_annotations()},
    )
    with pytest.raises(FreezeBuilderError, match="records must declare exactly"):
        load_annotation_pass(path, **_base_pass_kwargs("h"))


def test_load_annotation_pass_rejects_extra_key_in_scalar_label(tmp_path: Path) -> None:
    """A smuggled-in field (e.g. actual parser output) must be rejected --
    the raw label object is closed to exactly outcome/expected_value/
    expected_provenance."""
    annotations = _record_annotations(
        {("remote_type",): {**_scalar_label(), "actual_value": "remote"}}
    )
    path = _write_pass(
        tmp_path,
        "claude",
        annotator_role="claude",
        source_packet_hash="h",
        records={"a:1": annotations},
    )
    with pytest.raises(FreezeBuilderError, match="must declare exactly"):
        load_annotation_pass(path, **_base_pass_kwargs("h"))


def test_load_annotation_pass_rejects_extra_key_in_skill_label(tmp_path: Path) -> None:
    annotations = _record_annotations({("skills", "alpha"): {"outcome": "absent", "extra": 1}})
    path = _write_pass(
        tmp_path,
        "claude",
        annotator_role="claude",
        source_packet_hash="h",
        records={"a:1": annotations},
    )
    with pytest.raises(FreezeBuilderError, match="must declare exactly"):
        load_annotation_pass(path, **_base_pass_kwargs("h"))


def test_load_annotation_pass_rejects_present_supported_with_null_value(tmp_path: Path) -> None:
    annotations = _record_annotations(
        {("remote_type",): _scalar_label(outcome="present_supported")}
    )
    path = _write_pass(
        tmp_path,
        "claude",
        annotator_role="claude",
        source_packet_hash="h",
        records={"a:1": annotations},
    )
    with pytest.raises(FreezeBuilderError, match="expected_value must be non-null"):
        load_annotation_pass(path, **_base_pass_kwargs("h"))


def test_load_annotation_pass_rejects_disallowed_provenance_for_present_supported(
    tmp_path: Path,
) -> None:
    annotations = _record_annotations(
        {
            ("remote_type",): _scalar_label(
                outcome="present_supported", expected_value="remote", expected_provenance="derived"
            )
        }
    )
    path = _write_pass(
        tmp_path,
        "claude",
        annotator_role="claude",
        source_packet_hash="h",
        records={"a:1": annotations},
    )
    with pytest.raises(FreezeBuilderError, match="expected_provenance must be"):
        load_annotation_pass(path, **_base_pass_kwargs("h"))


def test_load_annotation_pass_rejects_missing_composite_component(tmp_path: Path) -> None:
    annotations = _record_annotations()
    del annotations["salary"]["currency"]
    path = _write_pass(
        tmp_path,
        "claude",
        annotator_role="claude",
        source_packet_hash="h",
        records={"a:1": annotations},
    )
    with pytest.raises(FreezeBuilderError, match="is missing"):
        load_annotation_pass(path, **_base_pass_kwargs("h"))


def test_load_annotation_pass_rejects_unknown_skill_id(tmp_path: Path) -> None:
    annotations = _record_annotations()
    annotations["skills"]["gamma"] = _skill_label()
    path = _write_pass(
        tmp_path,
        "claude",
        annotator_role="claude",
        source_packet_hash="h",
        records={"a:1": annotations},
    )
    with pytest.raises(FreezeBuilderError, match="skills must declare exactly"):
        load_annotation_pass(path, **_base_pass_kwargs("h"))


# ---------------------------------------------------------------------------
# _compute_required_audit_keys / load_adjudication_audit
# ---------------------------------------------------------------------------
def _passes_agreeing_on_everything(record_ids: list[str]) -> tuple[AnnotationPass, AnnotationPass]:
    records = {rid: _record_annotations() for rid in record_ids}
    claude_pass = AnnotationPass(
        annotator_role="claude",
        rubric_version="1.0.0",
        source_packet_hash="h",
        frozen_at=_TS,
        records=records,
    )
    sol_pass = AnnotationPass(
        annotator_role="sol",
        rubric_version="1.0.0",
        source_packet_hash="h",
        frozen_at=_TS_LATER,
        records=records,
    )
    return claude_pass, sol_pass


def test_required_audit_keys_include_every_present_supported_agreement() -> None:
    records = {
        "a:1": _record_annotations(
            {
                ("remote_type",): _scalar_label(
                    outcome="present_supported",
                    expected_value="remote",
                    expected_provenance="parsed_description",
                )
            }
        )
    }
    claude_pass = AnnotationPass("claude", "1.0.0", "h", _TS, records)
    sol_pass = AnnotationPass("sol", "1.0.0", "h", _TS, records)
    required, agreements = _compute_required_audit_keys(
        expected_record_ids=frozenset({"a:1"}),
        employer_by_record_id={"a:1": "A"},
        claude_pass=claude_pass,
        sol_pass=sol_pass,
        label_paths=_label_paths(_CANONICAL_IDS),
    )
    assert _artifact_key("a:1", ("remote_type",)) in required
    assert _artifact_key("a:1", ("remote_type",)) in agreements


def test_required_audit_keys_pick_smallest_id_per_non_supported_stratum() -> None:
    claude_pass, sol_pass = _passes_agreeing_on_everything(["a:2", "a:1", "a:3"])
    required, _agreements = _compute_required_audit_keys(
        expected_record_ids=frozenset({"a:1", "a:2", "a:3"}),
        employer_by_record_id={"a:1": "A", "a:2": "A", "a:3": "A"},
        claude_pass=claude_pass,
        sol_pass=sol_pass,
        label_paths=_label_paths(_CANONICAL_IDS),
    )
    key = _artifact_key("a:1", ("remote_type",))  # "a:1" < "a:2" < "a:3" lexicographically
    assert key in required
    assert _artifact_key("a:2", ("remote_type",)) not in required
    assert _artifact_key("a:3", ("remote_type",)) not in required


def test_required_audit_keys_treat_different_employers_as_separate_strata() -> None:
    claude_pass, sol_pass = _passes_agreeing_on_everything(["a:1", "b:1"])
    required, _agreements = _compute_required_audit_keys(
        expected_record_ids=frozenset({"a:1", "b:1"}),
        employer_by_record_id={"a:1": "A", "b:1": "B"},
        claude_pass=claude_pass,
        sol_pass=sol_pass,
        label_paths=_label_paths(_CANONICAL_IDS),
    )
    assert _artifact_key("a:1", ("remote_type",)) in required
    assert _artifact_key("b:1", ("remote_type",)) in required


def _all_label_paths() -> list[tuple[str, ...]]:
    return _label_paths(_CANONICAL_IDS)


def test_load_adjudication_audit_accepts_a_valid_artifact(tmp_path: Path) -> None:
    claude_pass, sol_pass = _passes_agreeing_on_everything(["a:1"])
    required, _agreements = _compute_required_audit_keys(
        expected_record_ids=frozenset({"a:1"}),
        employer_by_record_id={"a:1": "A"},
        claude_pass=claude_pass,
        sol_pass=sol_pass,
        label_paths=_all_label_paths(),
    )
    path = _write_adjudication_audit(
        tmp_path, disagreements={}, audited_agreements=_auto_audited_agreements(required)
    )
    result = load_adjudication_audit(
        path,
        expected_record_ids=frozenset({"a:1"}),
        employer_by_record_id={"a:1": "A"},
        claude_pass=claude_pass,
        sol_pass=sol_pass,
        known_canonical_ids=_CANONICAL_IDS,
    )
    assert result.disagreements == {}


def test_load_adjudication_audit_rejects_missing_required_audit(tmp_path: Path) -> None:
    claude_pass, sol_pass = _passes_agreeing_on_everything(["a:1"])
    path = _write_adjudication_audit(tmp_path, disagreements={}, audited_agreements={})
    with pytest.raises(FreezeBuilderError, match="required agreement audit"):
        load_adjudication_audit(
            path,
            expected_record_ids=frozenset({"a:1"}),
            employer_by_record_id={"a:1": "A"},
            claude_pass=claude_pass,
            sol_pass=sol_pass,
            known_canonical_ids=_CANONICAL_IDS,
        )


def test_load_adjudication_audit_rejects_genuine_disagreement_with_no_adjudication(
    tmp_path: Path,
) -> None:
    claude_records = {"a:1": _record_annotations()}
    sol_records = {
        "a:1": _record_annotations(
            {
                ("remote_type",): _scalar_label(
                    outcome="present_supported",
                    expected_value="remote",
                    expected_provenance="parsed_description",
                )
            }
        )
    }
    claude_pass = AnnotationPass("claude", "1.0.0", "h", _TS, claude_records)
    sol_pass = AnnotationPass("sol", "1.0.0", "h", _TS, sol_records)
    path = _write_adjudication_audit(tmp_path, disagreements={}, audited_agreements={})
    with pytest.raises(FreezeBuilderError, match="no recorded adjudication"):
        load_adjudication_audit(
            path,
            expected_record_ids=frozenset({"a:1"}),
            employer_by_record_id={"a:1": "A"},
            claude_pass=claude_pass,
            sol_pass=sol_pass,
            known_canonical_ids=_CANONICAL_IDS,
        )


def test_load_adjudication_audit_rejects_overturned_without_matching_disagreement(
    tmp_path: Path,
) -> None:
    claude_pass, sol_pass = _passes_agreeing_on_everything(["a:1"])
    required, _agreements = _compute_required_audit_keys(
        expected_record_ids=frozenset({"a:1"}),
        employer_by_record_id={"a:1": "A"},
        claude_pass=claude_pass,
        sol_pass=sol_pass,
        label_paths=_all_label_paths(),
    )
    audited = _auto_audited_agreements(required)
    some_key = next(iter(required))
    audited[some_key] = {"audited_by": "user", "audited_at": _TS, "result": "overturned"}
    path = _write_adjudication_audit(tmp_path, disagreements={}, audited_agreements=audited)
    with pytest.raises(FreezeBuilderError, match="overturned"):
        load_adjudication_audit(
            path,
            expected_record_ids=frozenset({"a:1"}),
            employer_by_record_id={"a:1": "A"},
            claude_pass=claude_pass,
            sol_pass=sol_pass,
            known_canonical_ids=_CANONICAL_IDS,
        )


def test_load_adjudication_audit_rejects_confirmed_entry_also_recorded_as_disagreement(
    tmp_path: Path,
) -> None:
    claude_pass, sol_pass = _passes_agreeing_on_everything(["a:1"])
    required, _agreements = _compute_required_audit_keys(
        expected_record_ids=frozenset({"a:1"}),
        employer_by_record_id={"a:1": "A"},
        claude_pass=claude_pass,
        sol_pass=sol_pass,
        label_paths=_all_label_paths(),
    )
    audited = _auto_audited_agreements(required)
    some_key = _artifact_key("a:1", ("remote_type",))
    assert some_key in required  # a lone record is its own smallest-id stratum
    disagreements = {
        some_key: {
            "adjudication": {
                "final_outcome": "present_supported",
                "final_value": "remote",
                "final_provenance": "parsed_description",
                "adjudicated_by": "user",
                "adjudicated_at": _TS,
            }
        }
    }
    path = _write_adjudication_audit(
        tmp_path, disagreements=disagreements, audited_agreements=audited
    )
    with pytest.raises(FreezeBuilderError, match="confirmed"):
        load_adjudication_audit(
            path,
            expected_record_ids=frozenset({"a:1"}),
            employer_by_record_id={"a:1": "A"},
            claude_pass=claude_pass,
            sol_pass=sol_pass,
            known_canonical_ids=_CANONICAL_IDS,
        )


def test_load_adjudication_audit_rejects_overturned_resolving_to_the_same_agreed_value(
    tmp_path: Path,
) -> None:
    claude_pass, sol_pass = _passes_agreeing_on_everything(["a:1"])
    required, _agreements = _compute_required_audit_keys(
        expected_record_ids=frozenset({"a:1"}),
        employer_by_record_id={"a:1": "A"},
        claude_pass=claude_pass,
        sol_pass=sol_pass,
        label_paths=_all_label_paths(),
    )
    audited = _auto_audited_agreements(required)
    key = _artifact_key("a:1", ("remote_type",))
    audited[key] = {"audited_by": "user", "audited_at": _TS, "result": "overturned"}
    disagreements = {
        key: {
            "adjudication": {
                "final_outcome": "absent",
                "final_value": None,
                "final_provenance": "unavailable",
                "adjudicated_by": "user",
                "adjudicated_at": _TS,
            }
        }
    }
    path = _write_adjudication_audit(
        tmp_path, disagreements=disagreements, audited_agreements=audited
    )
    with pytest.raises(FreezeBuilderError, match="already agreed on"):
        load_adjudication_audit(
            path,
            expected_record_ids=frozenset({"a:1"}),
            employer_by_record_id={"a:1": "A"},
            claude_pass=claude_pass,
            sol_pass=sol_pass,
            known_canonical_ids=_CANONICAL_IDS,
        )


# ---------------------------------------------------------------------------
# deterministic_split
# ---------------------------------------------------------------------------
def test_deterministic_split_picks_the_lexicographically_last_employer_as_holdout() -> None:
    dev, holdout = deterministic_split(frozenset({"Anthropic", "Discord", "GitLab"}))
    assert holdout == "GitLab"
    assert dev == frozenset({"Anthropic", "Discord"})


def test_deterministic_split_with_two_employers() -> None:
    dev, holdout = deterministic_split(frozenset({"Ainbow", "Bcorp"}))
    assert holdout == "Bcorp"
    assert dev == frozenset({"Ainbow"})


def test_deterministic_split_rejects_fewer_than_two_employers() -> None:
    with pytest.raises(FreezeBuilderError, match="at least two"):
        deterministic_split(frozenset({"OnlyOne"}))


# ---------------------------------------------------------------------------
# build_corpus -- end to end and required failure modes
# ---------------------------------------------------------------------------
def _build_valid_fixture_set(
    tmp_path: Path,
) -> tuple[Path, str, Path, Path, Path, Path, Path]:
    """Two "Ainbow" records (dev) and one "Bcorp" record (holdout); every
    label agrees between passes except `ainbow:1`'s `employment_type`,
    which is a genuine disagreement resolved by adjudication in Sol's
    favor. Returns (salvage_path, salvage_sha256, taxonomy_path, rubric_path,
    pass_claude_path, pass_sol_path, adjudication_audit_path)."""
    candidates = [
        _candidate(board_token="ainbow", job_id="1", employer="Ainbow"),
        _candidate(board_token="ainbow", job_id="2", employer="Ainbow"),
        _candidate(board_token="bcorp", job_id="1", employer="Bcorp"),
    ]
    salvage_path = _write_salvage(tmp_path, candidates)
    salvage_sha256 = hashlib.sha256(salvage_path.read_bytes()).hexdigest()
    taxonomy_path = _write_taxonomy(tmp_path)
    rubric_path = _write_rubric(tmp_path)
    _manifest, source_packet_hash = compute_source_packet_hash(
        salvage_path=salvage_path,
        taxonomy_path=taxonomy_path,
        rubric_path=rubric_path,
        rubric_version="1.0.0",
    )

    record_ids = ["ainbow:1", "ainbow:2", "bcorp:1"]
    claude_records = {rid: _record_annotations() for rid in record_ids}
    sol_records = {rid: _record_annotations() for rid in record_ids}
    sol_records["ainbow:1"] = _record_annotations(
        {
            ("employment_type",): _scalar_label(
                outcome="present_supported",
                expected_value="full_time",
                expected_provenance="parsed_description",
            )
        }
    )

    claude_pass = AnnotationPass("claude", "1.0.0", source_packet_hash, _TS, claude_records)
    sol_pass = AnnotationPass("sol", "1.0.0", source_packet_hash, _TS_LATER, sol_records)
    employer_by_record_id = {"ainbow:1": "Ainbow", "ainbow:2": "Ainbow", "bcorp:1": "Bcorp"}
    required, _agreements = _compute_required_audit_keys(
        expected_record_ids=frozenset(record_ids),
        employer_by_record_id=employer_by_record_id,
        claude_pass=claude_pass,
        sol_pass=sol_pass,
        label_paths=_all_label_paths(),
    )
    audited_agreements = _auto_audited_agreements(required)
    disagreements = {
        _artifact_key("ainbow:1", ("employment_type",)): {
            "adjudication": {
                "final_outcome": "present_supported",
                "final_value": "full_time",
                "final_provenance": "parsed_description",
                "adjudicated_by": "user",
                "adjudicated_at": _TS,
            }
        }
    }
    adjudication_audit_path = _write_adjudication_audit(
        tmp_path, disagreements=disagreements, audited_agreements=audited_agreements
    )
    pass_claude_path = _write_pass(
        tmp_path,
        "claude",
        annotator_role="claude",
        source_packet_hash=source_packet_hash,
        records=claude_records,
        frozen_at=_TS,
    )
    pass_sol_path = _write_pass(
        tmp_path,
        "sol",
        annotator_role="sol",
        source_packet_hash=source_packet_hash,
        records=sol_records,
        frozen_at=_TS_LATER,
    )
    return (
        salvage_path,
        salvage_sha256,
        taxonomy_path,
        rubric_path,
        pass_claude_path,
        pass_sol_path,
        adjudication_audit_path,
    )


def test_build_corpus_end_to_end(tmp_path: Path) -> None:
    (
        salvage_path,
        salvage_sha256,
        taxonomy_path,
        rubric_path,
        pass_claude_path,
        pass_sol_path,
        adjudication_audit_path,
    ) = _build_valid_fixture_set(tmp_path)
    output_path = tmp_path / "output" / "corpus.json"

    result_path = build_corpus(
        salvage_path=salvage_path,
        expected_salvage_sha256=salvage_sha256,
        taxonomy_path=taxonomy_path,
        rubric_path=rubric_path,
        rubric_version="1.0.0",
        pass_claude_path=pass_claude_path,
        pass_sol_path=pass_sol_path,
        adjudication_audit_path=adjudication_audit_path,
        output_path=output_path,
    )

    assert result_path == output_path
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(written) == 3
    splits = {r["id"]: r["split"] for r in written}
    assert splits == {"ainbow:1": "dev", "ainbow:2": "dev", "bcorp:1": "holdout"}

    adjudicated = next(r for r in written if r["id"] == "ainbow:1")
    employment = adjudicated["annotations"]["employment_type"]
    assert employment["annotator_role"] == "adjudicated:user"
    assert employment["expected_value"] == "full_time"
    assert employment["disagreement"]["second_annotation"]["annotator_role"] == "claude"

    agreed = next(r for r in written if r["id"] == "ainbow:2")
    assert agreed["annotations"]["remote_type"]["annotator_role"] == "claude+sol:agreed"
    assert "disagreement" not in agreed["annotations"]["remote_type"]

    assert adjudicated["provenance"]["manual_review"]["reviewer"] == "user"


def test_build_corpus_refuses_to_overwrite_an_existing_output(tmp_path: Path) -> None:
    (
        salvage_path,
        salvage_sha256,
        taxonomy_path,
        rubric_path,
        pass_claude_path,
        pass_sol_path,
        adjudication_audit_path,
    ) = _build_valid_fixture_set(tmp_path)
    output_path = tmp_path / "output" / "corpus.json"
    build_corpus(
        salvage_path=salvage_path,
        expected_salvage_sha256=salvage_sha256,
        taxonomy_path=taxonomy_path,
        rubric_path=rubric_path,
        rubric_version="1.0.0",
        pass_claude_path=pass_claude_path,
        pass_sol_path=pass_sol_path,
        adjudication_audit_path=adjudication_audit_path,
        output_path=output_path,
    )
    with pytest.raises(FreezeBuilderError, match="already exists"):
        build_corpus(
            salvage_path=salvage_path,
            expected_salvage_sha256=salvage_sha256,
            taxonomy_path=taxonomy_path,
            rubric_path=rubric_path,
            rubric_version="1.0.0",
            pass_claude_path=pass_claude_path,
            pass_sol_path=pass_sol_path,
            adjudication_audit_path=adjudication_audit_path,
            output_path=output_path,
        )


def test_build_corpus_rejects_a_salvage_hash_mismatch(tmp_path: Path) -> None:
    (
        salvage_path,
        _salvage_sha256,
        taxonomy_path,
        rubric_path,
        pass_claude_path,
        pass_sol_path,
        adjudication_audit_path,
    ) = _build_valid_fixture_set(tmp_path)
    with pytest.raises(FreezeBuilderError, match="does not match the expected"):
        build_corpus(
            salvage_path=salvage_path,
            expected_salvage_sha256="0" * 64,
            taxonomy_path=taxonomy_path,
            rubric_path=rubric_path,
            rubric_version="1.0.0",
            pass_claude_path=pass_claude_path,
            pass_sol_path=pass_sol_path,
            adjudication_audit_path=adjudication_audit_path,
            output_path=tmp_path / "output" / "corpus.json",
        )


def test_build_corpus_rejects_a_non_retained_candidate(tmp_path: Path) -> None:
    candidates = [
        _candidate(board_token="ainbow", job_id="1", employer="Ainbow"),
        _candidate(board_token="bcorp", job_id="1", employer="Bcorp", status="reject"),
    ]
    salvage_path = _write_salvage(tmp_path, candidates)
    salvage_sha256 = hashlib.sha256(salvage_path.read_bytes()).hexdigest()
    taxonomy_path = _write_taxonomy(tmp_path)
    rubric_path = _write_rubric(tmp_path)
    with pytest.raises(FreezeBuilderError, match="not retained"):
        build_corpus(
            salvage_path=salvage_path,
            expected_salvage_sha256=salvage_sha256,
            taxonomy_path=taxonomy_path,
            rubric_path=rubric_path,
            rubric_version="1.0.0",
            pass_claude_path=tmp_path / "unused-claude.json",
            pass_sol_path=tmp_path / "unused-sol.json",
            adjudication_audit_path=tmp_path / "unused-audit.json",
            output_path=tmp_path / "output" / "corpus.json",
        )
