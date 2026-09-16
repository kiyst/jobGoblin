"""Review-chain validation for Workflow v3.2 (`C -> A -> R`, merge at `M`,
and durable post-merge evidence publication at `Q`).

Distinct from `check_handoff.py` (which validates the metadata block's own
structure, in isolation) -- this module validates the *relational* facts
that require Git plumbing and the receipt/artifact files themselves: that
`A` is a direct child of `C`, `R` a direct child of `A`, `M` a merge whose
second parent is `R`, `Q` a direct child of `M`; that every commit's
published metadata references a receipt/artifact that genuinely exists
and is genuinely well-formed; and that every transition changed *only*
the specific, named content it is permitted to -- never taken on prose
alone.

**Record validity vs. merge eligibility** are deliberately distinct:
`validate_c_a_r_chain` accepts a well-formed `changes_requested` record
(record validity); `check_merge_eligibility` additionally requires
`verdict: approved` (merge eligibility). A clean receipt never implies an
approved verdict, and an approved verdict is never accepted without a
clean, approval-eligible receipt.

**Outer detached-checkout launcher**: `run_via_detached_checkout` creates
a disposable checkout at a target commit and re-invokes *that checkout's
own* `scripts/check_review.py --internal-validate ...` as a subprocess --
the code that performs validation is the code actually committed at that
commit, never the caller's in-process copy. `main()` implements the
`--internal-validate` entry point this launcher calls.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from scripts import check_handoff as ch
from scripts import verification_receipts as vr
from scripts import verification_scope as vs
from scripts import verification_worktree as vw

REPO_ROOT = Path(__file__).resolve().parents[2]

_REVIEW_METADATA_BLOCK_RE = re.compile(r"```workflow-review-metadata\n(.*?)\n```", re.DOTALL)
_ESCALATION_BLOCK_RE = re.compile(r"```workflow-escalation-metadata\n(.*?)\n```", re.DOTALL)
_METADATA_BLOCK_RE = re.compile(r"```workflow-metadata\n.*?\n```", re.DOTALL)
_ITERATION_RE = re.compile(r"^## Iteration \d+\s*$", re.MULTILINE)

_REQUIRED_REVIEW_FIELDS = (
    "schema_version",
    "slice_id",
    "risk_class",
    "reviewer",
    "reviewer_role",
    "reviewer_model",
    "reviewed_at",
    "candidate_sha",
    "publication_commit_sha",
    "receipt_path",
    "receipt_id",
    "gate",
    "verdict",
    "findings",
)
_REQUIRED_ESCALATION_FIELDS = (
    "schema_version",
    "slice_id",
    "reviewer",
    "reviewer_model",
    "reviewed_at",
    "candidate_sha",
    "verdict",
    "findings",
    "trigger",
)
_VALID_ESCALATION_TRIGGERS = frozenset(
    {
        "identity_security_concurrency_destructive_live_provider",
        "disputed_finding",
        "user_authorized_phase_gate",
        "scheduled_equal_effort_benchmark",
    }
)
_VALID_REVIEWER_ROLES = frozenset({"primary", "escalation"})
_VALID_VERDICTS = frozenset({"approved", "changes_requested"})
_REQUIRED_PRIMARY_REVIEWER_MODEL = "Sol Medium"
_EXECUTABLE_SLICE_KINDS = frozenset({"parser", "tooling"})
_SUPPORTED_REVIEW_SCHEMA_VERSION = "2"
_SUPPORTED_ESCALATION_SCHEMA_VERSION = "2"
_SUPPORTED_POST_MERGE_ARTIFACT_SCHEMA_VERSION = "1"

_REQUIRED_POST_MERGE_ARTIFACT_FIELDS = (
    "schema_version",
    "kind",
    "slice_id",
    "base_sha",
    "candidate_sha",
    "publication_commit_sha",
    "review_commit_sha",
    "original_receipt_id",
    "original_receipt_path",
    "merged_commit",
    "environment_descriptor",
    "coordinator",
    "full_suite",
    "mutation_witnesses",
    "migration_matrix",
    "steps",
    "cleanup",
)


class ReviewValidationError(Exception):
    """A chain-shape, cross-reference, transition-diff, or metadata
    problem -- fails closed, never a warning."""


def _git(args: list[str], cwd: Path = REPO_ROOT) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={REPO_ROOT.as_posix()}", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ReviewValidationError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _name_status_lines(a: str, b: str, repo_root: Path) -> list[str]:
    output = _git(["diff", "--name-status", a, b], repo_root)
    return [line for line in output.splitlines() if line.strip()]


def parents_of(commit: str, *, repo_root: Path = REPO_ROOT) -> list[str]:
    output = _git(["rev-parse", f"{commit}^@"], repo_root)
    return [line for line in output.splitlines() if line.strip()]


def require_single_parent(child: str, expected_parent: str, *, label: str, repo_root: Path) -> None:
    parents = parents_of(child, repo_root=repo_root)
    if parents != [expected_parent]:
        raise ReviewValidationError(
            f"{label} ({child}) must have exactly one parent ({expected_parent}); got {parents}"
        )


def require_single_parent_chain(
    candidate_sha: str, publication_sha: str, review_sha: str, *, repo_root: Path = REPO_ROOT
) -> None:
    require_single_parent(publication_sha, candidate_sha, label="A", repo_root=repo_root)
    require_single_parent(review_sha, publication_sha, label="R", repo_root=repo_root)


def read_file_at_commit(commit: str, relative_path: str, *, repo_root: Path = REPO_ROOT) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={REPO_ROOT.as_posix()}",
            "show",
            f"{commit}:{relative_path}",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ReviewValidationError(
            f"could not read {relative_path!r} at {commit}: {result.stderr.strip()}"
        )
    return result.stdout


# ---------------------------------------------------------------------------
# Metadata block extraction and schema validation
# ---------------------------------------------------------------------------


def _latest_iteration_text(handoff_text: str) -> str:
    """Scopes to the newest `## Iteration N` section only -- mirrors
    `check_handoff.py`'s own per-iteration scoping for its metadata-block
    search. A historical review (or escalation) block from an earlier,
    superseded iteration must never be confused with the current one; an
    unscoped whole-file search would find both once a second iteration's
    own `### Work review` exists alongside an earlier iteration's."""
    matches = list(_ITERATION_RE.finditer(handoff_text))
    if not matches:
        raise ReviewValidationError("no '## Iteration N' heading found in docs/LLM_HANDOFF.md")
    return handoff_text[matches[-1].start() :]


