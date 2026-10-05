# LLM Engineering Handoff

Purpose: this file is the shared communication ledger between the implementing LLM and
the reviewing LLM. Update it at the end of every bounded implementation or correction
pass so the user does not have to copy status messages between agents.

Canonical operating process: [LLM_WORKFLOW.md](LLM_WORKFLOW.md). Both agents must read
it before proposing, implementing, correcting, or reviewing work. This file is the
short-lived ledger; `LLM_WORKFLOW.md` defines roles, risk classes, verification depth,
and the mechanical-documentation correction rule.

This ledger records only the two latest completed iterations. Git remains the source of
truth for diffs and rollback; record commit or base references whenever they exist.

## Required workflow

1. Before working, read `LLM_WORKFLOW.md`, the master project documentation,
   `PHASE_RISK_CHECKLIST.md`, and both iterations in this file.
2. The implementing LLM completes only the approved slice, runs the required checks,
   and fills in a new `Work done` section. It must not fill in its own `Work review`.
3. The reviewing LLM independently inspects the repository and actual diff, runs
   proportionate checks, gives the user its findings, and writes the same findings in
   that iteration's `Work review` section. A review does not authorize code changes.
   Codex may directly resolve only a mechanical documentation defect that satisfies
   every condition in `LLM_WORKFLOW.md`; it records that edit in a separate review
   commit.
4. The implementing LLM reads the latest review on its next run. It changes only
   findings approved by the user, then records that correction pass as the next
   iteration.
5. Never allow both LLMs to edit implementation files simultaneously. Only the active
   implementer writes code; the reviewer writes its `Work review` and may make only the
   mechanical documentation fixes permitted by `LLM_WORKFLOW.md`, unless the user
   explicitly transfers broader implementation ownership.

## Two-iteration rotation rule

- Keep at most two completed iterations below.
- When adding a third iteration, delete only the oldest iteration, retain the newer
  iteration, and append the new one after it.
- Renumber the retained entries as `Iteration 1` and `Iteration 2` so `Iteration 2` is
  always the newest.
- Never erase an iteration whose `Work review` is still pending.
- Do not rewrite the other LLM's entry. Add corrections or disagreements to the next
  appropriate section and support them with file paths, tests, or documentation.

## Git workflow

Agents may automatically commit and push completed passes to the current task branch.
The user remains the only merge authority.

After completing an authorized pass and updating the agent's assigned handoff section:

1. Run all validation required for the bounded slice.
2. Inspect `git status` and the staged diff. Confirm that no secrets, `.env` files,
   caches, virtual environments, database files, generated artifacts, unrelated user
   changes, or other out-of-scope files will be committed.
3. Commit only files belonging to the authorized pass, using a descriptive conventional
   commit message.
4. Push only to the current task branch. Never push directly to `main`.
5. Never merge, force-push, rewrite or rebase shared history, delete branches, or create
   tags without explicit user authorization.
6. Stop after pushing and report the branch, commit hash, validation results, and any
   uncommitted files. Wait for the next agent or user approval.

Role boundaries:

- The implementing LLM may commit implementation files and its own `Work done` entry.
- The reviewing LLM may commit its own `Work review` entry and mechanical documentation
  fixes permitted by `LLM_WORKFLOW.md`; all other changes require explicit user
  authorization.
- Neither LLM may rewrite the other LLM's handoff content.
- Only one LLM may edit or perform Git writes at a time.
- A successful push is a checkpoint, not approval to begin another slice.
- Only the user may approve merging a task branch into `main`.

Recommended history per bounded slice:

```text
feat(phase-N): implement the approved slice
docs(review): record independent review of the slice
fix(phase-N): address approved review findings
docs(review): verify the corrected slice
```

Do not create an extra commit merely to insert that same commit's hash into its own
handoff entry. Before committing, record the branch and write `Ending commit: this
commit`. After committing, report the actual hash in the agent's final response. The Git
history already binds the handoff entry to its commit; the following agent must resolve
and record the actual commit it reviewed.

Keep new entries concise—target roughly 40 lines per agent section. Record command names
and exact outcomes, but do not narrate every individual test; Git and test files preserve
that detail.

---

## Iteration 1

### Work done

- Date/agent: 2026-10-04, Claude (implementer). Branch
  `phase-4/greenhouse-content-mapping-s2b`, base
  `e670575d5b05395cb9eeb2ec84833cc0034c7002` (`Q` of the S2 merge). The first immutable
  pre-publication advisory candidate was `bfc3b93447417344da769f2f2e4009db78547f70`; it is
  preserved unamended and superseded only by its correction child. Ending commit: this
  commit, advisory correction 1 (the direct single-parent child of `bfc3b93`), for Sol
  Medium's narrow advisory re-review. Neither is final `C`: no coordinator run, receipt,
  `A`, or formal review exists.
- Slice: Phase 4 S2b, offline Greenhouse content conversion and strict `PostingInputs`
  mapping, plus
  [ADR 0015](DECISIONS/0015-greenhouse-content-conversion-and-posting-input-mapping.md).
  Pilot product slice 3 of 3 under ADR 0012. Risk class H, `slice_kind: parser`,
  `declared_gate: final`, fixture `backend/tests/fixtures/evaluation/phase3_realistic_corpus.json`
  (30 records; the reconstructed-envelope source). Focused selector:
  `tests/test_greenhouse_content.py tests/test_greenhouse_posting_inputs.py`: **331** tests
  at this commit (265 + 66); 284 (219 + 65) at `bfc3b93`.
