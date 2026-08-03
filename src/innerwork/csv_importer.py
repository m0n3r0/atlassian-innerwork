"""CSV/TSV importer: read work-item rows from a local CSV/TSV file.

This module implements the locked mapping rules from
``docs/roadmap_csv_importer_scoping.md`` §2–§4:

* one file contains **work-item rows**; the ``projects`` collection is
  derived from the distinct ``project`` column values — there are no
  separate project rows;
* header matching is case-insensitive and whitespace-trimmed; unknown
  columns produce one warning and are ignored; a ``type`` column is
  recognized but dropped with a single warning (the domain model has
  no work-item type field);
* ``status`` cells map through the locked vocabulary
  (:data:`_STATUS_ALIASES`); anything else is an error;
* keys are explicit (validated ``PROJ-N``, prefix must match the
  project) or auto-allocated per project in file order, starting at the
  store's current ``next_sequence`` (1 on a fresh store);
* the importer writes **directly** through its own scoped insert path
  (projects, work_items, project_sequences) mirroring portability's SQL
  — it never produces a portability envelope, never calls
  ``import_domain``, and refuses to overlay existing projects / work
  items unless ``allow_populated`` is passed.

``scan_csv_file`` is the pure validation pass (filesystem reads only,
no database access). ``import_csv_file`` adds the store-level
fresh-target and conflict checks, then writes the scanned plan. All
user-facing failures raise :class:`CsvImportError`, which the CLI maps
to exit code 2.

No network access anywhere in this module; the only imports beyond the
standard library are the local ``DomainStore`` and domain helpers.
"""

from __future__ import annotations

import csv
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .domain import validate_project_key
from .domain_store import DomainStore, utc_now_iso

__all__ = (
    "CsvImportError",
    "CsvImportPlan",
    "CsvProject",
    "CsvWorkItem",
    "import_csv_file",
    "scan_csv_file",
)

#: Mirrors ``domain._NON_EMPTY_TEXT_MAX`` (title cap) — kept local so the
#: importer surfaces model-limit violations as :class:`CsvImportError`
#: (exit 2) instead of a raw ``ValueError`` from the store.
_TITLE_MAX = 200
#: Mirrors ``domain._DESCRIPTION_MAX``.
_DESCRIPTION_MAX = 4000

#: Project key shape: 2-10 uppercase chars starting with a letter.
_PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
#: Explicit work-item key shape: ``PROJ-NNN``.
_WORK_ITEM_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}-\d+$")

_ASCII_UPPER_DIGITS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

#: Canonical column -> accepted aliases. Header cells are matched
#: case-insensitively and whitespace-trimmed before lookup; ``project``
#: and ``title`` are required, everything else is optional.
_COLUMN_ALIASES: dict[str, frozenset[str]] = {
    "project": frozenset({"project", "project_key", "project key"}),
    "project_name": frozenset({"project_name", "project name"}),
    "title": frozenset({"title", "summary"}),
    "status": frozenset({"status", "state"}),
    "type": frozenset({"type", "work_item_type", "issue type"}),
    "description": frozenset({"description", "desc"}),
    "assignee": frozenset({"assignee"}),
    "key": frozenset({"key", "work_item_key"}),
}

#: Status vocabulary (locked in scoping §3.2). Cells are normalized as
#: strip + lowercase + collapse internal whitespace before lookup.
_STATUS_ALIASES: dict[str, str] = {
    "todo": "todo",
    "backlog": "todo",
    "open": "todo",
    "to do": "todo",
    "to-do": "todo",
    "in_progress": "in_progress",
    "in progress": "in_progress",
    "wip": "in_progress",
    "doing": "in_progress",
    "inprogress": "in_progress",
    "done": "done",
    "closed": "done",
    "complete": "done",
    "completed": "done",
    "resolved": "done",
}

_WS_RE = re.compile(r"\s+")


class CsvImportError(ValueError):
    """Raised for any user-facing CSV-import failure (CLI exit 2)."""


@dataclass(frozen=True)
class CsvProject:
    """One derived project: sanitized key, resolved name, owner."""

    key: str
    name: str
    owner: str
    #: True when ``name`` came from a non-blank ``project_name`` cell
    #: rather than the verbatim ``project`` cell fallback. Used to warn
    #: when a ``project_name`` would be ignored for an existing project.
    name_provided: bool = False