def extract_review_metadata_text(handoff_text: str) -> str:
    latest = _latest_iteration_text(handoff_text)
    matches = list(_REVIEW_METADATA_BLOCK_RE.finditer(latest))
    if not matches:
        raise ReviewValidationError("no 'workflow-review-metadata' block found")
    if len(matches) > 1:
        raise ReviewValidationError("more than one 'workflow-review-metadata' block found")
    return matches[0].group(1)


def extract_escalation_blocks(handoff_text: str) -> list[dict[str, str]]:
    latest = _latest_iteration_text(handoff_text)
    return [ch.parse_metadata_fields(m.group(1)) for m in _ESCALATION_BLOCK_RE.finditer(latest)]


def validate_review_metadata_structure(fields: dict[str, str], *, slice_kind: str) -> None:
    """`slice_kind` is the *published* (`A`) commit's own genuinely
    validated `workflow-metadata.slice_kind` -- never read from the review
    block itself (the review schema carries no such field), so a
    dishonest review block can never lower its own reviewer-policy bar."""
    missing = [k for k in _REQUIRED_REVIEW_FIELDS if k not in fields]
    if missing:
        raise ReviewValidationError(f"review metadata missing required field(s): {missing}")
    unknown = [k for k in fields if k not in _REQUIRED_REVIEW_FIELDS]
    if unknown:
        raise ReviewValidationError(f"review metadata declares unrecognized field(s): {unknown}")
    if fields["schema_version"] != _SUPPORTED_REVIEW_SCHEMA_VERSION:
        raise ReviewValidationError(
            f"review metadata 'schema_version' must be {_SUPPORTED_REVIEW_SCHEMA_VERSION!r}, "
            f"got {fields['schema_version']!r}"
        )

    if fields["reviewer_role"] not in _VALID_REVIEWER_ROLES:
        raise ReviewValidationError(
            f"'reviewer_role' must be one of {sorted(_VALID_REVIEWER_ROLES)}, "
            f"got {fields['reviewer_role']!r}"
        )
    _validate_verdict_findings_pair(fields["verdict"], fields["findings"], context="review")

    # Sol Medium is required for the primary review of every Class H
    # proposal *and* every executable (parser/tooling) slice, regardless
    # of risk_class -- not only risk_class == H.
    requires_sol_medium = fields["risk_class"] == "H" or slice_kind in _EXECUTABLE_SLICE_KINDS
    if (
        fields["reviewer_role"] == "primary"
        and requires_sol_medium
        and fields["reviewer_model"] != _REQUIRED_PRIMARY_REVIEWER_MODEL
    ):
        raise ReviewValidationError(
            f"the primary reviewer for Class H or executable (parser/tooling) work must be "
            f"{_REQUIRED_PRIMARY_REVIEWER_MODEL!r}, got {fields['reviewer_model']!r}"
        )


def validate_escalation_metadata_structure(fields: dict[str, str]) -> None:
    missing = [k for k in _REQUIRED_ESCALATION_FIELDS if k not in fields]
    if missing:
        raise ReviewValidationError(f"escalation metadata missing required field(s): {missing}")
    unknown = [k for k in fields if k not in _REQUIRED_ESCALATION_FIELDS]
    if unknown:
        raise ReviewValidationError(
            f"escalation metadata declares unrecognized field(s): {unknown}"
        )
    if fields["schema_version"] != _SUPPORTED_ESCALATION_SCHEMA_VERSION:
        raise ReviewValidationError(
            f"escalation metadata 'schema_version' must be "
            f"{_SUPPORTED_ESCALATION_SCHEMA_VERSION!r}, got {fields['schema_version']!r}"
        )
    if fields["trigger"] not in _VALID_ESCALATION_TRIGGERS:
        raise ReviewValidationError(
            f"'trigger' must be one of {sorted(_VALID_ESCALATION_TRIGGERS)}, "
            f"got {fields['trigger']!r}"
        )
    _validate_verdict_findings_pair(fields["verdict"], fields["findings"], context="escalation")


def extract_and_validate_published_metadata(
    handoff_at_a: str, *, publication_sha: str
) -> dict[str, str]:
    """Parses and structurally validates `A`'s own `workflow-metadata`
    block (reusing `check_handoff.py`'s own validator, never a parallel
    reimplementation of that schema) and asserts it is genuinely
    `state: published` -- a block that merely parses is never trusted as
    correct without this."""
    metadata_text = ch.extract_latest_work_done_metadata_text(handoff_at_a)
    fields = ch.parse_metadata_fields(metadata_text)
    try:
        ch.validate_structure(fields)
    except ch.HandoffValidationError as exc:
        raise ReviewValidationError(
            f"A ({publication_sha}) workflow-metadata block is invalid: {exc}"
        ) from exc
    if fields["state"] != "published":
        raise ReviewValidationError(
            f"A ({publication_sha}) workflow-metadata state must be 'published', "
            f"got {fields['state']!r}"
        )
    return fields


def _cross_check_published_and_review_metadata(
    published_fields: dict[str, str], review_fields: dict[str, str]
) -> None:
    """The published (`A`) and review (`R`) metadata blocks describe the
    same slice from two different commits -- every field they both carry
    must agree exactly; a reviewer's own claims are never trusted over
    what `A` itself published."""
    pairs = (
        ("slice_id", published_fields["slice_id"], review_fields["slice_id"]),
        ("risk_class", published_fields["risk_class"], review_fields["risk_class"]),
        ("candidate_sha", published_fields["candidate_sha"], review_fields["candidate_sha"]),
        ("gate", published_fields["executed_gate"], review_fields["gate"]),
        ("receipt_id", published_fields["receipt_id"], review_fields["receipt_id"]),
        ("receipt_path", published_fields["receipt_path"], review_fields["receipt_path"]),
    )
    for name, published_value, review_value in pairs:
        if published_value != review_value:
            raise ReviewValidationError(
                f"published (A) workflow-metadata {name}={published_value!r} does not match "
                f"review (R) metadata {name}={review_value!r}"
            )


