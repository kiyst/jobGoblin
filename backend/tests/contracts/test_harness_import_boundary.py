"""Harness-specific AST import-boundary test (Workflow v3.2 Slice 2,
binding clarification 2). Enforces imported *symbols*, not merely
module names: each adapter may import only its own parser's public
classify_* entry point. Does not modify any existing per-parser
allow-list test in `test_normalization_*.py`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_CONTRACTS_ROOT = Path(__file__).resolve().parent

_ADAPTER_ALLOWED_IMPORT: dict[str, tuple[str, str]] = {
    "location.py": ("app.normalization.location", "classify_location"),
    "salary.py": ("app.normalization.salary", "classify_salary"),
    "experience.py": ("app.normalization.experience", "classify_experience"),
}

# Non-adapter harness modules must import nothing from app.normalization.*
# at all (binding clarification 1) -- only adapters may.
_NON_ADAPTER_HARNESS_MODULES = (
    "schema.py",
    "taxonomy.py",
    "loader.py",
    "runner.py",
    "transforms.py",
    "mutation_registry.py",
)

# Modules held to the "no dynamic bypass" rule below: the three adapters
# plus every non-adapter harness module *except* `mutation_registry.py`,
# which is deliberately exempt -- it is the sanctioned mutation apparatus
# and legitimately uses `getattr`/`setattr` to monkeypatch production
# modules under controlled, fingerprinted conditions. That module (and
# `scripts/contract_mutation_witnesses.py`, outside this directory) is
# the one place dynamic access to production internals is authorized;
# nowhere else in the harness may reach for it.
_NO_DYNAMIC_BYPASS_MODULES = (
    "adapters/location.py",
    "adapters/salary.py",
    "adapters/experience.py",
    "schema.py",
    "taxonomy.py",
    "loader.py",
    "runner.py",
    "transforms.py",
)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_from_normalization(tree: ast.Module) -> list[tuple[str, str, bool]]:
    """Returns (module, imported_name, is_whole_module_import) for every
    import touching `app.normalization`, including equivalent forms:
    `import app.normalization.location`, `from app.normalization.location
    import classify_location`, and `from app import normalization` (which
    binds the whole `normalization` package/subtree under a local name,
    just as a whole-module `import` would, and is treated identically)."""
    results: list[tuple[str, str, bool]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app.normalization"):
                    results.append((alias.name, alias.name, True))
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module.startswith("app.normalization"):
                for alias in node.names:
                    results.append((node.module, alias.name, False))
            elif node.module == "app":
                for alias in node.names:
                    if alias.name == "normalization" or alias.name.startswith("normalization."):
                        results.append((f"app.{alias.name}", f"app.{alias.name}", True))
    return results


def _private_attribute_accesses(tree: ast.Module) -> list[str]:
    return [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr.startswith("_")
        and not node.attr.startswith("__")
    ]


_DYNAMIC_BYPASS_CALL_NAMES = frozenset({"getattr", "setattr", "delattr", "__import__"})
_BANNED_DOTTED_CALLS = frozenset(
    {"importlib.import_module", "importlib.util.spec_from_file_location"}
)


def _build_alias_map(tree: ast.Module) -> dict[str, str]:
    """Maps every locally-bound import name to its canonical dotted
    origin, so a call can be resolved back to what it really is
    regardless of `import X as Y` or `from X import Y as Z` aliasing."""
    alias_map: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                alias_map[bound] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                bound = alias.asname or alias.name
                alias_map[bound] = f"{node.module}.{alias.name}"
    return alias_map


def _resolve_name(name: str, alias_map: dict[str, str]) -> str:
    return alias_map.get(name, name)


def _dotted_path(node: ast.expr) -> str | None:
    """Reconstructs the complete dotted-name path of a `Name`/`Attribute`
    chain (e.g. `importlib.util.spec_from_file_location`), recursing
    through every level regardless of depth. Returns `None` if the node
    is not a pure dotted-name expression (e.g. the base is itself a call
    or subscript) -- such cases are not statically resolvable and are
    correctly left unflagged rather than guessed at."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_path(node.value)
        if base is None:
            return None
        return f"{base}.{node.attr}"
    return None


def _canonicalize_dotted_path(path: str, alias_map: dict[str, str]) -> str:
    """Resolves only the path's root component through the alias map,
    then reattaches the remainder unchanged -- so `il.util.foo` with
    `il` aliased to `importlib` canonicalizes to `importlib.util.foo`
    regardless of how many attribute levels follow the root."""
    root, _, remainder = path.partition(".")
    resolved_root = _resolve_name(root, alias_map)
    return f"{resolved_root}.{remainder}" if remainder else resolved_root


