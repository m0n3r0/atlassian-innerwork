"""FastAPI router for the Innerwork work-graph domain (Phase B slice 1).

Endpoints
=========

* ``GET    /v1/workflow``                                   workflow definition
* ``GET    /v1/projects``                                   list projects
* ``POST   /v1/projects``                                   create project
* ``GET    /v1/projects/{project_id}``                      get project
* ``GET    /v1/projects/{project_id}/work_items``           list project work items
* ``GET    /v1/work_items``                                 list work items
* ``POST   /v1/work_items``                                 create work item
* ``GET    /v1/work_items/{work_item_id}``                  get work item
* ``GET    /v1/work_items/{work_item_id}/transitions``      list transitions
* ``POST   /v1/work_items/{work_item_id}/transitions``      transition work item

Phase 6 additions
-----------------

* ``GET    /v1/search``                                     cross-graph search
* ``GET    /v1/search/kinds``                               list searchable kinds
* ``POST   /v1/ai_context``                                 build assistant context bundle

This is the smallest surface that satisfies the Phase B exit criteria for
the project + work-item half of the work-and-knowledge MVP. Space, Page,
Comment, and Link land in follow-up slices.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from .domain import WORKFLOW_STATES, InvalidTransitionError, default_workflow
from .ai_context import (
    AIContextError,
    DEFAULT_TOKEN_BUDGET,
    build_ai_context,
)
from .search import (
    SEARCHABLE_KINDS,
    SearchQueryError,
    search_domain,
)
from .permissions import parse_principal_header
from .analytics import (
    AnalyticsError,
    domain_rollup,
    project_rollup,
    space_rollup,
)
from .domain_store import (
    CommentNotFoundError,
    DomainStore,
    DuplicateLinkError,
    DuplicateProjectKeyError,
    DuplicateSpaceKeyError,
    LinkNotFoundError,
    PageNotFoundError,
    ProjectNotFoundError,
    SpaceNotFoundError,
    WorkItemNotFoundError,
)
from .knowledge import LINK_KINDS

# ----------------------------------------------------------------- pydantic IO


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=2, max_length=10)
    name: str = Field(min_length=1, max_length=200)
    owner: str = Field(min_length=1, max_length=200)


class WorkItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    assignee: str = Field(default="", max_length=200)


class TransitionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_state: str = Field(min_length=1, max_length=32)
    actor: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="", max_length=1000)


class SpaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=2, max_length=10)
    name: str = Field(min_length=1, max_length=200)
    owner: str = Field(min_length=1, max_length=200)


class PageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    space_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=200_000)
    author: str = Field(min_length=1, max_length=200)


class PageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=200_000)
    author: str = Field(min_length=1, max_length=200)


class LinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_item_id: str = Field(min_length=1, max_length=64)
    page_id: str = Field(min_length=1, max_length=64)
    kind: str = Field(min_length=1, max_length=40)
    created_by: str = Field(min_length=1, max_length=200)


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10_000)


class AIContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(default=None, max_length=200)
    anchor_kind: str | None = Field(default=None, max_length=20)
    anchor_id: str | None = Field(default=None, max_length=64)
    token_budget: int = Field(default=DEFAULT_TOKEN_BUDGET, ge=200, le=32_000)
    max_items: int = Field(default=20, ge=1, le=100)


# ----------------------------------------------------------------- idempotency

IDEMPOTENCY_HEADER = "X-Idempotency-Key"
IDEMPOTENCY_MIN_LEN = 16
IDEMPOTENCY_MAX_LEN = 128


def _require_idempotency_key(value: str | None) -> str:
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail=f"{IDEMPOTENCY_HEADER} header is required for mutating /v1/ operations",
        )
    cleaned = value.strip()
    if not (IDEMPOTENCY_MIN_LEN <= len(cleaned) <= IDEMPOTENCY_MAX_LEN):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"{IDEMPOTENCY_HEADER} must be between "
                f"{IDEMPOTENCY_MIN_LEN} and {IDEMPOTENCY_MAX_LEN} characters"
            ),
        )
    return cleaned


def _hash_request(scope: str, path_params: dict[str, Any], payload: BaseModel | None) -> str:
    body = payload.model_dump(mode="json") if payload is not None else None
    blob = json.dumps(
        {"scope": scope, "path": path_params, "body": body},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _idempotent(
    store: DomainStore,
    *,
    scope: str,
    key: str,
    path_params: dict[str, Any],
    payload: BaseModel | None,
):
    """Look up a replayed response.

    Returns ``(request_hash, replayed_body_or_None)``. The caller serialises
    the fresh response via :func:`_record_idempotent` once it has run.
    """

    request_hash = _hash_request(scope, path_params, payload)
    try:
        replayed = store.get_idempotent_response(scope=scope, key=key, request_hash=request_hash)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return request_hash, replayed


def _record_idempotent(
    store: DomainStore,
    *,
    scope: str,
    key: str,
    request_hash: str,
    response: Any,
) -> None:
    store.save_idempotent_response(
        scope=scope,
        key=key,
        request_hash=request_hash,
        response_body=json.dumps(response, sort_keys=True, separators=(",", ":")),
    )


# ----------------------------------------------------------------- router


def create_domain_router(store: DomainStore) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["work-graph"])

    @router.get("/workflow")
    def get_workflow() -> dict[str, Any]:
        return default_workflow().to_dict()

    # ---- projects
    @router.get("/projects")
    def list_projects() -> dict[str, Any]:
        return {"projects": [p.to_dict() for p in store.list_projects()]}

    @router.post("/projects", status_code=status.HTTP_201_CREATED)
    def create_project(
        payload: ProjectCreate,
        x_idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    ) -> Any:
        key = _require_idempotency_key(x_idempotency_key)
        request_hash, replayed = _idempotent(
            store, scope="projects.create", key=key, path_params={}, payload=payload
        )
        if replayed is not None:
            return json.loads(replayed)
        try:
            project = store.create_project(
                project_id=str(uuid.uuid4()),
                key=payload.key,
                name=payload.name,
                owner=payload.owner,
            )
        except DuplicateProjectKeyError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        body = project.to_dict()
        _record_idempotent(
            store, scope="projects.create", key=key, request_hash=request_hash, response=body
        )
        return body

    @router.get("/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        try:
            return store.get_project(project_id).to_dict()
        except ProjectNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="project not found",
            ) from None

    @router.get("/projects/{project_id}/work_items")
    def list_project_work_items(
        project_id: str,
        state: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            store.get_project(project_id)
        except ProjectNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="project not found",
            ) from None
        if state is not None and state not in WORKFLOW_STATES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unknown state filter: {state!r}",
            ) from None
        items = store.list_work_items(project_id=project_id, state=state)
        return {"work_items": [i.to_dict() for i in items]}

    # ---- work items
    @router.get("/work_items")
    def list_work_items(
        project_id: str | None = Query(default=None),
        state: str | None = Query(default=None),
    ) -> dict[str, Any]:
        if state is not None and state not in WORKFLOW_STATES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unknown state filter: {state!r}",
            )
        items = store.list_work_items(project_id=project_id, state=state)
        return {"work_items": [i.to_dict() for i in items]}

    @router.post("/work_items", status_code=status.HTTP_201_CREATED)
    def create_work_item(
        payload: WorkItemCreate,
        x_idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    ) -> Any:
        key = _require_idempotency_key(x_idempotency_key)
        request_hash, replayed = _idempotent(
            store, scope="work_items.create", key=key, path_params={}, payload=payload
        )
        if replayed is not None:
            return json.loads(replayed)
        try:
            item = store.create_work_item(
                work_item_id=str(uuid.uuid4()),
                project_id=payload.project_id,
                title=payload.title,
                description=payload.description,
                assignee=payload.assignee,
            )
        except ProjectNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="project not found",
            ) from None
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        body = item.to_dict()
        _record_idempotent(
            store, scope="work_items.create", key=key, request_hash=request_hash, response=body
        )
        return body

    @router.get("/work_items/{work_item_id}")
    def get_work_item(work_item_id: str) -> dict[str, Any]:
        try:
            return store.get_work_item(work_item_id).to_dict()
        except WorkItemNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="work item not found",
            ) from None

    @router.get("/work_items/{work_item_id}/transitions")
    def list_transitions(work_item_id: str) -> dict[str, Any]:
        try:
            store.get_work_item(work_item_id)
        except WorkItemNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="work item not found",
            ) from None
        return {
            "transitions": [t.to_dict() for t in store.list_transitions(work_item_id)],
        }

    @router.post(
        "/work_items/{work_item_id}/transitions",
        status_code=status.HTTP_201_CREATED,
    )
    def transition_work_item(
        work_item_id: str,
        payload: TransitionCreate,
        x_idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    ) -> Any:
        key = _require_idempotency_key(x_idempotency_key)
        request_hash, replayed = _idempotent(
            store,
            scope="work_items.transition",
            key=key,
            path_params={"work_item_id": work_item_id},
            payload=payload,
        )
        if replayed is not None:
            return json.loads(replayed)
        try:
            item, transition = store.transition_work_item(
                work_item_id=work_item_id,
                to_state=payload.to_state,
                actor=payload.actor,
                reason=payload.reason,
            )
        except WorkItemNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="work item not found",
            ) from None
        except InvalidTransitionError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        body = {"work_item": item.to_dict(), "transition": transition.to_dict()}
        _record_idempotent(
            store,
            scope="work_items.transition",
            key=key,
            request_hash=request_hash,
            response=body,
        )
        return body

    # ---- spaces / pages / page versions
    @router.get("/spaces")
    def list_spaces() -> dict[str, Any]:
        return {"spaces": [s.to_dict() for s in store.list_spaces()]}

    @router.post("/spaces", status_code=status.HTTP_201_CREATED)
    def create_space(
        payload: SpaceCreate,
        x_idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    ) -> Any:
        key = _require_idempotency_key(x_idempotency_key)
        request_hash, replayed = _idempotent(
            store, scope="spaces.create", key=key, path_params={}, payload=payload
        )
        if replayed is not None:
            return json.loads(replayed)
        try:
            space = store.create_space(
                space_id=str(uuid.uuid4()),
                key=payload.key,
                name=payload.name,
                owner=payload.owner,
            )
        except DuplicateSpaceKeyError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        body = space.to_dict()
        _record_idempotent(
            store, scope="spaces.create", key=key, request_hash=request_hash, response=body
        )
        return body

    @router.get("/spaces/{space_id}")
    def get_space(space_id: str) -> dict[str, Any]:
        try:
            return store.get_space(space_id).to_dict()
        except SpaceNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="space not found",
            ) from None

    @router.get("/spaces/{space_id}/pages")
    def list_space_pages(space_id: str) -> dict[str, Any]:
        try:
            store.get_space(space_id)
        except SpaceNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="space not found",
            ) from None
        pages = store.list_pages(space_id=space_id)
        return {"pages": [p.to_dict() for p in pages]}

    @router.get("/pages")
    def list_pages(
        space_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        pages = store.list_pages(space_id=space_id)
        return {"pages": [p.to_dict() for p in pages]}

    @router.post("/pages", status_code=status.HTTP_201_CREATED)
    def create_page(
        payload: PageCreate,
        x_idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    ) -> Any:
        key = _require_idempotency_key(x_idempotency_key)
        request_hash, replayed = _idempotent(
            store, scope="pages.create", key=key, path_params={}, payload=payload
        )
        if replayed is not None:
            return json.loads(replayed)
        try:
            page, version = store.create_page(
                page_id=str(uuid.uuid4()),
                space_id=payload.space_id,
                title=payload.title,
                body=payload.body,
                author=payload.author,
            )
        except SpaceNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="space not found",
            ) from None
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        body = {"page": page.to_dict(), "version": version.to_dict()}
        _record_idempotent(
            store, scope="pages.create", key=key, request_hash=request_hash, response=body
        )
        return body

    @router.get("/pages/{page_id}")
    def get_page(page_id: str) -> dict[str, Any]:
        try:
            return store.get_page(page_id).to_dict()
        except PageNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="page not found",
            ) from None

    @router.put("/pages/{page_id}", status_code=status.HTTP_201_CREATED)
    def update_page(
        page_id: str,
        payload: PageUpdate,
        x_idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    ) -> Any:
        key = _require_idempotency_key(x_idempotency_key)
        request_hash, replayed = _idempotent(
            store,
            scope="pages.update",
            key=key,
            path_params={"page_id": page_id},
            payload=payload,
        )
        if replayed is not None:
            return json.loads(replayed)
        try:
            page, version = store.update_page(
                page_id=page_id,
                title=payload.title,
                body=payload.body,
                author=payload.author,
            )
        except PageNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="page not found",
            ) from None
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        body = {"page": page.to_dict(), "version": version.to_dict()}
        _record_idempotent(
            store, scope="pages.update", key=key, request_hash=request_hash, response=body
        )
        return body

    @router.get("/pages/{page_id}/versions")
    def list_page_versions(page_id: str) -> dict[str, Any]:
        try:
            versions = store.list_page_versions(page_id)
        except PageNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="page not found",
            ) from None
        return {"versions": [v.to_dict() for v in versions]}

    @router.get("/pages/{page_id}/versions/{version_number}")
    def get_page_version(page_id: str, version_number: int) -> dict[str, Any]:
        try:
            store.get_page(page_id)
        except PageNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="page not found",
            ) from None
        try:
            return store.get_page_version(page_id, version_number).to_dict()
        except PageNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="page version not found",
            ) from None

    @router.get("/pages/{page_id}/links")
    def list_links_for_page(page_id: str) -> dict[str, Any]:
        try:
            links = store.list_links_for_page(page_id)
        except PageNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="page not found",
            ) from None
        return {"links": [link.to_dict() for link in links]}

    # ---- links
    @router.get("/links/kinds")
    def list_link_kinds() -> dict[str, Any]:
        return {"kinds": sorted(LINK_KINDS)}

    @router.post("/links", status_code=status.HTTP_201_CREATED)
    def create_link(
        payload: LinkCreate,
        x_idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    ) -> Any:
        key = _require_idempotency_key(x_idempotency_key)
        request_hash, replayed = _idempotent(
            store, scope="links.create", key=key, path_params={}, payload=payload
        )
        if replayed is not None:
            return json.loads(replayed)
        try:
            link = store.create_link(
                link_id=str(uuid.uuid4()),
                work_item_id=payload.work_item_id,
                page_id=payload.page_id,
                kind=payload.kind,
                created_by=payload.created_by,
            )
        except WorkItemNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="work item not found",
            ) from None
        except PageNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="page not found",
            ) from None
        except DuplicateLinkError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        body = link.to_dict()
        _record_idempotent(
            store, scope="links.create", key=key, request_hash=request_hash, response=body
        )
        return body

    @router.get("/links/{link_id}")
    def get_link(link_id: str) -> dict[str, Any]:
        try:
            return store.get_link(link_id).to_dict()
        except LinkNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="link not found",
            ) from None

    @router.delete("/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_link(
        link_id: str,
        x_idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    ) -> Response:
        key = _require_idempotency_key(x_idempotency_key)
        request_hash, replayed = _idempotent(
            store,
            scope="links.delete",
            key=key,
            path_params={"link_id": link_id},
            payload=None,
        )
        if replayed is not None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        try:
            store.delete_link(link_id)
        except LinkNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="link not found",
            ) from None
        _record_idempotent(
            store,
            scope="links.delete",
            key=key,
            request_hash=request_hash,
            response={"deleted": link_id},
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/work_items/{work_item_id}/links")
    def list_links_for_work_item(work_item_id: str) -> dict[str, Any]:
        try:
            links = store.list_links_for_work_item(work_item_id)
        except WorkItemNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="work item not found",
            ) from None
        return {"links": [link.to_dict() for link in links]}

    # ---- comments
    @router.get("/work_items/{work_item_id}/comments")
    def list_work_item_comments(work_item_id: str) -> dict[str, Any]:
        try:
            comments = store.list_work_item_comments(work_item_id)
        except WorkItemNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="work item not found",
            ) from None
        return {"comments": [c.to_dict() for c in comments]}

    @router.post(
        "/work_items/{work_item_id}/comments",
        status_code=status.HTTP_201_CREATED,
    )
    def create_work_item_comment(
        work_item_id: str,
        payload: CommentCreate,
        x_idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    ) -> Any:
        key = _require_idempotency_key(x_idempotency_key)
        request_hash, replayed = _idempotent(
            store,
            scope="work_item_comments.create",
            key=key,
            path_params={"work_item_id": work_item_id},
            payload=payload,
        )
        if replayed is not None:
            return json.loads(replayed)
        try:
            comment = store.create_work_item_comment(
                comment_id=str(uuid.uuid4()),
                work_item_id=work_item_id,
                author=payload.author,
                body=payload.body,
            )
        except WorkItemNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="work item not found",
            ) from None
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        body = comment.to_dict()
        _record_idempotent(
            store,
            scope="work_item_comments.create",
            key=key,
            request_hash=request_hash,
            response=body,
        )
        return body

    @router.get("/work_item_comments/{comment_id}")
    def get_work_item_comment(comment_id: str) -> dict[str, Any]:
        try:
            return store.get_work_item_comment(comment_id).to_dict()
        except CommentNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="comment not found",
            ) from None

    @router.get("/pages/{page_id}/comments")
    def list_page_comments(page_id: str) -> dict[str, Any]:
        try:
            comments = store.list_page_comments(page_id)
        except PageNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="page not found",
            ) from None
        return {"comments": [c.to_dict() for c in comments]}

    @router.post(
        "/pages/{page_id}/comments",
        status_code=status.HTTP_201_CREATED,
    )
    def create_page_comment(
        page_id: str,
        payload: CommentCreate,
        x_idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    ) -> Any:
        key = _require_idempotency_key(x_idempotency_key)
        request_hash, replayed = _idempotent(
            store,
            scope="page_comments.create",
            key=key,
            path_params={"page_id": page_id},
            payload=payload,
        )
        if replayed is not None:
            return json.loads(replayed)
        try:
            comment = store.create_page_comment(
                comment_id=str(uuid.uuid4()),
                page_id=page_id,
                author=payload.author,
                body=payload.body,
            )
        except PageNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="page not found",
            ) from None
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        body = comment.to_dict()
        _record_idempotent(
            store,
            scope="page_comments.create",
            key=key,
            request_hash=request_hash,
            response=body,
        )
        return body

    @router.get("/page_comments/{comment_id}")
    def get_page_comment(comment_id: str) -> dict[str, Any]:
        try:
            return store.get_page_comment(comment_id).to_dict()
        except CommentNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="comment not found",
            ) from None

    # ---- search + AI context (Phase 6)
    @router.get("/search")
    def search(
        q: str = Query(min_length=1, max_length=200),
        kinds: str | None = Query(default=None, description="comma-separated subset of work_item,page,comment"),
        limit: int = Query(default=20, ge=1, le=100),
        project_id: str | None = Query(default=None),
        space_id: str | None = Query(default=None),
        x_innerwork_principal: str | None = Header(
            default=None, alias="X-Innerwork-Principal"
        ),
    ) -> dict[str, Any]:
        try:
            principal = parse_principal_header(x_innerwork_principal)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        kinds_arg: tuple[str, ...] | None = None
        if kinds is not None:
            parts = tuple(p.strip() for p in kinds.split(",") if p.strip())
            if not parts:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="kinds parameter must contain at least one kind",
                )
            kinds_arg = parts
        try:
            result = search_domain(
                store,
                query=q,
                kinds=kinds_arg,
                limit=limit,
                project_id=project_id,
                space_id=space_id,
                principal=principal,
            )
        except SearchQueryError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        return result.to_dict()

    @router.get("/search/kinds")
    def search_kinds() -> dict[str, Any]:
        return {"kinds": list(SEARCHABLE_KINDS)}

    @router.post("/ai_context")
    def ai_context(
        payload: AIContextRequest,
        x_innerwork_principal: str | None = Header(
            default=None, alias="X-Innerwork-Principal"
        ),
    ) -> dict[str, Any]:
        try:
            principal = parse_principal_header(x_innerwork_principal)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        try:
            bundle = build_ai_context(
                store,
                query=payload.query,
                anchor_kind=payload.anchor_kind,
                anchor_id=payload.anchor_id,
                token_budget=payload.token_budget,
                max_items=payload.max_items,
                principal=principal,
            )
        except AIContextError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except (WorkItemNotFoundError, PageNotFoundError):
            # Collapse missing anchor onto the same 400 surface as
            # "anchor not readable" so callers cannot probe for the
            # existence of restricted IDs. Mirrors the analytics
            # endpoints' single-status policy.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="anchor is not readable",
            ) from None
        return bundle.to_dict()

    @router.get("/analytics/domain")
    def analytics_domain(
        x_innerwork_principal: str | None = Header(
            default=None, alias="X-Innerwork-Principal"
        ),
    ) -> dict[str, Any]:
        try:
            principal = parse_principal_header(x_innerwork_principal)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        return domain_rollup(store, principal=principal).to_dict()

    @router.get("/analytics/projects/{project_id}")
    def analytics_project(
        project_id: str,
        x_innerwork_principal: str | None = Header(
            default=None, alias="X-Innerwork-Principal"
        ),
    ) -> dict[str, Any]:
        try:
            principal = parse_principal_header(x_innerwork_principal)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        try:
            return project_rollup(store, project_id, principal=principal).to_dict()
        except AnalyticsError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc

    @router.get("/analytics/spaces/{space_id}")
    def analytics_space(
        space_id: str,
        x_innerwork_principal: str | None = Header(
            default=None, alias="X-Innerwork-Principal"
        ),
    ) -> dict[str, Any]:
        try:
            principal = parse_principal_header(x_innerwork_principal)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        try:
            return space_rollup(store, space_id, principal=principal).to_dict()
        except AnalyticsError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc

    return router


__all__ = ("create_domain_router",)