def _require_base_sha_ancestor(base_sha: str, candidate_sha: str, *, repo_root: Path) -> None:
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={repo_root.as_posix()}",
            "merge-base",
            "--is-ancestor",
            base_sha,
            candidate_sha,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ReviewValidationError(
            f"published base_sha {base_sha!r} is not an ancestor of candidate {candidate_sha!r}"
        )


def _diff_name_only(base_sha: str, candidate_sha: str, *, repo_root: Path) -> list[str]:
    output = _git(["diff", "--name-only", f"{base_sha}..{candidate_sha}"], repo_root)
    return [line for line in output.splitlines() if line.strip()]


def _cross_check_recorded_hashes(
    candidate_sha: str, receipt: dict[str, Any], *, repo_root: Path
) -> None:
    """Recomputes `verifier_hash`/`checker_hash`/`dependency_and_config_
    inputs` via `verification_receipts.committed_file_hash`/`dependency_
    and_config_inputs` -- the exact same canonical committed-blob
    mechanism `verification_coordinator.py` uses to produce the receipt
    in the first place, so the two can never diverge on a local checkout
    filter (e.g. `core.autocrlf`). No worktree is created for this check
    at all: a direct `git cat-file` read of `<candidate_sha>:<path>` is
    unaffected by checkout-time smudging, unlike a fresh `git worktree
    add` (which previously caused a genuine false-mismatch bug here)."""
    verifier_hash = vr.committed_file_hash(
        candidate_sha, "backend/scripts/verify.py", repo_root=repo_root
    )
    checker_hash = vr.committed_file_hash(
        candidate_sha, "backend/scripts/check_handoff.py", repo_root=repo_root
    )
    dependency_inputs = vr.dependency_and_config_inputs(
        candidate_sha, ["backend/pyproject.toml"], repo_root=repo_root
    )
    if receipt["verifier_hash"] != verifier_hash:
        raise ReviewValidationError(
            "receipt's verifier_hash does not match backend/scripts/verify.py at C"
        )
    if receipt["checker_hash"] != checker_hash:
        raise ReviewValidationError(
            "receipt's checker_hash does not match backend/scripts/check_handoff.py at C"
        )
    if receipt["dependency_and_config_inputs"] != dependency_inputs:
        raise ReviewValidationError(
            "receipt's dependency_and_config_inputs does not match the recomputed hashes at C"
        )


def _recompute_migration_required(base_sha: str, candidate_sha: str, *, repo_root: Path) -> bool:
    """Independently derives whether migration evidence is required for
    `base_sha..candidate_sha`, using this checkout's own `verification_
    scope.is_migration_trigger` -- never a value merely asserted by a
    receipt or post-merge artifact."""
    changed_paths = _diff_name_only(base_sha, candidate_sha, repo_root=repo_root)
    return any(vs.is_migration_trigger(p) for p in changed_paths)


def _cross_check_affected_surface(
    base_sha: str, candidate_sha: str, receipt: dict[str, Any], *, repo_root: Path
) -> None:
    """Independently recomputes `base_sha..candidate_sha` affected-surface
    coverage and migration triggering *using this checkout's own
    `verification_scope` module* -- when this validation runs inside
    `run_via_detached_checkout`'s subprocess, that module resolves to the
    target commit's own copy (the same cwd-precedence already proven for
    `check_review.py` itself), never the reviewer's possibly-stale
    in-process copy. Cross-checks every recomputed field against the
    receipt's own claims -- a receipt can never merely assert a
    convenient scope."""
    changed_paths = _diff_name_only(base_sha, candidate_sha, repo_root=repo_root)
    classifications = vs.classify_all(changed_paths)
    coverage = vs.compute_required_coverage(changed_paths)
    migration_required = any(vs.is_migration_trigger(p) for p in changed_paths)

    affected_surface = receipt["affected_surface"]
    recomputed_categories = sorted({c.category for c in classifications})
    if recomputed_categories != affected_surface["computed_categories"]:
        raise ReviewValidationError(
            "receipt's affected_surface.computed_categories does not match the recomputed "
            f"categories for {base_sha}..{candidate_sha} ({recomputed_categories!r} != "
            f"{affected_surface['computed_categories']!r})"
        )
    if (
        sorted(coverage.required_contract_families)
        != affected_surface["required_contract_families"]
    ):
        raise ReviewValidationError(
            "receipt's affected_surface.required_contract_families does not match the "
            "recomputed required contract families"
        )
    if sorted(coverage.required_guard_refs) != affected_surface["required_guard_refs"]:
        raise ReviewValidationError(
            "receipt's affected_surface.required_guard_refs does not match the recomputed "
            "required guard refs"
        )
    if sorted(coverage.directly_executed_tests) != affected_surface["directly_executed_tests"]:
        raise ReviewValidationError(
            "receipt's affected_surface.directly_executed_tests does not match the recomputed "
            "directly-executed tests"
        )
    if migration_required != receipt["migration_matrix"]["triggered"]:
        raise ReviewValidationError(
            f"recomputed migration trigger ({migration_required}) does not match receipt's "
            f"migration_matrix.triggered ({receipt['migration_matrix']['triggered']}) for "
            f"{base_sha}..{candidate_sha}"
        )

    computed_focus_targets = {
        target.removeprefix("backend/") for target in coverage.required_focus_targets
    }
    recorded_selector = set(receipt["focused_tests"].get("selector", "").split())
    if not computed_focus_targets <= recorded_selector:
        raise ReviewValidationError(
            "receipt's focused_tests.selector does not cover the recomputed required focus "
            f"targets (missing {sorted(computed_focus_targets - recorded_selector)!r})"
        )

    recorded_guard_refs = set(receipt["mutation_witnesses"].get("guard_refs", []))
    if not coverage.required_guard_refs <= recorded_guard_refs:
        raise ReviewValidationError(
            "receipt's mutation_witnesses.guard_refs does not cover the recomputed required "
            f"guard refs (missing {sorted(coverage.required_guard_refs - recorded_guard_refs)!r})"
        )


