# Claude Code project instructions

The durable engineering process is defined in `docs/LLM_WORKFLOW.md`. Before acting,
read that file, `docs/PHASE_RISK_CHECKLIST.md`, the latest two iterations in
`docs/LLM_HANDOFF.md`, the relevant product documentation/ADRs, and current Git state.
Conversation history and compacted summaries are navigation aids, never authority over
the repository.

## Workflow v3.1 (pilot)

`docs/LLM_WORKFLOW.md`'s "Workflow v3.1 pilot" section is in effect: a claim-to-evidence
matrix and a historical-defect checklist self-review before implementing a Class H
proposal introducing a new parsing form/invariant; for parser slices, two further
implementation-time self-review passes (contract-conformance, counterexample) plus a
load-bearing mutation proof for every regression test added; a rule that a
confidently-wrong case can never be an "accepted limitation" without explicit written user
approval; and a `slice_kind`/`verification_level` metadata block in every `Work done`
entry, validated by `scripts/check_handoff.py` and required by `scripts/verify.py`. This is
a measured three-**parser**-slice pilot starting with `classify_experience` — the
handoff-metadata tooling itself does not count as one of the three — not a permanent
process change; see that section's mandatory retrospective trigger and numerical
thresholds.

## Compact instructions

When Claude Code compacts this conversation, preserve only the information needed to
resume safely:

- the user's currently authorized outcome and explicit exclusions;
- current branch, HEAD, upstream state, and whether the working tree is clean;
- the active phase/slice, risk class, latest `Work done`/`Work review` verdict, and
  whether implementation, correction, review, or merge is the next permitted action;
- the active workflow version (e.g. `v3.1-pilot`, as recorded by the compaction hook) and
  the active slice's `slice_kind`/`verification_level`, when applicable;
- unresolved decisions, known limitations, failed/inconclusive verification, and any
  external side effect already performed;
- applicable identity, normalization, transaction, locking, database-safety, privacy,
  and network-request invariants;
- exact verification already completed and the checks still required;
- rollback boundary when one exists; and
- these authoritative recovery pointers: `docs/LLM_WORKFLOW.md`,
  `docs/LLM_HANDOFF.md`, `docs/PHASE_RISK_CHECKLIST.md`, `docs/ARCHITECTURE.md`,
  `docs/DATA_MODEL.md`, `docs/ROADMAP.md`, and relevant `docs/DECISIONS/` ADRs.

Compress aggressively or omit old proposals, resolved debates, superseded corrections,
full command/test output, pasted code, historical branch states, and explanations already
recoverable from Git or the handoff ledger.

After compaction, re-read current Git state and the recovery pointers before writing or
running a state-changing command. If the compacted summary conflicts with the repository,
trust the repository, report the discrepancy, and stop if it changes authorization.

### Safe proactive compaction checkpoints

The optimal checkpoint is after an approved feature has been merged, the merge record is
committed and pushed, `main` is clean and equals `origin/main`, verification is recorded,
and no next slice has begun. At that boundary, recommend that the user run `/compact` if
the session remains open.

A secondary recoverable checkpoint is a clean, pushed feature branch after `Work done` or
`Work review` has been committed and the agent has stopped at an authorization boundary.
Prefer the post-merge checkpoint because it has less active state to preserve.

Do not proactively request manual compaction while there are uncommitted changes, running
verification, an active database/network/destructive lifecycle, an incomplete handoff
entry, unresolved review corrections, or an unanswered decision that affects the current
implementation. Claude Code's built-in emergency auto-compaction must not be blocked;
the project hook snapshots recovery metadata before either automatic or manual compaction.