- Contract identity: frozen contract `.claude/runtime/phase4-s2b-frozen-contract.md`
  (gitignored, never committed), SHA-256
  `e409427bccfecd4f3f04c839f47826f5727355788ceab8fee061e6985e519df2`. Precedence: the
  user's decisions U1–U4 and requirements, then Sol Medium's binding amendments A1–A20
  and corrected mutation inventory W1–W19, then the proposal. Correction packet
  `.claude/runtime/phase4-s2b-correction1-packet.md` (gitignored), SHA-256
  `5d68c43a8537f629b7cd7c8392aa406297899bd82c0d7927b4d3c6e4588dcee8`: Sol's "Changes
  requested" review and the user's correction authorization, verbatim. The original
  contract packet is unmodified.
- Files (exact closed nine-path list):
  - `backend/app/providers/greenhouse_content.py` (new);
  - `backend/app/providers/greenhouse_posting_inputs.py` (new);
  - `backend/app/providers/greenhouse.py` (`content_mode`, conversion, partition, warnings);
  - `backend/tests/test_greenhouse_content.py` and `test_greenhouse_posting_inputs.py` (new);
  - `docs/DECISIONS/0015-…` (new);
  - `docs/ROADMAP.md`: the S2b bullet, plus the S2 bullet's merge SHAs, replacing its
    stale "S2b and later slices remain unauthorized" sentence (disclosed: beyond the S2b
    bullet itself);
  - `docs/ARCHITECTURE.md`: §4 tree rows (including S1's missing `greenhouse.py` row), the
    `providers/` dependency row's single named exception for the bridge, a §5 note, and a
    §10 note;
  - this file (rotation: S1's iteration removed, S2's retained byte-for-byte as
    Iteration 1).
- Material behavior:
  - **Board mode.** `GreenhouseBoard.content_mode` is `disabled` (default) or
    `declared-double-escaped`. Any other value raises the fixed A3 message.
  - **Disabled boards** (Sol's R1 interpretation). There is no selective or keyed access
    to, interpretation of, or conversion of `content`. Field-agnostic source parsing and
    the whole-record deep copy that preserves `raw` may traverse it without branching on
    its value.
  - **Declared boards.** `description` is the converter's text or `None`. Only
    `converted` is neutral. Every other outcome keeps the job with `description=None` and
    makes the board partial (`incomplete_results`, `possibly_incomplete`, partial health).
  - **Warnings.** Source-wide and token-free, one per outcome, sorted:
    `greenhouse content_unconverted=<outcome> count=<n>`.
  - **Unchanged from S1:** `raw` (deep, equal, non-aliased, equal hash), record validity,
    skipping, completeness, labels, and `compensation_text=None`.
  - **Converter.** It reimplements the frozen script's declared-mode algorithm exactly.
    - Order: mode, type (exact `str`), 200,000-code-point input cap, blank, encoding,
      one decode, extraction, meaningfulness, 100,000-code-point output cap. Nothing is
      truncated.
    - Only `RecursionError` from the parser becomes `parser_error`.
    - End-of-input integrity (correction 1): an unfinished construct that swallows the end
      of the input yields `malformed_truncated_markup` (see advisory review round 1).
  - **Mapper.** It reads only `provider`/`source`/`title`/`description`/`location` and
    returns those three values unchanged, with fixed errors.
  - Nothing registers, imports the mapper, or persists. No salary, no schema field, no
    parser, taxonomy, corpus, evaluator, or script change.
- Evidence identities (pinned in tests):
  - oracle script canonical-LF `fff4b1c0…cd06f` and its tests `2bdf3014…9fcd1`;
  - corpus canonical JSON `ca6e1291…8f00` and committed content
    `1863541bb784419be16bf4ffcf88bf1b4408c951a03b12008e9645e9f18e6930` (authoritative,
    Sol's R5; the earlier abbreviation `…6e930` was a typo and caused no corpus change);
  - canary `690b0a5d…db4d5`.

  The A16 bounded claim appears verbatim in ADR 0015 §9 and the test module docstring.
- Verification at the first advisory candidate `bfc3b93` (no receipt-producing
  coordinator run):
  - focused: **284 passed**;
  - acceptance selection, i.e. the focused modules plus unchanged
    `test_greenhouse_provider.py`, `test_greenhouse_html_convert.py`,
    `test_canary_greenhouse_mapping.py`, both S2 modules, and the D2 module: **857 passed**;
  - `tests/contracts`: **130 passed**;
  - full suite: **4,193 passed**;
  - `ruff format --check`, `ruff check`, `mypy` on the five Python files: clean;
  - evaluator `python -m scripts.evaluate_phase3_corpus`: SHA-256 `87a92187…01de6`,
    91,994 bytes, unchanged;
  - `check_handoff`, `check_repo`, `git diff --check`, nine-path scope: passed.
- Mutation experiments W1–W19 at `bfc3b93` (superseded as acceptance evidence by the
  correction-1 rerun below, because this v1 driver's result parsing was lossy; driver
  `.claude/runtime/phase4-s2b-mutation-driver.py`
  `bd6d9844d59dd4df50739639f79e27b9ae11b48d3cdde305bc08aee328385ed5`, log
  `phase4-s2b-mutation-log.json`
  `c06cfd5a412f9ef3a34dab67cdaf0c98bbba71d41f1d911290087e7c4c568c71`).
  - **Procedure.** Each experiment applied one unique anchor to one production file. The
    witness and controls passed beforehand. Under the mutation every named witness
    failed (W3 including both the raw `&ltfoo` and post-decode `&amp;ltfoo` cases) and the
    corrected controls passed. The file was restored byte-identically and the witness
    passed again.
  - **Restoration hashes,** before and after every experiment:
    - `greenhouse_content.py` `c1999524d8fa046195d954c00a9560e02feb169ed7f141352ce9e9b3a4a2adef`;
    - `greenhouse.py` `6c486d20c13eda813ef47315aa1c319a954cf03dc60b7455c0a7d19f73b22ed8`
      (CRLF working-tree form; its committed LF blob is
      `f20ee294dfe2f37da68deb238a5422db9bf2dd244efde0c9f154fe38903edf63`. The other two
      files are LF on disk and equal their committed blobs);
    - `greenhouse_posting_inputs.py` `00809ff005012f29f569df25a52e311c310e72802d7bf0e08aaca8e0b955fd2e`.
  - **Overlaps,** from the full overlap selection in the log. These are disclosed and none
    is a control:
    - W1–W5, W8, W9: oracle-differential cases;
    - W1/W2: conversion-warning and partition tests;
    - W4: the W5 control and the `<script>`-only abstention case;
    - W6: the code-point and order tests;
    - W8: the parser-sensitive goldens;
    - W10/W11: S1 `t05`/`t07` and the canary and mixed-board tests;
    - W12/W13/W15–W17: the canary test;
    - W14–W18: `mapper_ast_boundary` and/or the access trace;
    - W17: the corpus round trip, normalize-flow, and direct-mapping tests;
    - W19: the no-network-primitive import test.
  - **Driver defect.** The v1 driver keyed pytest results on node ID up to the first
    space, so parametrized IDs containing spaces were truncated and could collide (for
    example, the W3 control showed 2 of its 3 cases). Corrected in correction 1.
- Deviations and disclosures for Sol:
  - **Reconstruction escaping.** The reconstruction uses `html.escape(…, quote=False)` at
    both layers. The proposal's read-only check implied default quoting; the reviewer
    verified that both variants round-trip all 30 records.
  - **Hash abbreviation typo.** The proposal's (and so A15's) abbreviation `1863541b…6e930`
    was a typo; the authoritative full hash (R5) is the value pinned, and no corpus change
    occurred.
  - **Access guard scope.** The A5 test mapping raises on keyed access (`[]`, `get`, `in`,
    `pop`, `setdefault`), not on `items()`/`values()`. Deep copying for `raw`, which A13
    requires, iterates items.
- Adversarial self-review at `bfc3b93` (a fresh read-only subagent, before commit). It
  reported no P1;
  its 60,000-input differential fuzz against the oracle found 0 disagreements beyond the
  documented abstentions. It accidentally left an empty `%TEMP%\claude_fuzz.py` outside
  the repository. Fixed before commit:
  - **P2-1.** Unterminated comments, quoted attributes, and `<letter` silently truncate
    while staying `converted` (inherited from the oracle and `html.parser`). At `bfc3b93`
    this was only disclosed and pinned; Sol rejected that disposition (R2), and correction
    1 makes it fail-closed.
  - **P2-2.** Output depends on the interpreter's `html.parser`, which the oracle shares.
    Disclosed as verified on CPython 3.12.13, with literal golden expectations for
    parser-sensitive inputs. The catch is not broadened.
  - **P2-3.** The "never touched" wording overclaimed, since the deep copy for `raw` still
    carries `content`. Reworded in the code and ADR.
  - **P3s.** The W11 control was renamed `test_description_populated_on_declared_board`.
    ADR 0015 now states that ADR 0014's U6 list-endpoint deferral moves to S2c. The
    ARCHITECTURE tree alignment was fixed. The hash typo, reconstruction quoting, ROADMAP
    S2 edit, and access-guard scope are disclosed above.
- Known limitations:
  - no captured raw `content` or list-endpoint encoding evidence, and U6 moves to S2c;
  - synthetic HTML only;
  - table and section content merges, `noscript`/`template` text is kept, and escaped
    code examples are rejected;
  - only end-of-input truncation is fail-closed: text swallowed mid-input by a construct
    that a later quote or `-->` closes is still lost silently (a narrowing disclosure of
    the original truncation limitation, which is otherwise now fail-closed);
  - interpreter-dependent parser behavior;
  - unredacted in-memory text;
  - no mode or outcome traceability on the job (A11), which is not D1;
  - D1 unsatisfied; salary excluded (L4); ten unproven components; title smoke-only;
    exposed 30-record corpus;
  - nothing runtime-reachable; mutation experiments not registered.
- Advisory review round 1 (Sol Medium, pre-publication advisory review of `bfc3b93`;
  advisory prose only, not formal review metadata). Verdict "Changes requested".
  - **P2, malformed markup silently discarded parser input while reporting success**
    (Sol's reproductions `<p>Intro</p><!-- note <p>Requirements: Python</p>` →
    `Intro`, `<p>Intro</p><a href="x>More</a><p>Requirements: Python</p>` → `Intro`,
    `A<B rest` → `A`). *Accepted and corrected:*
    - The new closed outcome `malformed_truncated_markup` covers this.
    - After decoding, the parser is fed the source, then one internal marker element
      `<NAME></NAME>`. `NAME` is `ghintegrity-` plus one more `z` than the longest such
      run in the decoded text (case-insensitive), so it is absent from the source. It is
      pure and linear, emits no text or boundary, and is not counted by either cap.
    - After `close()`, exactly one ordered start/end pair is required; otherwise the
      outcome is the new one, with `text=None`.
    - Precedence: `parser_error`, then `unclosed_suppressed_element` (open
      `script`/`style`, recorded before the marker is fed), then
      `malformed_truncated_markup`, then meaningfulness, then the output cap.
    - The adapter (unchanged) keeps the job with `description=None`, makes the board
      partial/incomplete, and warns exactly
      `greenhouse content_unconverted=malformed_truncated_markup count=<n>`.
    - Converted text still equals the oracle wherever this module converts.
    - Disclosed behavior changes:
      - a trailing unfinished fragment (`A</`, `x</p`, `<p>Intro</p><!`) now abstains;
        `A</` previously converted to `A</`;
      - an unclosed raw-text element (`title`, `textarea`, `xmp`, `iframe`, `noembed`,
        `noframes`, `plaintext` on CPython 3.12.13) now abstains;
      - three oracle numeric fragments (`&#60x`, `a&#60b`, `&#x3cg`) now abstain.
  - **P2, the mutation log lost parametrized-node evidence.** *Accepted and corrected:*
    - the gitignored v2 driver reads per-run pytest JUnit XML (xunit2) and aborts on a
      duplicate or empty result;
    - a self-check proves distinct, exact IDs containing spaces (`[a b]`, `[a  b]`,
      `[a c]` failing, `[x y z]`), at the root and in a `tests/` package;
    - the complete W1–W20 inventory was rerun.
  - **P3, "no database access" overstated the boundary.** *Accepted:* replaced with the
    exact wording below.
  - **Dispositions:**
    - R1: recorded under Material behavior.
    - R2, R3, R4: corrected as above.
    - R5: recorded under Evidence identities.
    - R6: scope items confirmed in scope.
    - R7: W1–W19 are unchanged, except that W5's anchor follows its edited decision line.
- Correction 1 (this commit; six paths: `greenhouse_content.py`, both new test modules,
  ADR 0015, ROADMAP, this file):
  - **Unchanged:** `greenhouse.py`, `greenhouse_posting_inputs.py`, ARCHITECTURE, every
    fixture, the oracle, corpus, evaluator, dependencies, schemas, and registration.
  - **Cumulative `base..HEAD`:** still exactly the original nine paths.
  - **Tests:**
    - focused **331 passed**;
    - acceptance selection **904 passed**;
    - `tests/contracts` **130 passed**;
    - full suite **4,240 passed**.
  - **Checks:**
    - `ruff format --check`, `ruff check`, and `mypy` on the five Python files: clean;
    - evaluator SHA-256 `87a92187…01de6`, 91,994 bytes, byte-identical;
    - `check_handoff`, `check_repo`, `git diff --check`, direct-parent six-path and
      cumulative nine-path scope: passed.
  - **Mutation experiments W1–W20.** Driver
    `.claude/runtime/phase4-s2b-mutation-driver-v2.py`
    `7151c79fb7ebe08d57a2623d2da7bf9fe823d7720c27a2ae71a494fb4f7761b5`, log
    `phase4-s2b-mutation-log-correction1.json`
    `514ac00d46ea1a3b00e7b04366adaa5067ee7355e4359683fc9ebce5c745073e`. The self-check
    passed.
    - All 20 passed. Each had one unique anchor in one production file, a green
      baseline, every named witness failing, and every control green. Each file was
      restored byte-identically, all three production hashes were re-verified, and the
      witness passed again.
    - Lossless witness/control node counts (failed/total, controls): W1 6/6, 1; W2 4/4, 1;
      W3 10/10, 3 (including `[&ltfoo]` and `[&amp;ltfoo]`); W4 1/1, 1; W5 3/3, 1;
      W6 1/1, 1; W7 1/1, 1; W8 9/9, 1; W9 1/1, 1; W10 2/2, 1; W11 2/2, 1; W12 2/2, 1;
      W13 1/1, 1; W14 1/2, 1; W15 1/2, 1; W16 3/5, 5; W17 1/1, 9; W18 4/4, 1;
      W19 1/1, 1; W20 3/3, 18.
    - W20 disabled only the integrity-completeness decision. All three pinned witness
      nodes failed. Its probe confirmed the reproductions revert to the former truncated
      `converted` results `Intro`/`Intro`/`A`. The controls (valid HTML, recoverable
      malformed tags, adapter partition) stayed green.
    - Every overlapping failure is listed per experiment in the log; none is a control.
  - **Restoration hashes (working-tree bytes):**
    - `greenhouse_content.py`
      `00ea51d9a94e54200d3c251533915dbb5f880a9b3070c45eaea7a41be964c033`;
    - `greenhouse.py` `6c486d20…b22ed8` (CRLF form; committed LF blob `f20ee294…edf63`,
      unchanged);
    - `greenhouse_posting_inputs.py` `00809ff0…b955fd2e`.
  - **Correction self-review** (a fresh read-only subagent). It found no bypass of the
    check, 0 CONVERTED-text differences from the oracle or `bfc3b93` across 350,000 fuzz
    inputs, and linear cost. All of the following were fixed before commit:
    - P2-1: a dangling `</style` end tag completed by the marker turned
      `unclosed_suppressed_element` into the generic outcome. Open state is now
      recorded before the marker is fed, and pinned.
    - P2-2: the raw-text-element abstention was undisclosed and contradicted the ADR. Now
      disclosed and pinned.
    - P3: a non-vacuous forgery case was added (a complete source pair before the
      truncation); the end-of-input-only scope was disclosed in the ADR, module, and
      ROADMAP; the three W20 witness nodes were pinned; and the self-check gained a
      subdirectory case.
- Evidence boundary: No Greenhouse or other live-network contact, production database, or
  production-data access occurred. The full suite used the configured disposable test
  database. S2b introduces no application persistence or production database behavior.
- Pilot metrics so far (pilot product slice 3 of 3):
  - review rounds: proposal 1 (Sol, approved with A1–A20); advisory 1 (changes
    requested);
  - findings: 1 executable (P2 truncation), 1 evidence-integrity (P2 mutation log), and
    1 documentation (P3);
  - correction commits: 1 pre-`A` (this commit), 0 post-`A`;
  - full-suite executions: 3 non-receipt (implementer at `bfc3b93`, self-review subagent
    at `bfc3b93`, implementer at this commit); receipt-producing executions: 0;
  - user relays: 5 (the S2b proposal request; the authorization with Sol's table; then
    the correction authorization, sent twice without Sol's review and once with it);
  - branch created 2026-10-04T04:02:30Z.
- STOP after pushing this correction for Sol Medium's narrow advisory re-review. No final
  `C`, coordinator receipt, `A`, formal `R`, merge, `M`/`Q`, Greenhouse or network
  contact, production data access, pilot evaluation, S2c, S3, or S4.

**Pre-publication advisory re-review — approved (Sol Medium, advisory only; not formal R).** Reviewed corrected advisory candidate `9e86ba9ec50b089b6c76ade319b1ec6ec396941a` against original candidate `bfc3b93447417344da769f2f2e4009db78547f70`, frozen-contract SHA-256 `e409427bccfecd4f3f04c839f47826f5727355788ceab8fee061e6985e519df2`, and correction-packet SHA-256 `5d68c43a8537f629b7cd7c8392aa406297899bd82c0d7927b4d3c6e4588dcee8`; all material changes through the corrected SHA were reviewed. The six-path correction and cumulative nine-path scope are exact. The malformed-truncation, mutation-evidence, and database-wording findings are resolved: end-of-input swallowing now fails closed with deterministic source-absent marker enforcement and the required precedence; adapter retention, partiality, warning, caps, and disabled-mode behavior are correct; and the lossless JUnit driver self-check plus W1–W20 evidence and byte-identical restoration are accepted. The disclosed mid-input limitation is acceptable for this offline, runtime-unreachable, non-persisting slice and remains a bounded S2c observation question, not a production-readiness claim. Independent review reran 331 focused and 904 acceptance tests, Ruff, mypy, repository/handoff/diff checks, the driver self-check, and the unchanged 91,994-byte Phase 3 evaluator; recorded evidence for 130 contract tests, the 4,240-test full suite, and W1–W20 was inspected and accepted. Final candidate-bound verification may proceed; formal R retains unrestricted authority.

```workflow-metadata
workflow_version: v3.2
state: published
slice_id: 2026-10-04-phase4-greenhouse-content-mapping-s2b-e670575
slice_kind: parser
risk_class: H
base_sha: e670575d5b05395cb9eeb2ec84833cc0034c7002
declared_gate: final
executed_gate: final
candidate_sha: 505e4c1e1480b19fcecc1f0cbbdec5d3f2e1b01e
receipt_id: 9a62f701-d97c-4bb9-868a-8f7f796b1686
receipt_path: docs/verification-receipts/505e4c1e1480b19fcecc1f0cbbdec5d3f2e1b01e/9a62f701-d97c-4bb9-868a-8f7f796b1686.json
fixture_path: backend/tests/fixtures/evaluation/phase3_realistic_corpus.json
fixture_count: 30
```

### Work review

- Date/reviewer: 2026-10-04 (UTC), Sol (primary, Sol Medium). Formal review of Phase 4
  S2b, offline Greenhouse content conversion and strict `PostingInputs` mapping, on
  `phase-4/greenhouse-content-mapping-s2b`:
  - base `e670575d5b05395cb9eeb2ec84833cc0034c7002`;
  - final candidate `C` = `505e4c1e1480b19fcecc1f0cbbdec5d3f2e1b01e`;
  - publication `A` = `12c281357d94270c5ec9b125f3c335ee8afc92f1`.

  Reviewed against frozen contract SHA-256
  `e409427bccfecd4f3f04c839f47826f5727355788ceab8fee061e6985e519df2` (U1–U4, Sol's binding
  amendments A1–A20 and W1–W19, and the proposal). Also reviewed against correction packet
  SHA-256 `5d68c43a8537f629b7cd7c8392aa406297899bd82c0d7927b4d3c6e4588dcee8` (Sol's
  "Changes requested" review R1–R7 and the correction authorization). Sol's earlier
  pre-publication advisory review of `bfc3b93`, and re-review of the correction `9e86ba9`,
  were advisory only; this is the formal review.
- **1. Sol's formal verdict and dispositions** (as relayed by the user; the relay is the
  authority for this review):
  - verdict **approved**;
  - findings none;
  - primary reviewer Sol (Sol Medium);
  - gate `final`, published slice kind `parser`;
  - `C`/`A` above, receipt `9a62f701-d97c-4bb9-868a-8f7f796b1686`, receipt SHA-256
    `d4e97fa0070c03864f99060ca948b7b9b5bbc9ba1cb63f860bf7adac5356a7bf`.

  The relay supplies the verdict and chain plus the evidence classification below. It
  supplies no further itemized disposition, so none is attributed to Sol here. "No
  unresolved executable findings" is a review status, not production-readiness evidence.
- **2. Independently rerun or recomputed in formal review** (per the relay):
  - the focused S2b selection (`tests/test_greenhouse_content.py
    tests/test_greenhouse_posting_inputs.py`): **331 passed**;
  - the Phase 3 evaluator identity (`python -m scripts.evaluate_phase3_corpus`, SHA-256
    `87a92187…01de6`, 91,994 bytes): unchanged.
- **3. Committed implementation and evidence inspected directly.** These checks were
  re-verified from Git plumbing and the receipt itself when this review was recorded:
  - **ancestry:** `A`'s sole parent is `C`; `C`'s is the correction `9e86ba9`; its sole
    parent is the original advisory candidate `bfc3b93`, whose sole parent is the base;
  - **refs:** the local and remote branch equal `A`; `main`, `origin/main`, and the
    remote `main` remain at the base; the tree was clean;
  - **scope:**
    - `base..C` is exactly the authorized nine paths;
    - `9e86ba9..C` changes only this file (Sol's re-review paragraph, inserted verbatim
      before valid `state: pending` metadata);
    - `C..A` adds only the C-bound receipt and the permitted pending → published
      transition with `executed_gate: final` (`validate_c_to_a_transition` passed);
  - **production blobs at `A`:**
    - `greenhouse_content.py` `00ea51d9…4c033`;
    - `greenhouse.py` `f20ee294…edf63`;
    - `greenhouse_posting_inputs.py` `00809ff0…b955fd2e`;
  - **receipt:**
    - file SHA-256 `d4e97fa0…6a7bf` equals the committed blob;
    - schema-valid;
    - bound to `C`, the base, gate `final`, the slice, and risk class H;
    - the verifier, checker, and configuration hashes equal the files committed at `C`;
    - the affected surface (`docs-only`, `generic-changed-test`, `handoff-transition`,
      `unmapped`), focused selector, migration determination (not triggered), and
      complete 34-witness active inventory all recompute identically;
    - approval eligibility recomputes as `true`;
  - **runtime packets** (gitignored, untracked, unchanged): frozen contract
    `e409427b…519df2`; correction packet `5d68c43a…dcee8`; mutation driver v2
    `7151c79f…761b5`; mutation log `514ac00d…5073e`.
- **4. Relied upon from the genuine C-bound receipt** (coordinator run at `C`; not
  rerun in formal review):
  - all 12 steps PASS: Ruff format and check, mypy, `check_repo`, `git diff --check`,
    disposable test-database URL validation and reachability, focused pytest (331),
    the full suite (**4,240 passed**), registered contract mutation witnesses
    (**34 of 34 passed**), handoff metadata validation, and temporary-directory cleanup;
  - no migration triggered; isolated-worktree integrity and removal.
- **5. Manual advisory mutation evidence.** W1–W20 were run during advisory correction 1
  with the lossless JUnit driver (self-check passed; all 20 passed with byte-identical
  restoration). They were inspected, not rerun, during formal review. The coordinator
  did not execute them, and they are not registered witnesses.
- Evidence boundary: No Greenhouse or other live-network contact, production database, or
  production-data access occurred. The full suite used the configured disposable test
  database. S2b introduces no application persistence or production database behavior.
- **6. Limitations retained:**
  - S2b is runtime-unreachable and non-persisting; nothing is registered or wired;
  - no captured raw `content` or real `/jobs?content=true` list-endpoint evidence (ADR
    0014's U6 deferral moves to S2c); synthetic HTML and 30 reconstructed synthetic
    envelopes only, under the bounded A16 claim;
  - only end-of-input truncation fails closed; text swallowed mid-input by a construct
    that a later quote or `-->` closes is still lost silently (a bounded S2c observation
    question);
  - table and section content merges; `noscript`/`template` text is kept; escaped code
    examples are rejected;
  - output depends on the interpreter's `html.parser` (verified on CPython 3.12.13 and
    golden-pinned);
  - in-memory text is unredacted;
  - there is no mode or outcome traceability on the job (A11), and this is not D1;
  - D1 remains unsatisfied and no normalized write is authorized; salary is excluded
    (ADR 0011 L4 open); ten components remain unproven; title is smoke evidence only;
    the corpus is the exposed 30-record, three-employer corpus;
  - production usefulness and live list-endpoint behavior are unproven.
- Pilot metrics (ADR 0012, pilot product slice 3 of 3), as recorded in `Work done`:
  - proposal-review rounds 1; advisory-review rounds 2 (changes requested, then
    approved); advisory findings 1 executable, 1 evidence-integrity, and 1 documentation
    (all resolved before `A`); formal findings 0;
  - pre-`A` correction commits 1; handoff-only finalization commits 1; post-`A`
    corrections 0;
  - receipt-producing executions 1.

  The relay for this formal review occurred after `A` and is outside the `Work done`
  relay count.
- Findings by severity with exact references: none.
- Verdict: **approved** -- no findings.
- Exact bounded correction: none required.
- STOP -- record-only. This review authorizes no merge, `M`, `Q`, Greenhouse contact,
  pilot evaluation, S2c, runtime wiring, persistence, D1, or other slice. Merge requires
  separate user authorization.

```workflow-review-metadata
schema_version: 2
slice_id: 2026-10-04-phase4-greenhouse-content-mapping-s2b-e670575
risk_class: H
reviewer: Sol
reviewer_role: primary
reviewer_model: Sol Medium
reviewed_at: 2026-10-04T22:06:28+00:00
candidate_sha: 505e4c1e1480b19fcecc1f0cbbdec5d3f2e1b01e
publication_commit_sha: 12c281357d94270c5ec9b125f3c335ee8afc92f1
receipt_path: docs/verification-receipts/505e4c1e1480b19fcecc1f0cbbdec5d3f2e1b01e/9a62f701-d97c-4bb9-868a-8f7f796b1686.json
receipt_id: 9a62f701-d97c-4bb9-868a-8f7f796b1686
gate: final
verdict: approved
findings: none
```

### Merge record

- Date: 2026-10-04 (UTC). Merged `phase-4/greenhouse-content-mapping-s2b` into `main` with
  `git merge --no-ff`, at the approved, reviewed commit
  `defc55557191dafdb34216b059a1cdb080297292` (`R`). `R` is Sol Medium's
  "approved -- no findings" formal verdict on
  `C=505e4c1e1480b19fcecc1f0cbbdec5d3f2e1b01e` /
  `A=12c281357d94270c5ec9b125f3c335ee8afc92f1`.
  - Merge commit `M`: `692c420e47f0e0b23acc8be6aec020b7eb3377d9`.
  - Rollback boundary (the pre-merge `main`/`origin/main` tip):
    `e670575d5b05395cb9eeb2ec84833cc0034c7002`.
  - Full lineage: base `e670575` -> advisory candidate `bfc3b93` -> advisory correction 1
    `9e86ba9` -> `C` `505e4c1` -> `A` `12c2813` -> `R` `defc555` -> `M` `692c420` -> `Q`
    (this commit).
- Pre-merge checks, after a fresh fetch of `origin`:
  - the feature branch, its origin, and the remote ref all sat at `R`; `R`'s sole parent
    is `A` and `A`'s is `C`;
  - `main`/`origin/main`/remote `main` were clean and synchronized at the rollback
    boundary;
  - **receipt `9a62f701-d97c-4bb9-868a-8f7f796b1686`** (file SHA-256
    `d4e97fa0070c03864f99060ca948b7b9b5bbc9ba1cb63f860bf7adac5356a7bf`):
    - schema-valid and bound to `C`, the base, the slice, gate `final`, and risk class H;
    - its verifier, checker, and configuration hashes equal the files committed at `C`;
    - the affected surface, focused selector, migration decision (not triggered), and
      34-witness inventory recomputed identically;
    - independently recomputed as approval-eligible;
  - `validate_c_a_r_chain(C, A, R)` and `check_merge_eligibility(C, A, R)` returned
    `approved`, `findings: none`, `reviewer_model: Sol Medium`, `reviewer_role: primary`,
    `gate: final`, `published_slice_kind: parser`.
- Release sequence:
  - `M` was created locally and not pushed. It has two parents (the rollback boundary,
    then `R`), `R..M` has zero content difference, and
    `check_review.validate_merge(R, M, e670575)` passed.
  - `verification_coordinator.run_post_merge_verification` ran against `M` in a
    disposable detached worktree (always full/final). It produced artifact
    `08dcbdd3-9ba0-47e3-9ed4-5ca7ee1c0e6a`:
    - all 11 steps PASS: Ruff format and check, mypy, `check_repo`, `git diff --check`,
      disposable test-database URL validation and reachability preflight, the full
      suite, contract mutation witnesses, handoff metadata validation, and
      temporary-directory cleanup;
    - full pytest suite: **4240 passed**;
    - all 34 registered mutation witnesses passed, 0 failed;
    - no migration triggered;
    - identical worktree snapshots (tracked tree `90f54d7051cc2c5509129544f4ba644559474ccd`);
      worktree removed with no residual entry or directory; cleanup PASS.
  - `Q` is `M`'s direct mainline child. It contains that artifact plus this append-only
    merge record, in one commit (this entry).
- Post-merge evidence:
  `docs/post-merge/692c420e47f0e0b23acc8be6aec020b7eb3377d9/08dcbdd3-9ba0-47e3-9ed4-5ca7ee1c0e6a.json`
  (SHA-256 of the artifact file as written:
  `936e4f3526fe59f2b8984a10478be328db60014dc578eb1f3c8e1004b4c6d20d`). It references
  original receipt `9a62f701-d97c-4bb9-868a-8f7f796b1686`.
  `check_review.validate_published(C, A, R, M, Q)` and
  `verification_coordinator.confirm_main_unchanged` run immediately before the push.
  Their results are in the agent's final report rather than restated here in advance.
- Evidence by source:
  - **Post-merge coordinator (this artifact, at `M`):** the 11 steps above, including the
    4,240-test full suite and 34/34 registered witnesses.
  - **Pre-merge receipt (at `C`):** all 12 steps PASS, including focused 331, the full
    suite 4,240, and 34/34 registered witnesses.
  - **Manual advisory evidence:** W1–W20 were run during advisory correction 1 with the
    lossless JUnit driver (all passed, byte-identical restoration). Neither coordinator
    ran them; they are not registered witnesses and are not attributed to the receipt
    or this artifact.
  - **Formal review (`R`):** Sol independently reran the focused 331 and the evaluator
    identity, inspected the committed implementation and evidence, and relied on the
    receipt for the full suite and registered witnesses.
  - No Greenhouse or other live-network contact, production database, or
    production-data access occurred. Both suite runs used the configured disposable test
    database.
- S2b status: merged. S2b adds:
  - `app/providers/greenhouse_content.py`: declared-mode, bounded content-to-text
    extraction, fail-closed for the enumerated encoding, suppression, size,
    meaningfulness, and end-of-input truncation cases;
  - `content_mode` and incomplete-result handling in `app/providers/greenhouse.py`;
  - the three-field `app/providers/greenhouse_posting_inputs.py` bridge;
  - [ADR 0015](DECISIONS/0015-greenhouse-content-conversion-and-posting-input-mapping.md).

  S2b remains runtime-unreachable and non-persisting: nothing is registered, wired, or
  written. It is not a production-usefulness proof. D1 remains unsatisfied; no normalized
  write is authorized. Completing S2b completes ADR 0012 pilot product slice 3 of 3. It
  is not itself the ADR 0012 pilot evaluation and does not authorize S2c. The pilot
  evaluation, S2c, S3, and S4 each require separate authorization. Phase 4 is not
  complete.
- Retained limitations:
  - no captured raw Greenhouse `content`;
  - unknown live `/jobs?content=true` list-endpoint encoding (ADR 0014's U6 deferral
    moves to S2c);
  - synthetic HTML and 30 reconstructed synthetic envelopes only;
  - end-of-input-only truncation detection, so text can still be swallowed mid-input
    when a later quote or `-->` closes the construct;
  - extraction and suppression boundaries: table and section content merges,
    `noscript`/`template` text is kept, escaped code examples are rejected, and unclosed
    raw-text elements abstain;
  - dependence on CPython's `html.parser` (verified on 3.12.13, golden-pinned);
  - unredacted in-memory text;
  - no per-job conversion-mode or outcome traceability;
  - D1 unsatisfied; salary excluded (ADR 0011 L4 open);
  - ten components unproven; title smoke-only;
  - the exposed 30-record corpus;
  - no production-usefulness proof;
  - W1–W20 are not registered guards.
- Final pilot metrics (ADR 0012, pilot product slice 3 of 3):
  - review rounds: proposal 1 (approved with A1–A20); advisory 2 (changes requested,
    then approved); formal 1;
  - findings: advisory 1 executable, 1 evidence-integrity, and 1 documentation, all
    resolved before `A`; formal 0;
  - correction commits: 1 semantic pre-`A` (`9e86ba9`); 1 handoff-only finalization
    (`C`); 0 post-`A`;
  - receipt-producing executions: 1 (the clean-path target);
  - full-suite executions: 5 (3 non-receipt during authoring and self-review, the `C`
    receipt run, and the post-merge run at `M`);
  - user relays: 9 through merge (the proposal request; the implementation authorization
    with Sol's table; two correction-authorization relays that lacked Sol's review; Sol's
    review; one duplicate re-paste after the correction; the re-review approval and
    final-`C` authorization; the formal-review relay; and this merge authorization);
  - escaped post-merge defects: none known at merge; newly reachable runtime product
    behavior: none, by design.

  These are measurements, not conclusions; the ADR 0012 exit comparison is a separately
  authorized step.
- STOP -- report the synchronized final `main` SHA and stop. No ADR 0012 pilot
  evaluation, Greenhouse contact, S2c, runtime wiring, normalized persistence, D1 work,
  migration, S3, or S4 without separate explicit user authorization.

## Iteration 2

### Work done

- Date/agent: 2026-10-04, Claude (implementer). Branch
  `workflow/throughput-protocol-retention`, base
  `6752dcdc0ce1b57c0af164aa217d3181566086bd` (`Q` of the Phase 4 S2b merge
  `M=692c420`). Ending commit: this commit (candidate `C`).
- Slice: the ADR 0012 pilot evaluation and adoption, a bounded documentation-policy
  slice. Risk class D, `slice_kind: docs`, `declared_gate: final`. `docs/LLM_WORKFLOW.md`
  is a `workflow-governing-doc` under `scripts/verification_scope.py`, which forces
  `gate=final`. No executable, test, fixture, schema, or configuration change.
- Re-anchor, before any edit and after a fresh fetch:
  - local `main`, `origin/main`, and remote `main` all equalled the base, and the tree was
    clean;
  - S1, S2, and S2b each reached `Q`, which exhausts ADR 0012's three-slice
    authorization;
  - no S2c, provider-contact, persistence, D1, S3, or S4 work had begun.
- Contract: the user's adoption decision and authorization, frozen with every binding
  input in the create-only, gitignored runtime packet
  `.claude/runtime/workflow-throughput-protocol-retention-contract.md` (SHA-256
  `369a6c20c9135d087a50168576c5a1dff886b120ea9e8088743884e6eec4608a`). The packet is not
  committed. Inputs, in precedence order:
  1. the user's decision and authorization;
  2. Sol Medium's compatibility review, with binding amendments E9–E13;
  3. Astra's amendments E1–E8, as relayed. Astra's full response was not received, and
     ADR 0016 discloses this with E13's exact wording;
  4. the implementer's revised evaluation and O1–O5;
  5. ADR 0012 and Workflow v3.2.

  Both reviews were policy consultations, not formal `R` metadata.
- Files (exact closed four-path list):
  - `docs/DECISIONS/0016-workflow-throughput-pilot-evaluation-and-retention.md` (new).
    It records the required decision sentence verbatim, the evaluation with cited
    evidence paths, O1–O5, retained and deferred controls, the Phase 4 exit assessment,
    and rollback;
  - `docs/LLM_WORKFLOW.md`, in the Workflow v3.2 section:
    - the ADR 0012 subsection is renamed "Workflow Throughput Protocol (ADR 0012,
      retained by ADR 0016)", with an updated status and status pointer;
    - "pilot" becomes "protocol" in the precedence, product-priority, and metrics
      wording;
    - the exit paragraph now covers the exit evaluation, next assessment, and rollback;
    - O1–O5 are added;
    - two deferred items are added: a new metrics framework, and another model-approval
      layer.

    No existing requirement was deleted;
  - `docs/ROADMAP.md`: S2b's stale "in progress" status is replaced with its `M`/`Q`,
    and an entry is added for this evaluation;
  - this file: the two-iteration rotation. The S2 iteration was removed. The S2b
    iteration is retained unchanged as Iteration 1, apart from its renumbered heading.
- Not changed: ADR 0012 (byte-identical to the base), `CLAUDE.md`, validators and
  verification tooling, tests, fixtures, schemas, configuration, reviewer roles, receipt
  binding, handoff retention, and registered witnesses.
- Metrics, recomputed from committed evidence before commit (receipt and post-merge
  `duration_seconds` summed with exact decimal arithmetic; commit chains from `git log`):
  - committed receipts:
    - pilot: 3 across 3 slices (1.00 per slice);
    - Phase 3 risk class H: 16 across 6 (2.67);
    - all Phase 3 v3.2 product slices: 18 across 7 (2.57);
  - Phase 3 risk class H receipt-bearing corrections after the first `A`: 10, each
    changing code, tests, or fixtures;
  - recorded step time:
    - Phase 3 risk class H receipts: 6,158.988 seconds, averaging 384.937 seconds;
    - pilot candidate receipts: 1,190.484 seconds;
    - pilot post-merge runs: 1,238.609 seconds;
  - known pilot full-suite runs: 9;
  - pilot relays: 24 (19 necessary, 2 non-actionable, 3 indeterminate).

  Every cited receipt and artifact path exists.
- Implementer notes, recorded in the packet at freeze and disclosed for formal review:
  - N1. ADR 0016 names the evaluation checkpoint (`6752dcd`, 2026-10-04T22:18:42Z) so
    that E12's "less than 24 hours old" sentence stays true. At that instant, S1's `Q`
    was about 22.4 hours old;
  - N2. E9 is kept verbatim. One added factual sentence discloses `17f6f24`, the
    skill-classifier slice's handoff-only commit after its first `A`. It carries no
    receipt and is not a correction candidate.
- Pre-commit checks: `check_repo`, `check_handoff`, and `git diff --check` pass. A
  consistency review covered all four documents.
- Verification: the genuine `verification_coordinator` `gate=final` run against `C`,
  recorded in `A`.
- STOP after `A` for formal Sol Medium review. No `R`, merge, `M`/`Q`, validator or
  tooling change, Greenhouse or provider contact, S2c, persistence, D1, S3, or S4.

```workflow-metadata
workflow_version: v3.2
state: pending
slice_id: 2026-10-04-workflow-throughput-protocol-retention-6752dcd
slice_kind: docs
risk_class: D
base_sha: 6752dcdc0ce1b57c0af164aa217d3181566086bd
declared_gate: final
```