def _require_complete_active_witness_inventory(data: dict[str, Any], *, context: str) -> None:
    """Reuses `verification_receipts.witnesses_match_complete_active_
    inventory` -- the single mechanism shared by `compute_approval_
    eligible` (a receipt), this pre-merge cross-check, and the post-merge
    artifact/Q evidence check below -- so all three can never
    independently drift, and none of them retains a weaker positive-
    count-only or subset-only path. Raised with a detailed diff (never
    merely "false") by independently recomputing the same active-guard
    inventory the shared predicate itself uses."""
    if vr.witnesses_match_complete_active_inventory(data):
        return
    active_guard_refs = vr.compute_active_guard_refs()
    witnesses = data["mutation_witnesses"]
    recorded_guard_refs = frozenset(witnesses.get("guard_refs") or [])
    if recorded_guard_refs != active_guard_refs:
        raise ReviewValidationError(
            f"{context}'s mutation_witnesses.guard_refs does not equal the complete "
            f"active-guard inventory (missing "
            f"{sorted(active_guard_refs - recorded_guard_refs)!r}, unexpected "
            f"{sorted(recorded_guard_refs - active_guard_refs)!r})"
        )
    passed = witnesses.get("passed")
    failed = witnesses.get("failed")
    raise ReviewValidationError(
        f"{context}'s mutation_witnesses passed/failed ({passed!r}/{failed!r}) must equal "
        f"len(guard_refs)={len(recorded_guard_refs)}/0"
    )


def _cross_check_final_gate_witness_inventory(receipt: dict[str, Any]) -> None:
    """For `gate: final` specifically, the receipt's `mutation_witnesses`
    must cover the *complete* active-guard inventory -- never merely the
    diff-computed required subset (that weaker check is `_cross_check_
    affected_surface`'s job, and still applies for `fast`). `final` always
    runs every currently active guard (`verify.py`'s own `mutation_
    witnesses_step` passes `refs=[]` whenever `gate != 'fast'`)."""
    if receipt["gate"] != "final":
        return
    _require_complete_active_witness_inventory(receipt, context="receipt")


def _validate_verdict_findings_pair(verdict: str, findings: str, *, context: str) -> None:
    if verdict not in _VALID_VERDICTS:
        raise ReviewValidationError(
            f"{context} 'verdict' must be one of {sorted(_VALID_VERDICTS)}, got {verdict!r}"
        )
    if verdict == "approved" and findings != "none":
        raise ReviewValidationError(f"{context} verdict: approved requires findings: none")
    if verdict == "changes_requested" and findings == "none":
        raise ReviewValidationError(
            f"{context} verdict: changes_requested requires at least one <slice-id>/F### finding"
        )


# ---------------------------------------------------------------------------
# C -> A -> R chain validation (record validity)
# ---------------------------------------------------------------------------


def validate_c_a_r_chain(
    candidate_sha: str,
    publication_sha: str,
    review_sha: str,
    *,
    repo_root: Path = REPO_ROOT,
    handoff_relative_path: str = "docs/LLM_HANDOFF.md",
) -> dict[str, str]:
    """Validates the complete `C -> A -> R` chain -- parent shape, the
    `C..A` and `A..R` transition diffs, review-metadata structure, and the
    receipt cross-check -- and returns the parsed review-metadata fields
    on success. Accepts a well-formed `changes_requested` record: this is
    *record validity*, not merge eligibility (see `check_merge_eligibility`
    below)."""
    require_single_parent_chain(candidate_sha, publication_sha, review_sha, repo_root=repo_root)

    handoff_at_c = read_file_at_commit(candidate_sha, handoff_relative_path, repo_root=repo_root)
    handoff_at_a = read_file_at_commit(publication_sha, handoff_relative_path, repo_root=repo_root)
    handoff_at_r = read_file_at_commit(review_sha, handoff_relative_path, repo_root=repo_root)

    validate_c_to_a_transition(
        candidate_sha, publication_sha, handoff_at_c, handoff_at_a, repo_root=repo_root
    )
    validate_a_to_r_transition(
        publication_sha, review_sha, handoff_at_a, handoff_at_r, repo_root=repo_root
    )

    published_fields = extract_and_validate_published_metadata(
        handoff_at_a, publication_sha=publication_sha
    )
    if published_fields["candidate_sha"] != candidate_sha:
        raise ReviewValidationError(
            f"published (A) workflow-metadata candidate_sha "
            f"{published_fields['candidate_sha']!r} != actual C {candidate_sha!r}"
        )
    _require_base_sha_ancestor(published_fields["base_sha"], candidate_sha, repo_root=repo_root)

    review_text = extract_review_metadata_text(handoff_at_r)
    review_fields = ch.parse_metadata_fields(review_text)
    validate_review_metadata_structure(review_fields, slice_kind=published_fields["slice_kind"])
    for escalation_fields in extract_escalation_blocks(handoff_at_r):
        validate_escalation_metadata_structure(escalation_fields)

    if review_fields["candidate_sha"] != candidate_sha:
        raise ReviewValidationError(
            f"review metadata candidate_sha {review_fields['candidate_sha']!r} != "
            f"actual C {candidate_sha!r}"
        )
    if review_fields["publication_commit_sha"] != publication_sha:
        raise ReviewValidationError(
            f"review metadata publication_commit_sha {review_fields['publication_commit_sha']!r} "
            f"!= actual A {publication_sha!r}"
        )
    _cross_check_published_and_review_metadata(published_fields, review_fields)

    receipt_text = read_file_at_commit(
        publication_sha, review_fields["receipt_path"], repo_root=repo_root
    )
    receipt = vr.load_receipt_from_text(receipt_text)
    vr.validate_receipt_schema(receipt)
    if receipt["receipt_id"] != review_fields["receipt_id"]:
        raise ReviewValidationError("review metadata receipt_id does not match the receipt itself")
    if receipt["gate"] != review_fields["gate"]:
        raise ReviewValidationError("review metadata gate does not match the receipt's own gate")
    if receipt["candidate_sha"] != candidate_sha:
        raise ReviewValidationError("receipt's own candidate_sha does not match C")
    if receipt["slice_id"] != published_fields["slice_id"]:
        raise ReviewValidationError(
            "receipt's own slice_id does not match the published (A) workflow-metadata slice_id"
        )
    if receipt["risk_class"] != published_fields["risk_class"]:
        raise ReviewValidationError(
            "receipt's own risk_class does not match the published (A) workflow-metadata risk_class"
        )
    if receipt["base_sha"] != published_fields["base_sha"]:
        raise ReviewValidationError(
            "receipt's own base_sha does not match the published (A) workflow-metadata base_sha"
        )

    _cross_check_affected_surface(
        published_fields["base_sha"], candidate_sha, receipt, repo_root=repo_root
    )
    _cross_check_recorded_hashes(candidate_sha, receipt, repo_root=repo_root)
    _cross_check_final_gate_witness_inventory(receipt)

    recomputed_eligible = vr.compute_approval_eligible(receipt)
    if review_fields["verdict"] == "approved" and not recomputed_eligible:
        raise ReviewValidationError(
            "verdict: approved but the receipt's recomputed approval_eligible is false"
        )

    # Internal-only keys, never present in the parsed review text itself --
    # carry the independently-validated published metadata forward to
    # `check_merge_eligibility` and `validate_published` (e.g. for the
    # gate: docs merge-eligibility restriction and the post-merge
    # artifact's B/C/A/R cross-check) without re-reading the handoff again.
    review_fields["published_slice_kind"] = published_fields["slice_kind"]
    review_fields["published_base_sha"] = published_fields["base_sha"]
    return review_fields


