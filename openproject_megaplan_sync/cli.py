"""CLI-интерфейс для запуска миграции."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from dateutil import parser

from openproject_megaplan_sync.clients import MegaplanClient, OpenProjectClient
from openproject_megaplan_sync.config import AppConfig
from openproject_megaplan_sync.services.mapping_store import MappingStore
from openproject_megaplan_sync.services.sync import TaskSyncService

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

app = typer.Typer(help="Миграция задач Megaplan → OpenProject")


def configure_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format=LOG_FORMAT)


def build_service(
    config_path: Path, *, dry_run_override: Optional[bool] = None
) -> tuple[TaskSyncService, MappingStore]:
    config = AppConfig.load(config_path)
    if dry_run_override is not None:
        config.sync.dry_run = dry_run_override
    config.ensure_runtime_dirs()
    mapping_store = MappingStore(config.state_db)
    megaplan = MegaplanClient(config.megaplan)
    openproject = OpenProjectClient(config.openproject)
    service = TaskSyncService(config, megaplan, openproject, mapping_store)
    return service, mapping_store


@app.command("initial-sync")
def initial_sync(
    config_path: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="Путь к YAML конфигурации"),
    verbosity: int = typer.Option(0, "--verbose", "-v", count=True, help="Уровень логирования"),
    dry_run: Optional[bool] = typer.Option(
        None,
        "--dry-run/--no-dry-run",
        help="Переносить данные в режиме dry-run (по умолчанию берётся из конфигурации)",
    ),
) -> None:
    """Полная миграция всех задач проектов, указанных в конфиге."""
    configure_logging(verbosity)
    service, store = build_service(config_path, dry_run_override=dry_run)
    try:
        stats = service.initial_migration()
        typer.echo(json.dumps({k: vars(v) for k, v in stats.items()}, indent=2, ensure_ascii=False))
    finally:
        store.close()


@app.command("sync-updates")
def sync_updates(
    since: Optional[str] = typer.Option(None, help="ISO-время, с которого забирать изменения"),
    config_path: Path = typer.Option(Path("config.yaml"), "--config", "-c"),
    verbosity: int = typer.Option(0, "--verbose", "-v", count=True),
    dry_run: Optional[bool] = typer.Option(
        None,
        "--dry-run/--no-dry-run",
        help="Переносить данные в режиме dry-run (по умолчанию берётся из конфигурации)",
    ),
) -> None:
    """Инкрементальная синхронизация задач."""
    configure_logging(verbosity)
    service, store = build_service(config_path, dry_run_override=dry_run)
    try:
        since_dt = parser.isoparse(since) if since else None
        stats = service.incremental_sync(since=since_dt)
        typer.echo(json.dumps({k: vars(v) for k, v in stats.items()}, indent=2, ensure_ascii=False))
    finally:
        store.close()


@app.command("verify")
def verify(
    config_path: Path = typer.Option(Path("config.yaml"), "--config", "-c"),
    verbosity: int = typer.Option(0, "--verbose", "-v", count=True),
) -> None:
    """Проверяет соединение с API и базовую конфигурацию."""
    configure_logging(verbosity)
    config = AppConfig.load(config_path)
    config.ensure_runtime_dirs()
    megaplan = MegaplanClient(config.megaplan)
    openproject = OpenProjectClient(config.openproject)
    store = MappingStore(config.state_db)
    try:
        megaplan.authenticate()
        openproject._request("GET", "/api/v3/projects")  # noqa: SLF001 - тест запроса
        typer.echo("Соединение успешно")
    finally:
        store.close()


if __name__ == "__main__":
    app()
