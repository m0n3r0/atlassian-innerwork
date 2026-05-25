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

This is the smallest surface that satisfies the Phase B exit criteria for
the project + work-item half of the work-and-knowledge MVP. Space, Page,
Comment, and Link land in follow-up slices.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from .domain import WORKFLOW_STATES, InvalidTransitionError, default_workflow
from .domain_store import (
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
    def create_project(payload: ProjectCreate) -> dict[str, Any]:
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
        return project.to_dict()

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
    def create_work_item(payload: WorkItemCreate) -> dict[str, Any]:
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
        return item.to_dict()

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
    ) -> dict[str, Any]:
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
        return {"work_item": item.to_dict(), "transition": transition.to_dict()}

    # ---- spaces / pages / page versions
    @router.get("/spaces")
    def list_spaces() -> dict[str, Any]:
        return {"spaces": [s.to_dict() for s in store.list_spaces()]}

    @router.post("/spaces", status_code=status.HTTP_201_CREATED)
    def create_space(payload: SpaceCreate) -> dict[str, Any]:
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
        return space.to_dict()

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
    def create_page(payload: PageCreate) -> dict[str, Any]:
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
        return {"page": page.to_dict(), "version": version.to_dict()}

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
    def update_page(page_id: str, payload: PageUpdate) -> dict[str, Any]:
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
        return {"page": page.to_dict(), "version": version.to_dict()}

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
    def create_link(payload: LinkCreate) -> dict[str, Any]:
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
        return link.to_dict()

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
    def delete_link(link_id: str) -> Response:
        try:
            store.delete_link(link_id)
        except LinkNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="link not found",
            ) from None
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

    return router


__all__ = ("create_domain_router",)
