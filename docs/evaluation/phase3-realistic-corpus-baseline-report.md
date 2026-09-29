# Phase 3 realistic-corpus baseline evaluation report

First baseline evaluation of the seven existing classifiers (`classify_remote_type`, `classify_employment_type`, `classify_seniority`, `classify_experience`, `classify_salary`, `classify_location`, `classify_skills`) against the frozen, human-adjudicated Phase 3 realistic corpus, produced by `python -m scripts.evaluate_phase3_corpus` exactly as implemented -- no parser, taxonomy, provider-mapping, fixture, rubric, or threshold change. This is a report only; no pass/fail threshold is defined anywhere in this pipeline.

## Source and lineage hashes

| Artifact | Path | SHA-256 |
|---|---|---|
| Reviewed salvage batch (30 human-retained candidates) | `backend/.evaluation-staging/greenhouse_candidates_second_pass_review.json` | `1273b6eafd42d05898520a783ad94f063da4507e8c00f3c4da86a3273b36fd6a` |
| Skills taxonomy | `backend/app/taxonomy/skills.yaml` | `50ff7fb583bc55e72177b42b971cff66959a99b2225e127478aa55975adf2d49` |
| Annotation rubric (version 1.0.4) | `docs/evaluation/phase3-realistic-annotation-rubric.md` | `70961ec18fcbd5a316bb6ae49b4c9edc0cc1b3957aa6f5cd1f59c1684057eeb9` |
| Canonical `source_packet_hash` (salvage+taxonomy+rubric manifest) | n/a | `010a13e0b5040121d4f55df62a0dc3780033469c316380cc1e415c5a86641f92` |
| Claude annotation pass (`annotator_role: claude`) | `docs/evaluation/phase3-realistic-pass-claude.json` | `f732c9d0f1fa0f19609dc84c7346fab69d84d0f3646ac18a87b44ad5b87bc71d` |
| Sol annotation pass (`annotator_role: sol`) | `docs/evaluation/phase3-realistic-pass-sol.json` | `b6ce0ff33a94aa8afcc4332f26596ec548f264a6429f643ae696d5b1042227e1` |
| Adjudication/audit evidence (95 disagreements + 220 required agreement audits, all `adjudicated_by`/`audited_by: user`) | `docs/evaluation/phase3-realistic-adjudication-audit.json` | `8de5a3faf48e662fc13cad7b5d8c1d8958061cbf06f04e38862358ff300f8ad9` |
| Frozen evaluation corpus (30 records, 840 labels, 20 dev / 10 holdout) | `backend/tests/fixtures/evaluation/phase3_realistic_corpus.json` | `1863541bb784419be16bf4ffcf88bf1b4408c951a03b12008e9645e9f18e6930` |

The corpus was built by `scripts/freeze_phase3_realistic_corpus.py build`, which independently re-verifies every hash above, recomputes the canonical `source_packet_hash`, and validates the built corpus via `evaluate_phase3_corpus.load_corpus` (the same authoritative loader used to produce this report) before writing it. Employer/holdout split is deterministic: employers sorted ascending, the lexicographically last (`GitLab`) is `holdout`; `Anthropic`/`Discord` are `dev`.

## Headline result

Zero runtime failures across all 30 records x 7 classifiers. Zero `confidently_wrong` results anywhere (no classifier ever returned a present, non-null value that disagreed with a `present_supported` ground-truth value). Zero false positives on `absent`/`present_unsupported_form` ground truth anywhere. Every mismatch falls into one of: `missing_wired_input_gap` (100, entirely `salary.*` -- the ground truth pools `title`+`description`+`compensation_text`, but the real classifier is wired to `compensation_text` alone, which is empty for these postings), `supported_abstention` (56 -- the classifier correctly declines rather than guesses), `recall_miss` (5, all `skills.golang`), or `false_positive_ambiguous` (2, both `remote_type`, both Discord). A further 3 `location.country` cases have a correct value with a provenance-label difference only (expected `inferred`, actual `parsed_description`) -- not a `render_report` mismatch category, since the value itself is correct.

## Holdout exposure

Running this evaluation necessarily exposes the 10 GitLab holdout records' expected-vs-actual results. From this point forward, holdout is burned for generalization purposes on these specific findings: any future parser correction must be justified on general reasoning (never by fitting these exact holdout examples), must be validated primarily against `dev`, and any post-fix re-run against holdout is informational only, never independent proof of generalization. Per the approved contract, an exposed holdout record graduates to `dev` in any future corpus revision that manually inspects its mismatch; this report itself performs no such revision and preserves the original first-exposure result below immutably.

## Full deterministic evaluator output (`python -m scripts.evaluate_phase3_corpus`)

Verbatim `render_report()` output -- dev, holdout, combined, then one section per employer (`Anthropic`, `Discord`, `GitLab`). Reproduced byte-for-byte from the real run; confirmed deterministic (identical output across repeated runs against the same frozen corpus).

