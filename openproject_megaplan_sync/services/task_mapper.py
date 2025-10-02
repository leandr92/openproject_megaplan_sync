"""Маппинг задач между Megaplan и OpenProject."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from dateutil import parser

from openproject_megaplan_sync.models import Attachment, Comment, Task


class TaskMapper:
    """Конвертация данных между API и внутренними моделями."""

    def __init__(
        self,
        *,
        status_mapping: Optional[Dict[str, str]] = None,
        type_mapping: Optional[Dict[str, str]] = None,
    ) -> None:
        self._status_mapping = status_mapping or {}
        self._type_mapping = type_mapping or {}

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        return parser.parse(value)

    def map_task(self, payload: Dict) -> Task:
        fields = payload.get("data") if "data" in payload else payload
        task_id = str(fields.get("id") or fields.get("TaskId"))
        name = fields.get("name") or fields.get("Name") or fields.get("title")
        description = fields.get("description") or fields.get("Description") or ""
        status = fields.get("status") or fields.get("Status") or "unknown"
        project_id = str(
            fields.get("project_id")
            or fields.get("Project")
            or fields.get("project", {}).get("id")
            or ""
        )
        author_id = fields.get("author_id") or fields.get("Author")
        assignee_id = fields.get("responsible_id") or fields.get("Responsible")
        parent_id = fields.get("parent_id") or fields.get("ParentTask")
        created_at = self._parse_datetime(fields.get("created_at") or fields.get("CreatedAt"))
        updated_at = self._parse_datetime(fields.get("updated_at") or fields.get("UpdatedAt"))
        start_date = self._parse_datetime(fields.get("start_date") or fields.get("StartDate"))
        due_date = self._parse_datetime(fields.get("due_date") or fields.get("FinishDate"))

        task = Task(
            id=task_id,
            project_id=project_id,
            name=name or f"Task {task_id}",
            description=description or "",
            status=status,
            author_id=str(author_id) if author_id else None,
            assignee_id=str(assignee_id) if assignee_id else None,
            parent_id=str(parent_id) if parent_id else None,
            created_at=created_at,
            updated_at=updated_at,
            start_date=start_date,
            due_date=due_date,
        )
        return task

    def map_comment(self, payload: Dict) -> Comment:
        comment_id = str(payload.get("id") or payload.get("CommentId"))
        author_id = payload.get("author_id") or payload.get("Author")
        created_at = self._parse_datetime(payload.get("created_at") or payload.get("CreatedAt"))
        body = payload.get("text") or payload.get("Body") or ""
        return Comment(
            id=comment_id,
            author_id=str(author_id) if author_id else None,
            body=body,
            created_at=created_at or datetime.utcnow(),
        )

    def map_attachment(self, payload: Dict) -> Attachment:
        attachment_id = str(payload.get("id") or payload.get("FileId"))
        filename = payload.get("name") or payload.get("FileName") or attachment_id
        size = int(payload.get("size") or payload.get("FileSize") or 0)
        download_url = payload.get("download_url") or payload.get("DownloadUrl") or ""
        return Attachment(id=attachment_id, filename=filename, size=size, download_url=download_url)

    def to_openproject_payload(
        self,
        task: Task,
        *,
        project_id: int,
        type_id: Optional[int],
        parent_openproject_id: Optional[int],
        assignee_openproject_id: Optional[int],
    ) -> Dict:
        status = self._status_mapping.get(task.status, "default")
        payload: Dict[str, object] = {
            "subject": task.name,
            "description": {"raw": task.description or ""},
            "_links": {
                "project": {"href": f"/api/v3/projects/{project_id}"},
            },
        }
        if status != "default":
            payload["_links"]["status"] = {"href": f"/api/v3/statuses/{status}"}
        if type_id:
            payload["_links"]["type"] = {"href": f"/api/v3/types/{type_id}"}
        if assignee_openproject_id:
            payload["_links"]["assignee"] = {"href": f"/api/v3/users/{assignee_openproject_id}"}
        if parent_openproject_id:
            payload["_links"]["parent"] = {"href": f"/api/v3/work_packages/{parent_openproject_id}"}
        if task.start_date:
            payload["startDate"] = task.start_date.date().isoformat()
        if task.due_date:
            payload["dueDate"] = task.due_date.date().isoformat()
        return payload


__all__ = ["TaskMapper"]
