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
    exact_maps: list[dict[str, str]] = [_PARSER_FILES, _ADAPTER_FILES, _RECORD_FILES]
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

    for exact_map in (_PARSER_FILES, _ADAPTER_FILES, _RECORD_FILES):
        if path in exact_map:
            return Classification(path, exact_map[path])
    if path in _SHARED_HARNESS_CORE_FILES:
        return Classification(path, "shared-harness-core")
    if path in _WORKFLOW_SCRIPT_FILES:
        return Classification(path, "workflow-script", directly_execute=True)
    if path in _ROOT_CONFIG_FILES:
        return Classification(path, "root-configuration")
    if path in _WORKFLOW_GOVERNING_DOC_FILES:
        return Classification(path, "workflow-governing-doc")
    if path == "docs/LLM_HANDOFF.md":
        return Classification(path, "handoff-transition")
    if path in _DOCS_ONLY_ALLOWLIST or path.startswith(_DOCS_ONLY_PREFIX):
        return Classification(path, "docs-only")

    if path.startswith(_HOOK_PREFIX):
        return Classification(path, "workflow-hook", directly_execute=True)
    if path.startswith(_GENERIC_TEST_PREFIX):
        if path.endswith(".py"):
            return Classification(path, "generic-changed-test", directly_execute=True)
        raise OwnerMappingRequiredError(
            f"{path!r} is a non-Python path under backend/tests/ with no declared exact rule -- "
            "owner mapping required before verification can proceed"
        )

    return Classification(path, "unmapped", directly_execute=path.endswith(".py"))


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
