"""SQLite-backed store for the Innerwork work-graph domain.

This store sits next to ``SqliteStateStore`` (which persists edge-broker
intent) and uses its own tables in the same database file. Tables are
created on first use; existing edge-broker tables are not touched.

Concurrency model is single-process, like the broker store. Each call
opens and closes a connection.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

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

DOMAIN_SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    """Return a timezone-aware UTC ISO-8601 string with second precision."""

    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ProjectNotFoundError(KeyError):
    """Raised when a project lookup fails."""


class WorkItemNotFoundError(KeyError):
    """Raised when a work-item lookup fails."""


class DuplicateProjectKeyError(ValueError):
    """Raised when a project key is reused."""


class DomainStore:
    """Persistence layer for projects, work items, and transitions."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    # ------------------------------------------------------------------ projects
    def create_project(
        self,
        *,
        project_id: str,
        key: str,
        name: str,
        owner: str,
        created_at: str | None = None,
    ) -> Project:
        validate_project_key(key)
        timestamp = created_at or utc_now_iso()
        project = Project(
            project_id=project_id,
            key=key,
            name=name,
            owner=owner,
            created_at=timestamp,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO projects(project_id, key, name, owner, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        project.project_id,
                        project.key,
                        project.name,
                        project.owner,
                        project.created_at,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if "projects.key" in str(exc) or "UNIQUE" in str(exc).upper():
                raise DuplicateProjectKeyError(f"project key already exists: {key!r}") from exc
            raise
        return project

    def get_project(self, project_id: str) -> Project:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT project_id, key, name, owner, created_at "
                "FROM projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            raise ProjectNotFoundError(project_id)
        return Project(*row)

    def get_project_by_key(self, key: str) -> Project:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT project_id, key, name, owner, created_at FROM projects WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            raise ProjectNotFoundError(key)
        return Project(*row)

    def list_projects(self) -> tuple[Project, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT project_id, key, name, owner, created_at FROM projects ORDER BY key"
            ).fetchall()
        return tuple(Project(*row) for row in rows)

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
                    created_at TEXT NOT NULL
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
                INSERT INTO meta(key, value) VALUES ('domain_schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(DOMAIN_SCHEMA_VERSION),),
            )

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
    "DomainStore",
    "DuplicateProjectKeyError",
    "ProjectNotFoundError",
    "WorkItemNotFoundError",
    "initialize_meta_table",
    "utc_now_iso",
)
