"""
Session management WebSocket message handlers.

Handlers for switching and activating agent sessions.
"""

from ..connection import WebConnection, update_connection_websocket
from .base import WebSocketContext, get_session_store, logger
from .deep_plot import update_deep_plot_websocket
from .test import update_heartbeat_websocket


async def handle_switch_session(data: dict, ctx: WebSocketContext) -> None:
    """
    Handle switch_session message - switch to a different session.

    Stops current agent, creates new connection for the target session,
    starts the agent (resuming the session), and sends conversation history.

    Expected data:
        session_id: Session ID to switch to
    """
    switch_session_id = data.get("session_id")

    if not switch_session_id:
        logger.warning("switch_session message missing session_id")
        return

    logger.info(f"Switching to session: {switch_session_id}")

    # Stop current agent
    await ctx.stop_current_agent()

    # Get session name from database
    session_name = "Agent"  # Default
    try:
        session_store = get_session_store()
        session_info = session_store.get_session_info(switch_session_id)
        session_name = session_info.session_name
    except:
        pass  # Use default if session not found

    # Create new connection for the session
    new_conn = WebConnection(
        websocket=ctx.websocket,
        cwd=ctx.connection.cwd,
        resume_session_id=switch_session_id,
        model=ctx.agent_model
    )
    new_conn._session_name = session_name

    # Update context
    ctx.connection = new_conn
    ctx.active_connections[ctx.connection_id] = (ctx.websocket, new_conn)

    # Start agent (resume session)
    await new_conn.ensure_agent(session_name=session_name)

    # Send session info
    await ctx.send(
        "session_info",
        session_id=switch_session_id,
        session_name=session_name
    )

    # Send conversation history
    conversation_history = new_conn.get_conversation_history()
    if conversation_history:
        await ctx.send("conversation_history", blocks=conversation_history)

    # Send session stats (cost, duration, turns)
    try:
        session_store = get_session_store()
        session_info = session_store.get_session_info(switch_session_id)
        num_turns = max((b.get('turn_number', 0) for b in conversation_history), default=0)
        await ctx.send(
            "session_stats",
            stats={
                "total_cost_usd": session_info.total_cost_usd,
                "duration_ms": session_info.duration_ms,
                "num_turns": num_turns,
                "usage": {
                    "input_tokens": session_info.input_tokens,
                    "output_tokens": session_info.output_tokens
                }
            }
        )
    except Exception as e:
        logger.warning(f"Failed to send session stats: {e}")

    # Send global workspace UI state (include cwd info)
    from .workspace import get_cwd_info
    workspace = ctx.workspace_manager.load_workspace()
    await ctx.send("workspace_loaded", workspace=workspace, cwd=get_cwd_info())


async def handle_activate_session(data: dict, ctx: WebSocketContext) -> None:
    """
    Handle activate_session message - activate an existing session.

    Loads conversation history WITHOUT resuming agent (avoids SDK timeout).
    Agent will be created when user sends next query.

    Expected data:
        session_id: Session ID to activate
    """
    import json

    session_id_to_activate = data.get("session_id")

    if not session_id_to_activate:
        logger.warning("activate_session missing session_id")
        return

    try:
        # NOTE: We intentionally do NOT stop the current agent here.
        # If a query is running, it continues in the background.
        # Events from that query are tagged with session_id and filtered by frontend.
        # This allows users to switch tabs without interrupting long-running queries.

        # Load history directly from database (don't start agent yet)
        session_store = get_session_store()
        conversation_history = session_store.get_conversation(session_id_to_activate)

        logger.info(f"Activated session: {session_id_to_activate} ({len(conversation_history)} blocks)")

        # Check for deep_plot_report.json for Deep Plot sessions
        deep_plot_report = None
        try:
            session_info = session_store.get_session_info(session_id_to_activate)
            report_path = session_info.folder_path / "deep_plot_report.json"
            if report_path.exists():
                deep_plot_report = json.loads(report_path.read_text(encoding='utf-8'))
                logger.info(f"Loaded deep_plot_report.json for session {session_id_to_activate}")
        except Exception as e:
            logger.warning(f"Failed to load deep_plot_report.json: {e}")

        # Send conversation history to frontend (always send, even if empty, to signal loading complete)
        await ctx.send("conversation_history", blocks=conversation_history)

        # Check if there's a running agent/deep_plot/test for this session and re-attach WebSocket
        # This allows resuming streaming after WebSocket reconnection
        if update_deep_plot_websocket(session_id_to_activate, ctx):
            # Running Deep Plot analysis
            await ctx.send("deep_plot_running", session_id=session_id_to_activate)
            logger.info(f"Re-attached WebSocket to running Deep Plot: {session_id_to_activate}")
        elif update_connection_websocket(session_id_to_activate, ctx.websocket):
            # Running regular agent query
            await ctx.send("agent_running", session_id=session_id_to_activate)
            logger.info(f"Re-attached WebSocket to running agent: {session_id_to_activate}")
        elif update_heartbeat_websocket(session_id_to_activate, ctx):
            # Running heartbeat test
            await ctx.send("heartbeat_running", session_id=session_id_to_activate)
            logger.info(f"Re-attached WebSocket to running heartbeat test: {session_id_to_activate}")

        # Send session stats and current_cwd
        try:
            session_info = session_store.get_session_info(session_id_to_activate)
            num_turns = max((b.get('turn_number', 0) for b in conversation_history), default=0)
            await ctx.send(
                "session_stats",
                stats={
                    "total_cost_usd": session_info.total_cost_usd,
                    "duration_ms": session_info.duration_ms,
                    "num_turns": num_turns,
                    "usage": {
                        "input_tokens": session_info.input_tokens,
                        "output_tokens": session_info.output_tokens
                    }
                },
                current_cwd=session_info.current_cwd
            )
        except Exception as e:
            logger.warning(f"Failed to send session stats: {e}")

        # Send deep_plot_complete if this was a Deep Plot session
        if deep_plot_report:
            await ctx.send(
                "deep_plot_complete",
                result={
                    'summary': deep_plot_report.get('summary', ''),
                    'evidence_plots': deep_plot_report.get('evidence_plots', []),
                    'session_id': session_id_to_activate
                }
            )

        # Create new connection configured for resume
        # When user sends a query, it will resume the session
        new_conn = WebConnection(
            websocket=ctx.websocket,
            cwd=ctx.connection.cwd,
            resume_session_id=session_id_to_activate,
            model=ctx.agent_model
        )

        # Update context
        ctx.connection = new_conn
        ctx.active_connections[ctx.connection_id] = (ctx.websocket, new_conn)

    except Exception as e:
        logger.error(f"Failed to activate session: {e}")
        # Send empty conversation_history to signal loading complete (even on error)
        await ctx.send("conversation_history", blocks=[])
        await ctx.send_error(f"Failed to activate session: {str(e)}")
