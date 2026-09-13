from __future__ import annotations

import pytest

from scripts import verification_scope as vs


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


def test_unmapped_python_path_is_marked_for_direct_execution() -> None:
    c = vs.classify_path("backend/app/some_new_unmapped_module.py")
    assert c.category == "unmapped"
    assert c.directly_execute is True


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
