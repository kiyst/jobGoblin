# 0012 — Workflow Throughput Protocol pilot

## Status

Accepted as a bounded pilot. This ADR is the durable record of the Workflow Throughput
Protocol pilot's activation slice (`workflow/throughput-protocol-pilot`, base
`6b4d9ea1a2503553c18ef5efd684fc354adf515a`). The pilot takes effect only after this
slice is formally reviewed, merged, and published (`Q` on `main`). Until then, and in any
conflict afterwards, the existing Workflow v3.2 rules in
[LLM_WORKFLOW.md](../LLM_WORKFLOW.md) control.

This ADR changes no validator, verification tool, metadata schema, reviewer-identity
rule, handoff-retention rule, executable file, test, fixture, or configuration. It does
not begin Phase 4 and does not alter Phase 3's closure
([ADR 0011](0011-phase-3-exit-audit.md)).

## Approvals

- **Astra** approved the original Workflow Throughput Protocol as a policy analysis,
  subject to binding amendments A1–A10. Every amendment is incorporated in the
  consolidated policy below.
- **Sol** then approved the amended protocol as compatible with the current Workflow
  v3.2 validators.

Both were policy consultations on a proposal. Neither is a formal `R` review of this
slice, and neither is recorded as `workflow-review-metadata`. This slice's formal review
is a separate, later Sol Medium review of its own `C`/`A`.

## Context: Phase 3 sources of delay

The committed receipts under `docs/verification-receipts/` and the handoff and roadmap
history show where Phase 3's time went. These are observations from the record, not
measured durations.

- **Review after publication.** Independent implementation review normally began only
  after a candidate's final receipt had been published. Each accepted executable finding
  then required a new candidate, a new full `gate=final` run, and a new receipt.
- **Repeated final verification.** The seven Phase 3 slices verified under Workflow v3.2
  produced 18 committed receipts:
  - skill-taxonomy foundation: 2;
  - skill classifier: 3;
  - realistic evaluation corpus: 6;
  - realistic-corpus freeze/evaluation: 1;
  - baseline correction (Go/remote): 2;
  - title classifier: 2;
  - exit audit: 2.

  Each slice also had one always-full post-merge run against `M`.
- **Long correction chains.** The realistic-evaluation-corpus slice ran from `C` through
  `C6`. Earlier, under Workflow v3.1, the experience classifier needed five correction
  rounds against that pilot's one-round target (see [ROADMAP.md](../ROADMAP.md)).
- **A counter-example.** The realistic-corpus freeze slice resolved its review findings
  F1–F15 in Stage 1, before its single receipt. It is the only Phase 3 slice with exactly
  one pre-merge receipt.
- **Manual relay.** Review requests, findings, and corrections moved between sessions
  largely by user copy and paste, even when the same information was already committed.
- **Docs-correction receipt classification.** In the exit-audit slice, the cumulative
  `base..C2` diff included `A`'s committed receipt. `scripts/verification_scope.py`
  classified that receipt as `unmapped`, which forced the correction round from
  `gate=docs` to `gate=final`. The verification tooling was correctly left unchanged in
  that slice.

## Decision

Pilot one operational change: hold independent implementation review **before** the
final receipt is published.

`contract -> immutable advisory candidate -> advisory review -> corrected final C ->
receipt/A -> formal R -> M/Q`

The pilot changes operational ordering and review timing only. The formal
`C -> A -> R -> M -> Q` chain, its validators, its metadata schema, and its meaning are
unchanged.

### Hypotheses (to be measured, not assumed)

- Earlier review reduces post-`A` executable corrections, and so reduces the number of
  receipt-producing runs per slice.
- Consolidated findings reduce review rounds.
- Repository-first handoff reduces user relay.
- None of these changes reduces assurance.

This ADR does not claim that the pilot is faster or equally safe. Those are the
hypotheses the pilot measures.

### Duration and product priority

The pilot applies to the next three product-oriented implementation slices after
activation.

This priority does not authorize skipping ADR 0011's prerequisites, enlarging slices,
bypassing safety or evidence work, suppressing findings, or avoiding necessary
migrations, database checks, or provider safeguards. Bounded work that satisfies ADR
0011's normalization-version (D1) and realistic-output protection (D2) requirements
counts as progress toward product capability. Safety and evidence blockers may interrupt
the three-slice sequence; cosmetic cleanup ordinarily may not.

### Retained controls

Unchanged:

