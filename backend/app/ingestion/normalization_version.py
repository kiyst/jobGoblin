"""D1 parser-version manifest (Phase 4 S3, Class H;
`docs/DECISIONS/0018-d1-parser-version-and-normalized-persistence.md`).

ADR 0011's D1 requires a deterministic parser-version identifier bound to every
implementation, taxonomy, and configuration input that can affect a persisted
normalized value. This module builds that identifier from an explicit manifest,
serialized canonically, and fails closed whenever any part of the evidence is
missing, unreadable, unresolvable, undeclared, or no longer matches what this
process first observed.

Manifest boundary (schema `jgnorm-v1`):

- **Application closure.** Every `app.*` module reachable by import from
  `CLOSURE_ROOTS`, found by walking each module's syntax tree (all import
  statements anywhere in the file, including function bodies), plus each
  module's parent package `__init__.py`. Each is identified by the SHA-256 of
  its UTF-8 bytes with CRLF and lone CR normalized to LF, so Windows and Linux
  checkouts agree and no Git metadata is needed. A relative import, a dynamic
  import (`importlib`, `__import__`), an unparsable file, or an `app.*` module
  that does not resolve to a file fails closed. The Greenhouse adapter
  `app/providers/greenhouse.py` is a root and is bound whole (conservative):
  it still owns the association between a response, its board, and the jobs it
  returns, so any edit to it, transport and retry code included, rotates the
  version. Its value semantics also live, unchanged, in the hashed
  `app/providers/greenhouse_record.py`.
- **Standard library.** Any top-level module in `sys.stdlib_module_names` (and
  `__future__`) is bound collectively through the complete interpreter
  implementation and version below, never hashed individually.
- **Third-party.** Every other top-level import must be declared in
  `THIRD_PARTY_BINDINGS`, which records its exact installed version; an
  undeclared third-party import fails closed. YAML additionally records the
  exact loader class hierarchy the taxonomy loader uses.
- **Taxonomy.** The canonical *parsed* content actually consumed -- every
  `(lookup key, canonical_id, display_name)` triple of the loaded
  `TaxonomyIndex`, sorted -- not the file's bytes, so the identity proves what
  the parsers see. The file is re-read after loading and must be unchanged.
  Every file in `app/taxonomy/` must be a declared data input.
- **Runtime.** Python implementation, full version (including micro), and the
  Unicode database version.
- **Configuration.** The provider and its read-only board -> content-mode
  snapshot. Every mode must be an approved normalizing mode.

The identifier is `jgnorm-v1:sha256:<hex>`, the SHA-256 of the manifest's
canonical JSON (sorted keys, compact separators, ASCII-escaped, no NaN). Equal
code, data, runtime, and configuration always give the same identifier; any
change to one of them gives a different one, and nothing outside the manifest
can change it.
"""

from __future__ import annotations

import ast
import hashlib
import json
import platform
import sys
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from importlib.metadata import version as _distribution_version
from pathlib import Path
from typing import Any

import pydantic
import pydantic_core
import yaml

from app.normalization.taxonomy import (
    DEFAULT_SKILLS_TAXONOMY_PATH,
    TaxonomyIndex,
    _StrictYamlLoader,
    load_taxonomy,
)

MANIFEST_SCHEMA = "jgnorm-v1"
PARSER_VERSION_PREFIX = f"{MANIFEST_SCHEMA}:sha256:"

APP_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = APP_DIR.parent
TAXONOMY_DIR = APP_DIR / "taxonomy"

# The closure roots: the normalization context/projection/merge code (which
# imports the bridge and the composition), the Greenhouse record semantics
# (which import the content converter), and the whole Greenhouse adapter, which
# owns the response -> board -> returned-jobs association. Binding the adapter
# whole is deliberately conservative: until a separately reviewed boundary can
# bind that association independently, any adapter edit rotates the version.
CLOSURE_ROOTS = (
    "app.ingestion.normalized_fields",
    "app.providers.greenhouse",
    "app.providers.greenhouse_record",
)

