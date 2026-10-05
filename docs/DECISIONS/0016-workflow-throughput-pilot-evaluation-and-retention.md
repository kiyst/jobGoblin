# 0016 — Workflow Throughput Protocol pilot evaluation and retention

## Status

Accepted with the documentation-policy slice `workflow/throughput-protocol-retention`
(risk class D, `slice_kind: docs`, `gate: final`), base
`6752dcdc0ce1b57c0af164aa217d3181566086bd` (`Q` of the Phase 4 S2b merge). It takes
effect only after this slice is formally reviewed, merged, and published (`Q` on `main`).
Until then, and in any conflict afterwards, the existing Workflow v3.2 rules in
[LLM_WORKFLOW.md](../LLM_WORKFLOW.md) control.

This ADR records the evaluation that
[ADR 0012](0012-workflow-throughput-protocol-pilot.md)'s exit criteria required after its
third pilot product slice reached `Q`. ADR 0012 is unchanged and remains the record of
the pilot itself. This ADR changes no validator, verification tool, metadata schema,
reviewer role, receipt-binding rule, handoff-retention rule, executable file, test,
fixture, or configuration.

## Decision

**Retain the Workflow Throughput Protocol with O1–O5 as bounded operational revisions.**

ADR 0012 limited the pilot to its next three product-oriented slices. Those slices were
Phase 4 S1, S2, and S2b, and all three reached `Q`, so that authorization is exhausted.
From this slice's `Q`, the ADR 0012 operational ordering continues as amended by O1–O5
below. Every retained control listed in ADR 0012 remains in force.

## Contract and attribution

The contract is a create-only, gitignored runtime packet,
`.claude/runtime/workflow-throughput-protocol-retention-contract.md`, SHA-256
`369a6c20c9135d087a50168576c5a1dff886b120ea9e8088743884e6eec4608a`. It is not committed.
In precedence order, it contains:

1. the user's adoption decision and authorization;
2. Sol Medium's compatibility review, approved with binding amendments E9–E13;
3. Astra's binding amendments E1–E8, as relayed in the user's prior authorization;
4. the implementer's revised pilot evaluation and O1–O5, except where E9–E13 supersede
   them;
5. ADR 0012 and the existing Workflow v3.2 rules.

> The evaluator did not receive Astra’s full response. This contract incorporates only
> E1–E8 as relayed in the authorization and makes no claim that any additional Astra
> ruling was reviewed or adopted.

The Astra and Sol reviews were policy consultations on the evaluation. Neither is a
formal `R` for this slice, and neither is recorded as `workflow-review-metadata`. This
slice's formal review is a separate Sol Medium review of its own `C`/`A`.

## Evaluation

The evaluation was reconstructed from Git history, committed receipts, post-merge
artifacts, and handoff and merge records. The evaluation checkpoint is the published
`main` commit `6752dcdc0ce1b57c0af164aa217d3181566086bd` (committed 2026-10-04T22:18:42Z).

### Pilot metrics

| Metric | S1 | S2 | S2b |
|---|---|---|---|
| Risk class / receipt gate | H / final | H / final | H / final |
| Proposal-review rounds | 1 | 1 | 1 |
| Advisory-review rounds | 2 | 1 (no findings) | 2 |
| Formal-review rounds | 1 (no findings) | 1 (no findings) | 1 (no findings) |
| Advisory findings: executable / evidence-integrity / documentation | 2 / 0 / 1 | 0 / 0 / 0 | 1 / 1 / 1 |
| Semantic correction commits before `A` | 1 | 0 | 1 |
| Handoff-only commits before `A` | 1 | 1 | 1 |
| Correction commits after `A` | 0 | 0 | 0 |
| Committed receipts | 1 | 1 | 1 |
| Known full-suite runs | 2 | 2 | 5 |
| User relays | 8 | 7 | 9 |
| First-pass semantic clearance | no | yes | no |
| Escaped post-merge defects | none known | none known | none known |
| Newly reachable product behavior | none (by design) | none (by design) | none (by design) |

Git proves the committed receipts. Receipt-producing attempts, including failed or
abandoned ones that leave no committed receipt, are known only from the implementer's
handoff entries, which report one attempt per pilot slice.

### Known full-suite runs

There are nine known full-suite runs, across every actor for which evidence exists:

- **Six coordinator runs, all passing.** Each pilot slice had one candidate-receipt run
  at final `C` and one post-merge run at `M` (3,674, 3,909, and 4,240 tests for S1, S2,
  and S2b).
- **Three S2b runs outside the coordinator,** recorded in S2b's handoff entries:
  - the implementer at advisory candidate `bfc3b93` (4,193 passed);
  - the adversarial self-review agent at `bfc3b93` (result not recorded);
  - the implementer at corrected candidate `9e86ba9` (4,240 passed).

  Their durations are not recorded.

