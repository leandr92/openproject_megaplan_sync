"""Загрузка и валидация конфигурации приложения."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator


class MegaplanCredentials(BaseModel):
    """Настройки подключения к Megaplan."""

    base_url: str = Field(..., description="Базовый URL API Megaplan, например https://company.megaplan.ru/api/v3")
    username: str = Field(..., description="Логин пользователя Megaplan")
    password: str = Field(..., description="Пароль пользователя Megaplan")


class OpenProjectCredentials(BaseModel):
    """Настройки подключения к OpenProject."""

    base_url: str = Field(..., description="Базовый URL OpenProject, например https://openproject.example.com")
    username: str = Field(..., description="Логин пользователя OpenProject")
    password: str = Field(..., description="Пароль пользователя или API token, используемый в Basic Auth")
    default_user_id: Optional[int] = Field(
        None,
        description="ID пользователя, который будет назначен исполнителем, если оригинальный пользователь не найден",
    )


class ProjectMapping(BaseModel):
    """Правило соответствия проектов."""

    megaplan_id: str = Field(..., description="Идентификатор проекта Megaplan")
    openproject_id: int = Field(..., description="Идентификатор проекта OpenProject")
    include_closed: bool = Field(False, description="Синхронизировать ли закрытые задачи")


class SyncOptions(BaseModel):
    """Параметры синхронизации."""

    page_size: int = Field(100, description="Размер страницы при выгрузке задач из Megaplan")
    attachment_max_mb: float = Field(200.0, description="Максимальный размер вложения для копирования")
    sync_attachments: bool = Field(True, description="Переносить ли вложенные файлы")
    sync_comments: bool = Field(True, description="Переносить ли комментарии")
    dry_run: bool = Field(False, description="Если True, изменения в OpenProject не выполняются")
    tmp_dir: Path = Field(Path(".sync_tmp"), description="Каталог для временных файлов")

    @field_validator("tmp_dir", mode="before")
    @classmethod
    def _ensure_path(cls, value: Path | str) -> Path:
        return Path(value)


class AppConfig(BaseModel):
    """Корневая конфигурация приложения."""

    megaplan: MegaplanCredentials
    openproject: OpenProjectCredentials
    projects: List[ProjectMapping]
    sync: SyncOptions = Field(default_factory=SyncOptions)
    state_db: Path = Field(Path(".sync_state.sqlite"), description="Путь к SQLite-базе соответствий")

    @field_validator("state_db", mode="before")
    @classmethod
    def _state_db_path(cls, value: Path | str) -> Path:
        return Path(value)

    @classmethod
    def load(cls, path: Path | str) -> "AppConfig":
        """Загружает конфигурацию из YAML-файла."""
        path = Path(path)
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(f"Конфигурация {path} некорректна: {exc}") from exc

    def project_lookup(self) -> Dict[str, ProjectMapping]:
        """Возвращает словарь быстрых соответствий мегаплановских проектов."""
        return {item.megaplan_id: item for item in self.projects}

    def ensure_runtime_dirs(self) -> None:
        """Создаёт недостающие служебные каталоги."""
        self.sync.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.state_db.parent.mkdir(parents=True, exist_ok=True)


__all__ = ["AppConfig", "MegaplanCredentials", "OpenProjectCredentials", "ProjectMapping", "SyncOptions"]
