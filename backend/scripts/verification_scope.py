"""Affected-surface classification for Workflow v3.2 (activation slice).

Classifies every repository-root-relative, POSIX-normalized changed path
(as produced by `git diff --name-only` run at the repository root) into
exactly one category, using only two deterministic, explicitly anchored
matching kinds -- never a glob library, never mid-path wildcard semantics:

- **Exact-path** rules: `changed_path == pattern`.
- **Directory-prefix** rules: `changed_path.startswith(prefix + "/")`.

Exact rules take precedence over directory rules. The rule table itself is
validated once, at import time, to contain no duplicate exact path and no
duplicate directory prefix -- a configuration error, never a per-run
ambiguity. Given that invariant, no two rules in this table can ever match
the same changed path (the two directory prefixes are disjoint; an exact
path is unique), so the "multiple matches" case is structurally
unreachable and is not defended against at runtime with a synthetic
same-specificity test -- only genuinely reachable behavior is tested here.

Unknown/unmapped paths -- and any `.py` file directly under
`backend/tests/` not already covered by a more specific exact rule --
resolve via the standing rules below, never silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass

Category = str

# ---------------------------------------------------------------------------
# Exact-path rules -- one literal repository-root-relative path each.
# ---------------------------------------------------------------------------

_PARSER_FILES: dict[str, str] = {
    "backend/app/normalization/location.py": "parser:location",
    "backend/app/normalization/salary.py": "parser:salary",
    "backend/app/normalization/experience.py": "parser:experience",
}

_ADAPTER_FILES: dict[str, str] = {
    "backend/tests/contracts/adapters/location.py": "adapter:location",
    "backend/tests/contracts/adapters/salary.py": "adapter:salary",
    "backend/tests/contracts/adapters/experience.py": "adapter:experience",
}

_RECORD_FILES: dict[str, str] = {
    "backend/tests/contracts/records/location.json": "contract-record:location",
    "backend/tests/contracts/records/salary.json": "contract-record:salary",
    "backend/tests/contracts/records/experience.json": "contract-record:experience",
}

# The skill-taxonomy-foundation slice's own non-Python fault-injection/
# positive-control fixtures -- not a contract-record (no contract-harness
# guard/family involvement; `required_contract_families` only recognizes
# `parser`/`adapter`/`contract-record` kinds against location/salary/
# experience, so this deliberately distinct "test-fixture" kind never
# spuriously requires any of that coverage).
_TAXONOMY_FIXTURE_FILES: dict[str, str] = {
    f"backend/tests/fixtures/taxonomy/{name}.yaml": "test-fixture:skill-taxonomy"
    for name in (
        "alias_collides_with_other_canonical_id",
        "alias_equals_own_canonical_id",
        "duplicate_alias_cross_entry",
        "duplicate_alias_within_entry",
        "duplicate_canonical_id",
        "duplicate_yaml_key",
        "invalid_canonical_id_slug",
        "unknown_entry_field",
        "unknown_top_level_field",
        "unreachable_display_name",
        "valid_minimal",
        "wrong_schema_version",
        "schema_version_boolean_true",
        "sequence_mapping_key",
    )
}

# The skill-classifier slice's own JSON regression corpus -- not a
# contract-record (no contract-harness guard/family involvement, same
# reasoning as `_TAXONOMY_FIXTURE_FILES` above).
_SKILL_FIXTURE_FILES: dict[str, str] = {
    "backend/tests/fixtures/normalization/skill_cases.json": "test-fixture:skill-classifier",
}

# The realistic Phase 3 evaluation corpus -- not a contract-record (same
# reasoning as `_TAXONOMY_FIXTURE_FILES`/`_SKILL_FIXTURE_FILES` above).
# Declared here regardless of whether the file exists yet on disk (a
# rule-table key names a path, it does not require the path to already
# be present) -- the fixture itself is populated only after the
# separately authorized network contact and manual review complete.
_EVALUATION_FIXTURE_FILES: dict[str, str] = {
    "backend/tests/fixtures/evaluation/phase3_realistic_corpus.json": (
        "test-fixture:phase3-evaluation"
    ),
}

_SHARED_HARNESS_CORE_FILES: frozenset[str] = frozenset(
    {
        "backend/tests/contracts/taxonomy.py",
        "backend/tests/contracts/transforms.py",
        "backend/tests/contracts/mutation_registry.py",
        "backend/tests/contracts/schema.py",
        "backend/tests/contracts/loader.py",
        "backend/tests/contracts/runner.py",
        "backend/scripts/contract_mutation_witnesses.py",
    }
)

_WORKFLOW_SCRIPT_FILES: frozenset[str] = frozenset(
    {
        "backend/scripts/verify.py",
        "backend/scripts/check_handoff.py",
        "backend/scripts/check_review.py",
        "backend/scripts/verification_scope.py",
        "backend/scripts/verification_receipts.py",
        "backend/scripts/verification_worktree.py",
        "backend/scripts/verification_coordinator.py",
        "backend/scripts/migration_matrix.py",
    }
)

_WORKFLOW_HOOK_FILE_PREFIX = ".claude/hooks/"

_ROOT_CONFIG_FILES: frozenset[str] = frozenset(
    {
        ".claude/settings.json",
        "backend/pyproject.toml",
        ".gitignore",
    }
)

_WORKFLOW_GOVERNING_DOC_FILES: frozenset[str] = frozenset(
    {
        "CLAUDE.md",
        "docs/LLM_WORKFLOW.md",
    }
)

# LLM_HANDOFF.md is deliberately absent from every category below -- it is
# validated exclusively by the dedicated per-transition handoff-diff
# validator (see `check_review.py`), never treated as generic docs-only.
_DOCS_ONLY_ALLOWLIST: frozenset[str] = frozenset(
    {
        "docs/ARCHITECTURE.md",
        "docs/DATA_MODEL.md",
        "docs/ROADMAP.md",
        "docs/PHASE_RISK_CHECKLIST.md",
    }
)
_DOCS_ONLY_PREFIX = "docs/DECISIONS/"

# ---------------------------------------------------------------------------
# Directory-prefix rules -- deliberately just these two, disjoint by
# construction (validated below).
# ---------------------------------------------------------------------------

_GENERIC_TEST_PREFIX = "backend/tests/"
_HOOK_PREFIX = ".claude/hooks/"

_ALL_DIRECTORY_PREFIXES: tuple[str, ...] = (_GENERIC_TEST_PREFIX, _HOOK_PREFIX)

# Migration/schema-change trigger paths (exact, per the frozen contract).
_MIGRATION_TRIGGER_PREFIXES: tuple[str, ...] = (
    "backend/migrations/",
    "backend/app/db/",
)
_MIGRATION_TRIGGER_EXACT: frozenset[str] = frozenset({"backend/alembic.ini"})


class ScopeConfigurationError(Exception):
    """Raised once, at import time, if the rule table itself is malformed --
    a duplicate exact path or a non-disjoint/duplicate directory prefix.
    Never raised per-run; this is a programmer error, caught before any
    diff is ever classified."""


def _validate_configuration() -> None:
    exact_maps: list[dict[str, str]] = [
        _PARSER_FILES,
        _ADAPTER_FILES,
        _RECORD_FILES,
        _TAXONOMY_FIXTURE_FILES,
        _SKILL_FIXTURE_FILES,
        _EVALUATION_FIXTURE_FILES,
    ]
    exact_sets: list[frozenset[str]] = [
        _SHARED_HARNESS_CORE_FILES,
        _WORKFLOW_SCRIPT_FILES,
        _ROOT_CONFIG_FILES,
        _WORKFLOW_GOVERNING_DOC_FILES,
    ]
    seen: dict[str, str] = {}
    for m in exact_maps:
        for path in m:
            if path in seen:
                raise ScopeConfigurationError(f"duplicate exact-path rule: {path!r}")
            seen[path] = "exact"
    for s in exact_sets:
        for path in s:
            if path in seen:
                raise ScopeConfigurationError(f"duplicate exact-path rule: {path!r}")
            seen[path] = "exact"

    if len(_ALL_DIRECTORY_PREFIXES) != len(set(_ALL_DIRECTORY_PREFIXES)):
        raise ScopeConfigurationError("duplicate directory-prefix rule declared")
    for a in _ALL_DIRECTORY_PREFIXES:
        for b in _ALL_DIRECTORY_PREFIXES:
            if a != b and (a.startswith(b) or b.startswith(a)):
                raise ScopeConfigurationError(
                    f"directory-prefix rules must be disjoint, got nested prefixes {a!r}/{b!r}"
                )


_validate_configuration()


@dataclass(frozen=True)
class Classification:
    path: str
    category: Category
    directly_execute: bool = False


class OwnerMappingRequiredError(Exception):
    """A non-`.py` path under `backend/tests/` was not covered by any more
    specific exact rule -- it is never silently handed to pytest as though
    it were a test node."""


def _normalize(path: str) -> str:
    """Rejects a non-POSIX or non-repository-root-relative path outright
    rather than guessing; callers are expected to have already produced
    `git diff --name-only` output from the repository root."""
    if "\\" in path or path.startswith("/") or path.startswith("./") or ".." in path.split("/"):
        raise ScopeConfigurationError(f"not a normalized repository-root-relative path: {path!r}")
    return path


def classify_path(path: str) -> Classification:
    path = _normalize(path)

    for exact_map in (
        _PARSER_FILES,
        _ADAPTER_FILES,
        _RECORD_FILES,
        _TAXONOMY_FIXTURE_FILES,
        _SKILL_FIXTURE_FILES,
        _EVALUATION_FIXTURE_FILES,
    ):
        if path in exact_map:
            return Classification(path, exact_map[path])
    if path in _SHARED_HARNESS_CORE_FILES:
        return Classification(path, "shared-harness-core")
    if path in _WORKFLOW_SCRIPT_FILES:
        # Forces --gate final (below) -- already covered by the full suite
        # there, so this is never itself a literal pytest --focus target
        # (it isn't a test file, and generally isn't even under
        # backend/tests/, which verify.py's own focus validation requires).
        return Classification(path, "workflow-script")
    if path in _ROOT_CONFIG_FILES:
        return Classification(path, "root-configuration")
    if path in _WORKFLOW_GOVERNING_DOC_FILES:
        return Classification(path, "workflow-governing-doc")
    if path == "docs/LLM_HANDOFF.md":
        return Classification(path, "handoff-transition")
    if path in _DOCS_ONLY_ALLOWLIST or path.startswith(_DOCS_ONLY_PREFIX):
        return Classification(path, "docs-only")

    if path.startswith(_HOOK_PREFIX):
        # Also forces --gate final; not a pytest target (see workflow-script above).
        return Classification(path, "workflow-hook")
    if path.startswith(_GENERIC_TEST_PREFIX):
        if path.endswith(".py"):
            return Classification(path, "generic-changed-test", directly_execute=True)
        raise OwnerMappingRequiredError(
            f"{path!r} is a non-Python path under backend/tests/ with no declared exact rule -- "
            "owner mapping required before verification can proceed"
        )

    # Never a literal pytest --focus target: an unmapped path is not known
    # to be a test file at all (and typically isn't even under
    # backend/tests/, which verify.py's own focus validation requires) --
    # it forces --gate final (below) instead, which already runs the full
    # suite unconditionally.
    return Classification(path, "unmapped")


def classify_all(paths: list[str]) -> list[Classification]:
    return [classify_path(p) for p in paths]


def is_migration_trigger(path: str) -> bool:
    path = _normalize(path)
    if path in _MIGRATION_TRIGGER_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in _MIGRATION_TRIGGER_PREFIXES)


_CONTRACT_FAMILIES = ("location", "salary", "experience")


def required_contract_families(classifications: list[Classification]) -> frozenset[str]:
    families: set[str] = set()
    for c in classifications:
        if c.category in ("shared-harness-core",):
            return frozenset(_CONTRACT_FAMILIES)
        if ":" in c.category:
            kind, _, parser = c.category.partition(":")
            if kind in ("parser", "adapter", "contract-record") and parser in _CONTRACT_FAMILIES:
                families.add(parser)
    return frozenset(families)


def forces_final_gate(classifications: list[Classification]) -> bool:
    """Categories that are never eligible for a scoped fast gate -- shared
    harness surface, gate-governing tooling, security-relevant hooks,
    workflow-governing documentation, root configuration, or an unmapped
    path -- always force `--gate final`."""
    broad = {
        "shared-harness-core",
        "workflow-script",
        "workflow-hook",
        "root-configuration",
        "workflow-governing-doc",
        "unmapped",
    }
    return any(c.category in broad for c in classifications)


_CONTRACT_TEST_FILES: dict[str, str] = {
    "location": "backend/tests/contracts/test_location_contract.py",
    "salary": "backend/tests/contracts/test_salary_contract.py",
    "experience": "backend/tests/contracts/test_experience_contract.py",
}
_SHARED_HARNESS_TEST_FILES: frozenset[str] = frozenset(
    {
        "backend/tests/contracts/test_harness_self.py",
        "backend/tests/contracts/test_harness_import_boundary.py",
    }
)


@dataclass(frozen=True)
class RequiredCoverage:
    """The mandatory, base_sha..candidate_sha-derived verification scope --
    computed once, before any verification step runs, and never narrowed by
    a caller. A caller may only *add* focus targets or witness refs beyond
    what this returns."""

    forces_final: bool
    required_contract_families: frozenset[str]
    required_focus_targets: frozenset[str]
    required_guard_refs: frozenset[str]
    directly_executed_tests: frozenset[str]
    not_applicable_reason: str | None


def compute_required_coverage(changed_paths: list[str]) -> RequiredCoverage:
    """The single source of truth for "what must run" -- both the
    coordinator (to decide the actual `--focus`/`--witness` arguments it
    passes to `verify.py`) and the receipt's own `affected_surface` field
    are derived from calling this once, on the same input, so the receipt
    can never silently diverge from what actually ran."""
    if not changed_paths:
        return RequiredCoverage(
            forces_final=False,
            required_contract_families=frozenset(),
            required_focus_targets=frozenset(),
            required_guard_refs=frozenset(),
            directly_executed_tests=frozenset(),
            not_applicable_reason="no_changed_paths",
        )

    classifications = classify_all(changed_paths)
    families = required_contract_families(classifications)
    forces_final = forces_final_gate(classifications)
    directly_executed = frozenset(c.path for c in classifications if c.directly_execute)

    focus_targets: set[str] = set(directly_executed)
    for family in families:
        focus_targets.add(_CONTRACT_TEST_FILES[family])
    if families or any(c.category == "shared-harness-core" for c in classifications):
        focus_targets.update(_SHARED_HARNESS_TEST_FILES)

    guard_refs: frozenset[str] = frozenset()
    if families:
        from tests.contracts.taxonomy import active_guards

        guard_refs = frozenset(
            ref for ref, guard in active_guards().items() if guard.parser in families
        )

    docs_only_paths = {
        c.path for c in classifications if c.category in ("docs-only", "handoff-transition")
    }
    not_applicable_reason: str | None = None
    if len(docs_only_paths) == len(classifications):
        not_applicable_reason = "docs_only_within_executable_slice"

    return RequiredCoverage(
        forces_final=forces_final,
        required_contract_families=families,
        required_focus_targets=frozenset(focus_targets),
        required_guard_refs=guard_refs,
        directly_executed_tests=directly_executed,
        not_applicable_reason=not_applicable_reason,
    )
