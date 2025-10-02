"""HTTP-клиент для Megaplan API."""
from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional

import requests
from requests.auth import HTTPBasicAuth

from openproject_megaplan_sync.config import MegaplanCredentials

ISO_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


class MegaplanAPIError(RuntimeError):
    """Исключение при ошибке Megaplan API."""


@dataclass
class MegaplanTaskPage:
    """Контейнер для страницы задач."""

    items: List[Dict]
    next_offset: Optional[str]


class MegaplanClient:
    """Минимальный клиент Megaplan API."""

    def __init__(self, config: MegaplanCredentials, session: Optional[requests.Session] = None) -> None:
        self._config = config
        self._session = session or requests.Session()
        self._session.auth = HTTPBasicAuth(config.username, config.password)
        self._session.headers.update({
            "User-Agent": "openproject-megaplan-sync/0.1",
            "Accept": "application/json",
        })

    @property
    def base_url(self) -> str:
        return self._config.base_url.rstrip("/")

    def authenticate(self, force: bool = False) -> None:
        """Проверяет наличие учётных данных для Basic Auth."""
        if not (self._config.username and self._config.password):
            raise MegaplanAPIError("Необходимо задать username/password в конфигурации")

    # region low-level helpers
    def _request(self, method: str, endpoint: str, *, retry: bool = True, **kwargs) -> requests.Response:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", "openproject-megaplan-sync/0.1")
        response = self._session.request(method, url, headers=headers, timeout=30, **kwargs)
        if response.status_code == 401 and retry:
            raise MegaplanAPIError(f"Ошибка авторизации Megaplan при запросе {method} {url}")
        if response.status_code >= 400:
            raise MegaplanAPIError(
                f"Ошибка Megaplan API {response.status_code} при запросе {method} {url}: {response.text}"
            )
        return response

    def list_tasks(
        self,
        project_id: str,
        *,
        offset: Optional[str] = None,
        page_size: int = 100,
        updated_since: Optional[datetime] = None,
    ) -> MegaplanTaskPage:
        """Возвращает страницу задач проекта."""
        params: Dict[str, str] = {
            "project": project_id,
            "limit": str(page_size),
        }
        if offset:
            params["offset"] = offset
        if updated_since:
            params["updated_after"] = updated_since.strftime(ISO_DATE_FORMAT)
        response = self._request("GET", "/tasks", params=params)
        payload = response.json()
        tasks = payload.get("data", {}).get("items", [])
        next_offset = payload.get("data", {}).get("next")
        return MegaplanTaskPage(items=tasks, next_offset=next_offset)

    def iter_project_tasks(
        self,
        project_id: str,
        *,
        page_size: int,
        updated_since: Optional[datetime] = None,
    ) -> Iterable[Dict]:
        """Итерирует задачи проекта с учётом пагинации."""
        offset = None
        while True:
            page = self.list_tasks(
                project_id,
                offset=offset,
                page_size=page_size,
                updated_since=updated_since,
            )
            for item in page.items:
                yield item
            if not page.next_offset:
                break
            offset = page.next_offset

    def get_comments(self, task_id: str) -> List[Dict]:
        response = self._request("GET", f"/tasks/{task_id}/comments")
        payload = response.json()
        return payload.get("data", {}).get("items", [])

    def get_files(self, task_id: str) -> List[Dict]:
        response = self._request("GET", f"/tasks/{task_id}/files")
        payload = response.json()
        return payload.get("data", {}).get("items", [])

    def download_file(self, file_id: str, target_path: Path) -> Path:
        response = self._request("GET", f"/files/{file_id}/download", stream=True)
        with target_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=16384):
                if chunk:
                    handle.write(chunk)
        return target_path

    def get_users(self, user_ids: List[str]) -> List[Dict]:
        response = self._request("GET", "/users", params={"ids": ",".join(user_ids)})
        payload = response.json()
        return payload.get("data", {}).get("items", [])

    # endregion


__all__ = ["MegaplanClient", "MegaplanAPIError", "MegaplanTaskPage"]
