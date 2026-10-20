"""D1 parser-version manifest tests (Phase 4 S3; ADR 0018 A1/A2).

Pure: no database or network. Every alternative version here comes from the real
`build_manifest` over a controlled change to one manifest input -- never from an
injected version string.
"""

from __future__ import annotations

import ast
import hashlib
import json
import platform
import re
import sys
import unicodedata
from collections.abc import Callable
from pathlib import Path

import pydantic
import pydantic_core
import pytest
import yaml

from app.ingestion import normalization_version as nv
from app.normalization.taxonomy import (
    DEFAULT_SKILLS_TAXONOMY_PATH,
    _StrictYamlLoader,
    load_taxonomy,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"
MODES = {"acme-synthetic": "declared-double-escaped"}
VERSION_RE = r"jgnorm-v1:sha256:[0-9a-f]{64}"

# The pinned application closure. A change here is a review trigger: it means
# the set of code bound into the parser version changed.
EXPECTED_CLOSURE = (
    "app/__init__.py",
    "app/ingestion/__init__.py",
    "app/ingestion/normalization_version.py",
    "app/ingestion/normalized_fields.py",
    "app/normalization/__init__.py",
    "app/normalization/employment.py",
    "app/normalization/experience.py",
    "app/normalization/location.py",
    "app/normalization/posting.py",
    "app/normalization/remote.py",
    "app/normalization/seniority.py",
    "app/normalization/skills.py",
    "app/normalization/taxonomy.py",
    "app/normalization/titles.py",
    "app/normalization/types.py",
    "app/providers/__init__.py",
    "app/providers/greenhouse_content.py",
    "app/providers/greenhouse_posting_inputs.py",
    "app/providers/greenhouse_record.py",
    "app/schemas/__init__.py",
    "app/schemas/discovered_job.py",
    "app/schemas/identifiers.py",
)


def _reader(overrides: dict[str, bytes]) -> Callable[[Path], bytes]:
    """A reader returning the real bytes except for the backend-relative paths
    given, so exactly one manifest input changes."""

    def read(path: Path) -> bytes:
        relative = path.resolve().relative_to(BACKEND_DIR).as_posix()
        if relative in overrides:
            return overrides[relative]
        return path.read_bytes()

    return read


def _real(relative: str) -> bytes:
    return (BACKEND_DIR / relative).read_bytes()


def _build(**kwargs: object) -> nv.ManifestEvidence:
    return nv.build_manifest(MODES, **kwargs)  # type: ignore[arg-type]


# --- determinism, format, canonical serialization ---


def test_version_is_well_formed_and_deterministic() -> None:
    first, second = _build(), _build()
    assert first.canonical == second.canonical
    assert first.version == second.version
    assert re.fullmatch(VERSION_RE, first.version)
    assert first.version == nv.PARSER_VERSION_PREFIX + hashlib.sha256(first.canonical).hexdigest()


def test_manifest_boundary_and_canonical_serialization_are_explicit() -> None:
    evidence = _build()
    manifest = json.loads(evidence.canonical)
    assert evidence.canonical == json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")
    assert set(manifest) == {
        "schema",
        "closure",
        "standard_library",
        "third_party",
        "taxonomy",
        "runtime",
        "config",
    }
    assert manifest["schema"] == "jgnorm-v1"
    assert manifest["closure"]["roots"] == sorted(nv.CLOSURE_ROOTS)
    assert tuple(manifest["closure"]["modules"]) == EXPECTED_CLOSURE
    assert manifest["standard_library"] == "bound by runtime.implementation and runtime.python"
    assert manifest["third_party"] == {
        "pydantic": {"version": pydantic.VERSION},
        "pydantic_core": {"version": pydantic_core.__version__},
        "yaml": {
            "version": yaml.__version__,
            "loader_mro": [
                "app.normalization.taxonomy._StrictYamlLoader",
                "yaml.loader.SafeLoader",
                "yaml.reader.Reader",
                "yaml.scanner.Scanner",
                "yaml.parser.Parser",
                "yaml.composer.Composer",
                "yaml.constructor.SafeConstructor",
                "yaml.constructor.BaseConstructor",
                "yaml.resolver.Resolver",
                "yaml.resolver.BaseResolver",
                "builtins.object",
            ],
        },
    }
    runtime = manifest["runtime"]
    assert runtime == {
        "implementation": platform.python_implementation(),
        "python": platform.python_version(),
        "unicodedata": unicodedata.unidata_version,
    }
    assert len(runtime["python"].split(".")) == 3  # includes the micro version
    assert manifest["config"] == {
        "provider": "greenhouse",
        "board_content_modes": {"acme-synthetic": "declared-double-escaped"},
    }


def test_taxonomy_identity_is_the_canonical_parsed_content() -> None:
    manifest = json.loads(_build().canonical)
    index = load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)
    skills = manifest["taxonomy"]["skills"]
    assert skills == sorted(skills)
    assert {canonical for _, canonical, _ in skills} == set(index.canonical_ids())
    for key, canonical, display in skills:
        match = index.lookup(key).entry
        assert match is not None
        assert (match.canonical_id, match.display_name) == (canonical, display)


