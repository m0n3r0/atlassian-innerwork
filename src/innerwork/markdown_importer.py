"""Markdown-tree importer: read a directory of ``.md`` files into spaces/pages.

This module implements the locked mapping rules from
``docs/roadmap_markdown_importer_scoping.md`` §2–§4:

* each **immediate subdirectory** of the root is one space;
* every ``*.md`` file anywhere below a space directory is one page
  (nested paths flatten into the page title — the model has no
  parent-page field);
* an optional YAML frontmatter block may set ``title`` / ``author`` /
  ``created_at`` (parsed with ``pyyaml``, a declared dependency);
* the importer writes **directly through** :class:`DomainStore` — it
  never produces a portability envelope, never creates projects / work
  items / links / comments, and never overlays a non-empty knowledge
  graph (fresh-target requirement).

``scan_markdown_tree`` is the pure validation pass (filesystem reads
only, no database access). ``import_markdown_tree`` writes the scanned
tree into a store through ``create_space`` / ``create_page``. All
user-facing failures raise :class:`MarkdownImportError`, which the CLI
maps to exit code 2.

No network access anywhere in this module; the only imports beyond the
standard library are ``yaml`` and the local ``DomainStore``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .domain_store import DomainStore, utc_now_iso
from .knowledge import validate_space_key

__all__ = (
    "MarkdownImportError",
    "MarkdownPage",
    "MarkdownSpace",
    "MarkdownTree",
    "import_markdown_tree",
    "scan_markdown_tree",
)

#: Mirrors ``knowledge._PAGE_BODY_MAX`` — kept local so the importer
#: surfaces model-limit violations as :class:`MarkdownImportError`
#: (exit 2) instead of a raw ``ValueError`` from ``create_page``.
_PAGE_BODY_MAX = 200_000
#: Mirrors ``knowledge._NON_EMPTY_TEXT_MAX`` (title cap).
_TITLE_MAX = 200

#: Frontmatter keys the importer understands. Anything else is ignored
#: and recorded as a per-file warning (the model has nowhere to store it).
_RECOGNIZED_KEYS = frozenset({"title", "author", "created_at"})

_ASCII_UPPER_DIGITS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


class MarkdownImportError(ValueError):
    """Raised for any user-facing markdown-import failure (CLI exit 2)."""


@dataclass(frozen=True)
class MarkdownPage:
    """One imported page: resolved title/body/author plus provenance."""

    space_key: str
    title: str
    body: str
    author: str
    relative_path: str


@dataclass(frozen=True)
class MarkdownSpace:
    """One imported space: derived key, verbatim directory name, pages."""

    key: str
    name: str
    pages: tuple[MarkdownPage, ...] = ()


@dataclass(frozen=True)
class MarkdownTree:
    """Result of a scan: validated spaces and sorted per-file warnings."""

    spaces: tuple[MarkdownSpace, ...] = ()
    warnings: tuple[str, ...] = ()


# ------------------------------------------------------------------ scanning


def scan_markdown_tree(
    root: Path | str,
    *,
    author: str,
    created_at: str | None = None,
) -> MarkdownTree:
    """Walk ``root`` and return the validated space/page tree.

    Deterministic: all directory iteration is sorted, pages within a
    space are ordered by relative path, warnings are sorted. Raises
    :class:`MarkdownImportError` for any structural problem so a broken
    tree never reaches the store.
    """

    root_path = Path(root)
    if not root_path.is_dir():
        raise MarkdownImportError(f"not a directory: {root_path}")
    default_author = (author or "").strip()
    if not default_author:
        raise MarkdownImportError("author must be a non-blank string")
    if created_at is not None and not created_at.strip():
        raise MarkdownImportError("created_at must be a non-blank string")

    _reject_root_level_markdown(root_path)

    warnings: list[str] = []
    spaces: list[MarkdownSpace] = []
    seen_keys: dict[str, Path] = {}
    for dir_path in sorted(
        (p for p in root_path.iterdir() if p.is_dir() and not p.is_symlink()),
        key=lambda p: p.name,
    ):
        key = _space_key_from_dirname(dir_path.name)
        collision = seen_keys.get(key)
        if collision is not None:
            raise MarkdownImportError(
                "space key collision: "
                f"{dir_path.name!r} and {collision.name!r} both map to key {key!r}"
            )
        seen_keys[key] = dir_path
        pages = _scan_pages(dir_path, key, author=default_author, warnings=warnings)
        spaces.append(MarkdownSpace(key=key, name=dir_path.name, pages=tuple(pages)))
    return MarkdownTree(spaces=tuple(spaces), warnings=tuple(sorted(warnings)))


def _reject_root_level_markdown(root_path: Path) -> None:
    offenders = sorted(
        p.name
        for p in root_path.iterdir()
        if p.is_file() and not p.is_symlink() and p.suffix.lower() == ".md"
    )
    if offenders:
        raise MarkdownImportError(
            "root-level markdown file(s) have no space to belong to: "
            + ", ".join(offenders)
        )


def _scan_pages(
    space_dir: Path,
    space_key: str,
    *,
    author: str,
    warnings: list[str],
) -> list[MarkdownPage]:
    pages: list[MarkdownPage] = []
    for path in _collect_markdown_files(space_dir):
        # Root-relative path so warnings and errors name the file
        # unambiguously across spaces (e.g. ``eng/runbook.md``).
        relative_path = f"{space_dir.name}/{path.relative_to(space_dir).as_posix()}"
        frontmatter, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
        body = body.strip()
        if len(body) > _PAGE_BODY_MAX:
            raise MarkdownImportError(
                f"{relative_path}: body exceeds {_PAGE_BODY_MAX} characters"
            )
        if frontmatter:
            unknown = sorted(set(frontmatter) - _RECOGNIZED_KEYS)
            if unknown:
                warnings.append(
                    f"{relative_path}: unknown frontmatter key(s): {', '.join(unknown)}"
                )
        stem_title = path.relative_to(space_dir).with_suffix("").as_posix()
        title, page_author, _ = _resolve_frontmatter_fields(
            frontmatter,
            stem_title=stem_title,
            default_author=author,
            relative_path=relative_path,
        )
        pages.append(
            MarkdownPage(
                space_key=space_key,
                title=title,
                body=body,
                author=page_author,
                relative_path=relative_path,
            )
        )
    pages.sort(key=lambda p: p.relative_path)
    return pages


def _collect_markdown_files(space_dir: Path) -> list[Path]:
    """All ``*.md`` files below ``space_dir``, sorted, symlinks skipped."""

    found: list[Path] = []

    def _walk(current: Path) -> None:
        for entry in sorted(current.iterdir(), key=lambda p: p.name):
            if entry.is_symlink():
                continue
            if entry.is_dir():
                _walk(entry)
            elif entry.suffix.lower() == ".md":
                found.append(entry)

    _walk(space_dir)
    return found


def _resolve_frontmatter_fields(
    frontmatter: dict[str, Any] | None,
    *,
    stem_title: str,
    default_author: str,
    relative_path: str,
) -> tuple[str, str, str]:
    """Resolve (title, author, created_at) from frontmatter + defaults.

    ``title`` / ``author`` from frontmatter win over the stem / default
    author. ``created_at`` is recognized and validated for
    well-formedness but the page timestamp is the import-wide
    ``created_at`` (per scoping §2.8) — it is not applied per file.
    Malformed recognized keys raise :class:`MarkdownImportError` naming
    the file.
    """

    title = stem_title
    page_author = default_author
    created_at = ""
    if frontmatter is None:
        return title, page_author, created_at
    if "title" in frontmatter:
        raw_title = frontmatter["title"]
        if not isinstance(raw_title, str):
            raise MarkdownImportError(
                f"{relative_path}: frontmatter title must be a string"
            )
        title = raw_title.strip()
        if not title:
            raise MarkdownImportError(
                f"{relative_path}: frontmatter title must not be blank"
            )
        if len(title) > _TITLE_MAX:
            raise MarkdownImportError(
                f"{relative_path}: frontmatter title exceeds {_TITLE_MAX} characters"
            )
    if "author" in frontmatter:
        raw_author = frontmatter["author"]
        if not isinstance(raw_author, str):
            raise MarkdownImportError(
                f"{relative_path}: frontmatter author must be a string"
            )
        page_author = raw_author.strip()
        if not page_author:
            raise MarkdownImportError(
                f"{relative_path}: frontmatter author must not be blank"
            )
    if "created_at" in frontmatter:
        _validate_iso_timestamp(frontmatter["created_at"], relative_path=relative_path)
    return title, page_author, created_at


def _validate_iso_timestamp(value: Any, *, relative_path: str) -> None:
    if not isinstance(value, str):
        raise MarkdownImportError(
            f"{relative_path}: frontmatter created_at must be an ISO-8601 string"
        )
    # ``datetime.fromisoformat`` before 3.11 rejects a trailing "Z";
    # normalize it so valid ISO-8601 timestamps parse on Python 3.10.
    candidate = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise MarkdownImportError(
            f"{relative_path}: frontmatter created_at is not a valid "
            f"ISO-8601 timestamp: {value!r}"
        ) from exc


def _space_key_from_dirname(name: str) -> str:
    """Derive a space key per scoping §2.3: uppercase, drop non [A-Z0-9].

    The sanitized form must still match ``^[A-Z][A-Z0-9]{1,9}$`` — no
    silent truncation (truncation risks silent key collisions). Invalid
    results raise :class:`MarkdownImportError` telling the operator to
    rename the directory.
    """

    sanitized = "".join(ch for ch in name.upper() if ch in _ASCII_UPPER_DIGITS)
    try:
        validate_space_key(sanitized)
    except ValueError as exc:
        raise MarkdownImportError(
            f"directory {name!r} does not map to a valid space key "
            f"(sanitized: {sanitized!r}); rename it so the sanitized uppercase "
            "form is 2-10 characters starting with a letter"
        ) from exc
    return sanitized


def _parse_frontmatter(text: str) -> tuple[dict[str, Any] | None, str]:
    """Split an optional YAML frontmatter block from markdown body text.

    Recognized only when the file's first line is exactly ``---``; the
    block ends at the next line that is exactly ``---``. Returns
    ``(None, text)`` when there is no frontmatter. Raises
    :class:`MarkdownImportError` for an unclosed block or YAML that
    fails ``safe_load``.
    """

    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return None, text
    close_index: int | None = None
    for index in range(1, len(lines)):
        if lines[index] == "---":
            close_index = index
            break
    if close_index is None:
        raise MarkdownImportError(
            "frontmatter block is never closed (missing closing ---)"
        )
    block = "\n".join(lines[1:close_index])
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError as exc:
        raise MarkdownImportError(
            f"invalid YAML in frontmatter block: {exc}"
        ) from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise MarkdownImportError("frontmatter block must be a YAML mapping")
    body = "\n".join(lines[close_index + 1 :])
    return data, body


# ------------------------------------------------------------------ importing


def import_markdown_tree(
    store: DomainStore,
    root: Path | str,
    *,
    author: str = "importer",
    created_at: str | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """Scan ``root`` and write spaces/pages through ``store``.

    Returns ``{"spaces": int, "pages": int, "warnings": [...], "dry_run": bool}``.
    In dry-run mode nothing is written, but the fresh-target check still
    runs so the summary is an honest preview of a real import.
    """

    tree = scan_markdown_tree(root, author=author, created_at=created_at)
    _validate_fresh_target(store)
    if not dry_run:
        owner = (author or "").strip()
        _write_tree(store, tree, owner=owner, created_at=created_at)
    return {
        "spaces": len(tree.spaces),
        "pages": sum(len(space.pages) for space in tree.spaces),
        "warnings": list(tree.warnings),
        "dry_run": dry_run,
    }


def _write_tree(
    store: DomainStore,
    tree: MarkdownTree,
    *,
    owner: str,
    created_at: str | None,
) -> None:
    """Write scanned spaces/pages; every page becomes version 1."""

    timestamp = created_at or utc_now_iso()
    for space in tree.spaces:
        space_id = str(uuid.uuid4())
        store.create_space(
            space_id=space_id,
            key=space.key,
            name=space.name,
            owner=owner,
            created_at=timestamp,
        )
        for page in space.pages:
            try:
                store.create_page(
                    page_id=str(uuid.uuid4()),
                    space_id=space_id,
                    title=page.title,
                    body=page.body,
                    author=page.author,
                    created_at=timestamp,
                )
            except ValueError as exc:  # defensive: scan validates limits already
                raise MarkdownImportError(f"{page.relative_path}: {exc}") from exc


def _validate_fresh_target(store: DomainStore) -> None:
    """Refuse to run when any knowledge table already has rows.

    Mirrors ``portability``'s fresh-target posture: the importer never
    overlays an existing knowledge graph. Only the three knowledge
    tables gate; projects / work items / links / comments may exist and
    are untouched.
    """

    with store._connect() as connection:  # noqa: SLF001 — peer of DomainStore
        for table in ("spaces", "pages", "page_versions"):
            (count,) = connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()
            if int(count) > 0:
                raise MarkdownImportError(
                    f"target store is not empty: {table} has {count} row(s)"
                )
