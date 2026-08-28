"""Deterministic, offline, database-free repository consistency checker.

Covers four categories (docs/LLM_WORKFLOW.md's verification matrix requires
this for documentation and migration changes):

1. Markdown link and heading-anchor validation (relative links, local and
   cross-file anchors, GitHub-style duplicate-heading suffixes, image
   targets; HTTP(S) targets are syntax-only, never fetched).
2. Duplicate rows in `docs/DATA_MODEL.md`'s "Phase 1 constraints & indexes"
   summary table, detected by comparing each row's individual UNIQUE/INDEX
   signatures (constraint type, normalized column list, normalized WHERE
   predicate) per table — not by comparing whole rows or every column any
   CHECK happens to mention, which would miss a duplicate whose other row
   documents additional CHECKs (the exact defect this tool was built to
   catch; see the `saved_search_locations` regression test). A companion
   check fails closed if the table itself goes missing or its syntax
   changes enough that zero signatures can be parsed from it at all.
3. Stale or nonexistent Alembic migration-revision references (any
   four-digit, leading-zero revision, not just `0000`-`0009`) in product
   documentation.
4. Migration-chain integrity — exactly one head, exactly one baseline, no
   forked chain, no dangling/nonexistent parent, no merge (multi-parent)
   revision, and full connectivity from the head back to the baseline —
   read via Alembic's own `ScriptDirectory`, never a database connection.
   A malformed graph that Alembic itself refuses to load is reported as a
   normal finding rather than an uncontrolled traceback.

`docs/LLM_HANDOFF.md` is a rotating historical ledger (see
docs/LLM_WORKFLOW.md) and is excluded from checks 2 and 3, since it
deliberately preserves superseded wording verbatim as review history. It is
still covered by check 1 — a broken link is a bug regardless of file.

Every finding's path is rendered repository-relative (e.g.
`docs/DATA_MODEL.md`), not an absolute, checkout-dependent path.

Run from anywhere; all paths are resolved from this file's own location, not
the current working directory:

    cd backend && python scripts/check_repo.py

Prints sorted `path:line: message` findings to stdout and exits 1 if any are
found, 0 otherwise. Never opens a network or database connection.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError

SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPTS_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
MIGRATIONS_DIR = BACKEND_DIR / "migrations"

# Rotating historical ledger (docs/LLM_WORKFLOW.md) — excluded from the
# duplicate-summary-row and Alembic-reference checks, still covered by
# link/anchor validation.
HISTORICAL_LEDGER_FILES = frozenset({"LLM_HANDOFF.md"})

CONSTRAINTS_TABLE_HEADING = "## Phase 1 constraints & indexes"
DATA_MODEL_FILENAME = "DATA_MODEL.md"


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def _display_path(path: Path) -> str:
    """Repository-relative path (forward-slash, checkout-independent) for a
    real file inside this repository, e.g. `docs/DATA_MODEL.md` instead of
    an absolute path that differs between machines. Falls back to the given
    path unchanged when it doesn't exist on disk — synthetic paths used by
    unit tests (e.g. `Path("fake.md")`) are left exactly as given."""
    resolved = path.resolve()
    if resolved.exists():
        try:
            return str(resolved.relative_to(REPO_ROOT)).replace("\\", "/")
        except ValueError:
            pass
    return str(path)


# --------------------------------------------------------------------------
# Markdown link and heading-anchor validation
# --------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s][^)]*)\)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$", re.MULTILINE)
_SLUG_STRIP_RE = re.compile(r"[^\w\s-]")
_SLUG_WHITESPACE_RE = re.compile(r"\s")


def _strip_code_preserving_lines(text: str) -> str:
    """Blank out fenced code blocks and inline code spans without shifting
    any line numbers, so link/anchor findings still point at the real line
    a documentation example (not a live link) came from."""

    def _blank_fence(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    def _blank_inline(match: re.Match[str]) -> str:
        return " " * len(match.group(0))

    text = _FENCE_RE.sub(_blank_fence, text)
    return _INLINE_CODE_RE.sub(_blank_inline, text)


def _slugify(heading_text: str) -> str:
    """GitHub's heading-anchor algorithm: lowercase, drop everything except
    word characters/spaces/hyphens (backticks, periods, em-dashes, section
    signs, parens all disappear without leaving a separator), then turn each
    remaining whitespace character into its own hyphen (runs are not
    collapsed) — verified against anchors already used elsewhere in this
    repository, e.g. "6.5 `SavedSearch.enabled_sources` — ..." ->
    "65-savedsearchenabled_sources--...".
    """
    slug = heading_text.lower()
    slug = _SLUG_STRIP_RE.sub("", slug)
    return _SLUG_WHITESPACE_RE.sub("-", slug)


def _anchors_for_text(text: str) -> set[str]:
    seen: dict[str, int] = {}
    anchors: set[str] = set()
    for match in _HEADING_RE.finditer(text):
        base = _slugify(match.group(2))
        count = seen.get(base, 0)
        anchors.add(base if count == 0 else f"{base}-{count}")
        seen[base] = count + 1
    return anchors


def check_links_and_anchors(
    path: Path, raw_text: str, file_texts: dict[Path, str]
) -> list[Finding]:
    findings: list[Finding] = []
    text = _strip_code_preserving_lines(raw_text)
    for match in _LINK_RE.finditer(text):
        target = match.group(1).strip()
        # Drop an optional trailing markdown title: [text](url "title").
        target = target.split(" ", 1)[0].strip('"')
        if target.startswith(("http://", "https://", "mailto:")):
            continue  # offline/syntax-only — never fetched
        line_no = text.count("\n", 0, match.start()) + 1
        file_part, _, anchor_part = target.partition("#")

        if file_part:
            target_path = (path.parent / file_part).resolve()
            if not target_path.exists():
                findings.append(
                    Finding(
                        _display_path(path),
                        line_no,
                        f"broken link: target does not exist: {file_part}",
                    )
                )
                continue
        else:
            target_path = path.resolve()

        if anchor_part:
            target_text = file_texts.get(target_path)
            if target_text is None:
                continue  # target isn't a markdown file we read; nothing to check
            if anchor_part not in _anchors_for_text(target_text):
                findings.append(
                    Finding(
                        _display_path(path),
                        line_no,
                        f"broken anchor: #{anchor_part} not found in " f"{file_part or path.name}",
                    )
                )
    return findings


# --------------------------------------------------------------------------
# Duplicate constraints-summary row detection
# --------------------------------------------------------------------------

_TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
_SEPARATOR_CELL_RE = re.compile(r":?-{2,}:?")
_CELL_TABLE_NAME_RE = re.compile(r"`([^`]+)`")
_BACKTICK_SPAN_RE = re.compile(r"`([^`]+)`")
_UNIQUE_OR_INDEX_START_RE = re.compile(r"^(UNIQUE|INDEX)\s*\(")
_WHERE_RE = re.compile(r"^WHERE\s+(.+)$")
_WRAPPER_PREFIXES = ("lower(", "trim(")


def _split_top_level_commas(text: str) -> list[str]:
    """Splits on commas that are not nested inside parentheses, so a
    wrapped column expression like `lower(a)` is never torn apart."""
    parts: list[str] = []
    depth = 0
    current = ""
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return parts


def _match_unique_or_index(span: str) -> tuple[str, str, str | None] | None:
    """Parses a `UNIQUE (...)` / `INDEX (...) [WHERE ...]` span, finding the
    outer parenthesis pair by depth-tracking rather than a `[^)]*` regex
    class — the latter cannot skip past the inner `)` of a wrapped column
    like `lower(location_text)` and would fail to match at all."""
    start_match = _UNIQUE_OR_INDEX_START_RE.match(span)
    if not start_match:
        return None
    kind = start_match.group(1)
    depth = 1
    index = start_match.end()
    while index < len(span) and depth > 0:
        if span[index] == "(":
            depth += 1
        elif span[index] == ")":
            depth -= 1
        index += 1
    if depth != 0:
        return None  # unbalanced parentheses — not a well-formed span
    columns_raw = span[start_match.end() : index - 1]
    rest = span[index:].strip()
    if not rest:
        return kind, columns_raw, None
    where_match = _WHERE_RE.match(rest)
    if not where_match:
        return None
    return kind, columns_raw, where_match.group(1)


def _normalize_column(expr: str) -> str:
    expr = expr.strip()
    lowered = expr.lower()
    for prefix in _WRAPPER_PREFIXES:
        if lowered.startswith(prefix) and expr.endswith(")"):
            return _normalize_column(expr[len(prefix) : -1])
    return expr


def _normalize_where(where: str) -> str:
    return " ".join(where.split())


ConstraintSignature = tuple[str, tuple[str, ...], str | None]


def _extract_constraint_signatures(cell_text: str) -> list[ConstraintSignature]:
    signatures: list[ConstraintSignature] = []
    for match in _BACKTICK_SPAN_RE.finditer(cell_text):
        span = match.group(1).strip()
        parsed = _match_unique_or_index(span)
        if not parsed:
            continue
        kind, columns_raw, where_raw = parsed
        preceding = cell_text[: match.start()]
        is_partial = bool(re.search(r"\bpartial\s*$", preceding, re.IGNORECASE))
        constraint_type = f"partial {kind}" if is_partial else kind
        columns = tuple(_normalize_column(c) for c in _split_top_level_commas(columns_raw))
        where_norm = _normalize_where(where_raw) if where_raw else None
        signatures.append((constraint_type, columns, where_norm))
    return signatures


def _is_separator_row(cells: list[str]) -> bool:
    return all(_SEPARATOR_CELL_RE.fullmatch(c) for c in cells if c)


def _parse_constraints_table(text: str) -> list[tuple[int, str, str]]:
    """Returns (line_number, table_name, constraint_cell_text) for each data
    row of the "Phase 1 constraints & indexes" summary table."""
    rows: list[tuple[int, str, str]] = []
    in_table = False
    passed_separator = False
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped == CONSTRAINTS_TABLE_HEADING:
            in_table = True
            passed_separator = False
            continue
        if not in_table:
            continue
        if stripped.startswith("#"):
            break
        row_match = _TABLE_ROW_RE.match(stripped)
        if not row_match:
            if passed_separator:
                break
            continue
        cells = [c.strip() for c in row_match.group(1).split("|")]
        if not passed_separator:
            if _is_separator_row(cells):
                passed_separator = True
            continue
        if len(cells) < 2:
            continue
        name_match = _CELL_TABLE_NAME_RE.search(cells[0])
        if not name_match:
            continue
        rows.append((line_no, name_match.group(1), cells[1]))
    return rows


def check_duplicate_constraint_rows(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    display_path = _display_path(path)
    by_table: dict[str, list[tuple[int, str]]] = {}
    for line_no, table_name, cell in _parse_constraints_table(text):
        by_table.setdefault(table_name, []).append((line_no, cell))

    for table_name, entries in by_table.items():
        if len(entries) < 2:
            continue

        seen_exact: dict[str, int] = {}
        for line_no, cell in entries:
            normalized_cell = " ".join(cell.split())
            first_line = seen_exact.get(normalized_cell)
            if first_line is not None:
                findings.append(
                    Finding(
                        display_path,
                        line_no,
                        f"duplicate constraints-summary row for `{table_name}` is "
                        f"identical to the row at line {first_line}",
                    )
                )
            else:
                seen_exact[normalized_cell] = line_no

        seen_signatures: dict[ConstraintSignature, int] = {}
        for line_no, cell in entries:
            for signature in _extract_constraint_signatures(cell):
                first_line = seen_signatures.get(signature)
                if first_line is not None:
                    kind, columns, where = signature
                    findings.append(
                        Finding(
                            display_path,
                            line_no,
                            f"duplicate constraints-summary row for `{table_name}`: "
                            f"{kind} on {columns} (where={where!r}) already declared "
                            f"at line {first_line}",
                        )
                    )
                else:
                    seen_signatures[signature] = line_no
    return findings


def check_constraints_table_integrity(path: Path, text: str) -> list[Finding]:
    """Guards against `check_duplicate_constraint_rows` failing open: that
    function returns an empty (indistinguishable-from-clean) result if the
    "Phase 1 constraints & indexes" heading disappears, its table shape
    changes so no rows parse, or every row's UNIQUE/INDEX syntax changes so
    no signature can be extracted at all. Only meaningful for
    `docs/DATA_MODEL.md`, the file that must contain this table."""
    rows = _parse_constraints_table(text)
    display_path = _display_path(path)
    if not rows:
        return [
            Finding(
                display_path,
                1,
                f"'{CONSTRAINTS_TABLE_HEADING}' constraints-summary table not found "
                "or has no data rows",
            )
        ]
    if not any(_extract_constraint_signatures(cell) for _, _, cell in rows):
        return [
            Finding(
                display_path,
                1,
                f"'{CONSTRAINTS_TABLE_HEADING}' table has {len(rows)} row(s) but no "
                "UNIQUE/INDEX signature could be parsed from any of them",
            )
        ]
    return []


# --------------------------------------------------------------------------
# Alembic revision references and migration-chain integrity
# --------------------------------------------------------------------------

_BARE_REVISION_RE = re.compile(r"`(0\d{3})`")
_MIGRATION_CITATION_RE = re.compile(
    r"migration\s+`(\d{4})`[^`]{0,60}`down_revision\s*=\s*\"(\d{4})\"`", re.DOTALL
)


def _script_directory() -> ScriptDirectory:
    config = Config(str(ALEMBIC_INI))
    # Absolute path so this works identically regardless of the caller's
    # current working directory (tests, alternate invocation directories).
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return ScriptDirectory.from_config(config)


def _revision_map(script: ScriptDirectory) -> dict[str, str | None]:
    revision_map: dict[str, str | None] = {}
    for rev in script.walk_revisions():
        down = rev.down_revision
        revision_map[rev.revision] = down if isinstance(down, str) or down is None else str(down)
    return revision_map


def check_alembic_references(
    path: Path, text: str, revision_map: dict[str, str | None]
) -> list[Finding]:
    findings: list[Finding] = []
    display_path = _display_path(path)
    for match in _BARE_REVISION_RE.finditer(text):
        revision = match.group(1)
        if revision not in revision_map:
            line_no = text.count("\n", 0, match.start()) + 1
            findings.append(
                Finding(display_path, line_no, f"references nonexistent migration `{revision}`")
            )
    for match in _MIGRATION_CITATION_RE.finditer(text):
        revision, claimed_down = match.groups()
        if revision not in revision_map:
            continue  # already reported above
        actual_down = revision_map[revision]
        if actual_down != claimed_down:
            line_no = text.count("\n", 0, match.start()) + 1
            findings.append(
                Finding(
                    display_path,
                    line_no,
                    f"migration `{revision}` documented with down_revision "
                    f'"{claimed_down}", but its actual down_revision is {actual_down!r}',
                )
            )
    return findings


RevisionParent = str | tuple[str, ...] | None


def _chain_integrity_findings(
    location: str, heads: list[str], revisions: list[tuple[str, RevisionParent]]
) -> list[Finding]:
    """Pure logic, independent of Alembic's API — takes plain (revision,
    down_revision) pairs so it's directly unit-testable with synthetic data,
    not just against the real migrations/ directory. `down_revision` may be
    a tuple for a merge revision; this project requires a single unbranched
    chain, so any tuple parent is rejected outright rather than followed."""
    findings: list[Finding] = []

    if len(heads) != 1:
        findings.append(
            Finding(location, 1, f"expected exactly one migration head, found {sorted(heads)}")
        )

    all_revisions = {revision for revision, _ in revisions}
    down_revision_owners: dict[RevisionParent, list[str]] = {}
    bases: list[str] = []
    parent_of: dict[str, str] = {}
    merge_revisions: set[str] = set()

    for revision, down in revisions:
        down_revision_owners.setdefault(down, []).append(revision)
        if isinstance(down, tuple):
            merge_revisions.add(revision)
            findings.append(
                Finding(
                    location,
                    1,
                    f"migration `{revision}` has multiple parents {sorted(down)} (a "
                    "merge revision); this project requires a single unbranched chain",
                )
            )
            continue
        if down is None:
            bases.append(revision)
            continue
        parent_of[revision] = down
        if down not in all_revisions:
            findings.append(
                Finding(
                    location,
                    1,
                    f"migration `{revision}` references nonexistent parent `{down}`",
                )
            )

    if len(bases) != 1:
        findings.append(
            Finding(
                location,
                1,
                f"expected exactly one baseline migration (down_revision=None), "
                f"found {sorted(bases)}",
            )
        )
    for down, owners in down_revision_owners.items():
        if len(owners) > 1:
            findings.append(
                Finding(
                    location,
                    1,
                    f"multiple migrations share down_revision {down!r}: {sorted(owners)}",
                )
            )

    if len(heads) == 1:
        head = heads[0]
        reachable: set[str] = set()
        current: str | None = head
        while current is not None and current not in reachable:
            reachable.add(current)
            current = parent_of.get(current)
        unreachable = all_revisions - reachable - merge_revisions
        if unreachable:
            findings.append(
                Finding(
                    location,
                    1,
                    "migration graph is disconnected: revision(s) "
                    f"{sorted(unreachable)} are not reachable by walking parents "
                    f"from head `{head}`",
                )
            )

    return findings


def _normalize_down_revision(down: object) -> RevisionParent:
    if down is None or isinstance(down, str):
        return down
    if isinstance(down, list | tuple):
        return tuple(str(item) for item in down)
    return str(down)


def check_migration_chain_integrity(script: ScriptDirectory) -> list[Finding]:
    """Alembic eagerly resolves the whole revision graph while walking it, so
    a broken parent reference can raise before this function gets a chance
    to inspect it structurally; convert that into a normal finding instead
    of an uncontrolled traceback."""
    location = _display_path(MIGRATIONS_DIR)
    try:
        heads = list(script.get_heads())
        revisions = [
            (rev.revision, _normalize_down_revision(rev.down_revision))
            for rev in script.walk_revisions()
        ]
    except CommandError as exc:
        return [Finding(location, 1, f"failed to load migration graph: {exc}")]
    return _chain_integrity_findings(location, heads, revisions)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def _collect_markdown_files() -> list[Path]:
    candidates = [REPO_ROOT / "README.md", *sorted((REPO_ROOT / "docs").glob("*.md"))]
    decisions_dir = REPO_ROOT / "docs" / "DECISIONS"
    if decisions_dir.is_dir():
        candidates.extend(sorted(decisions_dir.glob("*.md")))
    return [path for path in candidates if path.is_file()]


def run_checks() -> list[Finding]:
    findings: list[Finding] = []
    markdown_files = _collect_markdown_files()
    file_texts = {path.resolve(): path.read_text(encoding="utf-8") for path in markdown_files}

    for path in markdown_files:
        text = file_texts[path.resolve()]
        findings.extend(check_links_and_anchors(path, text, file_texts))

    script = _script_directory()
    revision_map = _revision_map(script)

    for path in markdown_files:
        if path.name in HISTORICAL_LEDGER_FILES:
            continue
        text = file_texts[path.resolve()]
        findings.extend(check_duplicate_constraint_rows(path, text))
        findings.extend(check_alembic_references(path, text, revision_map))
        if path.name == DATA_MODEL_FILENAME:
            findings.extend(check_constraints_table_integrity(path, text))

    findings.extend(check_migration_chain_integrity(script))

    return sorted(findings)


def main() -> int:
    findings = run_checks()
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