@dataclass(frozen=True)
class CsvWorkItem:
    """One imported work item with its resolved key and provenance."""

    project_key: str
    key: str
    title: str
    description: str
    state: str
    assignee: str
    #: The explicit ``key`` cell when the row provided one, else None.
    explicit_key: str | None = None
    #: 1-based file row (the header is row 1) for error messages.
    row_number: int = 0

    @property
    def key_suffix(self) -> int:
        return int(self.key.rsplit("-", 1)[1])


@dataclass(frozen=True)
class CsvImportPlan:
    """Result of a scan: validated projects/work items and warnings."""

    projects: tuple[CsvProject, ...] = ()
    work_items: tuple[CsvWorkItem, ...] = ()
    warnings: tuple[str, ...] = ()
    delimiter: str = "comma"  # "comma" | "tab"


# ------------------------------------------------------------------ scanning


def scan_csv_file(
    path: Path | str,
    *,
    owner: str,
    delimiter: str = "auto",
    created_at: str | None = None,
) -> CsvImportPlan:
    """Parse, map, and validate ``path`` into a :class:`CsvImportPlan`.

    Pure: reads the file only, never touches a database. Deterministic:
    projects are derived in sorted-key order, work items keep file
    order, warnings are sorted. Raises :class:`CsvImportError` for any
    structural problem so a broken file never reaches the store.
    """

    file_path = Path(path)
    if not file_path.is_file():
        raise CsvImportError(f"not a file: {file_path}")
    resolved = _detect_delimiter(file_path, delimiter)
    owner_value = (owner or "").strip()
    if not owner_value:
        raise CsvImportError("owner must be a non-blank string")
    if created_at is not None and not created_at.strip():
        raise CsvImportError("created_at must be a non-blank string")

    rows = _read_table(file_path, "\t" if resolved == "tab" else ",")
    # csv.reader yields [] for blank lines; skipping them is documented,
    # not an error. The first remaining row is the header.
    rows = [row for row in rows if row]
    if not rows:
        raise CsvImportError("file is empty: no header row found")
    header = [cell.strip() for cell in rows[0]]
    normalized_header = [_normalize_header(cell) for cell in rows[0]]

    _check_duplicate_headers(header, normalized_header)
    column_index = _map_columns(normalized_header)
    missing = [name for name in ("project", "title") if name not in column_index]
    if missing:
        raise CsvImportError("missing required column(s): " + ", ".join(missing))

    warnings: list[str] = []
    unknown = sorted(
        raw
        for raw, normalized in zip(header, normalized_header, strict=True)
        if _canonical_column(normalized) is None
    )
    if unknown:
        warnings.append(f"unknown column(s): {', '.join(unknown)}")
    if "type" in column_index:
        warnings.append(
            "type column dropped: the domain model has no work-item type field"
        )

    data_rows = rows[1:]
    if not data_rows:
        raise CsvImportError("file has no data rows (header only)")

    raw_items: list[dict[str, Any]] = []
    for data_index, row in enumerate(data_rows):
        file_row = data_index + 2  # the header is file row 1
        try:
            dict(zip(header, row, strict=True))  # loud length check
        except ValueError as exc:
            raise CsvImportError(
                f"row {file_row}: expected {len(header)} columns, got {len(row)}"
            ) from exc
        raw_items.append(_map_row(row, column_index, file_row))

    project_keys = _derive_project_keys(raw_items)
    names, provided = _resolve_project_names(raw_items, project_keys)
    projects = tuple(
        CsvProject(key=key, name=names[key], owner=owner_value, name_provided=provided[key])
        for key in project_keys
    )
    work_items = _resolve_keys(
        tuple(
            CsvWorkItem(
                project_key=item["project_key"],
                key="",  # placeholder; replaced by _resolve_keys
                title=item["title"],
                description=item["description"],
                state=item["state"],
                assignee=item["assignee"],
                explicit_key=item["explicit_key"],
                row_number=item["row_number"],
            )
            for item in raw_items
        ),
        start_sequences={key: 1 for key in project_keys},
    )
    return CsvImportPlan(
        projects=projects,
        work_items=work_items,
        warnings=tuple(sorted(warnings)),
        delimiter=resolved,
    )


