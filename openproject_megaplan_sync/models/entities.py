"""Определения доменных сущностей."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass(slots=True)
class User:
    """Представление пользователя Megaplan/OpenProject."""

    id: str
    login: Optional[str]
    email: Optional[str]
    first_name: Optional[str] = None
    last_name: Optional[str] = None


@dataclass(slots=True)
class Comment:
    """Комментарий к задаче."""

    id: str
    author_id: Optional[str]
    body: str
    created_at: datetime


@dataclass(slots=True)
class Attachment:
    """Вложенный файл."""

    id: str
    filename: str
    size: int
    download_url: str


@dataclass(slots=True)
class Task:
    """Задача Megaplan."""

    id: str
    project_id: str
    name: str
    description: str
    status: str
    author_id: Optional[str]
    assignee_id: Optional[str]
    parent_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    start_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    comments: List[Comment] = field(default_factory=list)
    attachments: List[Attachment] = field(default_factory=list)


@dataclass(slots=True)
class ProjectMapping:
    """Соответствие проектов Megaplan и OpenProject."""

    megaplan_id: str
    openproject_id: int


__all__ = ["User", "Comment", "Attachment", "Task", "ProjectMapping"]