def _dynamic_bypass_calls(tree: ast.Module) -> list[str]:
    """Detects calls that could smuggle a private/cross-parser/whole-module
    access past the literal-name checks above: bare `getattr`/`setattr`/
    `delattr`/`__import__`; `importlib.import_module`/
    `importlib.util.spec_from_file_location` at any attribute-chain depth
    (however `importlib`/`importlib.util` was imported or aliased, e.g.
    `import importlib.util` then `importlib.util.spec_from_file_location(...)`,
    or `import importlib as il` then `il.util.spec_from_file_location(...)`);
    and any of the above reached via `from importlib import import_module
    as load` -- an aliased *function* import, not just an aliased module
    import. This is a closed-set canonical-path check, not a general
    security analyzer: an ordinary nested attribute call whose canonical
    root/path is not in the banned set is never flagged."""
    alias_map = _build_alias_map(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            resolved = _resolve_name(func.id, alias_map)
            if resolved in _BANNED_DOTTED_CALLS or func.id in _DYNAMIC_BYPASS_CALL_NAMES:
                found.append(func.id)
        elif isinstance(func, ast.Attribute):
            raw_path = _dotted_path(func)
            if raw_path is None:
                continue
            canonical = _canonicalize_dotted_path(raw_path, alias_map)
            if canonical in _BANNED_DOTTED_CALLS:
                found.append(func.attr)
    return found


@pytest.mark.parametrize("adapter_filename", sorted(_ADAPTER_ALLOWED_IMPORT))
def test_adapter_imports_exactly_its_own_public_classifier(adapter_filename: str) -> None:
    path = _CONTRACTS_ROOT / "adapters" / adapter_filename
    tree = _parse(path)
    allowed_module, allowed_symbol = _ADAPTER_ALLOWED_IMPORT[adapter_filename]

    imports = _imported_from_normalization(tree)
    assert imports, f"{adapter_filename} must import its public classifier, found no import"

    for module, name, is_whole_module in imports:
        assert not is_whole_module, (
            f"{adapter_filename}: whole-module import of {name!r} is not allowed -- "
            f"import only {allowed_symbol!r} via 'from'"
        )
        assert (
            module == allowed_module
        ), f"{adapter_filename}: imports from {module!r}, expected only {allowed_module!r}"
        assert name == allowed_symbol, (
            f"{adapter_filename}: imports {name!r} from {module!r}, expected only "
            f"{allowed_symbol!r} (a private or unrelated symbol is never allowed)"
        )


@pytest.mark.parametrize("adapter_filename", sorted(_ADAPTER_ALLOWED_IMPORT))
def test_adapter_has_no_private_attribute_access(adapter_filename: str) -> None:
    path = _CONTRACTS_ROOT / "adapters" / adapter_filename
    tree = _parse(path)
    private = _private_attribute_accesses(tree)
    assert not private, f"{adapter_filename}: private attribute access found: {private}"


@pytest.mark.parametrize("module_filename", _NON_ADAPTER_HARNESS_MODULES)
def test_non_adapter_harness_module_imports_no_normalization_code(module_filename: str) -> None:
    path = _CONTRACTS_ROOT / module_filename
    tree = _parse(path)
    imports = _imported_from_normalization(tree)
    assert not imports, (
        f"{module_filename} must not import anything from app.normalization.* -- only "
        f"adapter modules may; found {imports}"
    )


@pytest.mark.parametrize("relative_path", _NO_DYNAMIC_BYPASS_MODULES)
def test_module_has_no_dynamic_bypass_call(relative_path: str) -> None:
    path = _CONTRACTS_ROOT / relative_path
    tree = _parse(path)
    found = _dynamic_bypass_calls(tree)
    assert not found, f"{relative_path}: dynamic-bypass call(s) found: {found}"


def test_import_boundary_rejects_whole_module_import_synthetic_case() -> None:
    synthetic = "import app.normalization.location\n"
    tree = ast.parse(synthetic)
    imports = _imported_from_normalization(tree)
    assert imports == [("app.normalization.location", "app.normalization.location", True)]


def test_import_boundary_rejects_from_app_import_normalization_synthetic_case() -> None:
    """`from app import normalization` binds the whole `normalization`
    package/subtree under a local name, exactly as a whole-module
    `import app.normalization` would -- an equivalent form that must be
    caught identically, not treated as merely importing a plain name
    with no `app.normalization` prefix."""
    synthetic = "from app import normalization\n"
    tree = ast.parse(synthetic)
    imports = _imported_from_normalization(tree)
    assert imports == [("app.normalization", "app.normalization", True)]


def test_dynamic_bypass_detector_catches_aliased_import_module_synthetic_case() -> None:
    """`from importlib import import_module as load` then `load(...)` is
    a *function* alias, distinct from module aliasing -- the detector
    must resolve `load` back to `importlib.import_module` via the
    module's own import statement, not just recognize the literal name
    `import_module` or the literal attribute chain `importlib.x`."""
    synthetic = (
        "from importlib import import_module as load\n" 'load("app.normalization.location")\n'
    )
    tree = ast.parse(synthetic)
    assert _dynamic_bypass_calls(tree) == ["load"]


def test_import_boundary_rejects_private_symbol_synthetic_case() -> None:
    synthetic = "from app.normalization.location import _geo_span_is_rejected\n"
    tree = ast.parse(synthetic)
    imports = _imported_from_normalization(tree)
    assert imports == [("app.normalization.location", "_geo_span_is_rejected", False)]


def test_import_boundary_rejects_cross_parser_import_synthetic_case() -> None:
    synthetic = "from app.normalization.salary import classify_salary\n"
    tree = ast.parse(synthetic)
    imports = _imported_from_normalization(tree)
    allowed_module, allowed_symbol = _ADAPTER_ALLOWED_IMPORT["location.py"]
    module, name, _ = imports[0]
    assert not (module == allowed_module and name == allowed_symbol)


def test_import_boundary_rejects_private_attribute_access_synthetic_case() -> None:
    synthetic = "result._hidden_helper()\n"
    tree = ast.parse(synthetic)
    assert _private_attribute_accesses(tree) == ["_hidden_helper"]


def test_dynamic_bypass_detector_catches_getattr_synthetic_case() -> None:
    synthetic = 'getattr(_mod, "_geo_span_is_rejected")\n'
    tree = ast.parse(synthetic)
    assert _dynamic_bypass_calls(tree) == ["getattr"]


def test_dynamic_bypass_detector_catches_importlib_import_module_synthetic_case() -> None:
    synthetic = 'importlib.import_module("app.normalization.location")\n'
    tree = ast.parse(synthetic)
    assert _dynamic_bypass_calls(tree) == ["import_module"]


def test_dynamic_bypass_detector_catches_nested_attribute_chain_synthetic_case() -> None:
    """Reproduces the exact reported gap: a two-level attribute chain
    (`importlib.util.spec_from_file_location`) was invisible to the
    prior one-level-only handling, despite being named in
    `_BANNED_DOTTED_CALLS` and the function's own documentation."""
    synthetic = "import importlib\n" 'importlib.util.spec_from_file_location("x", "y")\n'
    tree = ast.parse(synthetic)
    assert _dynamic_bypass_calls(tree) == ["spec_from_file_location"]


def test_dynamic_bypass_detector_catches_aliased_nested_attribute_chain_synthetic_case() -> None:
    """Reproduces the exact reported gap combined with module aliasing:
    `il.util.spec_from_file_location` must canonicalize its root (`il`)
    through the alias map before the nested chain is compared against
    the banned set."""
    synthetic = "import importlib as il\n" 'il.util.spec_from_file_location("x", "y")\n'
    tree = ast.parse(synthetic)
    assert _dynamic_bypass_calls(tree) == ["spec_from_file_location"]


def test_dynamic_bypass_detector_allows_unrelated_nested_attribute_call_synthetic_case() -> None:
    """Positive control: an ordinary nested attribute call whose
    canonical root/path has nothing to do with the banned set must
    remain allowed -- this is a closed-set canonical-path check, not a
    general analyzer that flags every multi-level attribute call."""
    synthetic = 'import os.path\nos.path.join("a", "b")\n'
    tree = ast.parse(synthetic)
    assert _dynamic_bypass_calls(tree) == []


def test_dynamic_bypass_detector_allows_deeper_unrelated_attribute_chain_synthetic_case() -> None:
    """A second positive control at three attribute levels deep, with no
    import statement at all for the base name (mirrors how an adapter
    might call a chain of attributes on its own already-imported
    classifier result, e.g. `result.city.provenance.value`)."""
    synthetic = "some_module.sub.helper()\n"
    tree = ast.parse(synthetic)
    assert _dynamic_bypass_calls(tree) == []


def test_dynamic_bypass_detector_catches_dunder_import_synthetic_case() -> None:
    synthetic = '__import__("app.normalization.location")\n'
    tree = ast.parse(synthetic)
    assert _dynamic_bypass_calls(tree) == ["__import__"]


def test_dynamic_bypass_detector_allows_ordinary_calls_synthetic_case() -> None:
    synthetic = "classify_location(location)\nresult.city.value\n"
    tree = ast.parse(synthetic)
    assert _dynamic_bypass_calls(tree) == []
