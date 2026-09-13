"""Review-chain validation for Workflow v3.2 (`C -> A -> R`, and merge
validation at `M`).

Distinct from `check_handoff.py` (which validates the metadata block's
own structure, in isolation) -- this module validates the *relational*
facts that require Git plumbing and the receipt file itself: that `A` is
a direct child of `C`, `R` a direct child of `A`, that `A`'s published
metadata references a receipt that genuinely exists and is genuinely
well-formed, and that the review metadata's own claims about `C`/`A`/the
receipt agree with what Git and the receipt actually say -- never taken
on the review's own prose.

**Scope note (this activation slice):** this module is an authorized
component of the activation, exercised here only by its own test suite
against disposable Git repositories -- no `R`/`M`/`Q` is authored against
the real repository as part of this slice (see `docs/LLM_HANDOFF.md`).
The merge-mode (`--merge`) and post-merge (`--verify-published`) checks
implemented here cover the chain-shape and content-identity invariants;
the outer-launcher/subprocess-reexecution design for validating "R's own
code" and the full per-transition byte-identical-history diff validator
are recorded as known follow-on hardening, not yet implemented at the
same depth as the receipt/coordinator modules -- see this slice's `Work
done` deviations.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from scripts import check_handoff as ch
from scripts import verification_receipts as vr

REPO_ROOT = Path(__file__).resolve().parents[2]

_REVIEW_METADATA_BLOCK_RE = re.compile(r"```workflow-review-metadata\n(.*?)\n```", re.DOTALL)
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
_VALID_REVIEWER_ROLES = frozenset({"primary", "escalation"})
_VALID_VERDICTS = frozenset({"approved", "changes_requested"})
_REQUIRED_PRIMARY_REVIEWER_MODEL = "Sol Medium"


class ReviewValidationError(Exception):
    """A chain-shape, cross-reference, or review-metadata problem --
    fails closed, never a warning."""


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


def parents_of(commit: str, *, repo_root: Path = REPO_ROOT) -> list[str]:
    output = _git(["rev-parse", f"{commit}^@"], repo_root)
    return [line for line in output.splitlines() if line.strip()]


def require_single_parent_chain(
    candidate_sha: str, publication_sha: str, review_sha: str, *, repo_root: Path = REPO_ROOT
) -> None:
    a_parents = parents_of(publication_sha, repo_root=repo_root)
    if a_parents != [candidate_sha]:
        raise ReviewValidationError(
            f"A ({publication_sha}) must have exactly one parent, C ({candidate_sha}); "
            f"got {a_parents}"
        )
    r_parents = parents_of(review_sha, repo_root=repo_root)
    if r_parents != [publication_sha]:
        raise ReviewValidationError(
            f"R ({review_sha}) must have exactly one parent, A ({publication_sha}); "
            f"got {r_parents}"
        )


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


def extract_review_metadata_text(handoff_text: str) -> str:
    matches = list(_REVIEW_METADATA_BLOCK_RE.finditer(handoff_text))
    if not matches:
        raise ReviewValidationError("no 'workflow-review-metadata' block found")
    if len(matches) > 1:
        raise ReviewValidationError("more than one 'workflow-review-metadata' block found")
    return matches[0].group(1)


def validate_review_metadata_structure(fields: dict[str, str]) -> None:
    missing = [k for k in _REQUIRED_REVIEW_FIELDS if k not in fields]
    if missing:
        raise ReviewValidationError(f"review metadata missing required field(s): {missing}")

    if fields["reviewer_role"] not in _VALID_REVIEWER_ROLES:
        raise ReviewValidationError(
            f"'reviewer_role' must be one of {sorted(_VALID_REVIEWER_ROLES)}, "
            f"got {fields['reviewer_role']!r}"
        )
    if fields["verdict"] not in _VALID_VERDICTS:
        raise ReviewValidationError(
            f"'verdict' must be one of {sorted(_VALID_VERDICTS)}, got {fields['verdict']!r}"
        )
    findings = fields["findings"]
    if fields["verdict"] == "approved" and findings != "none":
        raise ReviewValidationError("verdict: approved requires findings: none")
    if fields["verdict"] == "changes_requested" and findings == "none":
        raise ReviewValidationError(
            "verdict: changes_requested requires at least one <slice-id>/F### finding"
        )
    # Simplified scope for this activation slice: enforced here using only
    # what review metadata itself carries (risk_class). Fully cross-
    # checking "executable" (slice_kind: parser|tooling) against the
    # published Work-done metadata at the same commit is recorded as
    # follow-on hardening, not yet implemented at this depth.
    if (
        fields["reviewer_role"] == "primary"
        and fields["risk_class"] == "H"
        and fields["reviewer_model"] != _REQUIRED_PRIMARY_REVIEWER_MODEL
    ):
        raise ReviewValidationError(
            f"the primary reviewer for Class H work must be "
            f"{_REQUIRED_PRIMARY_REVIEWER_MODEL!r}, got {fields['reviewer_model']!r}"
        )


def validate_c_a_r_chain(
    candidate_sha: str,
    publication_sha: str,
    review_sha: str,
    *,
    repo_root: Path = REPO_ROOT,
    handoff_relative_path: str = "docs/LLM_HANDOFF.md",
) -> dict[str, str]:
    """Validates the complete `C -> A -> R` chain and returns the parsed
    review-metadata fields on success."""
    require_single_parent_chain(candidate_sha, publication_sha, review_sha, repo_root=repo_root)

    handoff_at_r = read_file_at_commit(review_sha, handoff_relative_path, repo_root=repo_root)
    review_text = extract_review_metadata_text(handoff_at_r)
    review_fields = ch.parse_metadata_fields(review_text)
    validate_review_metadata_structure(review_fields)

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

    recomputed_eligible = vr.compute_approval_eligible(receipt)
    if review_fields["verdict"] == "approved" and not recomputed_eligible:
        raise ReviewValidationError(
            "verdict: approved but the receipt's recomputed approval_eligible is false"
        )

    return review_fields


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
