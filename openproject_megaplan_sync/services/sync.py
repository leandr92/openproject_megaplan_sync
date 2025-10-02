"""Бизнес-логика синхронизации задач."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from tqdm import tqdm

from openproject_megaplan_sync.clients import MegaplanClient, OpenProjectClient
from openproject_megaplan_sync.config import AppConfig, ProjectMapping
from openproject_megaplan_sync.models import Attachment, Comment, Task
from openproject_megaplan_sync.services.mapping_store import MappingStore
from openproject_megaplan_sync.services.task_mapper import TaskMapper

LOGGER = logging.getLogger(__name__)


@dataclass
class SyncStats:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    attachments: int = 0
    comments: int = 0


class TaskSyncService:
    """Оркестратор миграции задач."""

    def __init__(
        self,
        config: AppConfig,
        megaplan_client: MegaplanClient,
        openproject_client: OpenProjectClient,
        mapping_store: MappingStore,
        task_mapper: Optional[TaskMapper] = None,
    ) -> None:
        self._config = config
        self._megaplan = megaplan_client
        self._openproject = openproject_client
        self._store = mapping_store
        self._mapper = task_mapper or TaskMapper()

    # region public API
    def initial_migration(self) -> Dict[str, SyncStats]:
        results: Dict[str, SyncStats] = {}
        for mapping in self._config.projects:
            LOGGER.info("Старт миграции проекта %s", mapping.megaplan_id)
            stats = self._sync_project(mapping, updated_since=None)
            results[mapping.megaplan_id] = stats
            self._store.set_last_sync(mapping.megaplan_id, datetime.utcnow())
        return results

    def incremental_sync(self, *, since: Optional[datetime] = None) -> Dict[str, SyncStats]:
        results: Dict[str, SyncStats] = {}
        for mapping in self._config.projects:
            project_since = since or self._store.get_last_sync(mapping.megaplan_id)
            LOGGER.info(
                "Синхронизация проекта %s c момента %s",
                mapping.megaplan_id,
                project_since.isoformat() if project_since else "начала времён",
            )
            stats = self._sync_project(mapping, updated_since=project_since)
            results[mapping.megaplan_id] = stats
            self._store.set_last_sync(mapping.megaplan_id, datetime.utcnow())
        return results

    # endregion

    # region sync helpers
    def _sync_project(self, mapping: ProjectMapping, updated_since: Optional[datetime]) -> SyncStats:
        stats = SyncStats()
        self._megaplan.authenticate()
        raw_tasks = list(
            self._megaplan.iter_project_tasks(
                mapping.megaplan_id,
                page_size=self._config.sync.page_size,
                updated_since=updated_since,
            )
        )
        if not raw_tasks:
            LOGGER.info("Задачи в проекте %s не найдены", mapping.megaplan_id)
            return stats

        tasks: Dict[str, Task] = {}
        for raw in raw_tasks:
            task = self._mapper.map_task(raw)
            tasks[task.id] = task
        ordered_tasks = self._order_tasks(tasks)

        for task in tqdm(ordered_tasks, desc=f"Проект {mapping.megaplan_id}"):
            self._enrich_task(task)
            if self._config.sync.dry_run:
                LOGGER.info(
                    "[DRY-RUN] Задача %s → проект %s", task.id, mapping.openproject_id
                )
                stats.skipped += 1
                continue
            result = self._sync_task(mapping, task)
            stats.created += result.created
            stats.updated += result.updated
            stats.skipped += result.skipped
            stats.comments += result.comments
            stats.attachments += result.attachments
        return stats

    def _enrich_task(self, task: Task) -> None:
        if self._config.sync.sync_comments:
            comments_payload = self._megaplan.get_comments(task.id)
            task.comments = [self._mapper.map_comment(item) for item in comments_payload]
        if self._config.sync.sync_attachments:
            attachments_payload = self._megaplan.get_files(task.id)
            task.attachments = [self._mapper.map_attachment(item) for item in attachments_payload]

    def _sync_task(self, mapping: ProjectMapping, task: Task) -> SyncStats:
        stats = SyncStats()
        existing_open_id = self._store.get_task(task.id)
        parent_open_id = None
        if task.parent_id:
            parent_open_id = self._store.get_task(task.parent_id)
        assignee_open_id = self._resolve_user(task.assignee_id)
        payload = self._mapper.to_openproject_payload(
            task,
            project_id=mapping.openproject_id,
            type_id=None,
            parent_openproject_id=parent_open_id,
            assignee_openproject_id=assignee_open_id,
        )
        if existing_open_id:
            LOGGER.debug("Обновление задачи %s → #%s", task.id, existing_open_id)
            response = self._openproject.update_work_package(existing_open_id, payload)
            stats.updated += 1
            open_id = int(response.get("id", existing_open_id))
        else:
            LOGGER.debug("Создание задачи %s", task.id)
            response = self._openproject.create_work_package(payload)
            open_id = int(response.get("id"))
            self._store.upsert_task(task.id, open_id)
            stats.created += 1

        # сохраняем маппинг (на случай создания ранее через другой запуск)
        if not existing_open_id:
            existing_open_id = open_id
        else:
            self._store.upsert_task(task.id, existing_open_id)

        if self._config.sync.sync_comments:
            stats.comments += self._sync_comments(existing_open_id, task)
        if self._config.sync.sync_attachments:
            stats.attachments += self._sync_attachments(existing_open_id, task)
        return stats

    def _sync_comments(self, open_task_id: int, task: Task) -> int:
        synced = 0
        for comment in task.comments:
            comment_key = f"{task.id}:{comment.id}"
            if self._store.get_comment(comment_key):
                continue
            body = f"{comment.body}\n\n_Автор: {comment.author_id or 'неизвестно'}_"
            response = self._openproject.create_comment(open_task_id, body)
            comment_id = int(response.get('id') or 0)
            self._store.upsert_comment(comment_key, comment_id or open_task_id)
            synced += 1
        return synced

    def _sync_attachments(self, open_task_id: int, task: Task) -> int:
        synced = 0
        tmp_dir = self._config.sync.tmp_dir
        for attachment in task.attachments:
            if attachment.size > self._config.sync.attachment_max_mb * 1024 * 1024:
                LOGGER.warning(
                    "Пропуск файла %s из-за размера %s", attachment.filename, attachment.size
                )
                continue
            if self._store.get_attachment(attachment.id):
                continue
            tmp_path = tmp_dir / attachment.filename
            self._download_attachment(attachment, tmp_path)
            try:
                response = self._openproject.upload_attachment(open_task_id, tmp_path)
                attachment_id = int(response.get("id"))
                self._store.upsert_attachment(attachment.id, attachment_id)
                synced += 1
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
        return synced

    def _download_attachment(self, attachment: Attachment, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        self._megaplan.download_file(attachment.id, target_path)

    def _resolve_user(self, megaplan_user_id: Optional[str]) -> Optional[int]:
        if not megaplan_user_id:
            return self._config.openproject.default_user_id
        cached = self._store.get_user(megaplan_user_id)
        if cached:
            return cached
        users = self._megaplan.get_users([megaplan_user_id])
        if not users:
            LOGGER.warning("Не удалось получить пользователя %s", megaplan_user_id)
            return self._config.openproject.default_user_id
        payload = users[0]
        profile = {
            "login": payload.get("login") or payload.get("Login"),
            "email": payload.get("email") or payload.get("Email"),
            "first_name": payload.get("first_name") or payload.get("FirstName"),
            "last_name": payload.get("last_name") or payload.get("LastName"),
        }
        user = self._openproject.ensure_user(profile)
        open_id = int(user.get("id"))
        self._store.upsert_user(megaplan_user_id, open_id)
        return open_id

    # endregion

    @staticmethod
    def _order_tasks(tasks: Dict[str, Task]) -> Iterable[Task]:
        visited: Dict[str, bool] = {}
        ordered: List[Task] = []

        def visit(task_id: str) -> None:
            if visited.get(task_id):
                return
            visited[task_id] = True
            task = tasks[task_id]
            if task.parent_id and task.parent_id in tasks:
                visit(task.parent_id)
            ordered.append(task)

        for task_id in list(tasks.keys()):
            visit(task_id)
        return ordered


__all__ = ["TaskSyncService", "SyncStats"]
