"""
list_sessions.py — показывает последние сессии Claude Code с описанием первого сообщения.
Использование:
  python list_sessions.py            # последние 15 сессий всех проектов
  python list_sessions.py --n 20     # последние 20
  python list_sessions.py --resume <UUID>  # вывести команду для возобновления
"""
import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Фикс кириллицы в консоли Windows (cp1251 → utf-8)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Читабельные имена папок проектов: ~/claude-tg/sessions-names.json
# ({"<slug>": "имя", "<slug>": null} — null скрывает папку из списка).
PROJECT_LABELS = {}
try:
    PROJECT_LABELS = json.loads(
        (Path.home() / "claude-tg" / "sessions-names.json").read_text(
            encoding="utf-8"
        )
    )
except Exception:
    pass


def get_first_message(jsonl_path: Path) -> str:
    """Читает первое пользовательское сообщение из .jsonl файла."""
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if (
                        entry.get("type") == "queue-operation"
                        and entry.get("operation") == "enqueue"
                        and entry.get("content")
                    ):
                        content = entry["content"]
                        # Обрезаем до 80 символов
                        content = content.replace("\n", " ").strip()
                        if len(content) > 80:
                            content = content[:77] + "..."
                        return content
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return "(нет текста)"


def list_sessions(n: int = 15):
    """Собирает все сессии, сортирует по дате изменения, выводит последние n."""
    sessions = []

    if not PROJECTS_DIR.exists():
        print(f"Папка не найдена: {PROJECTS_DIR}")
        return []

    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        label = PROJECT_LABELS.get(project_dir.name, project_dir.name)
        for jsonl in project_dir.glob("*.jsonl"):
            mtime = jsonl.stat().st_mtime
            sessions.append((mtime, jsonl, label))

    # Сортируем: новые сверху
    sessions.sort(key=lambda x: x[0], reverse=True)
    sessions = sessions[:n]

    print(f"{'#':<3} {'Дата':<17} {'Проект':<22} {'Первое сообщение'}")
    print("-" * 95)
    for i, (mtime, path, label) in enumerate(sessions, 1):
        dt = datetime.fromtimestamp(mtime).strftime("%d.%m.%Y %H:%M")
        uuid = path.stem
        first_msg = get_first_message(path)
        print(f"{i:<3} {dt:<17} {label:<22} {first_msg}")
        print(f"    UUID: {uuid}")
        print()

    return sessions


def show_resume_command(uuid: str):
    """Показывает команду для возобновления сессии."""
    print(f"Команда для возобновления сессии {uuid}:")
    print(f'  claude --resume {uuid} -p "твой запрос"')
    print()
    print("Или через бота — напиши в Telegram:")
    print(f"  /resume {uuid}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Список сессий Claude Code")
    parser.add_argument("--n", type=int, default=15, help="Количество сессий (по умолч. 15)")
    parser.add_argument("--resume", type=str, help="UUID сессии для возобновления")
    args = parser.parse_args()

    if args.resume:
        show_resume_command(args.resume)
    else:
        list_sessions(args.n)