# --- independent reproduction ---


def _independent_closure() -> list[str]:
    """A second, independently written closure walk over `app.*` imports."""
    found: set[str] = set()
    pending = ["app.ingestion.normalized_fields", "app.providers.greenhouse_record"]
    while pending:
        name = pending.pop()
        parts = name.split(".")
        for depth in range(1, len(parts) + 1):
            package = APP_DIR.joinpath(*parts[1:depth])
            init = package / "__init__.py"
            if init.is_file():
                found.add(init.relative_to(BACKEND_DIR).as_posix())
        module = APP_DIR.joinpath(*parts[1:])
        path = module.with_suffix(".py") if module.with_suffix(".py").is_file() else None
        if path is None:
            continue
        relative = path.relative_to(BACKEND_DIR).as_posix()
        if relative in found:
            continue
        found.add(relative)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                pending += [a.name for a in node.names if a.name.startswith("app.")]
            elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app."):
                assert node.module is not None
                pending.append(node.module)
                pending += [f"{node.module}.{a.name}" for a in node.names]
    return sorted(found)


def test_parser_version_is_independently_reproducible() -> None:
    modules = _independent_closure()
    assert tuple(modules) == EXPECTED_CLOSURE
    index = load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)
    expected = {
        "schema": "jgnorm-v1",
        "closure": {
            "roots": ["app.ingestion.normalized_fields", "app.providers.greenhouse_record"],
            "modules": {
                path: hashlib.sha256(
                    _real(path).replace(b"\r\n", b"\n").replace(b"\r", b"\n")
                ).hexdigest()
                for path in modules
            },
        },
        "standard_library": "bound by runtime.implementation and runtime.python",
        "third_party": {
            "pydantic": {"version": pydantic.VERSION},
            "pydantic_core": {"version": pydantic_core.__version__},
            "yaml": {
                "version": yaml.__version__,
                "loader_mro": [
                    f"{c.__module__}.{c.__qualname__}" for c in _StrictYamlLoader.__mro__
                ],
            },
        },
        "taxonomy": {
            "skills": sorted(
                [key, entry.canonical_id, entry.display_name]
                for key, entry in index._by_normalized_key.items()
            )
        },
        "runtime": {
            "implementation": platform.python_implementation(),
            "python": platform.python_version(),
            "unicodedata": unicodedata.unidata_version,
        },
        "config": {"provider": "greenhouse", "board_content_modes": MODES},
    }
    canonical = json.dumps(
        expected, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    evidence = _build()
    assert evidence.canonical == canonical
    assert evidence.version == "jgnorm-v1:sha256:" + hashlib.sha256(canonical).hexdigest()


# --- every load-bearing input rotates the version ---


@pytest.mark.parametrize("relative", EXPECTED_CLOSURE)
def test_changing_any_closure_module_changes_the_version(relative: str) -> None:
    baseline = _build(read=_reader({})).version
    changed = _build(read=_reader({relative: _real(relative) + b"\n# changed\n"})).version
    assert changed != baseline


def test_changing_the_taxonomy_changes_the_version(tmp_path: Path) -> None:
    copy = tmp_path / "skills.yaml"
    copy.write_bytes(
        DEFAULT_SKILLS_TAXONOMY_PATH.read_bytes().rstrip()
        + b"\n  - canonical_id: zzzsynthetic\n    display_name: Zzzsynthetic\n    aliases: []\n"
    )
    assert _build(taxonomy_path=copy).version != _build().version


def test_taxonomy_formatting_alone_does_not_change_the_version(tmp_path: Path) -> None:
    copy = tmp_path / "skills.yaml"
    copy.write_bytes(b"# a comment only\n" + DEFAULT_SKILLS_TAXONOMY_PATH.read_bytes())
    assert _build(taxonomy_path=copy).version == _build().version


@pytest.mark.parametrize(
    ("target", "attribute", "value"),
    [
        (platform, "python_version", lambda: "3.99.0"),
        (platform, "python_implementation", lambda: "SyntheticPython"),
        (unicodedata, "unidata_version", "99.0.0"),
        (yaml, "__version__", "0.0.0-synthetic"),
        (pydantic, "VERSION", "0.0.0-synthetic"),
        (pydantic_core, "__version__", "0.0.0-synthetic"),
    ],
)
def test_changing_any_runtime_or_dependency_binding_changes_the_version(
    monkeypatch: pytest.MonkeyPatch, target: object, attribute: str, value: object
) -> None:
    baseline = _build().version
    monkeypatch.setattr(target, attribute, value)
    assert _build().version != baseline


def test_changing_the_board_configuration_changes_the_version() -> None:
    one = nv.build_manifest({"acme-synthetic": "declared-double-escaped"}).version
    two = nv.build_manifest(
        {"acme-synthetic": "declared-double-escaped", "beta-synthetic": "declared-double-escaped"}
    ).version
    assert one != two


# --- unrelated changes do not rotate it ---


@pytest.mark.parametrize(
    "relative",
    [
        "app/providers/greenhouse.py",
        "app/ingestion/persistence.py",
        "app/ingestion/pipeline.py",
        "app/ingestion/provider_execution.py",
        "app/normalization/salary.py",
        "app/normalization/url.py",
        "app/api/health.py",
        "app/db/models/job.py",
    ],
)
def test_unrelated_files_are_outside_the_closure_and_never_change_the_version(
    relative: str,
) -> None:
    assert relative not in EXPECTED_CLOSURE
    baseline = _build(read=_reader({})).version
    assert _build(read=_reader({relative: b"# entirely different\n"})).version == baseline


def test_crlf_and_lf_checkouts_produce_the_same_version() -> None:
    crlf = {
        relative: _real(relative).replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        for relative in EXPECTED_CLOSURE
    }
    lf = {relative: _real(relative).replace(b"\r\n", b"\n") for relative in EXPECTED_CLOSURE}
    assert _build(read=_reader(crlf)).version == _build(read=_reader(lf)).version


def test_a_new_module_imported_into_the_composition_joins_the_closure() -> None:
    posting = "app/normalization/posting.py"
    injected = _real(posting) + b"\nimport app.normalization.salary  # noqa\n"
    closure = nv.compute_closure(nv.CLOSURE_ROOTS, _reader({posting: injected}))
    assert "app/normalization/salary.py" in closure.modules.values()
    assert _build(read=_reader({posting: injected})).version != _build(read=_reader({})).version


def test_salary_and_the_transport_adapter_are_not_in_the_real_closure() -> None:
    modules = set(nv.compute_closure(nv.CLOSURE_ROOTS).modules.values())
    assert "app/normalization/salary.py" not in modules
    assert "app/providers/greenhouse.py" not in modules
    assert set(nv.compute_closure(nv.CLOSURE_ROOTS).third_party) == {
        "pydantic",
        "pydantic_core",
        "yaml",
    }


# --- missing, unresolvable, undeclared, stale: fail closed ---


@pytest.mark.parametrize(
    ("addition", "label"),
    [
        (b"\nfrom .types import Provenance\n", "relative import"),
        (b"\nimport importlib\n", "dynamic import"),
        (b"\nx = __import__('json')\n", "dunder import"),
        (b"\nimport requests\n", "undeclared third-party"),
        (b"\nimport app.normalization.does_not_exist\n", "unresolvable module"),
        (b"\ndef broken(:\n", "unparsable"),
    ],
)
def test_unfollowable_closure_evidence_fails_closed(addition: bytes, label: str) -> None:
    posting = "app/normalization/posting.py"
    with pytest.raises(nv.ParserVersionError):
        _build(read=_reader({posting: _real(posting) + addition}))


def test_an_unreadable_closure_module_fails_closed() -> None:
    def read(path: Path) -> bytes:
        if path.name == "seniority.py":
            raise OSError("unreadable")
        return path.read_bytes()

    with pytest.raises(nv.ParserVersionError):
        _build(read=read)


def test_a_missing_taxonomy_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(nv.ParserVersionError):
        _build(taxonomy_path=tmp_path / "absent.yaml")


def test_a_taxonomy_that_changes_while_loading_fails_closed() -> None:
    calls = {"count": 0}

    def read(path: Path) -> bytes:
        if path == DEFAULT_SKILLS_TAXONOMY_PATH:
            calls["count"] += 1
            if calls["count"] > 1:
                return b"changed"
        return path.read_bytes()

    with pytest.raises(nv.ParserVersionError):
        _build(read=read)


def test_an_undeclared_taxonomy_data_file_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "skills.yaml").write_bytes(DEFAULT_SKILLS_TAXONOMY_PATH.read_bytes())
    monkeypatch.setattr(nv, "TAXONOMY_DIR", tmp_path)
    _build()  # exactly the declared files: accepted
    (tmp_path / "titles.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    with pytest.raises(nv.ParserVersionError):
        _build()


def test_source_that_changed_after_this_process_observed_it_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _build()
    stale = dict(nv._FIRST_SEEN)
    stale["app/normalization/seniority.py"] = "0" * 64
    monkeypatch.setattr(nv, "_FIRST_SEEN", stale)
    with pytest.raises(nv.ParserVersionError):
        _build()


@pytest.mark.parametrize(
    "modes",
    [
        {},
        None,
        "declared-double-escaped",
        {"acme-synthetic": "disabled"},
        {"acme-synthetic": "something-else"},
        {"acme-synthetic": 1},
        {1: "declared-double-escaped"},
    ],
)
def test_missing_malformed_or_unapproved_configuration_fails_closed(modes: object) -> None:
    with pytest.raises(nv.ParserVersionError):
        nv.build_manifest(modes)


def test_stdlib_detection_uses_the_interpreter_list() -> None:
    assert "re" in sys.stdlib_module_names
    assert "yaml" not in sys.stdlib_module_names
