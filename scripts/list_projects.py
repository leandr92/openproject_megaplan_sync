"""Утилита для получения списков проектов Megaplan и OpenProject."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openproject_megaplan_sync.clients import MegaplanClient, OpenProjectClient
from openproject_megaplan_sync.config import AppConfig


def _format_table(title: str, rows: Iterable[Tuple[str, str]]) -> str:
    rows = list(rows)
    if not rows:
        return f"{title}: нет данных"
    id_width = max(len(r[0]) for r in rows)
    name_width = max(len(r[1]) for r in rows)
    header = (
        f"{title}:\n"
        f"  {'ID'.ljust(id_width)}  |  {'Name'.ljust(name_width)}\n"
        f"  {'-' * id_width}--+-{'-' * name_width}"
    )
    body = "\n".join(f"  {proj_id.ljust(id_width)}  |  {name}" for proj_id, name in rows)
    return f"{header}\n{body}"


def collect_megaplan_projects(client: MegaplanClient, limit: int) -> list[Tuple[str, str]]:
    client.authenticate()
    projects = []
    for item in client.iter_projects(limit=limit):
        proj_id = str(item.get("id") or item.get("Id") or item.get("uuid") or "")
        name = str(item.get("name") or item.get("Name") or "")
        projects.append((proj_id, name))
    return projects


def collect_openproject_projects(client: OpenProjectClient, page_size: int) -> list[Tuple[str, str]]:
    projects = []
    for element in client.iter_projects(page_size=page_size):
        proj_id = str(element.get("id") or "")
        name = str(element.get("name") or element.get("identifier") or "")
        projects.append((proj_id, name))
    return projects


def main() -> None:
    parser = argparse.ArgumentParser(description="Выводит списки проектов из Megaplan и/или OpenProject")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Путь к YAML конфигурации",
    )
    parser.add_argument(
        "--source",
        choices=["megaplan", "openproject", "both"],
        default="both",
        help="Какие проекты вывести",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Размер страницы при запросе проектов Megaplan",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=50,
        help="Размер страницы при запросе проектов OpenProject",
    )
    args = parser.parse_args()

    config = AppConfig.load(args.config)

    outputs: list[str] = []
    if args.source in ("megaplan", "both"):
        megaplan_client = MegaplanClient(config.megaplan)
        projects = collect_megaplan_projects(megaplan_client, limit=args.limit)
        outputs.append(_format_table("Megaplan projects", projects))

    if args.source in ("openproject", "both"):
        openproject_client = OpenProjectClient(config.openproject)
        projects = collect_openproject_projects(openproject_client, page_size=args.page_size)
        outputs.append(_format_table("OpenProject projects", projects))

    print("\n\n".join(outputs))


if __name__ == "__main__":
    main()
