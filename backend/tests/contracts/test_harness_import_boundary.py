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
    import touching `app.normalization`."""
    results: list[tuple[str, str, bool]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app.normalization"):
                    results.append((alias.name, alias.name, True))
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.startswith("app.normalization")
        ):
            for alias in node.names:
                results.append((node.module, alias.name, False))
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


def _dynamic_bypass_calls(tree: ast.Module) -> list[str]:
    """Detects calls that could smuggle a private/cross-parser/whole-module
    access past the literal-name checks above: bare `getattr`/`setattr`/
    `delattr`/`__import__`, and `importlib.import_module`/
    `importlib.util.spec_from_file_location` (however the `importlib`
    name was imported or aliased)."""
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in _DYNAMIC_BYPASS_CALL_NAMES:
            found.append(func.id)
        elif isinstance(func, ast.Attribute) and func.attr in (
            "import_module",
            "spec_from_file_location",
        ):
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


def test_dynamic_bypass_detector_catches_dunder_import_synthetic_case() -> None:
    synthetic = '__import__("app.normalization.location")\n'
    tree = ast.parse(synthetic)
    assert _dynamic_bypass_calls(tree) == ["__import__"]


def test_dynamic_bypass_detector_allows_ordinary_calls_synthetic_case() -> None:
    synthetic = "classify_location(location)\nresult.city.value\n"
    tree = ast.parse(synthetic)
    assert _dynamic_bypass_calls(tree) == []