# Every non-Python file under `app/taxonomy/`, by name. A new data file fails
# closed until it is declared here and bound into the manifest.
DECLARED_TAXONOMY_FILES = ("skills.yaml",)

NORMALIZED_PROVIDER = "greenhouse"
APPROVED_CONTENT_MODES = frozenset({"declared-double-escaped"})


def _yaml_binding() -> dict[str, Any]:
    return {
        "version": yaml.__version__,
        "loader_mro": [f"{cls.__module__}.{cls.__qualname__}" for cls in _StrictYamlLoader.__mro__],
    }


THIRD_PARTY_BINDINGS: Mapping[str, Callable[[], dict[str, Any]]] = {
    "yaml": _yaml_binding,
    "pydantic": lambda: {"version": pydantic.VERSION},
    "pydantic_core": lambda: {"version": pydantic_core.__version__},
    # The installed distribution's exact version, read from package metadata so
    # that `httpx` stays imported only by the Greenhouse adapter (S1's rule).
    "httpx": lambda: {"version": _distribution_version("httpx")},
}

_DYNAMIC_IMPORT_MODULES = frozenset({"importlib"})
# Read-only package metadata, used only to bind a declared dependency's version.
_PERMITTED_IMPORTLIB_MODULES = frozenset({"importlib.metadata"})


class ParserVersionError(Exception):
    """Version evidence is missing, unreadable, unresolvable, undeclared,
    stale, or mismatched. Messages are fixed and never include file content."""


Reader = Callable[[Path], bytes]


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()


# Per-process first observation of each real closure file's identity. A later
# build in the same process that sees different bytes on disk means the files
# no longer match the code this process loaded, which fails closed.
_FIRST_SEEN: dict[str, str] = {}


