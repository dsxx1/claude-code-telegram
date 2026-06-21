"""Persistent markdown "memory bank" loaded into every Claude session.

The memory bank lets the bot remember durable facts (preferences, decisions,
project context) across Telegram sessions and bot restarts — the same idea as
a CLAUDE.md, but writable by Claude during a session and surfaced/managed from
Telegram.

Two layers:

* **Global** — one shared set of notes for the whole bot, stored under
  ``<approved_directory>/.claude-memory/``. Kept inside ``APPROVED_DIRECTORY``
  on purpose so Claude's own ``Read``/``Write`` tools (which are sandboxed to
  that root) can read and update it.
* **Per-project** — an optional ``memory-bank/`` directory inside the current
  working directory. Loaded only when it exists.

Both layers are concatenated into the system prompt at session start. Existing
documentation ``*.md`` files (CLAUDE.md, README, docs/) are untouched — the
memory bank is purely additive.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List

# Directory (relative to APPROVED_DIRECTORY) holding the global memory bank.
GLOBAL_MEMORY_DIRNAME = ".claude-memory"
# Directory (relative to the working directory) holding per-project memory.
PROJECT_MEMORY_DIRNAME = "memory-bank"
# Primary memory file inside each memory bank.
MAIN_FILE = "MEMORY.md"

# Cap how much memory we inject so a runaway file can't blow the prompt budget.
_MAX_CONTEXT_CHARS = 16000

_TEMPLATE = """# Memory Bank

Долговременная память бота. Сохраняется между сессиями и перезапусками.
Claude читает этот файл в начале каждой сессии и может дописывать сюда
важные факты сам. Можно править вручную или командами /memory и /remember.

## Предпочтения пользователя
<!-- стиль ответов, язык, любимые инструменты и т.п. -->

## Контекст и решения
<!-- важные договорённости, архитектурные решения, статус задач -->

## Заметки
"""


def global_memory_dir(approved_directory: Path) -> Path:
    """Return the global memory-bank directory under the approved root."""
    return Path(approved_directory) / GLOBAL_MEMORY_DIRNAME


def global_memory_file(approved_directory: Path) -> Path:
    """Return the path to the main global memory file."""
    return global_memory_dir(approved_directory) / MAIN_FILE


def ensure_global_memory(approved_directory: Path) -> Path:
    """Create the global memory bank (dir + seeded MEMORY.md) if missing.

    Returns the path to the main memory file.
    """
    directory = global_memory_dir(approved_directory)
    directory.mkdir(parents=True, exist_ok=True)
    main = directory / MAIN_FILE
    if not main.exists():
        main.write_text(_TEMPLATE, encoding="utf-8")
    return main


def _read_md_files(directory: Path, primary: str = MAIN_FILE) -> List[tuple[str, str]]:
    """Read every ``*.md`` file in ``directory`` (primary first).

    Returns a list of ``(filename, text)`` tuples. Missing dir -> empty list.
    """
    if not directory.is_dir():
        return []
    files = sorted(
        directory.glob("*.md"),
        key=lambda p: (p.name != primary, p.name.lower()),
    )
    out: List[tuple[str, str]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if text:
            out.append((path.name, text))
    return out


def load_memory_context(approved_directory: Path, working_directory: Path) -> str:
    """Build the memory-bank block injected into the system prompt.

    Returns an empty string when there is nothing to inject.
    """
    sections: List[str] = []

    for name, text in _read_md_files(global_memory_dir(approved_directory)):
        sections.append(f"### memory-bank (global) · {name}\n{text}")

    project_dir = Path(working_directory) / PROJECT_MEMORY_DIRNAME
    for name, text in _read_md_files(project_dir):
        sections.append(f"### memory-bank (project) · {name}\n{text}")

    if not sections:
        return ""

    body = "\n\n".join(sections)
    if len(body) > _MAX_CONTEXT_CHARS:
        body = body[:_MAX_CONTEXT_CHARS] + "\n…(memory truncated)…"

    instructions = (
        "## Memory Bank\n"
        "Ниже — долговременная память (сохраняется между сессиями). "
        "Учитывай её. Если по ходу работы всплывают устойчивые факты "
        "(предпочтения пользователя, важные решения, статус задач), "
        "которые пригодятся в будущих сессиях — допиши их в файл "
        f"`{GLOBAL_MEMORY_DIRNAME}/{MAIN_FILE}` (или в `{PROJECT_MEMORY_DIRNAME}/` "
        "проекта) инструментами Edit/Write. Не дублируй уже записанное; "
        "не храни секреты и персональные данные.\n\n"
    )
    return instructions + body


def append_global_note(approved_directory: Path, text: str) -> Path:
    """Append a timestamped bullet to the global memory file.

    Creates the memory bank first if it does not exist. Returns the file path.
    """
    main = ensure_global_memory(approved_directory)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    note = text.strip().replace("\n", " ")
    existing = main.read_text(encoding="utf-8").rstrip()
    main.write_text(f"{existing}\n- [{stamp}] {note}\n", encoding="utf-8")
    return main


def read_all_memory(approved_directory: Path, working_directory: Path) -> str:
    """Return a human-readable dump of all memory for the /memory command."""
    parts: List[str] = []
    for name, text in _read_md_files(global_memory_dir(approved_directory)):
        parts.append(f"📌 global · {name}\n{text}")
    project_dir = Path(working_directory) / PROJECT_MEMORY_DIRNAME
    for name, text in _read_md_files(project_dir):
        parts.append(f"📁 project · {name}\n{text}")
    return "\n\n".join(parts)
