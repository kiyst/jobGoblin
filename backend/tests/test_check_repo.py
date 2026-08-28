import subprocess
import sys
from pathlib import Path

from scripts.check_repo import (
    REPO_ROOT,
    _anchors_for_text,
    _chain_integrity_findings,
    _display_path,
    check_alembic_references,
    check_constraints_table_integrity,
    check_duplicate_constraint_rows,
    check_links_and_anchors,
    run_checks,
)

_TABLE_HEADER = (
    "## Phase 1 constraints & indexes\n\n| Table | Constraint / index | Purpose |\n|---|---|---|\n"
)


# --------------------------------------------------------------------------
# Markdown link and heading-anchor validation
# --------------------------------------------------------------------------


def test_valid_relative_link_and_anchor_produce_no_finding(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text("# Some Heading\n\ncontent\n", encoding="utf-8")
    source = tmp_path / "source.md"
    source_text = "See [target](target.md#some-heading) for details.\n"
    source.write_text(source_text, encoding="utf-8")

    findings = check_links_and_anchors(
        source, source_text, {target.resolve(): target.read_text(encoding="utf-8")}
    )

    assert findings == []


def test_link_to_nonexistent_file_is_flagged(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source_text = "See [missing](does-not-exist.md) for details.\n"
    source.write_text(source_text, encoding="utf-8")

    findings = check_links_and_anchors(source, source_text, {})

    assert len(findings) == 1
    assert "does-not-exist.md" in findings[0].message


def test_anchor_not_present_in_target_is_flagged(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text("# Some Heading\n", encoding="utf-8")
    source = tmp_path / "source.md"
    source_text = "See [target](target.md#wrong-anchor) for details.\n"
    source.write_text(source_text, encoding="utf-8")

    findings = check_links_and_anchors(
        source, source_text, {target.resolve(): target.read_text(encoding="utf-8")}
    )

    assert len(findings) == 1
    assert "wrong-anchor" in findings[0].message


def test_image_target_is_validated_like_a_link(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source_text = "![alt text](missing-image.png)\n"
    source.write_text(source_text, encoding="utf-8")

    findings = check_links_and_anchors(source, source_text, {})

    assert len(findings) == 1
    assert "missing-image.png" in findings[0].message


def test_http_targets_are_offline_syntax_only(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source_text = "[external](https://example.com/does-not-exist)\n"
    source.write_text(source_text, encoding="utf-8")

    findings = check_links_and_anchors(source, source_text, {})

    assert findings == []


def test_fenced_code_block_examples_are_not_treated_as_live_links(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source_text = (
        "Real link: [ok](missing-real.md)\n\n"
        "```markdown\n"
        "[example](does-not-exist-in-example.md)\n"
        "```\n"
    )
    source.write_text(source_text, encoding="utf-8")

    findings = check_links_and_anchors(source, source_text, {})

    assert len(findings) == 1
    assert "missing-real.md" in findings[0].message


def test_inline_code_span_examples_are_not_treated_as_live_links(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source_text = "Not a link: `[example](does-not-exist.md)` is just inline code.\n"
    source.write_text(source_text, encoding="utf-8")

    findings = check_links_and_anchors(source, source_text, {})

    assert findings == []


def test_anchors_for_text_disambiguates_duplicate_headings() -> None:
    anchors = _anchors_for_text("# Overview\n\n# Overview\n")

    assert anchors == {"overview", "overview-1"}


def test_anchors_for_text_matches_github_slug_algorithm_for_repo_style_heading() -> None:
    """Reproduces an anchor already used elsewhere in this repository, to
    prove the slugifier agrees with GitHub's actual algorithm, not just an
    approximation of it."""
    heading = "### 6.5 `SavedSearch.enabled_sources` — unambiguous source selection"

    anchors = _anchors_for_text(heading + "\n")

    assert "65-savedsearchenabled_sources--unambiguous-source-selection" in anchors


# --------------------------------------------------------------------------
# Duplicate constraints-summary row detection
# --------------------------------------------------------------------------


def test_duplicate_row_flagged_when_unique_signature_matches_after_normalization() -> None:
    text = (
        _TABLE_HEADER
        + "| `widgets` | `UNIQUE (a, lower(b))` | first |\n"
        + "| `widgets` | `UNIQUE (a, lower(trim(b)))` | second |\n"
    )

    findings = check_duplicate_constraint_rows(Path("fake.md"), text)

    assert len(findings) == 1
    assert findings[0].line == 6


def test_same_table_distinct_columns_is_not_flagged() -> None:
    text = (
        _TABLE_HEADER
        + "| `widgets` | `UNIQUE (a, b)` | first |\n"
        + "| `widgets` | `UNIQUE (a, c)` | second |\n"
    )

    findings = check_duplicate_constraint_rows(Path("fake.md"), text)

    assert findings == []


def test_reproduces_the_saved_search_locations_rev11_regression() -> None:
    """The complete row references many columns through its CHECKs, while
    the obsolete row referenced only the location unique key — comparing
    whole flattened column sets would miss this. The checker must compare
    each row's UNIQUE/INDEX signature in isolation from its CHECKs."""
    text = (
        _TABLE_HEADER
        + "| `saved_search_locations` | `UNIQUE (saved_search_id, lower(location_text))`; "
        + "`CHECK (location_text = trim(both E'\\t\\n\\r ' from location_text))`; "
        + "`CHECK (trim(both E'\\t\\n\\r ' from location_text) <> '')`; "
        + "`CHECK` on latitude/longitude range; "
        + "`CHECK ((latitude IS NULL) = (longitude IS NULL))`; "
        + "`CHECK (radius_miles_override IS NULL OR radius_miles_override >= 0)` | complete |\n"
        + "| `saved_search_locations` | `UNIQUE (saved_search_id, lower(trim(location_text)))` "
        + "| obsolete |\n"
    )

    findings = check_duplicate_constraint_rows(Path("fake.md"), text)

    assert len(findings) == 1
    assert "saved_search_locations" in findings[0].message


def test_exact_duplicate_check_only_row_is_flagged() -> None:
    """A row with no UNIQUE/INDEX at all (only CHECKs) still needs coverage:
    an exact whole-cell duplicate is flagged even without a parseable
    signature."""
    text = (
        _TABLE_HEADER
        + "| `widgets` | `CHECK` on `status` | first |\n"
        + "| `widgets` | `CHECK` on `status` | second |\n"
    )

    findings = check_duplicate_constraint_rows(Path("fake.md"), text)

    assert len(findings) == 1


def test_partial_unique_not_confused_with_plain_unique_on_same_columns() -> None:
    text = (
        _TABLE_HEADER
        + "| `widgets` | `UNIQUE (a)` | first |\n"
        + "| `widgets` | partial `UNIQUE (a) WHERE is_primary` | second |\n"
    )

    findings = check_duplicate_constraint_rows(Path("fake.md"), text)

    assert findings == []


def test_different_where_predicate_is_not_a_duplicate() -> None:
    text = (
        _TABLE_HEADER
        + "| `widgets` | `UNIQUE (a) WHERE b IS NOT NULL` | first |\n"
        + "| `widgets` | `UNIQUE (a) WHERE b IS NULL` | second |\n"
    )

    findings = check_duplicate_constraint_rows(Path("fake.md"), text)

    assert findings == []


# --------------------------------------------------------------------------
# Constraints-table fail-closed integrity (guards against silent no-op
# extraction failure in check_duplicate_constraint_rows)
# --------------------------------------------------------------------------


def test_missing_constraints_summary_section_is_flagged() -> None:
    text = "# Some Other Document\n\nThere is no constraints table here at all.\n"

    findings = check_constraints_table_integrity(Path("fake.md"), text)

    assert len(findings) == 1
    assert "constraints-summary table not found" in findings[0].message


def test_section_with_no_extractable_signatures_is_flagged() -> None:
    """Rows exist, but none contain a parseable UNIQUE/INDEX span — e.g. the
    heading was kept but every row is CHECK-only, or the backtick syntax
    changed enough that extraction silently produces nothing at all."""
    text = _TABLE_HEADER + "| `widgets` | `CHECK` on `status` | first |\n"

    findings = check_constraints_table_integrity(Path("fake.md"), text)

    assert len(findings) == 1
    assert "no UNIQUE/INDEX signature could be parsed" in findings[0].message


def test_section_with_at_least_one_signature_is_not_flagged() -> None:
    text = (
        _TABLE_HEADER
        + "| `widgets` | `CHECK` on `status` | first |\n"
        + "| `gadgets` | `UNIQUE (a)` | second |\n"
    )

    findings = check_constraints_table_integrity(Path("fake.md"), text)

    assert findings == []


# --------------------------------------------------------------------------
# Stale/nonexistent Alembic revision references
# --------------------------------------------------------------------------


def test_nonexistent_revision_reference_is_flagged() -> None:
    revision_map: dict[str, str | None] = {"0001": None}
    text = "See migration `0002` for details.\n"

    findings = check_alembic_references(Path("fake.md"), text, revision_map)

    assert len(findings) == 1
    assert "0002" in findings[0].message


def test_existing_revision_at_0010_or_later_is_not_flagged() -> None:
    revision_map: dict[str, str | None] = {"0001": None, "0010": "0001"}
    text = "See migration `0010` for details.\n"

    findings = check_alembic_references(Path("fake.md"), text, revision_map)

    assert findings == []


def test_nonexistent_revision_at_0010_or_later_is_flagged() -> None:
    revision_map: dict[str, str | None] = {"0001": None, "0010": "0001"}
    text = "See migration `0099` for details.\n"

    findings = check_alembic_references(Path("fake.md"), text, revision_map)

    assert len(findings) == 1
    assert "0099" in findings[0].message


def test_down_revision_mismatch_is_flagged() -> None:
    revision_map = {"0001": None, "0002": "0001"}
    text = 'migration `0002`,\n`down_revision = "9999"` is wrong.\n'

    findings = check_alembic_references(Path("fake.md"), text, revision_map)

    assert any("down_revision" in f.message for f in findings)


def test_correct_down_revision_citation_is_not_flagged() -> None:
    revision_map = {"0001": None, "0002": "0001"}
    text = 'migration `0002`,\n`down_revision = "0001"` is correct.\n'

    findings = check_alembic_references(Path("fake.md"), text, revision_map)

    assert findings == []


# --------------------------------------------------------------------------
# Migration-chain integrity
# --------------------------------------------------------------------------


RevisionParentT = str | tuple[str, ...] | None


def test_clean_linear_chain_has_no_findings() -> None:
    revisions: list[tuple[str, RevisionParentT]] = [
        ("0001", None),
        ("0002", "0001"),
        ("0003", "0002"),
    ]

    findings = _chain_integrity_findings("migrations", ["0003"], revisions)

    assert findings == []


def test_forked_chain_is_flagged() -> None:
    revisions: list[tuple[str, RevisionParentT]] = [
        ("0001", None),
        ("0002", "0001"),
        ("0003", "0001"),
    ]

    findings = _chain_integrity_findings("migrations", ["0002", "0003"], revisions)

    messages = " ".join(f.message for f in findings)
    assert "head" in messages
    assert "0001" in messages


def test_missing_migration_parent_is_flagged() -> None:
    """`0002` claims a down_revision of `9999`, which no revision in the
    chain actually has."""
    revisions: list[tuple[str, RevisionParentT]] = [("0001", None), ("0002", "9999")]

    findings = _chain_integrity_findings("migrations", ["0002"], revisions)

    assert any("nonexistent parent" in f.message and "9999" in f.message for f in findings)


def test_disconnected_migration_graph_is_flagged() -> None:
    """`0004`/`0005` form their own closed loop, sharing no down_revision
    with the real `0001 -> 0002 -> 0003` chain and never being cited as
    anyone else's parent — so the head/base/shared-down-revision checks
    alone cannot see them; only walking the graph from the head can."""
    revisions: list[tuple[str, RevisionParentT]] = [
        ("0001", None),
        ("0002", "0001"),
        ("0003", "0002"),
        ("0004", "0005"),
        ("0005", "0004"),
    ]

    findings = _chain_integrity_findings("migrations", ["0003"], revisions)

    messages = " ".join(f.message for f in findings)
    assert "disconnected" in messages or "not reachable" in messages
    assert "0004" in messages
    assert "0005" in messages


def test_rejection_of_tuple_or_merge_parents() -> None:
    """This project requires a single unbranched migration chain — a merge
    revision (multiple parents, as Alembic represents with a tuple
    down_revision) must be rejected outright, not silently followed."""
    revisions: list[tuple[str, str | tuple[str, ...] | None]] = [
        ("0001", None),
        ("0002", "0001"),
        ("0003", ("0001", "0002")),
    ]

    findings = _chain_integrity_findings("migrations", ["0003"], revisions)

    assert any(
        "0003" in f.message and ("merge" in f.message or "multiple parents" in f.message)
        for f in findings
    )


# --------------------------------------------------------------------------
# Repository-relative CLI finding paths
# --------------------------------------------------------------------------


def test_real_repository_file_path_is_rendered_repository_relative() -> None:
    real_file = Path(__file__).resolve()

    assert _display_path(real_file) == "backend/tests/test_check_repo.py"


def test_synthetic_nonexistent_path_is_left_unchanged() -> None:
    assert _display_path(Path("fake.md")) == "fake.md"


def test_broken_link_finding_uses_a_repository_relative_path() -> None:
    """Exercises `_display_path` through the production `check_links_and_
    anchors` entry point against a real file, not just directly."""
    real_readme = REPO_ROOT / "README.md"
    source_text = "See [missing](does-not-exist-anywhere.md) for details.\n"

    findings = check_links_and_anchors(real_readme, source_text, {})

    assert len(findings) == 1
    assert findings[0].path == "README.md"


# --------------------------------------------------------------------------
# End-to-end
# --------------------------------------------------------------------------


def test_run_checks_against_the_real_repository_has_zero_findings() -> None:
    """The integration test requested alongside the synthetic unit tests:
    exercises the real production entry point against the actual repository
    (no monkeypatching), so the ordinary pytest suite catches future
    documentation/migration drift without anyone remembering to run the
    checker as a separate command."""
    findings = run_checks()

    assert findings == [], "\n".join(str(finding) for finding in findings)


def test_invocation_from_outside_backend_resolves_paths_independent_of_cwd(
    tmp_path: Path,
) -> None:
    """Runs the script as a subprocess from a working directory that is
    neither `backend/` nor the repository root, proving every path it uses
    is resolved from `__file__`, not the caller's current directory."""
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "check_repo.py"

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