def _detect_delimiter(path: Path, delimiter: str) -> str:
    """Resolve the delimiter: explicit override, else extension-based.

    ``auto`` means ``.tsv`` → tab and anything else → comma. No
    ``csv.Sniffer`` — heuristics are not stable enough to lock into a
    spec; extension + explicit override is deterministic and boring.
    """

    if delimiter == "comma":
        return "comma"
    if delimiter == "tab":
        return "tab"
    if delimiter == "auto":
        return "tab" if path.suffix.lower() == ".tsv" else "comma"
    raise CsvImportError(f"unknown delimiter: {delimiter!r}")


def _read_table(path: Path, delimiter_char: str) -> list[list[str]]:
    """Read every row with ``utf-8-sig`` + ``newline=""``.

    ``utf-8-sig`` strips a leading BOM; ``newline=""`` is the csv-module
    requirement so both CRLF and LF line endings parse.
    """

    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.reader(handle, delimiter=delimiter_char))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise CsvImportError(f"cannot parse {path}: {exc}") from exc


def _normalize_header(cell: str) -> str:
    """Header normalization: strip + lowercase + collapse whitespace."""

    return _WS_RE.sub(" ", cell.strip().lower())


def _check_duplicate_headers(header: list[str], normalized: list[str]) -> None:
    """Reject two headers normalizing to the same name, and two columns
    mapping to the same canonical column (both are ambiguous input)."""

    seen_by_name: dict[str, str] = {}
    for raw, normalized_name in zip(header, normalized, strict=True):
        previous = seen_by_name.get(normalized_name)
        if previous is not None:
            raise CsvImportError(
                f"duplicate header: columns {previous!r} and {raw!r} "
                f"normalize to the same name"
            )
        seen_by_name[normalized_name] = raw
    seen_by_canonical: dict[str, str] = {}
    for raw, normalized_name in zip(header, normalized, strict=True):
        canonical = _canonical_column(normalized_name)
        if canonical is None:
            continue
        previous = seen_by_canonical.get(canonical)
        if previous is not None:
            raise CsvImportError(
                f"duplicate {canonical} column: {previous!r} and {raw!r} "
                f"both map to {canonical!r}"
            )
        seen_by_canonical[canonical] = raw


def _map_columns(normalized_header: list[str]) -> dict[str, int]:
    """Map canonical column name -> header position (present columns only)."""

    column_index: dict[str, int] = {}
    for index, normalized in enumerate(normalized_header):
        canonical = _canonical_column(normalized)
        if canonical is not None:
            column_index[canonical] = index
    return column_index


def _canonical_column(normalized: str) -> str | None:
    for canonical, aliases in _COLUMN_ALIASES.items():
        if normalized in aliases:
            return canonical
    return None


def _map_row(row: list[str], column_index: dict[str, int], file_row: int) -> dict[str, Any]:
    """Validate and map one data row into a raw item dict."""

    def _cell(canonical: str) -> str:
        index = column_index.get(canonical)
        return row[index] if index is not None else ""

    project_raw = _cell("project").strip()
    if not project_raw:
        raise CsvImportError(f"row {file_row}: project is blank")
    project_key = _sanitize_project_key(project_raw, row=file_row)

    title = _cell("title").strip()
    if not title:
        raise CsvImportError(f"row {file_row}: title is blank")
    if len(title) > _TITLE_MAX:
        raise CsvImportError(f"row {file_row}: title exceeds {_TITLE_MAX} characters")

    description = _cell("description")
    if len(description) > _DESCRIPTION_MAX:
        raise CsvImportError(
            f"row {file_row}: description exceeds {_DESCRIPTION_MAX} characters"
        )
    description = description if description.strip() else ""

    assignee = _cell("assignee")
    assignee = assignee if assignee.strip() else ""

    status_cell = _cell("status")
    state = _map_state(status_cell, row=file_row) if status_cell.strip() else "todo"

    explicit_key_raw = _cell("key").strip()
    explicit_key: str | None = None
    if explicit_key_raw:
        if not _WORK_ITEM_KEY_RE.match(explicit_key_raw):
            raise CsvImportError(
                f"row {file_row}: invalid work item key {explicit_key_raw!r}; "
                "expected PROJECT-NNN (e.g. ENG-1)"
            )
        if explicit_key_raw.rsplit("-", 1)[0] != project_key:
            raise CsvImportError(
                f"row {file_row}: key {explicit_key_raw!r} does not match "
                f"project {project_key!r}"
            )
        explicit_key = explicit_key_raw

    return {
        "project_key": project_key,
        "project_raw": project_raw,
        "project_name": _cell("project_name").strip(),
        "title": title,
        "description": description,
        "state": state,
        "assignee": assignee,
        "explicit_key": explicit_key,
        "row_number": file_row,
    }


