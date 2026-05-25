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

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from .domain import WORKFLOW_STATES, InvalidTransitionError, default_workflow
from .domain_store import (
    DomainStore,
    DuplicateProjectKeyError,
    ProjectNotFoundError,
    WorkItemNotFoundError,
)

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

    return router


__all__ = ("create_domain_router",)
