"""HTTP-клиент для OpenProject API."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Optional

import requests
from requests.auth import HTTPBasicAuth

from openproject_megaplan_sync.config import OpenProjectCredentials


class OpenProjectAPIError(RuntimeError):
    """Ошибка OpenProject API."""


class OpenProjectClient:
    """Минимальный клиент OpenProject API."""

    def __init__(self, config: OpenProjectCredentials, session: Optional[requests.Session] = None) -> None:
        self._config = config
        self._session = session or requests.Session()
        self._session.auth = HTTPBasicAuth(self._config.username, self._config.password)
        self._session.headers.update(
            {
                "User-Agent": "openproject-megaplan-sync/0.1",
                "Accept": "application/json",
            }
        )

    @property
    def base_url(self) -> str:
        return self._config.base_url.rstrip("/")

    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self._session.request(method, url, timeout=30, **kwargs)
        if response.status_code >= 400:
            raise OpenProjectAPIError(
                f"Ошибка OpenProject {response.status_code} при запросе {method} {url}: {response.text}"
            )
        return response

    def list_projects(self, offset: Optional[int] = None, page_size: int = 50) -> Dict:
        """Возвращает страницу проектов OpenProject."""
        params: Dict[str, int] = {"pageSize": page_size}
        if offset is not None:
            params["offset"] = offset
        response = self._request("GET", "/api/v3/projects", params=params)
        return response.json()

    def iter_projects(self, page_size: int = 50) -> Iterable[Dict]:
        """Итерирует проекты OpenProject."""
        offset = 1
        while True:
            payload = self.list_projects(offset=offset, page_size=page_size)
            elements = payload.get("_embedded", {}).get("elements", [])
            if not elements:
                break
            for element in elements:
                yield element
            offset += len(elements)
            if len(elements) < page_size:
                break

    def create_work_package(self, payload: Dict) -> Dict:
        response = self._request("POST", "/api/v3/work_packages", json=payload)
        return response.json()

    def update_work_package(self, work_package_id: int, payload: Dict) -> Dict:
        response = self._request("PATCH", f"/api/v3/work_packages/{work_package_id}", json=payload)
        return response.json()

    def find_user(self, login: Optional[str] = None, email: Optional[str] = None) -> Optional[Dict]:
        params: Dict[str, str] = {}
        if login:
            params["login"] = login
        if email:
            params["email"] = email
        if not params:
            raise ValueError("Необходимо указать login или email для поиска пользователя")
        response = self._request("GET", "/api/v3/users", params=params)
        data = response.json()
        items = data.get("_embedded", {}).get("elements", [])
        return items[0] if items else None

    def ensure_user(self, profile: Dict) -> Dict:
        """Создаёт пользователя, если не найден. Требует прав администратора."""
        existing = self.find_user(login=profile.get("login"), email=profile.get("email"))
        if existing:
            return existing
        payload = {
            "login": profile.get("login"),
            "email": profile.get("email"),
            "firstName": profile.get("first_name"),
            "lastName": profile.get("last_name"),
            "status": "active",
        }
        response = self._request("POST", "/api/v3/users", json=payload)
        return response.json()

    def create_comment(self, work_package_id: int, text: str, notified_user_ids: Optional[list[int]] = None) -> Dict:
        payload: Dict[str, object] = {"comment": {"raw": text}}
        if notified_user_ids:
            payload["notify"] = [{"href": f"/api/v3/users/{user_id}"} for user_id in notified_user_ids]
        response = self._request("POST", f"/api/v3/work_packages/{work_package_id}/activities", json=payload)
        return response.json()

    def upload_attachment(self, work_package_id: int, file_path: Path, description: str = "") -> Dict:
        files = {
            "file": (file_path.name, file_path.open("rb")),
            "metadata": ("metadata", f"{{\"description\": \"{description}\"}}", "application/json"),
        }
        try:
            response = self._request(
                "POST",
                f"/api/v3/work_packages/{work_package_id}/attachments",
                files=files,
            )
            return response.json()
        finally:
            files["file"][1].close()

    def add_relation(self, work_package_id: int, payload: Dict) -> Dict:
        response = self._request(
            "POST",
            f"/api/v3/work_packages/{work_package_id}/relations",
            json=payload,
        )
        return response.json()


__all__ = ["OpenProjectClient", "OpenProjectAPIError"]