def _sanitize_project_key(value: str, *, row: int) -> str:
    """Derive a project key per scoping §2.5: uppercase, drop non [A-Z0-9].

    The sanitized form must still match ``^[A-Z][A-Z0-9]{1,9}$`` — no
    silent truncation (truncation risks silent key collisions).
    """

    sanitized = "".join(ch for ch in value.upper() if ch in _ASCII_UPPER_DIGITS)
    try:
        validate_project_key(sanitized)
    except ValueError as exc:
        raise CsvImportError(
            f"row {row}: project {value!r} does not map to a valid project key "
            f"(sanitized: {sanitized!r}); expected 2-10 uppercase chars "
            "starting with a letter"
        ) from exc
    return sanitized


def _map_state(value: str, *, row: int) -> str:
    """Map a status cell through the locked vocabulary (§3.2)."""

    normalized = _WS_RE.sub(" ", value.strip().lower())
    state = _STATUS_ALIASES.get(normalized)
    if state is None:
        raise CsvImportError(
            f"row {row}: unknown status {value.strip()!r}; "
            "expected one of todo, in_progress, done"
        )
    return state


def _derive_project_keys(raw_items: list[dict[str, Any]]) -> list[str]:
    """Distinct sanitized project keys, sorted; collisions are errors."""

    keys: list[str] = []
    raw_by_key: dict[str, str] = {}
    for item in raw_items:
        key = item["project_key"]
        previous = raw_by_key.get(key)
        if previous is not None and previous != item["project_raw"]:
            raise CsvImportError(
                f"project key collision: {previous!r} and {item['project_raw']!r} "
                f"both map to key {key!r}"
            )
        raw_by_key[key] = item["project_raw"]
        if key not in keys:
            keys.append(key)
    return sorted(keys)


def _resolve_project_names(
    raw_items: list[dict[str, Any]], project_keys: list[str]
) -> tuple[dict[str, str], dict[str, bool]]:
    """Resolve each project's name per scoping §2.5.

    ``name`` = the first non-blank ``project_name`` cell for the project
    (file order), else the verbatim ``project`` cell of the project's
    first row. Returns ``(names, provided_flags)`` keyed by project key.
    """

    names: dict[str, str] = {}
    provided: dict[str, bool] = {}
    for item in raw_items:
        key = item["project_key"]
        if item["project_name"] and key not in names:
            names[key] = item["project_name"]
            provided[key] = True
    for item in raw_items:
        key = item["project_key"]
        if key not in names:
            names[key] = item["project_raw"]
            provided[key] = False
    return names, provided


def _resolve_keys(
    work_items: tuple[CsvWorkItem, ...],
    *,
    start_sequences: dict[str, int],
) -> tuple[CsvWorkItem, ...]:
    """Allocate keys per scoping §3.3.

    Explicit keys are used verbatim (already validated); auto rows get
    ``{PROJ}-{n}`` where ``n`` starts at the project's starting
    sequence (1 on a fresh store) and advances past every used suffix.
    Within one file, a reused explicit key is an error naming both rows.
    """

    used_by_project: dict[str, set[int]] = {}
    row_by_suffix: dict[str, dict[int, int]] = {}
    next_auto = dict(start_sequences)
    resolved: list[CsvWorkItem] = []
    for item in work_items:
        project = item.project_key
        used = used_by_project.setdefault(project, set())
        rows_for_suffix = row_by_suffix.setdefault(project, {})
        if item.explicit_key is not None:
            suffix = int(item.explicit_key.rsplit("-", 1)[1])
            first_row = rows_for_suffix.get(suffix)
            if first_row is not None:
                raise CsvImportError(
                    f"duplicate work item key {item.explicit_key!r} in rows "
                    f"{first_row} and {item.row_number}"
                )
            used.add(suffix)
            rows_for_suffix[suffix] = item.row_number
            key = item.explicit_key
        else:
            candidate = next_auto.get(project, 1)
            while candidate in used:
                candidate += 1
            key = f"{project}-{candidate}"
            used.add(candidate)
            rows_for_suffix[candidate] = item.row_number
            next_auto[project] = candidate + 1
        resolved.append(
            CsvWorkItem(
                project_key=item.project_key,
                key=key,
                title=item.title,
                description=item.description,
                state=item.state,
                assignee=item.assignee,
                explicit_key=item.explicit_key,
                row_number=item.row_number,
            )
        )
    return tuple(resolved)


