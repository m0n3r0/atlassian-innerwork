"""SQLite-backed store for the Innerwork work-graph domain.

This store sits next to ``SqliteStateStore`` (which persists edge-broker
intent) and uses its own tables in the same database file. Tables are
created on first use; existing edge-broker tables are not touched.

Concurrency model is single-process, like the broker store. Each call
opens and closes a connection.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path

from .comments import (
    PageComment,
    WorkItemComment,
    validate_author,
    validate_comment_body,
)
from .domain import (
    INITIAL_STATE,
    WORKFLOW_STATES,
    InvalidTransitionError,
    Project,
    Transition,
    WorkItem,
    assert_transition_allowed,
    validate_project_key,
)
from .knowledge import (
    Link,
    Page,
    PageVersion,
    Space,
    validate_link_kind,
    validate_space_key,
)
from .permissions import (
    DEFAULT_VISIBILITY,
    Visibility,
    normalize_members,
    validate_visibility,
)

DOMAIN_SCHEMA_VERSION = 4


def utc_now_iso() -> str:
    """Return a timezone-aware UTC ISO-8601 string with second precision."""

    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ProjectNotFoundError(KeyError):
    """Raised when a project lookup fails."""


class WorkItemNotFoundError(KeyError):
    """Raised when a work-item lookup fails."""


class DuplicateProjectKeyError(ValueError):
    """Raised when a project key is reused."""


class SpaceNotFoundError(KeyError):
    """Raised when a space lookup fails."""


class PageNotFoundError(KeyError):
    """Raised when a page lookup fails."""


class LinkNotFoundError(KeyError):
    """Raised when a link lookup fails."""


class DuplicateSpaceKeyError(ValueError):
    """Raised when a space key is reused."""


class DuplicateLinkError(ValueError):
    """Raised when the same (work_item, page, kind) link already exists."""


class CommentNotFoundError(KeyError):
    """Raised when a comment lookup fails."""


class DomainStore:
    """Persistence layer for projects, work items, and transitions."""

    def __init__(
        self,
        path: Path | str,
        *,
        on_change: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._on_change = on_change
        self._initialize()

    # ------------------------------------------------------------------ change hook
    def set_change_hook(
        self, hook: Callable[[str, str, str], None] | None
    ) -> None:
        """Install or clear a change-notification callback.

        The hook is invoked as ``hook(entity, action, identifier)``.

        Current wired emissions (Phase 6):

        * ``("project", "created", project_id)`` — after ``create_project``.
        * ``("space",   "created", space_id)``   — after ``create_space``.

        Mutation paths for ``work_item``, ``page``, ``page_version``,
        ``transition``, ``comment``, and ``link`` do NOT currently emit;
        :mod:`innerwork.search` and :mod:`innerwork.analytics` query the
        store directly on each request rather than maintaining an
        invalidation-driven cache, so no subscribers exist today. The
        hook is retained as a forward-compatible extension point.

        Exceptions raised by the hook are swallowed to keep writes safe.
        """

        self._on_change = hook

    def _emit_change(self, entity: str, action: str, identifier: str) -> None:
        if self._on_change is None:
            return
        try:
            self._on_change(entity, action, identifier)
        except Exception:  # pragma: no cover - defensive isolation
            pass

    @staticmethod
    def _encode_members(members: Iterable[str] | None) -> str:
        return json.dumps(list(normalize_members(members)))

    @staticmethod
    def _decode_members(raw: str | None) -> tuple[str, ...]:
        if not raw:
            return ()
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError):
            return ()
        if not isinstance(decoded, list):
            return ()
        return tuple(str(m) for m in decoded if isinstance(m, str))

    # ------------------------------------------------------------------ projects
    def create_project(
        self,
        *,
        project_id: str,
        key: str,
        name: str,
        owner: str,
        created_at: str | None = None,
        visibility: str = DEFAULT_VISIBILITY,
        members: Iterable[str] = (),
    ) -> Project:
        validate_project_key(key)
        tag: Visibility = validate_visibility(visibility)
        member_tuple = normalize_members(members)
        timestamp = created_at or utc_now_iso()
        project = Project(
            project_id=project_id,
            key=key,
            name=name,
            owner=owner,
            created_at=timestamp,
            visibility=tag,
            members=member_tuple,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO projects(
                        project_id, key, name, owner, created_at,
                        visibility, members
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project.project_id,
                        project.key,
                        project.name,
                        project.owner,
                        project.created_at,
                        project.visibility,
                        self._encode_members(project.members),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if "projects.key" in str(exc) or "UNIQUE" in str(exc).upper():
                raise DuplicateProjectKeyError(f"project key already exists: {key!r}") from exc
            raise
        self._emit_change("project", "created", project.project_id)
        return project

    def _row_to_project(self, row: tuple) -> Project:
        return Project(
            project_id=row[0],
            key=row[1],
            name=row[2],
            owner=row[3],
            created_at=row[4],
            visibility=row[5] if len(row) > 5 and row[5] else DEFAULT_VISIBILITY,
            members=self._decode_members(row[6] if len(row) > 6 else None),
        )

    def get_project(self, project_id: str) -> Project:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT project_id, key, name, owner, created_at, visibility, members "
                "FROM projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            raise ProjectNotFoundError(project_id)
        return self._row_to_project(row)

    def get_project_by_key(self, key: str) -> Project:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT project_id, key, name, owner, created_at, visibility, members "
                "FROM projects WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            raise ProjectNotFoundError(key)
        return self._row_to_project(row)

    def list_projects(self) -> tuple[Project, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT project_id, key, name, owner, created_at, visibility, members "
                "FROM projects ORDER BY key"
            ).fetchall()
        return tuple(self._row_to_project(row) for row in rows)

    # ----------------------------------------------------------------- work items
    def create_work_item(
        self,
        *,
        work_item_id: str,
        project_id: str,
        title: str,
        description: str = "",
        assignee: str = "",
        created_at: str | None = None,
    ) -> WorkItem:
        project = self.get_project(project_id)  # raises ProjectNotFoundError
        timestamp = created_at or utc_now_iso()
        with self._connect() as connection:
            # Allocate the next project-scoped numeric suffix atomically.
            cursor = connection.execute(
                "SELECT next_sequence FROM project_sequences WHERE project_id = ?",
                (project_id,),
            )
            row = cursor.fetchone()
            if row is None:
                next_seq = 1
                connection.execute(
                    "INSERT INTO project_sequences(project_id, next_sequence) VALUES (?, ?)",
                    (project_id, next_seq + 1),
                )
            else:
                next_seq = int(row[0])
                connection.execute(
                    "UPDATE project_sequences SET next_sequence = ? WHERE project_id = ?",
                    (next_seq + 1, project_id),
                )
            key = f"{project.key}-{next_seq}"
            item = WorkItem(
                work_item_id=work_item_id,
                project_id=project_id,
                key=key,
                title=title.strip(),
                description=description or "",
                state=INITIAL_STATE,
                assignee=assignee or "",
                created_at=timestamp,
                updated_at=timestamp,
            )
            connection.execute(
                """
                INSERT INTO work_items(
                    work_item_id, project_id, key, title, description,
                    state, assignee, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.work_item_id,
                    item.project_id,
                    item.key,
                    item.title,
                    item.description,
                    item.state,
                    item.assignee,
                    item.created_at,
                    item.updated_at,
                ),
            )
        return item

    def get_work_item(self, work_item_id: str) -> WorkItem:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT work_item_id, project_id, key, title, description,
                       state, assignee, created_at, updated_at
                FROM work_items WHERE work_item_id = ?
                """,
                (work_item_id,),
            ).fetchone()
        if row is None:
            raise WorkItemNotFoundError(work_item_id)
        return WorkItem(*row)

    def list_work_items(
        self,
        *,
        project_id: str | None = None,
        state: str | None = None,
    ) -> tuple[WorkItem, ...]:
        if state is not None and state not in WORKFLOW_STATES:
            raise ValueError(f"unknown state filter: {state!r}")
        clauses: list[str] = []
        params: list[object] = []
        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        if state is not None:
            clauses.append("state = ?")
            params.append(state)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        query = (
            "SELECT work_item_id, project_id, key, title, description, "
            "state, assignee, created_at, updated_at FROM work_items"
            + where
            + " ORDER BY project_id, CAST(SUBSTR(key, INSTR(key,'-')+1) AS INTEGER)"
        )
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return tuple(WorkItem(*row) for row in rows)

    # ----------------------------------------------------------------- transitions
    def transition_work_item(
        self,
        *,
        work_item_id: str,
        to_state: str,
        actor: str,
        reason: str = "",
        occurred_at: str | None = None,
    ) -> tuple[WorkItem, Transition]:
        item = self.get_work_item(work_item_id)
        assert_transition_allowed(item.state, to_state)
        timestamp = occurred_at or utc_now_iso()
        actor_clean = (actor or "").strip()
        if not actor_clean:
            raise ValueError("actor must be a non-blank string")
        reason_clean = (reason or "").strip()
        new_item = item.with_state(new_state=to_state, updated_at=timestamp)
        with self._connect() as connection:
            connection.execute(
                "UPDATE work_items SET state = ?, updated_at = ? WHERE work_item_id = ?",
                (new_item.state, new_item.updated_at, new_item.work_item_id),
            )
            cursor = connection.execute(
                """
                INSERT INTO work_item_transitions(
                    work_item_id, from_state, to_state, actor, occurred_at, reason
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item.work_item_id,
                    item.state,
                    to_state,
                    actor_clean,
                    timestamp,
                    reason_clean,
                ),
            )
            transition_id = int(cursor.lastrowid or 0)
        transition = Transition(
            transition_id=transition_id,
            work_item_id=item.work_item_id,
            from_state=item.state,
            to_state=to_state,
            actor=actor_clean,
            occurred_at=timestamp,
            reason=reason_clean,
        )
        return new_item, transition

    def list_transitions(self, work_item_id: str) -> tuple[Transition, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT transition_id, work_item_id, from_state, to_state,
                       actor, occurred_at, reason
                FROM work_item_transitions
                WHERE work_item_id = ?
                ORDER BY transition_id
                """,
                (work_item_id,),
            ).fetchall()
        return tuple(
            Transition(
                transition_id=row[0],
                work_item_id=row[1],
                from_state=row[2],
                to_state=row[3],
                actor=row[4],
                occurred_at=row[5],
                reason=row[6],
            )
            for row in rows
        )

    # ------------------------------------------------------------------ spaces
    def create_space(
        self,
        *,
        space_id: str,
        key: str,
        name: str,
        owner: str,
        created_at: str | None = None,
        visibility: str = DEFAULT_VISIBILITY,
        members: Iterable[str] = (),
    ) -> Space:
        validate_space_key(key)
        tag: Visibility = validate_visibility(visibility)
        member_tuple = normalize_members(members)
        timestamp = created_at or utc_now_iso()
        space = Space(
            space_id=space_id,
            key=key,
            name=name,
            owner=owner,
            created_at=timestamp,
            visibility=tag,
            members=member_tuple,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO spaces(
                        space_id, key, name, owner, created_at, visibility, members
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        space.space_id,
                        space.key,
                        space.name,
                        space.owner,
                        space.created_at,
                        space.visibility,
                        self._encode_members(space.members),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if "spaces.key" in str(exc) or "UNIQUE" in str(exc).upper():
                raise DuplicateSpaceKeyError(f"space key already exists: {key!r}") from exc
            raise
        self._emit_change("space", "created", space.space_id)
        return space

    def _row_to_space(self, row: tuple) -> Space:
        return Space(
            space_id=row[0],
            key=row[1],
            name=row[2],
            owner=row[3],
            created_at=row[4],
            visibility=row[5] if len(row) > 5 and row[5] else DEFAULT_VISIBILITY,
            members=self._decode_members(row[6] if len(row) > 6 else None),
        )

    def get_space(self, space_id: str) -> Space:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT space_id, key, name, owner, created_at, visibility, members "
                "FROM spaces WHERE space_id = ?",
                (space_id,),
            ).fetchone()
        if row is None:
            raise SpaceNotFoundError(space_id)
        return self._row_to_space(row)

    def list_spaces(self) -> tuple[Space, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT space_id, key, name, owner, created_at, visibility, members "
                "FROM spaces ORDER BY key"
            ).fetchall()
        return tuple(self._row_to_space(row) for row in rows)

    # ------------------------------------------------------------------- pages
    def create_page(
        self,
        *,
        page_id: str,
        space_id: str,
        title: str,
        body: str,
        author: str,
        created_at: str | None = None,
    ) -> tuple[Page, PageVersion]:
        self.get_space(space_id)  # raises SpaceNotFoundError
        timestamp = created_at or utc_now_iso()
        author_clean = (author or "").strip()
        if not author_clean:
            raise ValueError("author must be a non-blank string")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pages(
                    page_id, space_id, current_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (page_id, space_id, 1, timestamp, timestamp),
            )
            cursor = connection.execute(
                """
                INSERT INTO page_versions(
                    page_id, version_number, title, body, author, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (page_id, 1, title.strip(), body, author_clean, timestamp),
            )
            version_id = int(cursor.lastrowid or 0)
        page = Page(
            page_id=page_id,
            space_id=space_id,
            current_version=1,
            created_at=timestamp,
            updated_at=timestamp,
        )
        version = PageVersion(
            version_id=version_id,
            page_id=page_id,
            version_number=1,
            title=title.strip(),
            body=body,
            author=author_clean,
            created_at=timestamp,
        )
        return page, version

    def update_page(
        self,
        *,
        page_id: str,
        title: str,
        body: str,
        author: str,
        created_at: str | None = None,
    ) -> tuple[Page, PageVersion]:
        page = self.get_page(page_id)
        timestamp = created_at or utc_now_iso()
        author_clean = (author or "").strip()
        if not author_clean:
            raise ValueError("author must be a non-blank string")
        new_version_number = page.current_version + 1
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO page_versions(
                    page_id, version_number, title, body, author, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    page_id,
                    new_version_number,
                    title.strip(),
                    body,
                    author_clean,
                    timestamp,
                ),
            )
            version_id = int(cursor.lastrowid or 0)
            connection.execute(
                "UPDATE pages SET current_version = ?, updated_at = ? WHERE page_id = ?",
                (new_version_number, timestamp, page_id),
            )
        new_page = Page(
            page_id=page.page_id,
            space_id=page.space_id,
            current_version=new_version_number,
            created_at=page.created_at,
            updated_at=timestamp,
        )
        version = PageVersion(
            version_id=version_id,
            page_id=page_id,
            version_number=new_version_number,
            title=title.strip(),
            body=body,
            author=author_clean,
            created_at=timestamp,
        )
        return new_page, version

    def get_page(self, page_id: str) -> Page:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT page_id, space_id, current_version, created_at, updated_at "
                "FROM pages WHERE page_id = ?",
                (page_id,),
            ).fetchone()
        if row is None:
            raise PageNotFoundError(page_id)
        return Page(*row)

    def list_pages(self, *, space_id: str | None = None) -> tuple[Page, ...]:
        clauses: list[str] = []
        params: list[object] = []
        if space_id is not None:
            clauses.append("space_id = ?")
            params.append(space_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT page_id, space_id, current_version, created_at, updated_at "
                "FROM pages" + where + " ORDER BY created_at, page_id",
                tuple(params),
            ).fetchall()
        return tuple(Page(*row) for row in rows)

    def get_page_version(self, page_id: str, version_number: int) -> PageVersion:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT version_id, page_id, version_number, title, body, author, created_at
                FROM page_versions
                WHERE page_id = ? AND version_number = ?
                """,
                (page_id, version_number),
            ).fetchone()
        if row is None:
            raise PageNotFoundError(f"{page_id}@v{version_number}")
        return PageVersion(*row)

    def list_page_versions(self, page_id: str) -> tuple[PageVersion, ...]:
        self.get_page(page_id)  # raises PageNotFoundError
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT version_id, page_id, version_number, title, body, author, created_at
                FROM page_versions
                WHERE page_id = ?
                ORDER BY version_number
                """,
                (page_id,),
            ).fetchall()
        return tuple(PageVersion(*row) for row in rows)

    # ------------------------------------------------------------------- links
    def create_link(
        self,
        *,
        link_id: str,
        work_item_id: str,
        page_id: str,
        kind: str,
        created_by: str,
        created_at: str | None = None,
    ) -> Link:
        cleaned_kind = validate_link_kind(kind)
        # Integrity: both endpoints must exist.
        self.get_work_item(work_item_id)
        self.get_page(page_id)
        timestamp = created_at or utc_now_iso()
        created_by_clean = (created_by or "").strip()
        if not created_by_clean:
            raise ValueError("created_by must be a non-blank string")
        link = Link(
            link_id=link_id,
            work_item_id=work_item_id,
            page_id=page_id,
            kind=cleaned_kind,
            created_by=created_by_clean,
            created_at=timestamp,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO work_item_page_links(
                        link_id, work_item_id, page_id, kind, created_by, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        link.link_id,
                        link.work_item_id,
                        link.page_id,
                        link.kind,
                        link.created_by,
                        link.created_at,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            msg = str(exc)
            if "ux_work_item_page_links_triple" in msg or "UNIQUE" in msg.upper():
                raise DuplicateLinkError(
                    "link already exists for "
                    f"(work_item_id={work_item_id!r}, page_id={page_id!r}, kind={cleaned_kind!r})"
                ) from exc
            raise
        return link

    def delete_link(self, link_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM work_item_page_links WHERE link_id = ?",
                (link_id,),
            )
            if cursor.rowcount == 0:
                raise LinkNotFoundError(link_id)

    def get_link(self, link_id: str) -> Link:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT link_id, work_item_id, page_id, kind, created_by, created_at
                FROM work_item_page_links WHERE link_id = ?
                """,
                (link_id,),
            ).fetchone()
        if row is None:
            raise LinkNotFoundError(link_id)
        return Link(*row)

    def list_links_for_work_item(self, work_item_id: str) -> tuple[Link, ...]:
        self.get_work_item(work_item_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT link_id, work_item_id, page_id, kind, created_by, created_at
                FROM work_item_page_links
                WHERE work_item_id = ?
                ORDER BY created_at, link_id
                """,
                (work_item_id,),
            ).fetchall()
        return tuple(Link(*row) for row in rows)

    def list_links_for_page(self, page_id: str) -> tuple[Link, ...]:
        self.get_page(page_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT link_id, work_item_id, page_id, kind, created_by, created_at
                FROM work_item_page_links
                WHERE page_id = ?
                ORDER BY created_at, link_id
                """,
                (page_id,),
            ).fetchall()
        return tuple(Link(*row) for row in rows)

    # --------------------------------------------------------------- comments
    def create_work_item_comment(
        self,
        *,
        comment_id: str,
        work_item_id: str,
        author: str,
        body: str,
        created_at: str | None = None,
    ) -> WorkItemComment:
        self.get_work_item(work_item_id)  # raises WorkItemNotFoundError
        author_clean = validate_author(author)
        body_clean = validate_comment_body(body)
        timestamp = created_at or utc_now_iso()
        comment = WorkItemComment(
            comment_id=comment_id,
            work_item_id=work_item_id,
            author=author_clean,
            body=body_clean,
            created_at=timestamp,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO work_item_comments(
                    comment_id, work_item_id, author, body, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    comment.comment_id,
                    comment.work_item_id,
                    comment.author,
                    comment.body,
                    comment.created_at,
                ),
            )
        return comment

    def get_work_item_comment(self, comment_id: str) -> WorkItemComment:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT comment_id, work_item_id, author, body, created_at "
                "FROM work_item_comments WHERE comment_id = ?",
                (comment_id,),
            ).fetchone()
        if row is None:
            raise CommentNotFoundError(comment_id)
        return WorkItemComment(*row)

    def list_work_item_comments(self, work_item_id: str) -> tuple[WorkItemComment, ...]:
        self.get_work_item(work_item_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT comment_id, work_item_id, author, body, created_at
                FROM work_item_comments
                WHERE work_item_id = ?
                ORDER BY created_at, comment_id
                """,
                (work_item_id,),
            ).fetchall()
        return tuple(WorkItemComment(*row) for row in rows)

    def create_page_comment(
        self,
        *,
        comment_id: str,
        page_id: str,
        author: str,
        body: str,
        created_at: str | None = None,
    ) -> PageComment:
        self.get_page(page_id)  # raises PageNotFoundError
        author_clean = validate_author(author)
        body_clean = validate_comment_body(body)
        timestamp = created_at or utc_now_iso()
        comment = PageComment(
            comment_id=comment_id,
            page_id=page_id,
            author=author_clean,
            body=body_clean,
            created_at=timestamp,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO page_comments(
                    comment_id, page_id, author, body, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    comment.comment_id,
                    comment.page_id,
                    comment.author,
                    comment.body,
                    comment.created_at,
                ),
            )
        return comment

    def get_page_comment(self, comment_id: str) -> PageComment:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT comment_id, page_id, author, body, created_at "
                "FROM page_comments WHERE comment_id = ?",
                (comment_id,),
            ).fetchone()
        if row is None:
            raise CommentNotFoundError(comment_id)
        return PageComment(*row)

    def list_page_comments(self, page_id: str) -> tuple[PageComment, ...]:
        self.get_page(page_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT comment_id, page_id, author, body, created_at
                FROM page_comments
                WHERE page_id = ?
                ORDER BY created_at, comment_id
                """,
                (page_id,),
            ).fetchall()
        return tuple(PageComment(*row) for row in rows)

    # --------------------------------------------------------- idempotency keys
    def get_idempotent_response(self, *, scope: str, key: str, request_hash: str) -> str | None:
        """Return a stored response body if ``(scope, key)`` was replayed.

        Returns ``None`` when no record exists. Raises :class:`ValueError`
        when the same ``(scope, key)`` was used with a different request
        body; the API layer translates that to HTTP 409.
        """

        with self._connect() as connection:
            row = connection.execute(
                "SELECT request_hash, response_body FROM v1_idempotency_keys "
                "WHERE scope = ? AND key = ?",
                (scope, key),
            ).fetchone()
        if row is None:
            return None
        stored_hash, response_body = row[0], row[1]
        if stored_hash != request_hash:
            raise ValueError(
                f"idempotency key already used with a different request body in scope {scope!r}"
            )
        return response_body

    def save_idempotent_response(
        self,
        *,
        scope: str,
        key: str,
        request_hash: str,
        response_body: str,
        created_at: str | None = None,
    ) -> None:
        timestamp = created_at or utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO v1_idempotency_keys(
                    scope, key, request_hash, response_body, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (scope, key, request_hash, response_body, timestamp),
            )

    # ------------------------------------------------------------------ internals
    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    key TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    visibility TEXT NOT NULL DEFAULT 'internal',
                    members TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS project_sequences (
                    project_id TEXT PRIMARY KEY,
                    next_sequence INTEGER NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS work_items (
                    work_item_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    key TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL CHECK (state IN ('todo','in_progress','done')),
                    assignee TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS work_item_transitions (
                    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    work_item_id TEXT NOT NULL,
                    from_state TEXT NOT NULL,
                    to_state TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(work_item_id) REFERENCES work_items(work_item_id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_work_items_project ON work_items(project_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_work_items_state ON work_items(state)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS spaces (
                    space_id TEXT PRIMARY KEY,
                    key TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    visibility TEXT NOT NULL DEFAULT 'internal',
                    members TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pages (
                    page_id TEXT PRIMARY KEY,
                    space_id TEXT NOT NULL,
                    current_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(space_id) REFERENCES spaces(space_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS page_versions (
                    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    page_id TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    author TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(page_id, version_number),
                    FOREIGN KEY(page_id) REFERENCES pages(page_id)
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS ix_pages_space ON pages(space_id)")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS work_item_page_links (
                    link_id TEXT PRIMARY KEY,
                    work_item_id TEXT NOT NULL,
                    page_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(work_item_id) REFERENCES work_items(work_item_id),
                    FOREIGN KEY(page_id) REFERENCES pages(page_id)
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ux_work_item_page_links_triple
                ON work_item_page_links(work_item_id, page_id, kind)
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_links_work_item "
                "ON work_item_page_links(work_item_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_links_page ON work_item_page_links(page_id)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS work_item_comments (
                    comment_id TEXT PRIMARY KEY,
                    work_item_id TEXT NOT NULL,
                    author TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(work_item_id) REFERENCES work_items(work_item_id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_work_item_comments_work_item "
                "ON work_item_comments(work_item_id)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS page_comments (
                    comment_id TEXT PRIMARY KEY,
                    page_id TEXT NOT NULL,
                    author TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(page_id) REFERENCES pages(page_id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_page_comments_page ON page_comments(page_id)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS v1_idempotency_keys (
                    scope TEXT NOT NULL,
                    key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    response_body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(scope, key)
                )
                """
            )
            # Phase 6 additive migrations: backfill visibility/members on
            # databases created under schema v3. SQLite has no
            # ``IF NOT EXISTS`` on ``ADD COLUMN``, so probe ``PRAGMA``.
            self._ensure_column(
                connection,
                table="projects",
                column="visibility",
                ddl="TEXT NOT NULL DEFAULT 'internal'",
            )
            self._ensure_column(
                connection,
                table="projects",
                column="members",
                ddl="TEXT NOT NULL DEFAULT '[]'",
            )
            self._ensure_column(
                connection,
                table="spaces",
                column="visibility",
                ddl="TEXT NOT NULL DEFAULT 'internal'",
            )
            self._ensure_column(
                connection,
                table="spaces",
                column="members",
                ddl="TEXT NOT NULL DEFAULT '[]'",
            )
            connection.execute(
                """
                INSERT INTO meta(key, value) VALUES ('domain_schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(DOMAIN_SCHEMA_VERSION),),
            )

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        *,
        table: str,
        column: str,
        ddl: str,
    ) -> None:
        existing = {
            row[1]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    # ------------------------------------------------------------------ utilities
    @staticmethod
    def reraise_invalid_transition(exc: InvalidTransitionError) -> None:
        """Hook used by callers to convert workflow errors uniformly."""

        raise exc


def initialize_meta_table(path: Path | str) -> None:
    """Ensure the shared ``meta`` table exists (the broker store also uses it)."""

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(p) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )


__all__: Iterable[str] = (
    "DOMAIN_SCHEMA_VERSION",
    "CommentNotFoundError",
    "DomainStore",
    "DuplicateLinkError",
    "DuplicateProjectKeyError",
    "DuplicateSpaceKeyError",
    "LinkNotFoundError",
    "PageNotFoundError",
    "ProjectNotFoundError",
    "SpaceNotFoundError",
    "WorkItemNotFoundError",
    "initialize_meta_table",
    "utc_now_iso",
)
