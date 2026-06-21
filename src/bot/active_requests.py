"""Cross-mode in-flight request registry used for /stop interruption.

Both the classic and agentic text handlers register their running Claude
call here so any command (/stop, the ⏹ Стоп keyboard button, or the
inline-Stop callback) can interrupt it. The registry itself is a plain
dict shared via ``context.bot_data``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict

# Key under which the registry lives inside python-telegram-bot's
# Application.bot_data dict.
ACTIVE_REQUESTS_KEY = "active_requests"


@dataclass
class ActiveRequest:
    """An in-flight Claude request that can be interrupted."""

    user_id: int
    interrupt_event: asyncio.Event = field(default_factory=asyncio.Event)
    interrupted: bool = False
    progress_msg: Any = None  # telegram Message object


def get_registry(bot_data: Dict[str, Any]) -> Dict[int, ActiveRequest]:
    """Return the shared registry, creating it on first access."""
    registry = bot_data.get(ACTIVE_REQUESTS_KEY)
    if registry is None:
        registry = {}
        bot_data[ACTIVE_REQUESTS_KEY] = registry
    return registry


async def interrupt_request(
    registry: Dict[int, ActiveRequest], user_id: int
) -> str:
    """Interrupt a running request.

    Returns one of: ``"interrupted"``, ``"already_stopping"``, ``"none"``.
    Safe to call from any handler.
    """
    active = registry.get(user_id)
    if not active:
        return "none"
    if active.interrupted:
        return "already_stopping"

    active.interrupt_event.set()
    active.interrupted = True
    try:
        if active.progress_msg is not None:
            await active.progress_msg.edit_text("Stopping...", reply_markup=None)
    except Exception:
        pass
    return "interrupted"