# ------------------------------------------------------------------ importing


def import_csv_file(
    store: DomainStore,
    path: Path | str,
    *,
    owner: str = "importer",
    delimiter: str = "auto",
    created_at: str | None = None,
    dry_run: bool = False,
    allow_populated: bool = False,
) -> dict[str, object]:
    """Scan ``path`` and write projects/work items through ``store``.

    Returns ``{"projects": int, "work_items": int, "warnings": [...],
    "dry_run": bool, "delimiter": "comma"|"tab"}``. In dry-run mode
    nothing is written, but the fresh-target and conflict checks still
    run so the summary is an honest preview of a real import.
    """

    plan = scan_csv_file(path, owner=owner, delimiter=delimiter, created_at=created_at)
    if not allow_populated:
        _validate_fresh_target(store)
    warnings = list(plan.warnings)
    warnings.extend(_existing_project_warnings(store, plan))
    _check_store_conflicts(store, plan)
    if not dry_run:
        timestamp = created_at or utc_now_iso()
        _write_plan(store, plan, created_at=timestamp)
    return {
        "projects": len(plan.projects),
        "work_items": len(plan.work_items),
        "warnings": sorted(warnings),
        "dry_run": dry_run,
        "delimiter": plan.delimiter,
    }


def _validate_fresh_target(store: DomainStore) -> None:
    """Refuse to run when projects or work_items already have rows.

    Only the two collections the importer touches gate; spaces / pages /
    links / comments may exist and are untouched (mirrors the markdown
    importer's scoping).
    """

    with store._connect() as connection:  # noqa: SLF001 — peer of DomainStore
        for table in ("projects", "work_items"):
            (count,) = connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()
            if int(count) > 0:
                raise CsvImportError(
                    f"target store is not empty: {table} has {count} row(s)"
                )


def _existing_project_warnings(store: DomainStore, plan: CsvImportPlan) -> list[str]:
    """Warn when a file's ``project_name`` would be ignored (§4).

    Under ``--allow-populated`` an existing project's rows are never
    modified, so a non-blank ``project_name`` cell for it is recorded as
    a warning instead of being applied.
    """

    if not plan.projects:
        return []
    with store._connect() as connection:  # noqa: SLF001
        rows = connection.execute("SELECT key FROM projects").fetchall()
    existing = {str(row[0]) for row in rows}
    return sorted(
        f"project name ignored for existing project {project.key}"
        for project in plan.projects
        if project.name_provided and project.key in existing
    )


def _check_store_conflicts(store: DomainStore, plan: CsvImportPlan) -> None:
    """DB-level conflict checks (scoping §3.3, across the store).

    Explicit keys must not already exist; auto-keyed rows use the
    natural key ``(project_key, title)``. Runs in dry-run mode too so
    the preview is honest, and runs before any write so a conflict
    leaves the store untouched.
    """

    with store._connect() as connection:  # noqa: SLF001
        for item in plan.work_items:
            if item.explicit_key is not None:
                row = connection.execute(
                    "SELECT key FROM work_items WHERE key = ?", (item.explicit_key,)
                ).fetchone()
                if row is not None:
                    raise CsvImportError(
                        f"work item key already exists: {item.explicit_key!r} "
                        f"(row {item.row_number})"
                    )
            else:
                row = connection.execute(
                    """
                    SELECT w.key FROM work_items w
                    JOIN projects p ON w.project_id = p.project_id
                    WHERE p.key = ? AND w.title = ?
                    """,
                    (item.project_key, item.title),
                ).fetchone()
                if row is not None:
                    raise CsvImportError(
                        f"work item already exists: {item.title!r} in project "
                        f"{item.project_key} (row {item.row_number}, "
                        f"existing key {row[0]})"
                    )