```text
===== split: dev =====
== employment_type ==
  opportunity matrix: {'absent': 10, 'ambiguous': 0, 'present_supported': 10, 'present_unsupported_form': 0}
  supported_correctness: 10/10
  supported_abstention: 0/10
  confidently_wrong: 0/10
  false_positive_absent: 0/10
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: 10/10
  missing_wired_input_gap: N/A
== experience.maximum ==
  opportunity matrix: {'absent': 20, 'ambiguous': 0, 'present_supported': 0, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/20
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== experience.minimum ==
  opportunity matrix: {'absent': 5, 'ambiguous': 2, 'present_supported': 13, 'present_unsupported_form': 0}
  supported_correctness: 0/13
  supported_abstention: 13/13
  confidently_wrong: 0/13
  false_positive_absent: 0/5
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: 0/2
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== location.city ==
  opportunity matrix: {'absent': 9, 'ambiguous': 8, 'present_supported': 3, 'present_unsupported_form': 0}
  supported_correctness: 0/3
  supported_abstention: 3/3
  confidently_wrong: 0/3
  false_positive_absent: 0/9
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: 0/8
  provenance_correctness: N/A
  missing_wired_input_gap: 0/3
== location.country ==
  opportunity matrix: {'absent': 9, 'ambiguous': 0, 'present_supported': 11, 'present_unsupported_form': 0}
  supported_correctness: 1/11
  supported_abstention: 10/11
  confidently_wrong: 0/11
  false_positive_absent: 0/9
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: 0/1
  missing_wired_input_gap: 0/11
== location.postal_code ==
  opportunity matrix: {'absent': 20, 'ambiguous': 0, 'present_supported': 0, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/20
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== location.state ==
  opportunity matrix: {'absent': 10, 'ambiguous': 8, 'present_supported': 2, 'present_unsupported_form': 0}
  supported_correctness: 0/2
  supported_abstention: 2/2
  confidently_wrong: 0/2
  false_positive_absent: 0/10
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: 0/8
  provenance_correctness: N/A
  missing_wired_input_gap: 0/2
== remote_type ==
  opportunity matrix: {'absent': 5, 'ambiguous': 2, 'present_supported': 13, 'present_unsupported_form': 0}
  supported_correctness: 0/13
  supported_abstention: 13/13
  confidently_wrong: 0/13
  false_positive_absent: 0/5
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: 2/2
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== salary.currency ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 20, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 20/20
== salary.maximum ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 20, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 20/20
== salary.minimum ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 20, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 20/20
== salary.period ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 20, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 20/20
== seniority ==
  opportunity matrix: {'absent': 8, 'ambiguous': 1, 'present_supported': 10, 'present_unsupported_form': 1}
  supported_correctness: 10/10
  supported_abstention: 0/10
  confidently_wrong: 0/10
  false_positive_absent: 0/8
  false_positive_unsupported_form: 0/1
  false_positive_ambiguous: 0/1
  provenance_correctness: 10/10
  missing_wired_input_gap: N/A
== skills ==
  opportunity matrix: {'absent': 278, 'ambiguous': 0, 'present_supported': 22, 'present_unsupported_form': 0}
  precision: 21/21
  recall: 21/22
  false_positive_absent: 0/278
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  false_positive_outside_frozen_set: 0/21
== runtime_failure (per parser invocation) ==
  employment_type: 0/20
  experience: 0/20
  location: 0/20
  remote_type: 0/20
  salary: 0/20
  seniority: 0/20
  skills: 0/20
== mismatches (124) ==
  record=anthropic:4017331008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4017331008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4017331008 parser=salary component=maximum category=missing_wired_input_gap expected=850000 actual=None
  record=anthropic:4017331008 parser=salary component=minimum category=missing_wired_input_gap expected=350000 actual=None
  record=anthropic:4017331008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4020350008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4020350008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4020350008 parser=salary component=maximum category=missing_wired_input_gap expected=850000 actual=None
  record=anthropic:4020350008 parser=salary component=minimum category=missing_wired_input_gap expected=280000 actual=None
  record=anthropic:4020350008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4423394008 parser=experience component=minimum category=supported_abstention expected=5 actual=None
  record=anthropic:4423394008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4423394008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4423394008 parser=salary component=maximum category=missing_wired_input_gap expected=380000 actual=None
  record=anthropic:4423394008 parser=salary component=minimum category=missing_wired_input_gap expected=222800 actual=None
  record=anthropic:4423394008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4461444008 parser=experience component=minimum category=supported_abstention expected=5 actual=None
  record=anthropic:4461444008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4461444008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4461444008 parser=salary component=maximum category=missing_wired_input_gap expected=315000 actual=None
  record=anthropic:4461444008 parser=salary component=minimum category=missing_wired_input_gap expected=240000 actual=None
  record=anthropic:4461444008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4461450008 parser=experience component=minimum category=supported_abstention expected=4 actual=None
  record=anthropic:4461450008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4461450008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4461450008 parser=salary component=maximum category=missing_wired_input_gap expected=290000 actual=None
  record=anthropic:4461450008 parser=salary component=minimum category=missing_wired_input_gap expected=222800 actual=None
  record=anthropic:4461450008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4502508008 parser=experience component=minimum category=supported_abstention expected=7 actual=None
  record=anthropic:4502508008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4502508008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4502508008 parser=salary component=maximum category=missing_wired_input_gap expected=485000 actual=None
  record=anthropic:4502508008 parser=salary component=minimum category=missing_wired_input_gap expected=320000 actual=None
  record=anthropic:4502508008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4502508008 parser=skills component=golang category=recall_miss expected='golang' actual=None
  record=anthropic:4572744008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4572744008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4572744008 parser=salary component=maximum category=missing_wired_input_gap expected=405000 actual=None
  record=anthropic:4572744008 parser=salary component=minimum category=missing_wired_input_gap expected=320000 actual=None
  record=anthropic:4572744008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4593216008 parser=experience component=minimum category=supported_abstention expected=8 actual=None
  record=anthropic:4593216008 parser=location component=city category=supported_abstention expected='San Francisco' actual=None
  record=anthropic:4593216008 parser=location component=state category=supported_abstention expected='CA' actual=None
  record=anthropic:4593216008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4593216008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4593216008 parser=salary component=maximum category=missing_wired_input_gap expected=850000 actual=None
  record=anthropic:4593216008 parser=salary component=minimum category=missing_wired_input_gap expected=350000 actual=None
  record=anthropic:4593216008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4595463008 parser=experience component=minimum category=supported_abstention expected=7 actual=None
  record=anthropic:4595463008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4595463008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4595463008 parser=salary component=maximum category=missing_wired_input_gap expected=405000 actual=None
  record=anthropic:4595463008 parser=salary component=minimum category=missing_wired_input_gap expected=320000 actual=None
  record=anthropic:4595463008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4610158008 parser=location component=city category=supported_abstention expected='London' actual=None
  record=anthropic:4610158008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4610158008 parser=salary component=currency category=missing_wired_input_gap expected='GBP' actual=None
  record=anthropic:4610158008 parser=salary component=maximum category=missing_wired_input_gap expected=370000 actual=None
  record=anthropic:4610158008 parser=salary component=minimum category=missing_wired_input_gap expected=260000 actual=None
  record=anthropic:4610158008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8214127002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8214127002 parser=remote_type component=None category=false_positive_ambiguous expected=None actual='remote'
  record=discord:8214127002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8214127002 parser=salary component=maximum category=missing_wired_input_gap expected=341000 actual=None
  record=discord:8214127002 parser=salary component=minimum category=missing_wired_input_gap expected=279000 actual=None
  record=discord:8214127002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8369347002 parser=experience component=minimum category=supported_abstention expected=4 actual=None
  record=discord:8369347002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8369347002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8369347002 parser=salary component=maximum category=missing_wired_input_gap expected=275000 actual=None
  record=discord:8369347002 parser=salary component=minimum category=missing_wired_input_gap expected=220000 actual=None
  record=discord:8369347002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8460791002 parser=experience component=minimum category=supported_abstention expected=5 actual=None
  record=discord:8460791002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8460791002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=discord:8460791002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8460791002 parser=salary component=maximum category=missing_wired_input_gap expected=220000 actual=None
  record=discord:8460791002 parser=salary component=minimum category=missing_wired_input_gap expected=196000 actual=None
  record=discord:8460791002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8464570002 parser=experience component=minimum category=supported_abstention expected=8 actual=None
  record=discord:8464570002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8464570002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8464570002 parser=salary component=maximum category=missing_wired_input_gap expected=279000 actual=None
  record=discord:8464570002 parser=salary component=minimum category=missing_wired_input_gap expected=248000 actual=None
  record=discord:8464570002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8498984002 parser=experience component=minimum category=supported_abstention expected=7 actual=None
  record=discord:8498984002 parser=location component=city category=supported_abstention expected='San Francisco' actual=None
  record=discord:8498984002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8498984002 parser=location component=state category=supported_abstention expected='CA' actual=None
  record=discord:8498984002 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=discord:8498984002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8498984002 parser=salary component=maximum category=missing_wired_input_gap expected=341000 actual=None
  record=discord:8498984002 parser=salary component=minimum category=missing_wired_input_gap expected=279000 actual=None
  record=discord:8498984002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8537955002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8537955002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=discord:8537955002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8537955002 parser=salary component=maximum category=missing_wired_input_gap expected=341000 actual=None
  record=discord:8537955002 parser=salary component=minimum category=missing_wired_input_gap expected=248000 actual=None
  record=discord:8537955002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8545675002 parser=experience component=minimum category=supported_abstention expected=5 actual=None
  record=discord:8545675002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8545675002 parser=remote_type component=None category=false_positive_ambiguous expected=None actual='remote'
  record=discord:8545675002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8545675002 parser=salary component=maximum category=missing_wired_input_gap expected=269500 actual=None
  record=discord:8545675002 parser=salary component=minimum category=missing_wired_input_gap expected=220500 actual=None
  record=discord:8545675002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8571766002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8571766002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8571766002 parser=salary component=maximum category=missing_wired_input_gap expected=550000 actual=None
  record=discord:8571766002 parser=salary component=minimum category=missing_wired_input_gap expected=450000 actual=None
  record=discord:8571766002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8575166002 parser=experience component=minimum category=supported_abstention expected=2 actual=None
  record=discord:8575166002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8575166002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8575166002 parser=salary component=maximum category=missing_wired_input_gap expected=130500 actual=None
  record=discord:8575166002 parser=salary component=minimum category=missing_wired_input_gap expected=116000 actual=None
  record=discord:8575166002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8581126002 parser=experience component=minimum category=supported_abstention expected=5 actual=None
  record=discord:8581126002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8581126002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8581126002 parser=salary component=maximum category=missing_wired_input_gap expected=220500 actual=None
  record=discord:8581126002 parser=salary component=minimum category=missing_wired_input_gap expected=196000 actual=None
  record=discord:8581126002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
===== split: holdout =====
== employment_type ==
  opportunity matrix: {'absent': 10, 'ambiguous': 0, 'present_supported': 0, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/10
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== experience.maximum ==
  opportunity matrix: {'absent': 10, 'ambiguous': 0, 'present_supported': 0, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/10
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== experience.minimum ==
  opportunity matrix: {'absent': 9, 'ambiguous': 0, 'present_supported': 1, 'present_unsupported_form': 0}
  supported_correctness: 0/1
  supported_abstention: 1/1
  confidently_wrong: 0/1
  false_positive_absent: 0/9
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== location.city ==
  opportunity matrix: {'absent': 7, 'ambiguous': 0, 'present_supported': 3, 'present_unsupported_form': 0}
  supported_correctness: 0/3
  supported_abstention: 3/3
  confidently_wrong: 0/3
  false_positive_absent: 0/7
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 0/3
== location.country ==
  opportunity matrix: {'absent': 0, 'ambiguous': 6, 'present_supported': 4, 'present_unsupported_form': 0}
  supported_correctness: 4/4
  supported_abstention: 0/4
  confidently_wrong: 0/4
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: 0/6
  provenance_correctness: 2/4
  missing_wired_input_gap: 0/4
== location.postal_code ==
  opportunity matrix: {'absent': 10, 'ambiguous': 0, 'present_supported': 0, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/10
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== location.state ==
  opportunity matrix: {'absent': 9, 'ambiguous': 0, 'present_supported': 1, 'present_unsupported_form': 0}
  supported_correctness: 0/1
  supported_abstention: 1/1
  confidently_wrong: 0/1
  false_positive_absent: 0/9
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 0/1
== remote_type ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 10, 'present_unsupported_form': 0}
  supported_correctness: 0/10
  supported_abstention: 10/10
  confidently_wrong: 0/10
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== salary.currency ==
  opportunity matrix: {'absent': 5, 'ambiguous': 0, 'present_supported': 5, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/5
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 5/5
== salary.maximum ==
  opportunity matrix: {'absent': 5, 'ambiguous': 0, 'present_supported': 5, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/5
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 5/5
== salary.minimum ==
  opportunity matrix: {'absent': 5, 'ambiguous': 0, 'present_supported': 5, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/5
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 5/5
== salary.period ==
  opportunity matrix: {'absent': 5, 'ambiguous': 0, 'present_supported': 5, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/5
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 5/5
== seniority ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 8, 'present_unsupported_form': 2}
  supported_correctness: 8/8
  supported_abstention: 0/8
  confidently_wrong: 0/8
  false_positive_absent: N/A
  false_positive_unsupported_form: 0/2
  false_positive_ambiguous: N/A
  provenance_correctness: 8/8
  missing_wired_input_gap: N/A
== skills ==
  opportunity matrix: {'absent': 132, 'ambiguous': 0, 'present_supported': 18, 'present_unsupported_form': 0}
  precision: 14/14
  recall: 14/18
  false_positive_absent: 0/132
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  false_positive_outside_frozen_set: 0/14
== runtime_failure (per parser invocation) ==
  employment_type: 0/10
  experience: 0/10
  location: 0/10
  remote_type: 0/10
  salary: 0/10
  seniority: 0/10
  skills: 0/10
== mismatches (39) ==
  record=gitlab:8396674002 parser=location component=city category=supported_abstention expected='San Francisco' actual=None
  record=gitlab:8396674002 parser=location component=state category=supported_abstention expected='CA' actual=None
  record=gitlab:8396674002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8396674002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=gitlab:8396674002 parser=salary component=maximum category=missing_wired_input_gap expected=231300 actual=None
  record=gitlab:8396674002 parser=salary component=minimum category=missing_wired_input_gap expected=154200 actual=None
  record=gitlab:8396674002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=gitlab:8451512002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8451512002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=gitlab:8451512002 parser=salary component=maximum category=missing_wired_input_gap expected=252000 actual=None
  record=gitlab:8451512002 parser=salary component=minimum category=missing_wired_input_gap expected=117600 actual=None
  record=gitlab:8451512002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=gitlab:8463922002 parser=location component=city category=supported_abstention expected='Bangalore' actual=None
  record=gitlab:8463922002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8463922002 parser=skills component=golang category=recall_miss expected='golang' actual=None
  record=gitlab:8476375002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8478405002 parser=experience component=minimum category=supported_abstention expected=4 actual=None
  record=gitlab:8478405002 parser=location component=city category=supported_abstention expected='Bangalore' actual=None
  record=gitlab:8478405002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8490477002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8490477002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=gitlab:8490477002 parser=salary component=maximum category=missing_wired_input_gap expected=282000 actual=None
  record=gitlab:8490477002 parser=salary component=minimum category=missing_wired_input_gap expected=131600 actual=None
  record=gitlab:8490477002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=gitlab:8490477002 parser=skills component=golang category=recall_miss expected='golang' actual=None
  record=gitlab:8500014002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8512220002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8512220002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=gitlab:8512220002 parser=salary component=maximum category=missing_wired_input_gap expected=235200 actual=None
  record=gitlab:8512220002 parser=salary component=minimum category=missing_wired_input_gap expected=139200 actual=None
  record=gitlab:8512220002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=gitlab:8512432002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8512432002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=gitlab:8512432002 parser=salary component=maximum category=missing_wired_input_gap expected=297000 actual=None
  record=gitlab:8512432002 parser=salary component=minimum category=missing_wired_input_gap expected=254000 actual=None
  record=gitlab:8512432002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=gitlab:8512432002 parser=skills component=golang category=recall_miss expected='golang' actual=None
  record=gitlab:8514960002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8514960002 parser=skills component=golang category=recall_miss expected='golang' actual=None
===== split: combined =====
== employment_type ==
  opportunity matrix: {'absent': 20, 'ambiguous': 0, 'present_supported': 10, 'present_unsupported_form': 0}
  supported_correctness: 10/10
  supported_abstention: 0/10
  confidently_wrong: 0/10
  false_positive_absent: 0/20
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: 10/10
  missing_wired_input_gap: N/A
== experience.maximum ==
  opportunity matrix: {'absent': 30, 'ambiguous': 0, 'present_supported': 0, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/30
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== experience.minimum ==
  opportunity matrix: {'absent': 14, 'ambiguous': 2, 'present_supported': 14, 'present_unsupported_form': 0}
  supported_correctness: 0/14
  supported_abstention: 14/14
  confidently_wrong: 0/14
  false_positive_absent: 0/14
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: 0/2
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== location.city ==
  opportunity matrix: {'absent': 16, 'ambiguous': 8, 'present_supported': 6, 'present_unsupported_form': 0}
  supported_correctness: 0/6
  supported_abstention: 6/6
  confidently_wrong: 0/6
  false_positive_absent: 0/16
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: 0/8
  provenance_correctness: N/A
  missing_wired_input_gap: 0/6
== location.country ==
  opportunity matrix: {'absent': 9, 'ambiguous': 6, 'present_supported': 15, 'present_unsupported_form': 0}
  supported_correctness: 5/15
  supported_abstention: 10/15
  confidently_wrong: 0/15
  false_positive_absent: 0/9
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: 0/6
  provenance_correctness: 2/5
  missing_wired_input_gap: 0/15
== location.postal_code ==
  opportunity matrix: {'absent': 30, 'ambiguous': 0, 'present_supported': 0, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/30
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== location.state ==
  opportunity matrix: {'absent': 19, 'ambiguous': 8, 'present_supported': 3, 'present_unsupported_form': 0}
  supported_correctness: 0/3
  supported_abstention: 3/3
  confidently_wrong: 0/3
  false_positive_absent: 0/19
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: 0/8
  provenance_correctness: N/A
  missing_wired_input_gap: 0/3
== remote_type ==
  opportunity matrix: {'absent': 5, 'ambiguous': 2, 'present_supported': 23, 'present_unsupported_form': 0}
  supported_correctness: 0/23
  supported_abstention: 23/23
  confidently_wrong: 0/23
  false_positive_absent: 0/5
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: 2/2
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== salary.currency ==
  opportunity matrix: {'absent': 5, 'ambiguous': 0, 'present_supported': 25, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/5
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 25/25
== salary.maximum ==
  opportunity matrix: {'absent': 5, 'ambiguous': 0, 'present_supported': 25, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/5
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 25/25
== salary.minimum ==
  opportunity matrix: {'absent': 5, 'ambiguous': 0, 'present_supported': 25, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/5
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 25/25
== salary.period ==
  opportunity matrix: {'absent': 5, 'ambiguous': 0, 'present_supported': 25, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/5
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 25/25
== seniority ==
  opportunity matrix: {'absent': 8, 'ambiguous': 1, 'present_supported': 18, 'present_unsupported_form': 3}
  supported_correctness: 18/18
  supported_abstention: 0/18
  confidently_wrong: 0/18
  false_positive_absent: 0/8
  false_positive_unsupported_form: 0/3
  false_positive_ambiguous: 0/1
  provenance_correctness: 18/18
  missing_wired_input_gap: N/A
== skills ==
  opportunity matrix: {'absent': 410, 'ambiguous': 0, 'present_supported': 40, 'present_unsupported_form': 0}
  precision: 35/35
  recall: 35/40
  false_positive_absent: 0/410
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  false_positive_outside_frozen_set: 0/35
== runtime_failure (per parser invocation) ==
  employment_type: 0/30
  experience: 0/30
  location: 0/30
  remote_type: 0/30
  salary: 0/30
  seniority: 0/30
  skills: 0/30
== mismatches (163) ==
  record=anthropic:4017331008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4017331008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4017331008 parser=salary component=maximum category=missing_wired_input_gap expected=850000 actual=None
  record=anthropic:4017331008 parser=salary component=minimum category=missing_wired_input_gap expected=350000 actual=None
  record=anthropic:4017331008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4020350008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4020350008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4020350008 parser=salary component=maximum category=missing_wired_input_gap expected=850000 actual=None
  record=anthropic:4020350008 parser=salary component=minimum category=missing_wired_input_gap expected=280000 actual=None
  record=anthropic:4020350008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4423394008 parser=experience component=minimum category=supported_abstention expected=5 actual=None
  record=anthropic:4423394008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4423394008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4423394008 parser=salary component=maximum category=missing_wired_input_gap expected=380000 actual=None
  record=anthropic:4423394008 parser=salary component=minimum category=missing_wired_input_gap expected=222800 actual=None
  record=anthropic:4423394008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4461444008 parser=experience component=minimum category=supported_abstention expected=5 actual=None
  record=anthropic:4461444008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4461444008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4461444008 parser=salary component=maximum category=missing_wired_input_gap expected=315000 actual=None
  record=anthropic:4461444008 parser=salary component=minimum category=missing_wired_input_gap expected=240000 actual=None
  record=anthropic:4461444008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4461450008 parser=experience component=minimum category=supported_abstention expected=4 actual=None
  record=anthropic:4461450008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4461450008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4461450008 parser=salary component=maximum category=missing_wired_input_gap expected=290000 actual=None
  record=anthropic:4461450008 parser=salary component=minimum category=missing_wired_input_gap expected=222800 actual=None
  record=anthropic:4461450008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4502508008 parser=experience component=minimum category=supported_abstention expected=7 actual=None
  record=anthropic:4502508008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4502508008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4502508008 parser=salary component=maximum category=missing_wired_input_gap expected=485000 actual=None
  record=anthropic:4502508008 parser=salary component=minimum category=missing_wired_input_gap expected=320000 actual=None
  record=anthropic:4502508008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4502508008 parser=skills component=golang category=recall_miss expected='golang' actual=None
  record=anthropic:4572744008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4572744008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4572744008 parser=salary component=maximum category=missing_wired_input_gap expected=405000 actual=None
  record=anthropic:4572744008 parser=salary component=minimum category=missing_wired_input_gap expected=320000 actual=None
  record=anthropic:4572744008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4593216008 parser=experience component=minimum category=supported_abstention expected=8 actual=None
  record=anthropic:4593216008 parser=location component=city category=supported_abstention expected='San Francisco' actual=None
  record=anthropic:4593216008 parser=location component=state category=supported_abstention expected='CA' actual=None
  record=anthropic:4593216008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4593216008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4593216008 parser=salary component=maximum category=missing_wired_input_gap expected=850000 actual=None
  record=anthropic:4593216008 parser=salary component=minimum category=missing_wired_input_gap expected=350000 actual=None
  record=anthropic:4593216008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4595463008 parser=experience component=minimum category=supported_abstention expected=7 actual=None
  record=anthropic:4595463008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4595463008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4595463008 parser=salary component=maximum category=missing_wired_input_gap expected=405000 actual=None
  record=anthropic:4595463008 parser=salary component=minimum category=missing_wired_input_gap expected=320000 actual=None
  record=anthropic:4595463008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4610158008 parser=location component=city category=supported_abstention expected='London' actual=None
  record=anthropic:4610158008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4610158008 parser=salary component=currency category=missing_wired_input_gap expected='GBP' actual=None
  record=anthropic:4610158008 parser=salary component=maximum category=missing_wired_input_gap expected=370000 actual=None
  record=anthropic:4610158008 parser=salary component=minimum category=missing_wired_input_gap expected=260000 actual=None
  record=anthropic:4610158008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8214127002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8214127002 parser=remote_type component=None category=false_positive_ambiguous expected=None actual='remote'
  record=discord:8214127002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8214127002 parser=salary component=maximum category=missing_wired_input_gap expected=341000 actual=None
  record=discord:8214127002 parser=salary component=minimum category=missing_wired_input_gap expected=279000 actual=None
  record=discord:8214127002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8369347002 parser=experience component=minimum category=supported_abstention expected=4 actual=None
  record=discord:8369347002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8369347002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8369347002 parser=salary component=maximum category=missing_wired_input_gap expected=275000 actual=None
  record=discord:8369347002 parser=salary component=minimum category=missing_wired_input_gap expected=220000 actual=None
  record=discord:8369347002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8460791002 parser=experience component=minimum category=supported_abstention expected=5 actual=None
  record=discord:8460791002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8460791002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=discord:8460791002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8460791002 parser=salary component=maximum category=missing_wired_input_gap expected=220000 actual=None
  record=discord:8460791002 parser=salary component=minimum category=missing_wired_input_gap expected=196000 actual=None
  record=discord:8460791002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8464570002 parser=experience component=minimum category=supported_abstention expected=8 actual=None
  record=discord:8464570002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8464570002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8464570002 parser=salary component=maximum category=missing_wired_input_gap expected=279000 actual=None
  record=discord:8464570002 parser=salary component=minimum category=missing_wired_input_gap expected=248000 actual=None
  record=discord:8464570002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8498984002 parser=experience component=minimum category=supported_abstention expected=7 actual=None
  record=discord:8498984002 parser=location component=city category=supported_abstention expected='San Francisco' actual=None
  record=discord:8498984002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8498984002 parser=location component=state category=supported_abstention expected='CA' actual=None
  record=discord:8498984002 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=discord:8498984002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8498984002 parser=salary component=maximum category=missing_wired_input_gap expected=341000 actual=None
  record=discord:8498984002 parser=salary component=minimum category=missing_wired_input_gap expected=279000 actual=None
  record=discord:8498984002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8537955002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8537955002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=discord:8537955002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8537955002 parser=salary component=maximum category=missing_wired_input_gap expected=341000 actual=None
  record=discord:8537955002 parser=salary component=minimum category=missing_wired_input_gap expected=248000 actual=None
  record=discord:8537955002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8545675002 parser=experience component=minimum category=supported_abstention expected=5 actual=None
  record=discord:8545675002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8545675002 parser=remote_type component=None category=false_positive_ambiguous expected=None actual='remote'
  record=discord:8545675002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8545675002 parser=salary component=maximum category=missing_wired_input_gap expected=269500 actual=None
  record=discord:8545675002 parser=salary component=minimum category=missing_wired_input_gap expected=220500 actual=None
  record=discord:8545675002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8571766002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8571766002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8571766002 parser=salary component=maximum category=missing_wired_input_gap expected=550000 actual=None
  record=discord:8571766002 parser=salary component=minimum category=missing_wired_input_gap expected=450000 actual=None
  record=discord:8571766002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8575166002 parser=experience component=minimum category=supported_abstention expected=2 actual=None
  record=discord:8575166002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8575166002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8575166002 parser=salary component=maximum category=missing_wired_input_gap expected=130500 actual=None
  record=discord:8575166002 parser=salary component=minimum category=missing_wired_input_gap expected=116000 actual=None
  record=discord:8575166002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8581126002 parser=experience component=minimum category=supported_abstention expected=5 actual=None
  record=discord:8581126002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8581126002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8581126002 parser=salary component=maximum category=missing_wired_input_gap expected=220500 actual=None
  record=discord:8581126002 parser=salary component=minimum category=missing_wired_input_gap expected=196000 actual=None
  record=discord:8581126002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=gitlab:8396674002 parser=location component=city category=supported_abstention expected='San Francisco' actual=None
  record=gitlab:8396674002 parser=location component=state category=supported_abstention expected='CA' actual=None
  record=gitlab:8396674002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8396674002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=gitlab:8396674002 parser=salary component=maximum category=missing_wired_input_gap expected=231300 actual=None
  record=gitlab:8396674002 parser=salary component=minimum category=missing_wired_input_gap expected=154200 actual=None
  record=gitlab:8396674002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=gitlab:8451512002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8451512002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=gitlab:8451512002 parser=salary component=maximum category=missing_wired_input_gap expected=252000 actual=None
  record=gitlab:8451512002 parser=salary component=minimum category=missing_wired_input_gap expected=117600 actual=None
  record=gitlab:8451512002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=gitlab:8463922002 parser=location component=city category=supported_abstention expected='Bangalore' actual=None
  record=gitlab:8463922002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8463922002 parser=skills component=golang category=recall_miss expected='golang' actual=None
  record=gitlab:8476375002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8478405002 parser=experience component=minimum category=supported_abstention expected=4 actual=None
  record=gitlab:8478405002 parser=location component=city category=supported_abstention expected='Bangalore' actual=None
  record=gitlab:8478405002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8490477002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8490477002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=gitlab:8490477002 parser=salary component=maximum category=missing_wired_input_gap expected=282000 actual=None
  record=gitlab:8490477002 parser=salary component=minimum category=missing_wired_input_gap expected=131600 actual=None
  record=gitlab:8490477002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=gitlab:8490477002 parser=skills component=golang category=recall_miss expected='golang' actual=None
  record=gitlab:8500014002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8512220002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8512220002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=gitlab:8512220002 parser=salary component=maximum category=missing_wired_input_gap expected=235200 actual=None
  record=gitlab:8512220002 parser=salary component=minimum category=missing_wired_input_gap expected=139200 actual=None
  record=gitlab:8512220002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=gitlab:8512432002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8512432002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=gitlab:8512432002 parser=salary component=maximum category=missing_wired_input_gap expected=297000 actual=None
  record=gitlab:8512432002 parser=salary component=minimum category=missing_wired_input_gap expected=254000 actual=None
  record=gitlab:8512432002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=gitlab:8512432002 parser=skills component=golang category=recall_miss expected='golang' actual=None
  record=gitlab:8514960002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8514960002 parser=skills component=golang category=recall_miss expected='golang' actual=None
===== split: employer:Anthropic =====
== employment_type ==
  opportunity matrix: {'absent': 10, 'ambiguous': 0, 'present_supported': 0, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/10
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== experience.maximum ==
  opportunity matrix: {'absent': 10, 'ambiguous': 0, 'present_supported': 0, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/10
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== experience.minimum ==
  opportunity matrix: {'absent': 4, 'ambiguous': 0, 'present_supported': 6, 'present_unsupported_form': 0}
  supported_correctness: 0/6
  supported_abstention: 6/6
  confidently_wrong: 0/6
  false_positive_absent: 0/4
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== location.city ==
  opportunity matrix: {'absent': 0, 'ambiguous': 8, 'present_supported': 2, 'present_unsupported_form': 0}
  supported_correctness: 0/2
  supported_abstention: 2/2
  confidently_wrong: 0/2
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: 0/8
  provenance_correctness: N/A
  missing_wired_input_gap: 0/2
== location.country ==
  opportunity matrix: {'absent': 9, 'ambiguous': 0, 'present_supported': 1, 'present_unsupported_form': 0}
  supported_correctness: 1/1
  supported_abstention: 0/1
  confidently_wrong: 0/1
  false_positive_absent: 0/9
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: 0/1
  missing_wired_input_gap: 0/1
== location.postal_code ==
  opportunity matrix: {'absent': 10, 'ambiguous': 0, 'present_supported': 0, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/10
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== location.state ==
  opportunity matrix: {'absent': 1, 'ambiguous': 8, 'present_supported': 1, 'present_unsupported_form': 0}
  supported_correctness: 0/1
  supported_abstention: 1/1
  confidently_wrong: 0/1
  false_positive_absent: 0/1
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: 0/8
  provenance_correctness: N/A
  missing_wired_input_gap: 0/1
== remote_type ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 10, 'present_unsupported_form': 0}
  supported_correctness: 0/10
  supported_abstention: 10/10
  confidently_wrong: 0/10
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== salary.currency ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 10, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 10/10
== salary.maximum ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 10, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 10/10
== salary.minimum ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 10, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 10/10
== salary.period ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 10, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 10/10
== seniority ==
  opportunity matrix: {'absent': 7, 'ambiguous': 1, 'present_supported': 2, 'present_unsupported_form': 0}
  supported_correctness: 2/2
  supported_abstention: 0/2
  confidently_wrong: 0/2
  false_positive_absent: 0/7
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: 0/1
  provenance_correctness: 2/2
  missing_wired_input_gap: N/A
== skills ==
  opportunity matrix: {'absent': 140, 'ambiguous': 0, 'present_supported': 10, 'present_unsupported_form': 0}
  precision: 9/9
  recall: 9/10
  false_positive_absent: 0/140
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  false_positive_outside_frozen_set: 0/9
== runtime_failure (per parser invocation) ==
  employment_type: 0/10
  experience: 0/10
  location: 0/10
  remote_type: 0/10
  salary: 0/10
  seniority: 0/10
  skills: 0/10
== mismatches (60) ==
  record=anthropic:4017331008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4017331008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4017331008 parser=salary component=maximum category=missing_wired_input_gap expected=850000 actual=None
  record=anthropic:4017331008 parser=salary component=minimum category=missing_wired_input_gap expected=350000 actual=None
  record=anthropic:4017331008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4020350008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4020350008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4020350008 parser=salary component=maximum category=missing_wired_input_gap expected=850000 actual=None
  record=anthropic:4020350008 parser=salary component=minimum category=missing_wired_input_gap expected=280000 actual=None
  record=anthropic:4020350008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4423394008 parser=experience component=minimum category=supported_abstention expected=5 actual=None
  record=anthropic:4423394008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4423394008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4423394008 parser=salary component=maximum category=missing_wired_input_gap expected=380000 actual=None
  record=anthropic:4423394008 parser=salary component=minimum category=missing_wired_input_gap expected=222800 actual=None
  record=anthropic:4423394008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4461444008 parser=experience component=minimum category=supported_abstention expected=5 actual=None
  record=anthropic:4461444008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4461444008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4461444008 parser=salary component=maximum category=missing_wired_input_gap expected=315000 actual=None
  record=anthropic:4461444008 parser=salary component=minimum category=missing_wired_input_gap expected=240000 actual=None
  record=anthropic:4461444008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4461450008 parser=experience component=minimum category=supported_abstention expected=4 actual=None
  record=anthropic:4461450008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4461450008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4461450008 parser=salary component=maximum category=missing_wired_input_gap expected=290000 actual=None
  record=anthropic:4461450008 parser=salary component=minimum category=missing_wired_input_gap expected=222800 actual=None
  record=anthropic:4461450008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4502508008 parser=experience component=minimum category=supported_abstention expected=7 actual=None
  record=anthropic:4502508008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4502508008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4502508008 parser=salary component=maximum category=missing_wired_input_gap expected=485000 actual=None
  record=anthropic:4502508008 parser=salary component=minimum category=missing_wired_input_gap expected=320000 actual=None
  record=anthropic:4502508008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4502508008 parser=skills component=golang category=recall_miss expected='golang' actual=None
  record=anthropic:4572744008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4572744008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4572744008 parser=salary component=maximum category=missing_wired_input_gap expected=405000 actual=None
  record=anthropic:4572744008 parser=salary component=minimum category=missing_wired_input_gap expected=320000 actual=None
  record=anthropic:4572744008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4593216008 parser=experience component=minimum category=supported_abstention expected=8 actual=None
  record=anthropic:4593216008 parser=location component=city category=supported_abstention expected='San Francisco' actual=None
  record=anthropic:4593216008 parser=location component=state category=supported_abstention expected='CA' actual=None
  record=anthropic:4593216008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4593216008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4593216008 parser=salary component=maximum category=missing_wired_input_gap expected=850000 actual=None
  record=anthropic:4593216008 parser=salary component=minimum category=missing_wired_input_gap expected=350000 actual=None
  record=anthropic:4593216008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4595463008 parser=experience component=minimum category=supported_abstention expected=7 actual=None
  record=anthropic:4595463008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4595463008 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=anthropic:4595463008 parser=salary component=maximum category=missing_wired_input_gap expected=405000 actual=None
  record=anthropic:4595463008 parser=salary component=minimum category=missing_wired_input_gap expected=320000 actual=None
  record=anthropic:4595463008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=anthropic:4610158008 parser=location component=city category=supported_abstention expected='London' actual=None
  record=anthropic:4610158008 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=anthropic:4610158008 parser=salary component=currency category=missing_wired_input_gap expected='GBP' actual=None
  record=anthropic:4610158008 parser=salary component=maximum category=missing_wired_input_gap expected=370000 actual=None
  record=anthropic:4610158008 parser=salary component=minimum category=missing_wired_input_gap expected=260000 actual=None
  record=anthropic:4610158008 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
===== split: employer:Discord =====
== employment_type ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 10, 'present_unsupported_form': 0}
  supported_correctness: 10/10
  supported_abstention: 0/10
  confidently_wrong: 0/10
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: 10/10
  missing_wired_input_gap: N/A
== experience.maximum ==
  opportunity matrix: {'absent': 10, 'ambiguous': 0, 'present_supported': 0, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/10
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== experience.minimum ==
  opportunity matrix: {'absent': 1, 'ambiguous': 2, 'present_supported': 7, 'present_unsupported_form': 0}
  supported_correctness: 0/7
  supported_abstention: 7/7
  confidently_wrong: 0/7
  false_positive_absent: 0/1
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: 0/2
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== location.city ==
  opportunity matrix: {'absent': 9, 'ambiguous': 0, 'present_supported': 1, 'present_unsupported_form': 0}
  supported_correctness: 0/1
  supported_abstention: 1/1
  confidently_wrong: 0/1
  false_positive_absent: 0/9
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 0/1
== location.country ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 10, 'present_unsupported_form': 0}
  supported_correctness: 0/10
  supported_abstention: 10/10
  confidently_wrong: 0/10
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 0/10
== location.postal_code ==
  opportunity matrix: {'absent': 10, 'ambiguous': 0, 'present_supported': 0, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/10
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== location.state ==
  opportunity matrix: {'absent': 9, 'ambiguous': 0, 'present_supported': 1, 'present_unsupported_form': 0}
  supported_correctness: 0/1
  supported_abstention: 1/1
  confidently_wrong: 0/1
  false_positive_absent: 0/9
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 0/1
== remote_type ==
  opportunity matrix: {'absent': 5, 'ambiguous': 2, 'present_supported': 3, 'present_unsupported_form': 0}
  supported_correctness: 0/3
  supported_abstention: 3/3
  confidently_wrong: 0/3
  false_positive_absent: 0/5
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: 2/2
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== salary.currency ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 10, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 10/10
== salary.maximum ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 10, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 10/10
== salary.minimum ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 10, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 10/10
== salary.period ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 10, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 10/10
== seniority ==
  opportunity matrix: {'absent': 1, 'ambiguous': 0, 'present_supported': 8, 'present_unsupported_form': 1}
  supported_correctness: 8/8
  supported_abstention: 0/8
  confidently_wrong: 0/8
  false_positive_absent: 0/1
  false_positive_unsupported_form: 0/1
  false_positive_ambiguous: N/A
  provenance_correctness: 8/8
  missing_wired_input_gap: N/A
== skills ==
  opportunity matrix: {'absent': 138, 'ambiguous': 0, 'present_supported': 12, 'present_unsupported_form': 0}
  precision: 12/12
  recall: 12/12
  false_positive_absent: 0/138
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  false_positive_outside_frozen_set: 0/12
== runtime_failure (per parser invocation) ==
  employment_type: 0/10
  experience: 0/10
  location: 0/10
  remote_type: 0/10
  salary: 0/10
  seniority: 0/10
  skills: 0/10
== mismatches (64) ==
  record=discord:8214127002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8214127002 parser=remote_type component=None category=false_positive_ambiguous expected=None actual='remote'
  record=discord:8214127002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8214127002 parser=salary component=maximum category=missing_wired_input_gap expected=341000 actual=None
  record=discord:8214127002 parser=salary component=minimum category=missing_wired_input_gap expected=279000 actual=None
  record=discord:8214127002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8369347002 parser=experience component=minimum category=supported_abstention expected=4 actual=None
  record=discord:8369347002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8369347002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8369347002 parser=salary component=maximum category=missing_wired_input_gap expected=275000 actual=None
  record=discord:8369347002 parser=salary component=minimum category=missing_wired_input_gap expected=220000 actual=None
  record=discord:8369347002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8460791002 parser=experience component=minimum category=supported_abstention expected=5 actual=None
  record=discord:8460791002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8460791002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=discord:8460791002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8460791002 parser=salary component=maximum category=missing_wired_input_gap expected=220000 actual=None
  record=discord:8460791002 parser=salary component=minimum category=missing_wired_input_gap expected=196000 actual=None
  record=discord:8460791002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8464570002 parser=experience component=minimum category=supported_abstention expected=8 actual=None
  record=discord:8464570002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8464570002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8464570002 parser=salary component=maximum category=missing_wired_input_gap expected=279000 actual=None
  record=discord:8464570002 parser=salary component=minimum category=missing_wired_input_gap expected=248000 actual=None
  record=discord:8464570002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8498984002 parser=experience component=minimum category=supported_abstention expected=7 actual=None
  record=discord:8498984002 parser=location component=city category=supported_abstention expected='San Francisco' actual=None
  record=discord:8498984002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8498984002 parser=location component=state category=supported_abstention expected='CA' actual=None
  record=discord:8498984002 parser=remote_type component=None category=supported_abstention expected='hybrid' actual=None
  record=discord:8498984002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8498984002 parser=salary component=maximum category=missing_wired_input_gap expected=341000 actual=None
  record=discord:8498984002 parser=salary component=minimum category=missing_wired_input_gap expected=279000 actual=None
  record=discord:8498984002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8537955002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8537955002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=discord:8537955002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8537955002 parser=salary component=maximum category=missing_wired_input_gap expected=341000 actual=None
  record=discord:8537955002 parser=salary component=minimum category=missing_wired_input_gap expected=248000 actual=None
  record=discord:8537955002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8545675002 parser=experience component=minimum category=supported_abstention expected=5 actual=None
  record=discord:8545675002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8545675002 parser=remote_type component=None category=false_positive_ambiguous expected=None actual='remote'
  record=discord:8545675002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8545675002 parser=salary component=maximum category=missing_wired_input_gap expected=269500 actual=None
  record=discord:8545675002 parser=salary component=minimum category=missing_wired_input_gap expected=220500 actual=None
  record=discord:8545675002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8571766002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8571766002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8571766002 parser=salary component=maximum category=missing_wired_input_gap expected=550000 actual=None
  record=discord:8571766002 parser=salary component=minimum category=missing_wired_input_gap expected=450000 actual=None
  record=discord:8571766002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8575166002 parser=experience component=minimum category=supported_abstention expected=2 actual=None
  record=discord:8575166002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8575166002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8575166002 parser=salary component=maximum category=missing_wired_input_gap expected=130500 actual=None
  record=discord:8575166002 parser=salary component=minimum category=missing_wired_input_gap expected=116000 actual=None
  record=discord:8575166002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=discord:8581126002 parser=experience component=minimum category=supported_abstention expected=5 actual=None
  record=discord:8581126002 parser=location component=country category=supported_abstention expected='United States' actual=None
  record=discord:8581126002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=discord:8581126002 parser=salary component=maximum category=missing_wired_input_gap expected=220500 actual=None
  record=discord:8581126002 parser=salary component=minimum category=missing_wired_input_gap expected=196000 actual=None
  record=discord:8581126002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
===== split: employer:GitLab =====
== employment_type ==
  opportunity matrix: {'absent': 10, 'ambiguous': 0, 'present_supported': 0, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/10
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== experience.maximum ==
  opportunity matrix: {'absent': 10, 'ambiguous': 0, 'present_supported': 0, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/10
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== experience.minimum ==
  opportunity matrix: {'absent': 9, 'ambiguous': 0, 'present_supported': 1, 'present_unsupported_form': 0}
  supported_correctness: 0/1
  supported_abstention: 1/1
  confidently_wrong: 0/1
  false_positive_absent: 0/9
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== location.city ==
  opportunity matrix: {'absent': 7, 'ambiguous': 0, 'present_supported': 3, 'present_unsupported_form': 0}
  supported_correctness: 0/3
  supported_abstention: 3/3
  confidently_wrong: 0/3
  false_positive_absent: 0/7
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 0/3
== location.country ==
  opportunity matrix: {'absent': 0, 'ambiguous': 6, 'present_supported': 4, 'present_unsupported_form': 0}
  supported_correctness: 4/4
  supported_abstention: 0/4
  confidently_wrong: 0/4
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: 0/6
  provenance_correctness: 2/4
  missing_wired_input_gap: 0/4
== location.postal_code ==
  opportunity matrix: {'absent': 10, 'ambiguous': 0, 'present_supported': 0, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/10
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== location.state ==
  opportunity matrix: {'absent': 9, 'ambiguous': 0, 'present_supported': 1, 'present_unsupported_form': 0}
  supported_correctness: 0/1
  supported_abstention: 1/1
  confidently_wrong: 0/1
  false_positive_absent: 0/9
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 0/1
== remote_type ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 10, 'present_unsupported_form': 0}
  supported_correctness: 0/10
  supported_abstention: 10/10
  confidently_wrong: 0/10
  false_positive_absent: N/A
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: N/A
== salary.currency ==
  opportunity matrix: {'absent': 5, 'ambiguous': 0, 'present_supported': 5, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/5
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 5/5
== salary.maximum ==
  opportunity matrix: {'absent': 5, 'ambiguous': 0, 'present_supported': 5, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/5
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 5/5
== salary.minimum ==
  opportunity matrix: {'absent': 5, 'ambiguous': 0, 'present_supported': 5, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/5
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 5/5
== salary.period ==
  opportunity matrix: {'absent': 5, 'ambiguous': 0, 'present_supported': 5, 'present_unsupported_form': 0}
  supported_correctness: N/A
  supported_abstention: N/A
  confidently_wrong: N/A
  false_positive_absent: 0/5
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  provenance_correctness: N/A
  missing_wired_input_gap: 5/5
== seniority ==
  opportunity matrix: {'absent': 0, 'ambiguous': 0, 'present_supported': 8, 'present_unsupported_form': 2}
  supported_correctness: 8/8
  supported_abstention: 0/8
  confidently_wrong: 0/8
  false_positive_absent: N/A
  false_positive_unsupported_form: 0/2
  false_positive_ambiguous: N/A
  provenance_correctness: 8/8
  missing_wired_input_gap: N/A
== skills ==
  opportunity matrix: {'absent': 132, 'ambiguous': 0, 'present_supported': 18, 'present_unsupported_form': 0}
  precision: 14/14
  recall: 14/18
  false_positive_absent: 0/132
  false_positive_unsupported_form: N/A
  false_positive_ambiguous: N/A
  false_positive_outside_frozen_set: 0/14
== runtime_failure (per parser invocation) ==
  employment_type: 0/10
  experience: 0/10
  location: 0/10
  remote_type: 0/10
  salary: 0/10
  seniority: 0/10
  skills: 0/10
== mismatches (39) ==
  record=gitlab:8396674002 parser=location component=city category=supported_abstention expected='San Francisco' actual=None
  record=gitlab:8396674002 parser=location component=state category=supported_abstention expected='CA' actual=None
  record=gitlab:8396674002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8396674002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=gitlab:8396674002 parser=salary component=maximum category=missing_wired_input_gap expected=231300 actual=None
  record=gitlab:8396674002 parser=salary component=minimum category=missing_wired_input_gap expected=154200 actual=None
  record=gitlab:8396674002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=gitlab:8451512002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8451512002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=gitlab:8451512002 parser=salary component=maximum category=missing_wired_input_gap expected=252000 actual=None
  record=gitlab:8451512002 parser=salary component=minimum category=missing_wired_input_gap expected=117600 actual=None
  record=gitlab:8451512002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=gitlab:8463922002 parser=location component=city category=supported_abstention expected='Bangalore' actual=None
  record=gitlab:8463922002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8463922002 parser=skills component=golang category=recall_miss expected='golang' actual=None
  record=gitlab:8476375002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8478405002 parser=experience component=minimum category=supported_abstention expected=4 actual=None
  record=gitlab:8478405002 parser=location component=city category=supported_abstention expected='Bangalore' actual=None
  record=gitlab:8478405002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8490477002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8490477002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=gitlab:8490477002 parser=salary component=maximum category=missing_wired_input_gap expected=282000 actual=None
  record=gitlab:8490477002 parser=salary component=minimum category=missing_wired_input_gap expected=131600 actual=None
  record=gitlab:8490477002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=gitlab:8490477002 parser=skills component=golang category=recall_miss expected='golang' actual=None
  record=gitlab:8500014002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8512220002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8512220002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=gitlab:8512220002 parser=salary component=maximum category=missing_wired_input_gap expected=235200 actual=None
  record=gitlab:8512220002 parser=salary component=minimum category=missing_wired_input_gap expected=139200 actual=None
  record=gitlab:8512220002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=gitlab:8512432002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8512432002 parser=salary component=currency category=missing_wired_input_gap expected='USD' actual=None
  record=gitlab:8512432002 parser=salary component=maximum category=missing_wired_input_gap expected=297000 actual=None
  record=gitlab:8512432002 parser=salary component=minimum category=missing_wired_input_gap expected=254000 actual=None
  record=gitlab:8512432002 parser=salary component=period category=missing_wired_input_gap expected='annual' actual=None
  record=gitlab:8512432002 parser=skills component=golang category=recall_miss expected='golang' actual=None
  record=gitlab:8514960002 parser=remote_type component=None category=supported_abstention expected='remote' actual=None
  record=gitlab:8514960002 parser=skills component=golang category=recall_miss expected='golang' actual=None
note: every record's provenance.template_family is 'unknown' -- a per-template breakdown would only ever duplicate the combined result above, so it is intentionally omitted; see the per-employer sections instead.
```