Neither advisory reviewers nor formal `R` recorded a full-suite run in any pilot slice.
Each formal `R` relied on the receipt for the full suite. Unrecorded runs by any actor
remain unknown, so this is a count of known runs, not a project-wide cost metric.

### Committed receipts

| Group | Slices | Committed receipts | Per slice |
|---|---|---|---|
| Pilot (all risk class H) | 3 | 3 | 1.00 |
| Phase 3, risk class H (the comparison group) | 6 | 16 | 2.67 |
| All Phase 3 Workflow v3.2 product slices | 7 | 18 | 2.57 |

**The comparison group.** It consists of the Phase 3 product slices verified and merged
under Workflow v3.2 whose receipts record risk class H, which matches all three pilot
slices.

| Slice | Committed receipts |
|---|---|
| Skill taxonomy | 2 |
| Skill classifier | 3 |
| Realistic evaluation corpus | 6 |
| Freeze/evaluation | 1 |
| Go/remote baseline correction | 2 |
| Title classifier | 2 |

The Phase 3 exit audit is the seventh v3.2 product slice. It is excluded from the
comparison group because it is risk class D and documentation-only, but it is included
in the all-slices row.

Together these have 10 receipt-bearing correction candidates after their first A. All 10
changed executable code, tests, or fixtures; none was handoff-only. The excluded D/docs
exit-audit slice separately contained a handoff-only C3 gate-escalation correction.

The skill-classifier slice also contains `17f6f24`, a commit after that slice's first `A`
that changed only `docs/LLM_HANDOFF.md`. It is not a correction candidate and carries no
receipt.

Phase 3 is a historical comparison group, not a controlled baseline. Sharing a risk class
does not make the tasks closely matched:

- Phase 3 was parser, corpus, and evaluator work.
- The pilot was an offline provider adapter, a pure composition, and content conversion.
- The Phase 3 freeze/evaluation slice resolved findings F1–F15 before its candidate and
  then needed one receipt. It is a historical precedent for the mechanism, not a control.

### Timing

Complete end-to-end timing is unavailable; recorded verification-step durations are
available.

Recorded durations are the sums of the committed `duration_seconds` step values:

- **Phase 3 risk class H receipts:** 6,158.988 seconds across 16 receipts, averaging
  384.937 seconds per receipt.
- **Pilot candidate receipts:** 1,190.484 seconds across three receipts.
- **Pilot post-merge runs:** 1,238.609 seconds across three runs.

These are recorded coordinator-step durations only. The following remain unknown:

- authoring time;
- reviewer time;
- waiting time;
- relay time;
- coordinator overhead outside the recorded steps;
- unrecorded local, self-review, and advisory verification overhead, including S2b's
  three runs outside the coordinator.

No recorded verification duration is a measure of delivery time.

Duration evidence, pilot:

- S1 receipt:
  `docs/verification-receipts/d9813b492121b78e2fee35113f033eecd59f0a6e/6489709d-6ab6-4def-ad56-a9da7729de52.json`
- S1 post-merge:
  `docs/post-merge/48cc5c7204ec34ad911d7d9ce9839d9cc49777ea/f788f2db-78ca-46db-8847-7c6fd696728a.json`
- S2 receipt:
  `docs/verification-receipts/2a3f50d681d2a97b9adc2cf097f933ce4507ead2/5b39efd7-64c7-491f-8ca0-98803789b1e4.json`
- S2 post-merge:
  `docs/post-merge/f509e80f68505dbdee7d8aed5f2748b805eaec4d/eb15c344-c68f-42a9-8df0-97739b73e953.json`
- S2b receipt:
  `docs/verification-receipts/505e4c1e1480b19fcecc1f0cbbdec5d3f2e1b01e/9a62f701-d97c-4bb9-868a-8f7f796b1686.json`
- S2b post-merge:
  `docs/post-merge/692c420e47f0e0b23acc8be6aec020b7eb3377d9/08dcbdd3-9ba0-47e3-9ed4-5ca7ee1c0e6a.json`

Duration evidence, Phase 3 risk class H receipts, all under `docs/verification-receipts/`:

- skill taxonomy:
  - `138f68d8aee7931662877c9971e85ecd51ffa0c9/d4b54862-f2f1-425e-b12b-5636653259db.json`
  - `c08e89d3fe073ac34cada82e52df3710cb9e2c3d/2231dafb-4057-4b1b-9c86-f51780a18907.json`
