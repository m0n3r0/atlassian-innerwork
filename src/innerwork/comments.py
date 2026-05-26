"""Comment dataclasses for the Innerwork product-domain.

Comments are append-only audit-style records attached to a work item or a
page. They share validation rules but live in their own tables so that
permission scoping (Phase D) can be applied independently per graph.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

MAX_BODY_LENGTH = 10_000


def validate_comment_body(body: str) -> str:
    """Validate a comment body and return its stripped form."""

    if not isinstance(body, str):
        raise TypeError("comment body must be a string")
    cleaned = body.strip()
    if not cleaned:
        raise ValueError("comment body must be non-blank")
    if len(cleaned) > MAX_BODY_LENGTH:
        raise ValueError(f"comment body too long: {len(cleaned)} > {MAX_BODY_LENGTH}")
    return cleaned


def validate_author(author: str) -> str:
    if not isinstance(author, str):
        raise TypeError("author must be a string")
    cleaned = author.strip()
    if not cleaned:
        raise ValueError("author must be a non-blank string")
    if len(cleaned) > 200:
        raise ValueError("author too long")
    return cleaned


@dataclass(frozen=True)
class WorkItemComment:
    comment_id: str
    work_item_id: str
    author: str
    body: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "comment_id": self.comment_id,
            "work_item_id": self.work_item_id,
            "author": self.author,
            "body": self.body,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class PageComment:
    comment_id: str
    page_id: str
    author: str
    body: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "comment_id": self.comment_id,
            "page_id": self.page_id,
            "author": self.author,
            "body": self.body,
            "created_at": self.created_at,
        }


__all__: Iterable[str] = (
    "MAX_BODY_LENGTH",
    "PageComment",
    "WorkItemComment",
    "validate_author",
    "validate_comment_body",
)