def canonical_lf_sha256(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def parser_version_for(canonical_manifest: bytes) -> str:
    return PARSER_VERSION_PREFIX + hashlib.sha256(canonical_manifest).hexdigest()


def _module_file(name: str) -> Path | None:
    parts = name.split(".")
    if parts[0] != "app":
        return None
    base = APP_DIR.joinpath(*parts[1:])
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if parts[1:] and candidate.is_file():
            return candidate
    if not parts[1:] and (APP_DIR / "__init__.py").is_file():
        return APP_DIR / "__init__.py"
    return None


def _is_stdlib(top: str) -> bool:
    return top == "__future__" or top in sys.stdlib_module_names


@dataclass(frozen=True)
class Closure:
    """`modules` maps each module name to its backend-relative POSIX path."""

    modules: Mapping[str, str]
    third_party: frozenset[str]


def compute_closure(roots: Iterable[str], read: Reader = read_bytes) -> Closure:
    modules: dict[str, str] = {}
    third_party: set[str] = set()
    pending = list(roots)
    while pending:
        name = pending.pop()
        if name in modules:
            continue
        path = _module_file(name)
        if path is None:
            raise ParserVersionError("an application module in the closure does not resolve")
        modules[name] = path.relative_to(BACKEND_DIR).as_posix()
        parts = name.split(".")
        pending.extend(".".join(parts[:i]) for i in range(1, len(parts)))
        try:
            tree = ast.parse(read(path).decode("utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as exc:
            raise ParserVersionError("a closure module is unreadable or unparsable") from exc
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "__import__":
                raise ParserVersionError("a closure module uses a dynamic import")
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level != 0 or node.module is None:
                    raise ParserVersionError("a closure module uses a relative import")
                imported = [node.module]
                if node.module == "app" or node.module.startswith("app."):
                    imported += [
                        f"{node.module}.{alias.name}"
                        for alias in node.names
                        if _module_file(f"{node.module}.{alias.name}") is not None
                    ]
            for module in imported:
                top = module.partition(".")[0]
                if top == "app":
                    pending.append(module)
                elif module in _PERMITTED_IMPORTLIB_MODULES:
                    continue
                elif top in _DYNAMIC_IMPORT_MODULES:
                    raise ParserVersionError("a closure module uses a dynamic import")
                elif _is_stdlib(top):
                    continue
                elif top in THIRD_PARTY_BINDINGS:
                    third_party.add(top)
                else:
                    raise ParserVersionError("a closure module imports an undeclared dependency")
    return Closure(modules=dict(sorted(modules.items())), third_party=frozenset(third_party))


def taxonomy_identity(index: TaxonomyIndex) -> list[list[str]]:
    """The canonical parsed taxonomy content the parsers actually consume:
    every lookup key with the entry it resolves to, sorted."""
    entries = index._by_normalized_key
    return [
        [key, entry.canonical_id, entry.display_name]
        for key, entry in sorted(entries.items(), key=lambda item: item[0])
    ]


def _validated_content_modes(content_modes: object) -> dict[str, str]:
    if not isinstance(content_modes, Mapping) or not content_modes:
        raise ParserVersionError("the board content-mode snapshot is missing or empty")
    snapshot: dict[str, str] = {}
    for token, mode in content_modes.items():
        if type(token) is not str or type(mode) is not str:
            raise ParserVersionError("the board content-mode snapshot is malformed")
        if mode not in APPROVED_CONTENT_MODES:
            raise ParserVersionError("a board's content mode is not approved for normalization")
        snapshot[token] = mode
    return dict(sorted(snapshot.items()))


@dataclass(frozen=True)
class ManifestEvidence:
    canonical: bytes
    version: str
    taxonomy: TaxonomyIndex
    content_modes: Mapping[str, str]


def build_manifest(
    content_modes: object,
    *,
    read: Reader = read_bytes,
    taxonomy_path: Path = DEFAULT_SKILLS_TAXONOMY_PATH,
) -> ManifestEvidence:
    """Builds and validates the complete manifest. Raises `ParserVersionError`
    for any missing, unresolvable, undeclared, stale, or unapproved input."""
    snapshot = _validated_content_modes(content_modes)
    closure = compute_closure(CLOSURE_ROOTS, read)
    module_hashes: dict[str, str] = {}
    for relative in closure.modules.values():
        try:
            digest = canonical_lf_sha256(read(BACKEND_DIR / relative))
        except OSError as exc:
            raise ParserVersionError("a closure module is unreadable") from exc
        if read is read_bytes:
            first = _FIRST_SEEN.setdefault(relative, digest)
            if first != digest:
                raise ParserVersionError("closure source changed after this process observed it")
        module_hashes[relative] = digest

    try:
        data_files = sorted(
            path.name for path in TAXONOMY_DIR.iterdir() if path.name != "__pycache__"
        )
    except OSError as exc:
        raise ParserVersionError("the taxonomy directory is unreadable") from exc
    if data_files != sorted(DECLARED_TAXONOMY_FILES):
        raise ParserVersionError("the taxonomy directory contains an undeclared data file")
    try:
        before = read(taxonomy_path)
        taxonomy = load_taxonomy(taxonomy_path)
        after = read(taxonomy_path)
    except Exception as exc:
        raise ParserVersionError("the taxonomy is missing, unreadable, or invalid") from exc
    if before != after:
        raise ParserVersionError("the taxonomy changed while it was being loaded")

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "closure": {"roots": sorted(CLOSURE_ROOTS), "modules": module_hashes},
        "standard_library": "bound by runtime.implementation and runtime.python",
        "third_party": {name: THIRD_PARTY_BINDINGS[name]() for name in sorted(closure.third_party)},
        "taxonomy": {"skills": taxonomy_identity(taxonomy)},
        "runtime": {
            "implementation": platform.python_implementation(),
            "python": platform.python_version(),
            "unicodedata": unicodedata.unidata_version,
        },
        "config": {"provider": NORMALIZED_PROVIDER, "board_content_modes": snapshot},
    }
    canonical = canonical_json_bytes(manifest)
    return ManifestEvidence(
        canonical=canonical,
        version=parser_version_for(canonical),
        taxonomy=taxonomy,
        content_modes=snapshot,
    )
