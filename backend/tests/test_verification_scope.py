from __future__ import annotations

from pathlib import Path

import pytest

from scripts import verification_scope as vs

_TAXONOMY_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "taxonomy"


def test_direct_child_test_file_classified_as_generic_changed_test() -> None:
    c = vs.classify_path("backend/tests/test_verify.py")
    assert c.category == "generic-changed-test"
    assert c.directly_execute is True


def test_nested_test_file_classified_as_generic_changed_test() -> None:
    c = vs.classify_path("backend/tests/contracts/test_harness_import_boundary.py")
    assert c.category == "generic-changed-test"
    assert c.directly_execute is True


@pytest.mark.parametrize(
    ("path", "expected_category"),
    [
        ("backend/app/normalization/location.py", "parser:location"),
        ("backend/app/normalization/salary.py", "parser:salary"),
        ("backend/app/normalization/experience.py", "parser:experience"),
        ("backend/tests/contracts/adapters/location.py", "adapter:location"),
        ("backend/tests/contracts/adapters/salary.py", "adapter:salary"),
        ("backend/tests/contracts/adapters/experience.py", "adapter:experience"),
        ("backend/tests/contracts/records/location.json", "contract-record:location"),
        ("backend/tests/contracts/records/salary.json", "contract-record:salary"),
        ("backend/tests/contracts/records/experience.json", "contract-record:experience"),
        (
            "backend/tests/fixtures/taxonomy/valid_minimal.yaml",
            "test-fixture:skill-taxonomy",
        ),
        (
            "backend/tests/fixtures/taxonomy/duplicate_canonical_id.yaml",
            "test-fixture:skill-taxonomy",
        ),
        (
            "backend/tests/fixtures/normalization/skill_cases.json",
            "test-fixture:skill-classifier",
        ),
        ("backend/tests/contracts/taxonomy.py", "shared-harness-core"),
        ("backend/tests/contracts/transforms.py", "shared-harness-core"),
        ("backend/tests/contracts/mutation_registry.py", "shared-harness-core"),
        ("backend/tests/contracts/schema.py", "shared-harness-core"),
        ("backend/tests/contracts/loader.py", "shared-harness-core"),
        ("backend/tests/contracts/runner.py", "shared-harness-core"),
        ("backend/scripts/contract_mutation_witnesses.py", "shared-harness-core"),
        ("backend/scripts/verify.py", "workflow-script"),
        ("backend/scripts/check_handoff.py", "workflow-script"),
        ("backend/scripts/check_review.py", "workflow-script"),
        ("backend/scripts/verification_scope.py", "workflow-script"),
        ("backend/scripts/verification_receipts.py", "workflow-script"),
        ("backend/scripts/verification_worktree.py", "workflow-script"),
        ("backend/scripts/verification_coordinator.py", "workflow-script"),
        ("backend/scripts/migration_matrix.py", "workflow-script"),
        (".claude/hooks/compact_checkpoint.py", "workflow-hook"),
        (".claude/settings.json", "root-configuration"),
        ("backend/pyproject.toml", "root-configuration"),
        (".gitignore", "root-configuration"),
        ("CLAUDE.md", "workflow-governing-doc"),
        ("docs/LLM_WORKFLOW.md", "workflow-governing-doc"),
        ("docs/LLM_HANDOFF.md", "handoff-transition"),
        ("docs/ARCHITECTURE.md", "docs-only"),
        ("docs/DATA_MODEL.md", "docs-only"),
        ("docs/ROADMAP.md", "docs-only"),
        ("docs/PHASE_RISK_CHECKLIST.md", "docs-only"),
        ("docs/DECISIONS/0009-workflow-v3.2-activation.md", "docs-only"),
        ("backend/app/some_new_unmapped_module.py", "unmapped"),
    ],
)
def test_every_declared_pattern_classifies_correctly(path: str, expected_category: str) -> None:
    assert vs.classify_path(path).category == expected_category


def test_non_python_path_under_backend_tests_requires_owner_mapping() -> None:
    with pytest.raises(vs.OwnerMappingRequiredError, match="owner mapping required"):
        vs.classify_path("backend/tests/some_stray_fixture.data")