def check_merge_eligibility(
    candidate_sha: str, publication_sha: str, review_sha: str, *, repo_root: Path = REPO_ROOT
) -> dict[str, str]:
    """Record validity (`validate_c_a_r_chain`) plus the additional,
    stricter requirements that make a record actually *merge*-eligible:
    `verdict: approved` (findings: none and reviewer-policy compliance are
    already enforced by `validate_review_metadata_structure`, and
    approval-eligibility is already cross-checked above); and, for a
    `gate: docs` receipt specifically, that the bound published slice is
    genuinely `slice_kind: docs` -- a docs-gate receipt (which never runs
    the full suite or witnesses) must never be reused to merge
    parser/tooling work."""
    review_fields = validate_c_a_r_chain(
        candidate_sha, publication_sha, review_sha, repo_root=repo_root
    )
    if review_fields["verdict"] != "approved":
        raise ReviewValidationError(
            f"not merge-eligible: verdict is {review_fields['verdict']!r}, not 'approved'"
        )
    if review_fields["gate"] == "docs" and review_fields["published_slice_kind"] != "docs":
        raise ReviewValidationError(
            "gate: docs is only merge-eligible when the published slice is genuinely "
            f"slice_kind: docs, got {review_fields['published_slice_kind']!r}"
        )
    return review_fields


# ---------------------------------------------------------------------------
# Transition diff validators -- byte-identical everywhere except the one
# permitted, named change.
# ---------------------------------------------------------------------------


def _replace_last_metadata_block(text: str, replacement: str) -> str:
    matches = list(_METADATA_BLOCK_RE.finditer(text))
    if not matches:
        raise ReviewValidationError("no 'workflow-metadata' block found")
    last = matches[-1]
    return text[: last.start()] + replacement + text[last.end() :]


def validate_c_to_a_transition(
    candidate_sha: str,
    publication_sha: str,
    handoff_at_c: str,
    handoff_at_a: str,
    *,
    repo_root: Path = REPO_ROOT,
) -> None:
    """`C..A` may add exactly one receipt file (status `A`, never
    modified/renamed) and change `docs/LLM_HANDOFF.md` *only* within the
    newest `workflow-metadata` block (the pending -> published
    transition) -- every other byte of the file, and every other path in
    the repository, must be identical."""
    lines = _name_status_lines(candidate_sha, publication_sha, repo_root)
    receipt_additions = [
        line for line in lines if line.startswith("A\t") and "verification-receipts" in line
    ]
    if len(receipt_additions) != 1:
        raise ReviewValidationError(
            f"C..A must add exactly one receipt file (status A), got {receipt_additions}"
        )
    handoff_lines = [line for line in lines if line.endswith("docs/LLM_HANDOFF.md")]
    if len(handoff_lines) != 1 or not handoff_lines[0].startswith("M\t"):
        raise ReviewValidationError(
            f"C..A must modify (not add/delete/rename) docs/LLM_HANDOFF.md, got {handoff_lines}"
        )
    other = [line for line in lines if line not in receipt_additions and line not in handoff_lines]
    if other:
        raise ReviewValidationError(f"C..A must not change any other path, got {other}")

    normalized_c = _replace_last_metadata_block(handoff_at_c, "<BLOCK>")
    normalized_a = _replace_last_metadata_block(handoff_at_a, "<BLOCK>")
    if normalized_c != normalized_a:
        raise ReviewValidationError(
            "C..A changed docs/LLM_HANDOFF.md outside the newest workflow-metadata block"
        )


def validate_a_to_r_transition(
    publication_sha: str,
    review_sha: str,
    handoff_at_a: str,
    handoff_at_r: str,
    *,
    repo_root: Path = REPO_ROOT,
) -> None:
    """`A..R` may change only `docs/LLM_HANDOFF.md`, and only by
    *appending* the newest Work-review section (one `workflow-review-
    metadata` block plus zero or more `workflow-escalation-metadata`
    blocks) -- every previously existing byte, including every earlier
    iteration's historical text, must remain exactly as it was."""
    lines = _name_status_lines(publication_sha, review_sha, repo_root)
    if lines != ["M\tdocs/LLM_HANDOFF.md"]:
        raise ReviewValidationError(f"A..R must change only docs/LLM_HANDOFF.md, got {lines}")

    if not handoff_at_r.startswith(handoff_at_a):
        raise ReviewValidationError(
            "A..R must be a pure append to docs/LLM_HANDOFF.md -- every existing byte "
            "(including historical iterations) must remain unchanged"
        )
    if handoff_at_r == handoff_at_a:
        raise ReviewValidationError("A..R added no new content to docs/LLM_HANDOFF.md")