- explicit user authorization;
- one active implementation slice;
- a clean, synchronized base;
- closed affected-file scope;
- immutable commits, with no force-push or amended workflow history;
- fail-closed affected-surface classification;
- candidate-bound verification and receipts;
- focused tests and relevant evaluator evidence;
- mutation evidence for changed safety-critical invariants;
- current reviewer independence and identity rules;
- genuine receipt publication;
- `C -> A -> R` validation;
- an approved `R` before merge;
- a `--no-ff` `M`;
- full post-merge verification against `M`;
- a `Q` containing only the permitted artifact and merge record;
- combined remote publication of `M` and `Q`;
- explicit authorization for provider, network, database, migration, credential, and
  production-write effects;
- ADR 0011's provenance, normalization-version, and realistic-output requirements.

### Pre-publication advisory review

For executable or semantic slices:

1. Freeze the reviewed contract.
2. Implement an immutable advisory-review candidate.
3. Run focused tests, static checks, relevant evaluator comparisons, and targeted
   mutation experiments.
4. The assigned primary reviewer inspects the actual candidate.
5. Record the reviewed SHA, frozen-contract identity, findings, dispositions, and any
   later reviewed changes as durable ordinary prose, or through a durable decision
   pointer.
6. Correct all accepted findings.
7. The reviewer examines all material changes through the final candidate `C`.
8. Only then run the genuine coordinator against final `C` and publish `A`.
9. Perform formal `R`.
10. Merge and publish `M`/`Q` normally.

Material changes include production code, tests and fixtures, configuration,
dependencies, schemas, behavioral or semantic documentation, and evidence that
materially affects approval. If final `C` materially differs from the last commit the
advisory reviewer inspected, the reviewer inspects the changed portion before final
verification.

Advisory review stays distinct from formal `R`. It does not use
`workflow-review-metadata`, is not called formal approval, is not an `A -> R`
transition, and is not merge authorization.

### Formal `R` remains authoritative

Formal `R` keeps unrestricted authority to reject `C`/`A` for:

- newly discovered or previously missed defects;
- contradictory evidence;
- invalid or insufficient checks;
- unresolved findings;
- incorrect affected-surface classification;
- lineage or receipt problems;
- any other concrete approval blocker.

Advisory clearance is reusable evidence, never an approval guarantee. If the formal
reviewer differs from the advisory reviewer, the formal reviewer independently assesses
enough of the implementation to own the approval.

### Reviewer assignment

Current reviewer policy is unchanged:

- Sol Medium remains the required formal primary reviewer wherever current policy or
  `scripts/check_review.py` requires it, including every Class H, parser, and tooling
  slice.
- Astra may lead policy analysis or escalation review but cannot replace the required
  formal Sol Medium role without a separately authorized policy and validator change.
- No reviewer may independently approve their own implementation or substantive
  correction.

### Verification-run target

For a normal successful executable slice, the clean-path target is one candidate-bound
final coordinator run at final `C` and one always-full post-merge run at `M`.

This is a target, not a cap or quota. Additional runs remain required for:

- failed verification;
- a replacement candidate;
- executable or material evidence changes;
- invalid evidence;
- newly discovered defects;
- migrations;
- provider or persistence risk;
- dependency changes;
- database requirements;
- security requirements;
- any other applicable risk-specific check.

Every replacement candidate requires evidence bound to its exact SHA under the existing
gate rules. A passing receipt for one candidate never covers another. Authoritative
affected surface is still calculated across the complete configured base-to-candidate
range. A direct-parent diff alone is never used to omit inherited changes.

### Consolidated review findings

Reviewers should consolidate all reasonably discoverable findings into one response
containing:

- one verdict;
- severity-ranked concrete findings;
- reproductions or counterexamples;
- one complete binding amendment table when amendments are required;
- exact replacement language for ambiguous rules;
- positive and negative cases;
- intended mutation witnesses;
- explicit user decisions still required.

This is an efficiency expectation, not a restriction on later findings. A reviewer
reports a defect whenever it is discovered, including one missed earlier. Avoidable
review churn is measured, never suppressed by policy.

### Blocking findings versus preferences

A blocking finding identifies at least one of:

- a violated frozen requirement;
- reproducible incorrect behavior;
- missing load-bearing evidence;
- invalid lineage or receipt;
- an unsafe boundary;
- internally contradictory documentation;
- a concrete maintainability defect likely to affect correctness.

Style preferences, alternative designs, speculative extensibility, and harmless behavior
outside the frozen domain are non-blocking unless the authorized contract includes them.

### Mutation-witness timing

During design, freeze the protected invariant, the intended mutation, the proposed
witness behavior, and the relevant positive controls.

After the implementation exists and before final `C` is published:

