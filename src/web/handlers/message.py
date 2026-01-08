"""
Message handler for user queries.

Handles the main "message" WebSocket message type for agent interactions.
"""

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
    """
    content = data.get("content", "")
    new_session = data.get("new_session", False)
    session_name = data.get("session_name", "Agent")

    if not content.strip():
        return

    # If new_session requested, create a fresh connection
    if new_session:
        logger.info(f"Creating new session for message (name: {session_name})")
        await ctx.stop_current_agent()

        new_conn = WebConnection(
            websocket=ctx.websocket,
            cwd=ctx.connection.cwd,
            model=ctx.agent_model
        )
        new_conn._session_name = session_name

        ctx.connection = new_conn
        ctx.active_connections[ctx.connection_id] = (ctx.websocket, new_conn)

    # Execute query (streaming handled by WebConnection's event subscriptions)
    # session_info is automatically streamed when SDK assigns session_id
    await ctx.connection.query(content)