# ---------------------------------------------------------------------------
# Merge (M) and post-merge evidence publication (Q) validation
# ---------------------------------------------------------------------------


def validate_merge(
    review_sha: str,
    merge_sha: str,
    expected_first_parent: str,
    *,
    repo_root: Path = REPO_ROOT,
) -> None:
    """`M`'s second parent must be exactly `R`; its first parent must be
    exactly the caller-supplied expected pre-merge `main` tip; `R..M` must
    introduce no content difference."""
    parents = parents_of(merge_sha, repo_root=repo_root)
    if len(parents) != 2:
        raise ReviewValidationError(f"M ({merge_sha}) must be a merge commit with two parents")
    first_parent, second_parent = parents
    if second_parent != review_sha:
        raise ReviewValidationError(
            f"M's second parent ({second_parent}) must equal R ({review_sha})"
        )
    if first_parent != expected_first_parent:
        raise ReviewValidationError(
            f"M's first parent ({first_parent}) must equal the expected pre-merge main tip "
            f"({expected_first_parent}) -- reuse is not permitted if main advanced"
        )
    diff = subprocess.run(
        ["git", "-c", f"safe.directory={REPO_ROOT.as_posix()}", "diff", review_sha, merge_sha],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if diff.stdout.strip():
        raise ReviewValidationError("R..M must introduce no content difference, but it does")


def _validate_post_merge_artifact_schema(artifact: dict[str, Any]) -> None:
    """Recursively closed/typed, mirroring `verification_receipts.py`'s
    own nested validators for every field this artifact shares with a
    receipt (`coordinator`, `steps`, `full_suite`, `mutation_witnesses`,
    `migration_matrix`, `cleanup`, `environment_descriptor`) -- never a
    parallel, drifting reimplementation of those same rules."""
    missing = [k for k in _REQUIRED_POST_MERGE_ARTIFACT_FIELDS if k not in artifact]
    if missing:
        raise ReviewValidationError(f"post-merge artifact missing required field(s): {missing}")
    unknown = [k for k in artifact if k not in _REQUIRED_POST_MERGE_ARTIFACT_FIELDS]
    if unknown:
        raise ReviewValidationError(
            f"post-merge artifact declares unrecognized field(s): {unknown}"
        )
    if artifact["kind"] != "post_merge_verification":
        raise ReviewValidationError(
            f"post-merge artifact 'kind' must be 'post_merge_verification', "
            f"got {artifact['kind']!r}"
        )
    # Q is never named inside the artifact it creates -- a self-reference
    # would be a schema violation, enforced here by the closed field list
    # above simply never including any "publication of self" key.

    for sha_field in (
        "base_sha",
        "candidate_sha",
        "publication_commit_sha",
        "review_commit_sha",
        "merged_commit",
    ):
        value = artifact[sha_field]
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ReviewValidationError(
                f"post-merge artifact {sha_field!r} must be a full 40-hex commit SHA, "
                f"got {value!r}"
            )

    # Every nested-shape check below reuses `verification_receipts.py`'s
    # own (private) validators -- never a parallel reimplementation --
    # so its `ReceiptError` is converted to this module's own exception
    # type at this single boundary, once.
    try:
        if artifact["schema_version"] != _SUPPORTED_POST_MERGE_ARTIFACT_SCHEMA_VERSION:
            raise vr.ReceiptError(
                f"post-merge artifact 'schema_version' must be "
                f"{_SUPPORTED_POST_MERGE_ARTIFACT_SCHEMA_VERSION!r}, "
                f"got {artifact['schema_version']!r}"
            )
        vr.validate_slice_id(artifact["slice_id"])
        vr.validate_receipt_id(artifact["original_receipt_id"])
        vr._require_str(artifact, "original_receipt_path", context="post-merge artifact")
        if not artifact["original_receipt_path"]:
            raise vr.ReceiptError("post-merge artifact 'original_receipt_path' must not be empty")

        env_descriptor = vr._require_exact_keys(
            artifact["environment_descriptor"],
            vr._ENV_DESCRIPTOR_KEYS,
            context="environment_descriptor",
        )
        vr._require_str(env_descriptor, "python_version", context="environment_descriptor")
        vr._require_str(env_descriptor, "platform", context="environment_descriptor")
        if env_descriptor["postgresql_version"] is not None and not isinstance(
            env_descriptor["postgresql_version"], str
        ):
            raise vr.ReceiptError("environment_descriptor.postgresql_version must be a str or null")
        vr._require_str(
            env_descriptor, "installed_distributions_digest", context="environment_descriptor"
        )

        vr._validate_coordinator(artifact["coordinator"])
        vr._validate_steps(artifact)
        vr._validate_ran_or_not_run_summary(
            artifact, "full_suite", ran_keys=frozenset({"status", "count"})
        )
        vr._validate_ran_or_not_run_summary(
            artifact,
            "mutation_witnesses",
            ran_keys=frozenset({"status", "guard_refs", "passed", "failed"}),
        )
        vr._validate_migration_matrix(artifact)

        cleanup = vr._require_exact_keys(artifact["cleanup"], vr._CLEANUP_KEYS, context="cleanup")
        vr._require_bool(cleanup, "attempted", context="cleanup")
        if cleanup["status"] not in ("PASS", "FAIL"):
            raise vr.ReceiptError("cleanup.status must be 'PASS' or 'FAIL'")
    except vr.ReceiptError as exc:
        raise ReviewValidationError(f"post-merge artifact invalid: {exc}") from exc


def _require_post_merge_steps_present(artifact: dict[str, Any]) -> None:
    """Every applicable step for an always-full post-merge re-verification
    -- static checks, DB URL safety, DB reachability, full suite, all
    witnesses, migration matrix when triggered, handoff validation, and
    temporary-directory cleanup (post-merge never has a "focused tests"
    concept, so that one conditional step of `compute_applicable_final_
    step_names` never applies here) -- must exist in the post-merge
    artifact's own `steps` exactly once, with status `PASS`. Reuses the
    *same* step-name computation `verification_receipts.compute_approval_
    eligible` uses for a receipt, defined once, so the two can never
    independently drift. An omitted step and a step merely present-but-
    `NOT_RUN` are both rejected identically, never treated as "close
    enough"."""
    required_names = vr.compute_applicable_final_step_names(
        focused_tests_computed=False,
        migration_triggered=bool(artifact["migration_matrix"].get("triggered")),
    )
    for name in required_names:
        matching = [s for s in artifact["steps"] if s["name"] == name]
        if len(matching) != 1:
            raise ReviewValidationError(
                f"post-merge artifact must declare step {name!r} exactly once, found "
                f"{len(matching)}"
            )
        if matching[0]["status"] != "PASS":
            raise ReviewValidationError(
                f"post-merge artifact's step {name!r} is not PASS (status: "
                f"{matching[0]['status']!r})"
            )


def _validate_post_merge_artifact_evidence(artifact: dict[str, Any]) -> None:
    """Beyond shape: a post-merge artifact must show genuine, positive
    success evidence -- mirroring `verification_receipts.compute_approval_
    eligible`'s logic, but for the always-full-suite `M..Q` re-verification
    record specifically (post-merge verification is never partial)."""
    if not artifact["steps"]:
        raise ReviewValidationError("post-merge artifact has no recorded steps")
    _require_post_merge_steps_present(artifact)
    if any(step["status"] == "FAIL" for step in artifact["steps"]):
        raise ReviewValidationError("post-merge artifact records a FAILed step")
    if artifact["cleanup"].get("status") != "PASS":
        raise ReviewValidationError("post-merge artifact's cleanup did not pass")

    full_suite = artifact["full_suite"]
    count = full_suite.get("count")
    if (
        full_suite.get("status") != "ran"
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count <= 0
    ):
        raise ReviewValidationError(
            "post-merge artifact's full suite did not genuinely run and pass"
        )

    # Post-merge is inherently full/final-equivalent (never gated) -- the
    # complete active-guard inventory is always required here, the exact
    # same shared mechanism `compute_approval_eligible` and the pre-merge
    # cross-check use.
    _require_complete_active_witness_inventory(artifact, context="post-merge artifact")

    # Reuses the same deep migration-evidence check a receipt's own
    # `compute_approval_eligible` applies -- exists exactly once with
    # PASS (already required above), matrix status PASS, before/after
    # DevelopmentState equal, fresh database created and cleaned up.
    if not vr._migration_matrix_genuinely_passed(artifact):
        raise ReviewValidationError(
            "post-merge artifact's migration matrix was triggered but its evidence is invalid "
            "or did not genuinely pass"
        )


def validate_m_to_q_transition(
    merge_sha: str,
    q_sha: str,
    handoff_at_m: str,
    handoff_at_q: str,
    *,
    repo_root: Path = REPO_ROOT,
) -> None:
    """`M..Q` may touch `docs/LLM_HANDOFF.md` at most once, and only by
    *appending* -- mirrors `validate_a_to_r_transition`'s pure-append
    check. Unlike `A..R`, an append is not mandatory: `Q` may add only the
    post-merge artifact and leave the handoff untouched."""
    lines = _name_status_lines(merge_sha, q_sha, repo_root)
    handoff_lines = [line for line in lines if line.endswith("docs/LLM_HANDOFF.md")]
    if len(handoff_lines) > 1:
        raise ReviewValidationError("M..Q must touch docs/LLM_HANDOFF.md at most once")
    if not handoff_lines:
        return
    if not handoff_lines[0].startswith("M\t"):
        raise ReviewValidationError(
            f"M..Q must modify (not add/delete/rename) docs/LLM_HANDOFF.md, got {handoff_lines}"
        )
    if not handoff_at_q.startswith(handoff_at_m):
        raise ReviewValidationError(
            "M..Q must be a pure append to docs/LLM_HANDOFF.md -- every existing byte "
            "must remain unchanged"
        )


def validate_q(
    merge_sha: str,
    q_sha: str,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """`Q` is identified *externally*, as the caller-supplied direct child
    of `M` -- never discovered by walking `M`'s children (Git has no such
    query). `M..Q` may add exactly one post-merge artifact (status `A`)
    plus the permitted append-only merge-record addition to
    `docs/LLM_HANDOFF.md` (see `validate_m_to_q_transition`)."""
    require_single_parent(q_sha, merge_sha, label="Q", repo_root=repo_root)

    lines = _name_status_lines(merge_sha, q_sha, repo_root)
    artifact_additions = [line for line in lines if line.startswith("A\t") and "post-merge" in line]
    if len(artifact_additions) != 1:
        raise ReviewValidationError(
            f"M..Q must add exactly one post-merge artifact (status A), got {artifact_additions}"
        )
    other = [line for line in lines if line not in artifact_additions]
    handoff_lines = [line for line in other if line.endswith("docs/LLM_HANDOFF.md")]
    unexpected = [line for line in other if line not in handoff_lines]
    if unexpected:
        raise ReviewValidationError(f"M..Q must not change any other path, got {unexpected}")

    handoff_at_m = read_file_at_commit(merge_sha, "docs/LLM_HANDOFF.md", repo_root=repo_root)
    handoff_at_q = read_file_at_commit(q_sha, "docs/LLM_HANDOFF.md", repo_root=repo_root)
    validate_m_to_q_transition(merge_sha, q_sha, handoff_at_m, handoff_at_q, repo_root=repo_root)

    artifact_path = artifact_additions[0].split("\t", 1)[1]
    artifact_text = read_file_at_commit(q_sha, artifact_path, repo_root=repo_root)
    artifact = vr.load_receipt_from_text(artifact_text)
    _validate_post_merge_artifact_schema(artifact)
    _validate_post_merge_artifact_evidence(artifact)
    if artifact["merged_commit"] != merge_sha:
        raise ReviewValidationError("post-merge artifact's merged_commit does not match M")
    return artifact


def validate_published(
    candidate_sha: str,
    publication_sha: str,
    review_sha: str,
    merge_sha: str,
    q_sha: str,
    expected_first_parent: str,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """The complete post-merge validation: independently re-derives
    `C -> A -> R`, validates `M`, validates `Q`'s artifact, cross-checks
    the artifact's own recorded `B`/`C`/`A`/`R` references against the
    independently recomputed chain, and cross-checks the artifact's
    recorded original-receipt reference against that receipt's own
    content, re-read and re-validated at `M` -- a reader recomputes, it
    never trusts the artifact's own claims alone."""
    review_fields = validate_c_a_r_chain(
        candidate_sha, publication_sha, review_sha, repo_root=repo_root
    )
    validate_merge(review_sha, merge_sha, expected_first_parent, repo_root=repo_root)
    artifact = validate_q(merge_sha, q_sha, repo_root=repo_root)

    if (
        artifact["candidate_sha"] != candidate_sha
        or artifact["publication_commit_sha"] != publication_sha
        or artifact["review_commit_sha"] != review_sha
        or artifact["base_sha"] != review_fields["published_base_sha"]
        or artifact["slice_id"] != review_fields["slice_id"]
        or artifact["original_receipt_id"] != review_fields["receipt_id"]
        or artifact["original_receipt_path"] != review_fields["receipt_path"]
    ):
        raise ReviewValidationError(
            "post-merge artifact's recorded B/C/A/R references do not match "
            "the independently recomputed chain"
        )

    original_receipt_text = read_file_at_commit(
        merge_sha, artifact["original_receipt_path"], repo_root=repo_root
    )
    original_receipt = vr.load_receipt_from_text(original_receipt_text)
    vr.validate_receipt_schema(original_receipt)
    if (
        original_receipt["receipt_id"] != artifact["original_receipt_id"]
        or original_receipt["candidate_sha"] != artifact["candidate_sha"]
        or original_receipt["base_sha"] != artifact["base_sha"]
    ):
        raise ReviewValidationError(
            "post-merge artifact's original_receipt reference does not match "
            "that receipt's own content"
        )

    migration_required = _recompute_migration_required(
        review_fields["published_base_sha"], candidate_sha, repo_root=repo_root
    )
    if migration_required != artifact["migration_matrix"]["triggered"]:
        raise ReviewValidationError(
            f"post-merge artifact's migration_matrix.triggered "
            f"({artifact['migration_matrix']['triggered']}) does not match the independently "
            f"recomputed migration trigger ({migration_required}) for the original "
            f"{review_fields['published_base_sha']}..{candidate_sha} diff"
        )

    if review_fields["verdict"] != "approved":
        raise ReviewValidationError("post-merge validation requires an approved review record")
    return artifact


# ---------------------------------------------------------------------------
# Outer detached-checkout launcher -- runs the *target commit's own*
# check_review.py, never the caller's in-process copy.
# ---------------------------------------------------------------------------


def run_via_detached_checkout(
    commit_sha: str, mode: str, extra_args: list[str], *, repo_root: Path = REPO_ROOT
) -> subprocess.CompletedProcess[str]:
    """Fails closed on cleanup: unlike a prior version of this function
    (which suppressed `WorktreeError` and used `shutil.rmtree(...,
    ignore_errors=True)`, silently swallowing any teardown failure), a
    worktree-removal or run-directory-removal failure here is raised as
    `ReviewValidationError` -- the caller can rely on either a clean
    return (no residual worktree or run directory, verified below) or an
    explicit exception, never a silent partial cleanup."""
    run_dir = Path(tempfile.mkdtemp(prefix="launcher-"))
    worktree: Path | None = None
    cleanup_errors: list[str] = []
    try:
        worktree = vw.create_detached_worktree(commit_sha, run_dir)
        command = [
            sys.executable,
            "-m",
            "scripts.check_review",
            "--internal-validate",
            mode,
            *extra_args,
        ]
        result = subprocess.run(
            command, cwd=str(worktree / "backend"), capture_output=True, text=True
        )
    finally:
        if worktree is not None:
            try:
                vw.remove_worktree(worktree)
                vw.confirm_no_leak(worktree)
            except (vw.WorktreeError, OSError) as exc:
                cleanup_errors.append(f"worktree teardown: {exc}")
        try:
            if run_dir.exists():
                shutil.rmtree(run_dir)
        except OSError as exc:
            cleanup_errors.append(f"run directory removal: {exc}")

    if cleanup_errors:
        raise ReviewValidationError(
            f"detached-checkout launcher cleanup failed: {'; '.join(cleanup_errors)}"
        )
    if worktree is not None and worktree.exists():
        raise ReviewValidationError(
            f"detached-checkout launcher left a residual worktree: {worktree}"
        )
    if run_dir.exists():
        raise ReviewValidationError(
            f"detached-checkout launcher left a residual run directory: {run_dir}"
        )
    return result


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="check_review.py")
    parser.add_argument(
        "--internal-validate", choices=["single", "merge", "published"], required=True
    )
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--publication", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--merge", default=None)
    parser.add_argument("--q", default=None)
    parser.add_argument("--expected-first-parent", default=None)
    parser.add_argument("--require-approved", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.internal_validate == "single":
            fields = (
                check_merge_eligibility(args.candidate, args.publication, args.review)
                if args.require_approved
                else validate_c_a_r_chain(args.candidate, args.publication, args.review)
            )
            print(f"OK verdict={fields['verdict']}")
        elif args.internal_validate == "merge":
            if not args.merge or not args.expected_first_parent:
                raise ReviewValidationError(
                    "--merge validation requires --merge and --expected-first-parent"
                )
            check_merge_eligibility(args.candidate, args.publication, args.review)
            validate_merge(args.review, args.merge, args.expected_first_parent)
            print("OK merge validated")
        else:  # published
            if not args.merge or not args.q or not args.expected_first_parent:
                raise ReviewValidationError(
                    "--published validation requires --merge, --q, and --expected-first-parent"
                )
            validate_published(
                args.candidate,
                args.publication,
                args.review,
                args.merge,
                args.q,
                args.expected_first_parent,
            )
            print("OK published validated")
    except ReviewValidationError as exc:
        print(f"FAIL {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
