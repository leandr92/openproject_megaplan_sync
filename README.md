# openproject-megaplan-sync

Python-инструмент для миграции задач из Megaplan в OpenProject с учётом иерархии, авторов, комментариев и вложений.

## Возможности
- Разовая миграция задач по заданным проектам.
- Инкрементальная синхронизация новых и изменённых задач до полного перехода.
- Перенос комментариев и файлов (с ограничением по размеру).
- Иллюстрация соответствий идентификаторов в SQLite для повторного запуска и отчётности.

Архитектурная схема описана в `docs/architecture.md`.

## Быстрый старт
1. Скопируйте `config.example.yaml` в `config.yaml` и заполните доступы к Megaplan и OpenProject.
2. Установите зависимости через Pipenv (включая dev-пакеты):
   ```bash
   pipenv install --dev
   ```
3. (Опционально) активируйте окружение `pipenv shell` или используйте `pipenv run` для запуска команд.
4. Проверьте соединение с API:
   ```bash
   pipenv run cli verify --config config.yaml -v
   ```
5. Запустите первичную миграцию (для тестового прогона добавьте `--dry-run`):
   ```bash
   pipenv run cli initial-sync --config config.yaml --dry-run -v
   ```
6. Для периодической синхронизации вызывайте (аналогично можно добавить `--dry-run`):
   ```bash
   pipenv run cli sync-updates --config config.yaml --since 2024-01-01T00:00:00
   ```
7. Чтобы узнать идентификаторы проектов, используйте вспомогательный скрипт:
   ```bash
   pipenv run python scripts/list_projects.py --config config.yaml --source both
   ```

## Конфигурация
Основные параметры описаны в разделе `config.example.yaml`:
- `megaplan.username` / `megaplan.password` — учётные данные для Basic Auth в Megaplan.
- `openproject.username` / `openproject.password` — логин и пароль (или токен) для Basic Auth в OpenProject.
- `projects` — список соответствий проектов Megaplan → OpenProject.
- `sync.dry_run` — если `true`, изменения не отправляются в OpenProject, используется для теста.
- `sync.attachment_max_mb` — ограничение на размеры файлов.
- `state_db` — путь к SQLite-файлу для хранения соответствий.

## Расширение
- Таблицы статусов и типов задач можно добавить через расширение `TaskMapper` (см. `services/task_mapper.py`).
- При необходимости поддержать другие сущности (например, подзадачи, зависимости) добавьте соответствующие сервисы и сохранение в `MappingStore`.

## Ограничения
- Скрипт предполагает наличие прав на создание пользователей в OpenProject (или задайте `default_user_id`).
- Конкретные поля Megaplan могут отличаться: при необходимости адаптируйте маппер (`TaskMapper`).
- В коде нет автоматических повторов при ошибках API; добавьте обработку при интеграции.

## Структура проекта
```
openproject_megaplan_sync/
├── clients/          # HTTP-клиенты для Megaplan и OpenProject
├── models/           # Доменные dataclass-модели
├── services/         # Логика синхронизации и хранилище соответствий
├── cli.py            # Точки входа CLI
└── config.py         # Загрузка конфигурации
```