def _write_plan(
    store: DomainStore,
    plan: CsvImportPlan,
    *,
    created_at: str,
) -> None:
    """Insert projects + work items and bump sequences (scoped write).

    Mirrors portability's SQL against the three tables the importer
    owns (projects, work_items, project_sequences). Existing rows are
    never modified; conflicting rows already errored in
    :func:`_check_store_conflicts`. Runs in one transaction so any
    failure rolls back everything.
    """

    with store._connect() as connection:  # noqa: SLF001 — peer of DomainStore
        existing = {
            str(key): (str(project_id), str(name))
            for key, project_id, name in connection.execute(
                "SELECT key, project_id, name FROM projects"
            ).fetchall()
        }
        project_ids: dict[str, str] = {}
        for project in plan.projects:
            if project.key in existing:
                project_ids[project.key] = existing[project.key][0]
            else:
                project_id = str(uuid.uuid4())
                connection.execute(
                    "INSERT INTO projects(project_id, key, name, owner, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (project_id, project.key, project.name, project.owner, created_at),
                )
                project_ids[project.key] = project_id

        start_sequences = _read_start_sequences(connection, plan)
        items = _resolve_keys(plan.work_items, start_sequences=start_sequences)
        items_by_project: dict[str, list[CsvWorkItem]] = {}
        for item in items:
            items_by_project.setdefault(item.project_key, []).append(item)
        for project in plan.projects:
            for item in items_by_project.get(project.key, []):
                connection.execute(
                    """
                    INSERT INTO work_items(
                        work_item_id, project_id, key, title, description,
                        state, assignee, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        project_ids[item.project_key],
                        item.key,
                        item.title,
                        item.description,
                        item.state,
                        item.assignee,
                        created_at,
                        created_at,
                    ),
                )
        _bump_sequences(connection, plan, items, project_ids)


def _read_start_sequences(connection: Any, plan: CsvImportPlan) -> dict[str, int]:
    """Current ``next_sequence`` per project in the file (1 if absent)."""

    keys = [project.key for project in plan.projects]
    if not keys:
        return {}
    placeholders = ", ".join("?" for _ in keys)
    rows = connection.execute(
        f"SELECT p.key, COALESCE(s.next_sequence, 1) "
        f"FROM projects p LEFT JOIN project_sequences s "
        f"ON p.project_id = s.project_id WHERE p.key IN ({placeholders})",
        keys,
    ).fetchall()
    return {str(key): int(sequence) for key, sequence in rows}


def _bump_sequences(
    connection: Any,
    plan: CsvImportPlan,
    items: tuple[CsvWorkItem, ...],
    project_ids: dict[str, str],
) -> None:
    """Incrementally bump ``project_sequences`` for the projects in the file.

    ``next_sequence = max(current, max_used_suffix) + 1`` per project
    (INSERT-or-UPDATE). Deliberately diverges from portability's
    wipe-and-reseed: ``--allow-populated`` must not disturb projects
    that are not in the file.
    """

    max_suffix_by_project: dict[str, int] = {}
    for item in items:
        suffix = item.key_suffix
        current = max_suffix_by_project.get(item.project_key, 0)
        if suffix > current:
            max_suffix_by_project[item.project_key] = suffix
    for project in plan.projects:
        project_id = project_ids[project.key]
        max_used = max_suffix_by_project.get(project.key, 0)
        existing = connection.execute(
            "SELECT next_sequence FROM project_sequences WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if existing is None:
            connection.execute(
                "INSERT INTO project_sequences(project_id, next_sequence) "
                "VALUES (?, ?)",
                (project_id, max_used + 1),
            )
        else:
            next_sequence = max(int(existing[0]), max_used) + 1
            connection.execute(
                "UPDATE project_sequences SET next_sequence = ? WHERE project_id = ?",
                (next_sequence, project_id),
            )