- skill classifier:
  - `109a3070375be1b8a412abc3dbbbbc76dc379290/769a9115-2e13-4c92-abfe-6c37a92e26e9.json`
  - `e867450a12d63fd961cfe691cb1e84cf406a292e/9e01075f-5141-4137-9d1d-870fb2811550.json`
  - `0dbdbc54443237d35b0f139910eb84d11c06b29d/b8a569cb-ce08-462e-8172-372f42e00b07.json`
- realistic evaluation corpus:
  - `a0ddad9489c9020b1c1921d4dac182e7a42ef3d0/788ec89b-c81f-41c0-859b-ded428c2d466.json`
  - `f9f531eb568027ebad311404ed05cba9c28ab0c2/2b6174d6-138e-4cd9-b1f8-7b770fdbd282.json`
  - `5aa1a57271b2317885e154e0de5e7b4cd183d94e/c394be69-b724-44ab-8e26-05bdce25cfba.json`
  - `61a18819abb509ab0a5f74c60924cc968dc1499f/16ea83c7-ea7a-4a5e-aea8-e53e3c4b8c1a.json`
  - `e5a72f6926b826ca9af8cdb93e5368d1fb8ddae8/59ee72fa-ca86-4596-bf9c-a8e971cf9ed2.json`
  - `4771c2df38a7c913a852fa5cfe24dc795c5d587f/69759bd7-d539-4417-8685-730900e4db20.json`
- freeze/evaluation:
  - `03609018215285cca21dd31fc126978fe2de8d15/338d5c4b-37fd-47dd-a220-f67919ca45de.json`
- Go/remote baseline correction:
  - `467ec75273c3bee00e939c720cba072b2b7754d1/24a31360-502b-4c35-8be3-a35374679077.json`
  - `14083dd27c73609e67bdaac2793f3769bdb367e7/dcbb1847-7130-4f78-a833-b51732754965.json`
- title classifier:
  - `e2573bc9792e74f60b59fd2b2974141a1a32302b/d8ea060c-298d-473e-93a6-aa6d32b7c7d7.json`
  - `4c6f933fb3112357f6a96f751115776e74831d73/1541f94b-45fe-49ef-af52-2afd39fcb367.json`

### User relays

The pilot recorded 24 user relays:

- **19 necessary:** decisions, authorizations, complete review content, and merge
  authorizations.
- **2 non-actionable:** both were S2b correction authorizations that arrived without the
  review they depended on. Their cause is not recorded.
- **3 indeterminate:** an identical re-paste in each slice. None supplied new content,
  and none has a recorded reason.

These counts show continuing coordination friction. They do not prove improvement or
regression, because no matched Phase 3 relay counts exist.

### Hypotheses

1. **Earlier advisory review reduces executable corrections after `A`.** The pilot had
   none, against 10 receipt-bearing correction candidates in the comparison group. S1's
   two P1 findings and S2b's truncation finding were resolved before `A`. This is
   consistent with the hypothesis but not proved: there are three slices, the tasks are
   unmatched, and there is no counterfactual.
2. **It reduces receipt-producing runs.** This is supported for committed receipts (1.00
   per slice against 2.67). It is not established for all attempts, because Phase 3
   attempts are not recorded, and it is not established for elapsed time.
3. **Consolidated review reduces review rounds.** Inconclusive. The pilot slices used
   three or four rounds each, and two of them needed a second advisory round. Rounds
   moved earlier and no longer each required a receipt, but no reduction in their number
   is shown.
4. **Repository-first handoff reduces user relay.** Not determinable without matched
   historical counts. Complete review text still travelled by user relay.
5. **Assurance is preserved.** See Assurance below.

### Assurance

All three pilot slices reached `Q` with passing recorded verification:

- candidate-bound receipts, independently recomputed as approval-eligible;
- `C -> A -> R` and merge-eligibility validation;
- full post-merge runs with 34 of 34 registered witnesses passing;
- publication validation.

Advisory review found real defects before `A`. In S2b, the self-review agent disclosed a
silent-truncation behavior, and the advisory review turned it into an executable
correction. No escaped defect is currently known.

The limits on this evidence:

- At this evaluation checkpoint, all three pilot Q commits are less than 24 hours old,
  with S2b published the same day; escaped defects are therefore largely unobservable.
- Nothing in the pilot is reachable at runtime, and its evidence is offline or synthetic.
- The same reviewer performed advisory and formal review, and formal review found nothing
  in any pilot slice. The record cannot distinguish thorough advisory review from formal
  review that anchored on advisory clearance.

This supports continued use but does not prove equal assurance.

### Throughput

The pilot used fewer committed receipts per slice. Recorded total full-suite executions
show a smaller reduction than receipt counts, but incomplete historical execution records
and unmatched task scope prevent attributing a precise time saving to the protocol.