1. record normal behavior;
2. disable only the intended guard;
3. prove the named witness fails;
4. verify relevant positive controls remain stable;
5. restore the implementation;
6. prove the witness passes;
7. confirm byte-identical restoration where applicable.

A case independently caught by another guard may remain as overlap coverage but is not
an isolating witness. Existing registered guards remain mandatory. Witnesses are added or
revised only where the slice changes the protected invariant.

### Correction classification

- **Executable or semantic** (for example parser behavior, schema behavior, fixtures,
  safety invariants, executable verification logic) requires:
  - a corrected candidate;
  - focused verification;
  - renewed review of the affected material;
  - candidate-bound final evidence.
- **Evidence integrity** (for example false test totals, incorrect invocations, bad
  hashes, wrong receipt binding, incorrect reported results) requires:
  - a corrected candidate;
  - verification appropriate to the affected evidence;
  - independent re-review;
  - exact candidate binding.
- **Genuinely harmless editorial matter** is prose that alters no contract, reported
  evidence, scope, authorization, instruction, interpretation, candidate identity, or
  approval meaning.
  - Fix it before `A` whenever possible.
  - After `A`, it may remain as a disclosed non-blocking issue when meaning and evidence
    remain correct.
  - Never silently change `C`, `A`, or their meaning.
  - A specific transition validator overrides any general mechanical-edit allowance.

### Repository-first handoff

The repository is the canonical handoff. A compact current-slice entry still records:

- objective and contract identity;
- base and candidate SHA;
- exact changed paths;
- material behavior changes;
- deviations and unresolved issues;
- focused verification;
- evaluator differences;
- advisory-review SHA, findings, and dispositions;
- receipt and publication state;
- all required workflow metadata and durable external-decision pointers.

Reviewers inspect the branch, diff, tests, handoff, and receipts directly. The user
normally relays only the branch name, candidate SHA, requested reviewer role, and any
external decisions not already preserved durably. The existing latest-two-iterations
handoff rule is retained.

### Docs-correction receipt limitation

A prior receipt included in the cumulative base-to-candidate scope may classify as
`unmapped`, conservatively forcing `gate=final` during a docs correction round. During
the pilot:

- reduce this risk by reviewing substantive documentation before `A`;
- keep the fail-closed final-gate workaround when it occurs;
- do not change verification tooling inside an unrelated product slice.

Direct-parent-only authoritative scope calculation is prohibited. Any future
optimization must validate full lineage and account for inherited changes against valid
prior evidence. It requires a separately authorized proposal, tests, a final gate, and
independent review.

### Metrics

For each of the three pilot slices, measure separately:

- proposal-review rounds;
- advisory-review rounds;
- formal-review rounds;
- executable findings;
- pre-`A` correction commits;
- post-`A` correction commits;
- full-suite executions;
- receipt-producing executions;
- active implementation time;
- active review time;
- machine verification time;
- waiting and relay time;
- user copy/paste handoffs;
- first-pass semantic clearance;
- escaped post-merge defects;
- newly reachable product behavior.

Clean-path targets: one consolidated proposal review, no normal post-`A` executable
correction, one pre-merge final receipt, one post-merge full run, and compact user
relay. Failures, additional checks, and extra runs are reported honestly and are not
policy violations.

## Exit criteria

After the third product-oriented pilot slice reaches `Q`:

- compare the collected metrics with similarly risky Phase 3 slices;
- decide separately whether to retain, revise, or end the pilot.

Three defect-free slices do not by themselves prove unchanged assurance. No improvement
in throughput and no preservation of assurance may be claimed until the evidence
supports it.

## Deferred, separately unauthorized changes

- special classification of immutable prior receipt paths;
- lineage-aware verification-scope optimization;
- advisory-review metadata or schema support;
- allowing Astra to replace Sol in formal reviewer roles;
- automated cross-session relay;
- changed handoff retention;
- changed review schemas;
- validator or verification-tooling changes.

## Rollback

Stop using the pilot and return to the prior operational ordering, where review follows
receipt publication. Historical commits, receipts, review records, and merge records are
never rewritten. Pilot-era slices keep their recorded evidence.

## Consequences

- The next three product-oriented slices use pre-publication advisory review.
- Each of those slices records its advisory review and pilot metrics in its handoff
  entry.
- Workflow v3.2's validators, transitions, roles, gates, receipt binding, and safety
  policy remain controlling. Where this pilot conflicts with an existing
  validator-enforced rule, the existing rule wins until it is separately amended.
- Phase 4 is not begun or authorized by this ADR.