def test_json_fixture_already_mapped_does_not_require_owner_mapping() -> None:
    # A non-.py path under backend/tests/ that IS covered by a more specific
    # exact rule must resolve to that rule, never to OwnerMappingRequiredError.
    c = vs.classify_path("backend/tests/contracts/records/location.json")
    assert c.category == "contract-record:location"


def test_every_taxonomy_fixture_file_is_mapped_never_owner_mapping_required() -> None:
    """Complete inventory, never a subset -- genuinely discovers every
    file actually present on disk under `backend/tests/fixtures/
    taxonomy/` and asserts exact equality with `_TAXONOMY_FIXTURE_FILES`'
    own keys, so an added-but-not-mapped (or removed-but-still-mapped)
    fixture file fails this test, not merely the samples this test
    happens to check by name."""
    actual_paths = {
        f"backend/tests/fixtures/taxonomy/{entry.name}"
        for entry in _TAXONOMY_FIXTURES_DIR.iterdir()
        if entry.is_file() and entry.suffix == ".yaml"
    }
    assert actual_paths == set(vs._TAXONOMY_FIXTURE_FILES)
    for path in actual_paths:
        assert vs.classify_path(path).category == "test-fixture:skill-taxonomy"


def test_taxonomy_fixture_category_never_requires_contract_family_coverage() -> None:
    classifications = [vs.classify_path(path) for path in vs._TAXONOMY_FIXTURE_FILES]
    assert vs.required_contract_families(classifications) == frozenset()


def test_skill_fixture_file_is_mapped_never_owner_mapping_required() -> None:
    for path in vs._SKILL_FIXTURE_FILES:
        assert vs.classify_path(path).category == "test-fixture:skill-classifier"


def test_skill_fixture_category_never_requires_contract_family_coverage() -> None:
    classifications = [vs.classify_path(path) for path in vs._SKILL_FIXTURE_FILES]
    assert vs.required_contract_families(classifications) == frozenset()


def test_unmapped_python_path_is_never_a_literal_pytest_focus_target() -> None:
    """An unmapped path is not known to be a test file (and typically
    isn't even under backend/tests/, which verify.py's own focus
    validation requires) -- it must never be passed as a literal --focus
    target; it forces --gate final instead, which already runs the full
    suite unconditionally."""
    c = vs.classify_path("backend/app/some_new_unmapped_module.py")
    assert c.category == "unmapped"
    assert c.directly_execute is False


def test_non_normalized_path_is_rejected() -> None:
    with pytest.raises(vs.ScopeConfigurationError):
        vs.classify_path("backend\\scripts\\verify.py")
    with pytest.raises(vs.ScopeConfigurationError):
        vs.classify_path("./backend/scripts/verify.py")
    with pytest.raises(vs.ScopeConfigurationError):
        vs.classify_path("../backend/scripts/verify.py")


def test_duplicate_exact_rule_is_rejected_at_configuration_time() -> None:
    # Direct fault injection: construct a colliding table shape and confirm
    # the same validator function rejects it.
    original = dict(vs._PARSER_FILES)
    try:
        vs._PARSER_FILES["backend/scripts/verify.py"] = (
            "parser:bogus"  # collides w/ workflow-script
        )
        with pytest.raises(vs.ScopeConfigurationError, match="duplicate exact-path rule"):
            vs._validate_configuration()
    finally:
        vs._PARSER_FILES.clear()
        vs._PARSER_FILES.update(original)


def test_duplicate_or_nested_directory_prefix_is_rejected_at_configuration_time() -> None:
    original = vs._ALL_DIRECTORY_PREFIXES
    try:
        vs._ALL_DIRECTORY_PREFIXES = (*original, "backend/tests/contracts/")  # nested prefix
        with pytest.raises(vs.ScopeConfigurationError, match="disjoint"):
            vs._validate_configuration()
    finally:
        vs._ALL_DIRECTORY_PREFIXES = original


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("backend/migrations/versions/0004_new.py", True),
        ("backend/alembic.ini", True),
        ("backend/app/db/models/job.py", True),
        ("backend/app/db/session.py", True),
        ("backend/app/normalization/location.py", False),
        ("docs/ARCHITECTURE.md", False),
    ],
)
def test_migration_trigger_paths(path: str, expected: bool) -> None:
    assert vs.is_migration_trigger(path) is expected


