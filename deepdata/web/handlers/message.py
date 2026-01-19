"""
Message handler for user queries.

Handles the main "message" WebSocket message type for agent interactions.
"""

import os
from pathlib import Path

from ..connection import WebConnection
from .base import WebSocketContext, logger


async def handle_message(data: dict, ctx: WebSocketContext) -> None:
    """
    Handle user message - execute query via agent.

    Session info is streamed automatically by WebConnection via agent.events
    when the agent starts or resumes.

    Expected data:
        content: User message text
        new_session: If true, create a new session (user clicked "+")
        session_name: Display name for the session (e.g., "Agent", "Deep Plot")
        cwd: Working directory for the session (only used for new sessions)
    """
    content = data.get("content", "")
    new_session = data.get("new_session", False)
    session_name = data.get("session_name", "Agent")
    custom_cwd = data.get("cwd")  # Optional custom cwd from frontend

    if not content.strip():
        return

    # If new_session requested, create a fresh connection
    if new_session:
        logger.info(f"Creating new session for message (name: {session_name})")
        await ctx.stop_current_agent()

        # Determine cwd: use custom_cwd if provided, otherwise use default
        if custom_cwd:
            # Expand ~ and resolve to absolute path
            expanded = os.path.expanduser(custom_cwd)
            cwd_path = Path(expanded).resolve()

            # Create directory if it doesn't exist (parent must exist - validated by frontend)
            if not cwd_path.exists():
                cwd_path.mkdir(parents=False, exist_ok=True)
                logger.info(f"Created new directory: {cwd_path}")
        else:
            cwd_path = ctx.connection.cwd

        new_conn = WebConnection(
            websocket=ctx.websocket,
            cwd=cwd_path,
            model=ctx.agent_model
        )
        new_conn._session_name = session_name

        ctx.connection = new_conn
        ctx.active_connections[ctx.connection_id] = (ctx.websocket, new_conn)

    # Execute query (streaming handled by WebConnection's event subscriptions)
    # session_info is automatically streamed when SDK assigns session_id
    await ctx.connection.query(content)
