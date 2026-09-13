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
import contextlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from scripts import check_handoff as ch
from scripts import verification_receipts as vr
from scripts import verification_worktree as vw

REPO_ROOT = Path(__file__).resolve().parents[2]

_REVIEW_METADATA_BLOCK_RE = re.compile(r"```workflow-review-metadata\n(.*?)\n```", re.DOTALL)
_ESCALATION_BLOCK_RE = re.compile(r"```workflow-escalation-metadata\n(.*?)\n```", re.DOTALL)
_METADATA_BLOCK_RE = re.compile(r"```workflow-metadata\n.*?\n```", re.DOTALL)

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


def extract_review_metadata_text(handoff_text: str) -> str:
    matches = list(_REVIEW_METADATA_BLOCK_RE.finditer(handoff_text))
    if not matches:
        raise ReviewValidationError("no 'workflow-review-metadata' block found")
    if len(matches) > 1:
        raise ReviewValidationError("more than one 'workflow-review-metadata' block found")
    return matches[0].group(1)


def extract_escalation_blocks(handoff_text: str) -> list[dict[str, str]]:
    return [
        ch.parse_metadata_fields(m.group(1)) for m in _ESCALATION_BLOCK_RE.finditer(handoff_text)
    ]


def validate_review_metadata_structure(fields: dict[str, str]) -> None:
    missing = [k for k in _REQUIRED_REVIEW_FIELDS if k not in fields]
    if missing:
        raise ReviewValidationError(f"review metadata missing required field(s): {missing}")

    if fields["reviewer_role"] not in _VALID_REVIEWER_ROLES:
        raise ReviewValidationError(
            f"'reviewer_role' must be one of {sorted(_VALID_REVIEWER_ROLES)}, "
            f"got {fields['reviewer_role']!r}"
        )
    _validate_verdict_findings_pair(fields["verdict"], fields["findings"], context="review")

    # Simplified scope: enforced here using only what review metadata
    # itself carries (risk_class). Fully cross-checking "executable"
    # (slice_kind: parser|tooling) against the published Work-done
    # metadata at the same commit is recorded as follow-on hardening.
    if (
        fields["reviewer_role"] == "primary"
        and fields["risk_class"] == "H"
        and fields["reviewer_model"] != _REQUIRED_PRIMARY_REVIEWER_MODEL
    ):
        raise ReviewValidationError(
            f"the primary reviewer for Class H work must be "
            f"{_REQUIRED_PRIMARY_REVIEWER_MODEL!r}, got {fields['reviewer_model']!r}"
        )


def validate_escalation_metadata_structure(fields: dict[str, str]) -> None:
    missing = [k for k in _REQUIRED_ESCALATION_FIELDS if k not in fields]
    if missing:
        raise ReviewValidationError(f"escalation metadata missing required field(s): {missing}")
    if fields["trigger"] not in _VALID_ESCALATION_TRIGGERS:
        raise ReviewValidationError(
            f"'trigger' must be one of {sorted(_VALID_ESCALATION_TRIGGERS)}, "
            f"got {fields['trigger']!r}"
        )
    _validate_verdict_findings_pair(fields["verdict"], fields["findings"], context="escalation")


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

    review_text = extract_review_metadata_text(handoff_at_r)
    review_fields = ch.parse_metadata_fields(review_text)
    validate_review_metadata_structure(review_fields)
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


def check_merge_eligibility(
    candidate_sha: str, publication_sha: str, review_sha: str, *, repo_root: Path = REPO_ROOT
) -> dict[str, str]:
    """Record validity (`validate_c_a_r_chain`) plus the additional,
    stricter requirement that the record is actually *merge*-eligible:
    `verdict: approved` (findings: none and reviewer-policy compliance are
    already enforced by `validate_review_metadata_structure`, and
    approval-eligibility is already cross-checked above)."""
    review_fields = validate_c_a_r_chain(
        candidate_sha, publication_sha, review_sha, repo_root=repo_root
    )
    if review_fields["verdict"] != "approved":
        raise ReviewValidationError(
            f"not merge-eligible: verdict is {review_fields['verdict']!r}, not 'approved'"
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


def validate_q(
    merge_sha: str,
    q_sha: str,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """`Q` is identified *externally*, as the caller-supplied direct child
    of `M` -- never discovered by walking `M`'s children (Git has no such
    query). `M..Q` may add exactly one post-merge artifact (status `A`)
    plus the permitted merge-record addition to `docs/LLM_HANDOFF.md`."""
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
    if len(handoff_lines) > 1:
        raise ReviewValidationError("M..Q must touch docs/LLM_HANDOFF.md at most once")

    artifact_path = artifact_additions[0].split("\t", 1)[1]
    artifact_text = read_file_at_commit(q_sha, artifact_path, repo_root=repo_root)
    artifact = vr.load_receipt_from_text(artifact_text)
    _validate_post_merge_artifact_schema(artifact)
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
    `C -> A -> R`, validates `M`, validates `Q`'s artifact, and cross-
    checks the artifact's own recorded references against the
    independently recomputed chain -- a reader recomputes, it never
    trusts the artifact's own claims alone."""
    review_fields = validate_c_a_r_chain(
        candidate_sha, publication_sha, review_sha, repo_root=repo_root
    )
    validate_merge(review_sha, merge_sha, expected_first_parent, repo_root=repo_root)
    artifact = validate_q(merge_sha, q_sha, repo_root=repo_root)

    if (
        artifact["candidate_sha"] != candidate_sha
        or artifact["publication_commit_sha"] != publication_sha
        or artifact["review_commit_sha"] != review_sha
    ):
        raise ReviewValidationError(
            "post-merge artifact's recorded C/A/R do not match the independently recomputed chain"
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
    run_dir = Path(tempfile.mkdtemp(prefix="launcher-"))
    worktree: Path | None = None
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
        return subprocess.run(
            command, cwd=str(worktree / "backend"), capture_output=True, text=True
        )
    finally:
        if worktree is not None:
            with contextlib.suppress(vw.WorktreeError):
                vw.remove_worktree(worktree)
        shutil.rmtree(run_dir, ignore_errors=True)


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