S2b's three runs outside the coordinator each had a recorded occasion: the implementer's
two runs each followed changes to shared adapter behavior, and the self-review agent's run
had no recorded reason or result. They are not presumed to be waste.

### Not established

This evaluation does not establish:

- measured end-to-end delivery-time improvement;
- a controlled Phase 3 comparison;
- unchanged assurance;
- improved relay frequency;
- generalization to live-provider, runtime-reachable, or persistence work;
- production readiness of anything delivered by the pilot slices.

## Operational revisions O1–O5

These revisions change operational practice only. Where any of them conflicts with an
existing validator-enforced rule, the existing rule wins until it is separately amended.

### O1 — Pre-advisory verification default

Before advisory implementation review, the default evidence is:

- focused tests;
- static checks;
- relevant evaluator comparisons;
- contract tests;
- targeted mutation evidence.

Routine full-suite execution is normally reserved for:

- genuine final `C` verification; and
- post-merge `M` verification.

This is a default, not a prohibition or a closed exception list. Any concrete risk-based
reason may justify an earlier broad run. Required checks always win. Additional runs are
not presumed waste without examining their purpose and results.

### O2 — Actionable review evidence

An implementation, advisory, or formal review of an immutable repository candidate is
actionable only when it gives the verdict, an accessible immutable reference to the
complete findings or amendments, the reviewed candidate SHA, and the contract identity. A
proposal or policy review for which no candidate commit exists instead requires an
accessible immutable proposal or decision identity and the applicable repository base; it
must not invent a reviewed candidate SHA.

If no durable accessible reference exists, relay the complete actionable review.

A repeated message may be acknowledged without action only when:

- it has already been handled;
- repository state is unchanged;
- it provides no new authorization, evidence, finding, or branch change.

Otherwise, reassess current state before acting.

### O3 — Product capability statement

Every subsequent authorized product slice must state the concrete dependency it removes
or the newly reachable capability it creates. This requirement does not force premature
runtime wiring or weaken prerequisites.

### O4 — Formal-review evidence reuse and authority

Formal `R` must record:

- the reviewed advisory SHA;
- material changes through final `C`;
- how those changes were reviewed;
- checks independently rerun;
- evidence inspected or relied upon;
- unresolved limitations.

This permits formal R to reuse advisory evidence. The formal reviewer still determines the
proportionate review depth, independently verifies C/A lineage, receipt integrity, all
material changes through final C, and enough semantics to own the verdict. Nothing
presumes advisory clearance, caps formal-review scope, or prevents a complete semantic
rereview. Formal R’s unrestricted authority to reject is unchanged.

### O5 — Incident assessment trigger

Any escaped defect or post-`A` executable correction must:

1. be handled immediately under existing controls;
2. trigger a bounded assessment of whether advisory-review ordering contributed;
3. produce a decision to retain, revise, pause, or end the adopted ordering.

This is an assessment trigger. It is not:

- automatic rollback;
- emergency tooling authorization;
- permission to bypass the workflow;
- permission for S2c;
- permission for provider contact;
- permission for persistence or D1;
- permission for reviewer-role or schema changes.

## Retained and deferred

Unchanged:

- validators;
- verification tooling;
- metadata schemas;
- reviewer roles, including Sol Medium as the required formal primary reviewer wherever
  current policy or `scripts/check_review.py` requires it;
- receipt binding;
- the `C -> A -> R -> M -> Q` chain;
- handoff retention;
- registered-witness policy;
- affected-surface calculation;
- merge and publication rules;
- explicit user authorization and user-only merge authority;
- ADR 0011's provenance, normalization-version, and realistic-output requirements.

Not implemented, each requiring its own separately authorized proposal:

- automated cross-session relay;
- receipt-path classification changes;
- lineage-aware verification optimization;
- a new metrics framework;
- another model-approval layer.

ADR 0012's deferred list is otherwise unchanged.

## Next assessment

The next workflow assessment happens at Phase 4 exit. An O5 incident assessment happens
earlier whenever O5 is triggered. Slices continue to record ADR 0012's existing metrics
in their handoff entries; no new metric, field, schema, or tool is introduced.

## Rollback

Stop using the adopted ordering and return to the prior ordering, where review follows
receipt publication. Historical commits, receipts, review records, and merge records are
never rewritten.

## Consequences

- Advisory implementation review before final `C` continues as the operational ordering
  for executable or semantic slices, with O1–O5.
- Workflow v3.2's validators, transitions, roles, gates, receipt binding, and safety
  policy remain controlling.
- This ADR does not authorize S2c, Greenhouse or other provider contact, persistence,
  D1, S3, or S4. Each still requires separate explicit user authorization.
