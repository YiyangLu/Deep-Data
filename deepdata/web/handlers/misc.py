"""
Miscellaneous WebSocket message handlers.

Simple handlers for ping, transcript, stats, and rename_session.
"""

from .base import WebSocketContext, get_session_store, logger


async def handle_ping(data: dict, ctx: WebSocketContext) -> None:
    """Handle ping message - respond with pong."""
    await ctx.send("pong")


async def handle_pong(data: dict, ctx: WebSocketContext) -> None:
    """Handle pong message - client responded to our ping, connection is alive."""
    # No action needed - the fact we received this confirms the connection is alive
    pass


async def handle_get_transcript(data: dict, ctx: WebSocketContext) -> None:
    """Handle get_transcript message - return full agent transcript."""
    if ctx.connection.agent:
        transcript = ctx.connection.agent.transcript
    else:
        transcript = ""
    await ctx.send("transcript", content=transcript)


async def handle_get_stats(data: dict, ctx: WebSocketContext) -> None:
    """Handle get_stats message - return agent statistics."""
    stats = ctx.connection.get_stats()
    await ctx.send("stats", **stats)


async def handle_rename_session(data: dict, ctx: WebSocketContext) -> None:
    """
    Handle rename_session message - update session name in database.

    Expected data:
        session_id: Session to rename
        new_name: New name for the session
    """
    rename_session_id = data.get("session_id")
    new_name = data.get("new_name")

    if not rename_session_id or not new_name:
        logger.warning("rename_session missing session_id or new_name")
        await ctx.send(
            "rename_session_result",
            success=False,
            error="Missing session_id or new_name"
        )
        return

    try:
        session_store = get_session_store()

        # NO BACKEND DEDUPLICATION
        # Store raw name - UI handles deduplication at render time
        # This aligns with agent tabs design (UI-only deduplication)
        clean_name = new_name.strip()

        # Update session name in database
        session_store.update_session_metadata(
            rename_session_id,
            session_name=clean_name
        )

        logger.info(f"Renamed session {rename_session_id} to '{clean_name}'")

        await ctx.send(
            "rename_session_result",
            success=True,
            session_id=rename_session_id,
            session_name=clean_name
        )

    except Exception as e:
        logger.error(f"Failed to rename session: {e}")
        await ctx.send(
            "rename_session_result",
            success=False,
            error=str(e)
        )
