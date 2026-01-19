"""
WebSocket message handlers.

Each handler is an async function with signature:
    async def handle_xxx(data: dict, ctx: WebSocketContext) -> None
"""

from .base import WebSocketContext, get_session_store

from .misc import (
    handle_ping,
    handle_pong,
    handle_get_transcript,
    handle_get_stats,
    handle_rename_session,
)

from .workspace import (
    handle_load_workspace,
    handle_save_workspace,
)

from .message import handle_message

from .session import (
    handle_switch_session,
    handle_activate_session,
)

from .deep_plot import handle_deep_plot
from .test import handle_test_heartbeat

# Handler dispatch table
HANDLERS = {
    "message": handle_message,
    "deep_plot": handle_deep_plot,
    "ping": handle_ping,
    "pong": handle_pong,
    "get_transcript": handle_get_transcript,
    "get_stats": handle_get_stats,
    "switch_session": handle_switch_session,
    "load_workspace": handle_load_workspace,
    "save_workspace": handle_save_workspace,
    "rename_session": handle_rename_session,
    "activate_session": handle_activate_session,
    # Test handlers (triggered via REST API /api/test/heartbeat, not WebSocket)
    "test_heartbeat": handle_test_heartbeat,
}

__all__ = [
    "WebSocketContext",
    "get_session_store",
    "HANDLERS",
    # Individual handlers
    "handle_message",
    "handle_deep_plot",
    "handle_ping",
    "handle_pong",
    "handle_get_transcript",
    "handle_get_stats",
    "handle_switch_session",
    "handle_load_workspace",
    "handle_save_workspace",
    "handle_rename_session",
    "handle_activate_session",
]