def test_required_contract_families_shared_harness_requires_all_three() -> None:
    classifications = vs.classify_all(["backend/tests/contracts/taxonomy.py"])
    families = vs.required_contract_families(classifications)
    assert families == frozenset({"location", "salary", "experience"})


def test_required_contract_families_single_parser_change() -> None:
    classifications = vs.classify_all(["backend/app/normalization/salary.py"])
    assert vs.required_contract_families(classifications) == frozenset({"salary"})


def test_forces_final_gate_for_workflow_hook_change() -> None:
    classifications = vs.classify_all([".claude/hooks/compact_checkpoint.py"])
    assert vs.forces_final_gate(classifications) is True


def test_forces_final_gate_for_unmapped_path() -> None:
    classifications = vs.classify_all(["backend/app/some_new_unmapped_module.py"])
    assert vs.forces_final_gate(classifications) is True


def test_does_not_force_final_gate_for_single_parser_change() -> None:
    classifications = vs.classify_all(["backend/app/normalization/salary.py"])
    assert vs.forces_final_gate(classifications) is False


# ---------------------------------------------------------------------------
# compute_required_coverage -- the single pre-execution source of truth
# ---------------------------------------------------------------------------


def test_compute_required_coverage_empty_diff_is_not_applicable() -> None:
    coverage = vs.compute_required_coverage([])
    assert coverage.not_applicable_reason == "no_changed_paths"
    assert coverage.forces_final is False
    assert coverage.required_focus_targets == frozenset()


def test_compute_required_coverage_single_parser_change() -> None:
    coverage = vs.compute_required_coverage(["backend/app/normalization/salary.py"])
    assert coverage.forces_final is False
    assert coverage.required_contract_families == frozenset({"salary"})
    assert "backend/tests/contracts/test_salary_contract.py" in coverage.required_focus_targets
    assert "backend/tests/contracts/test_harness_self.py" in coverage.required_focus_targets
    assert all(ref.startswith("salary/") for ref in coverage.required_guard_refs)
    assert len(coverage.required_guard_refs) == 5  # all 5 active salary guards
    assert coverage.not_applicable_reason is None


def test_compute_required_coverage_shared_harness_requires_all_three_families() -> None:
    coverage = vs.compute_required_coverage(["backend/tests/contracts/taxonomy.py"])
    assert coverage.required_contract_families == frozenset({"location", "salary", "experience"})
    assert coverage.forces_final is True
    assert len(coverage.required_guard_refs) == 34  # every active guard, all three parsers


def test_compute_required_coverage_docs_only_diff_is_not_applicable() -> None:
    coverage = vs.compute_required_coverage(["docs/ARCHITECTURE.md"])
    assert coverage.not_applicable_reason == "docs_only_within_executable_slice"
    assert coverage.forces_final is False


def test_compute_required_coverage_workflow_hook_forces_final_never_a_focus_target() -> None:
    """A workflow-hook path forces --gate final (which runs the full
    suite unconditionally) but must never itself be passed as a literal
    pytest --focus target -- it isn't under backend/tests/, and verify.py
    would reject it outright."""
    coverage = vs.compute_required_coverage([".claude/hooks/compact_checkpoint.py"])
    assert coverage.forces_final is True
    assert ".claude/hooks/compact_checkpoint.py" not in coverage.directly_executed_tests
    assert ".claude/hooks/compact_checkpoint.py" not in coverage.required_focus_targets


def test_compute_required_coverage_generic_test_change_is_directly_executed() -> None:
    coverage = vs.compute_required_coverage(["backend/tests/test_verify.py"])
    assert "backend/tests/test_verify.py" in coverage.required_focus_targets
    assert "backend/tests/test_verify.py" in coverage.directly_executed_tests
    assert coverage.required_contract_families == frozenset()
