"""
Deep Plot WebSocket message handler.

Handles autonomous data analysis with visualization generation.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Optional

from .base import WebSocketContext, get_session_store, logger


@dataclass
class RunningDeepPlot:
    """Tracks a running Deep Plot analysis for WebSocket reconnection."""
    session_id: str
    ctx: WebSocketContext  # Mutable - updated on reconnect
    current_message_id: Optional[str] = None


# Registry of running Deep Plot analyses by session_id
# Allows reconnecting WebSocket to resume streaming
_running_deep_plots: dict[str, RunningDeepPlot] = {}


def get_running_deep_plot(session_id: str) -> Optional[RunningDeepPlot]:
    """Get running Deep Plot for a session (if any)."""
    return _running_deep_plots.get(session_id)


def update_deep_plot_websocket(session_id: str, ctx: WebSocketContext) -> bool:
    """
    Update the WebSocket context for a running Deep Plot.

    Called when user reconnects to a session with running analysis.
    Returns True if there was a running Deep Plot to update.
    """
    running = _running_deep_plots.get(session_id)
    if running:
        logger.info(f"Re-attaching WebSocket to running Deep Plot: {session_id}")
        running.ctx = ctx
        return True
    return False


async def handle_deep_plot(data: dict, ctx: WebSocketContext) -> None:
    """
    Handle deep_plot message - run autonomous Deep Plot analysis.

    DeepPlotAgent creates Agent directly. We provide an on_event callback
    to forward streaming events to the WebSocket.

    Expected data:
        files: List of file names to analyze (optional - if empty, agent explores cwd)
        timeout: Timeout in seconds (default: 120)
        prompt: Optional user prompt for analysis direction
    """
    files = data.get("files", [])
    timeout = data.get("timeout", 120)
    prompt = data.get("prompt", "")
    session_name = data.get("session_name", "Deep Plot")  # Unique name from frontend

    # Create a placeholder for tracking this running analysis
    # session_id will be set once the agent starts
    running_state = RunningDeepPlot(session_id="", ctx=ctx)

    try:
        from ...deep_plot import DeepPlotAgent

        # Stop current agent before starting Deep Plot
        await ctx.stop_current_agent()

        # Event callback that converts agent events to frontend protocol
        # Uses running_state.ctx which can be updated on reconnect
        async def on_event(event_type: str, event_data: dict):
            """Forward agent events to WebSocket with protocol conversion."""
            # Use the mutable ctx from running_state (updated on reconnect)
            current_ctx = running_state.ctx

            if event_type == 'query_start':
                # Generate new message_id for this query
                running_state.current_message_id = uuid.uuid4().hex[:12]

            elif event_type == 'text':
                # Convert 'text' event to streaming protocol
                message_id = running_state.current_message_id or uuid.uuid4().hex[:12]
                content = event_data.get('content', '')

                # Send text_start
                await current_ctx.send("text_start", message_id=message_id)

                # Send content in chunks for streaming effect
                chunk_size = 5
                for i in range(0, len(content), chunk_size):
                    chunk = content[i:i + chunk_size]
                    await current_ctx.send("text_chunk", content=chunk, message_id=message_id)
                    await asyncio.sleep(0.01)

                # Send text_end
                await current_ctx.send("text_end", message_id=message_id)

            elif event_type == 'tool_use':
                # Frontend expects 'tool_start' with tool_name/tool_input
                message_id = running_state.current_message_id or "unknown"
                await current_ctx.send("tool_start",
                    tool_name=event_data.get('name'),
                    tool_input=event_data.get('input'),
                    message_id=message_id
                )

            elif event_type == 'tool_result':
                # Tool results are not displayed in frontend currently
                pass

            elif event_type == 'plot_show':
                # Forward plot_show - session_name comes from event_data (set by agent)
                logger.info(f"Forwarding plot_show to WebSocket: plot_id={event_data.get('plot_id')}")
                await current_ctx.send("plot_show", **event_data)
                logger.info(f"Forwarded plot_show: plot_id={event_data.get('plot_id')}")

            elif event_type == 'plot_command':
                # Forward plot_command directly
                await current_ctx.send(event_type, **event_data)

            elif event_type == 'session_info':
                # Register in running registry now that we have session_id
                session_id = event_data.get('session_id')
                if session_id:
                    running_state.session_id = session_id
                    _running_deep_plots[session_id] = running_state
                    logger.info(f"Registered running Deep Plot: {session_id}")
                # Forward session_info to frontend (for immediate tab update)
                await current_ctx.send("session_info", **event_data)

            elif event_type == 'plots_renumbered':
                # Forward plots_renumbered to frontend (for cache invalidation)
                await current_ctx.send("plots_renumbered", **event_data)

            elif event_type == 'complete':
                message_id = running_state.current_message_id or "unknown"
                await current_ctx.send("complete",
                    message_id=message_id,
                    stats=event_data
                )

            elif event_type == 'error':
                message_id = running_state.current_message_id or "unknown"
                await current_ctx.send("error",
                    error=event_data.get('error'),
                    message_id=message_id
                )

        # Create Deep Plot agent directly (no WebConnection needed)
        deep_plot_agent = DeepPlotAgent(
            cwd=ctx.connection.cwd,
            data_files=files,
            timeout_seconds=timeout,
            user_prompt=prompt,
            on_event=on_event,
            model=ctx.agent_model,
            session_name=session_name  # Use unique name from frontend
        )

        logger.info(f"Starting Deep Plot: files={files}, timeout={timeout}s")

        # Run the agent (streaming happens via on_event callback)
        result = await deep_plot_agent.run()

        # Get session_id from result
        session_id = result.get('session_id')

        if session_id:
            # Update session_name in database (use unique name from frontend)
            session_store = get_session_store()
            session_store.update_session_metadata(
                session_id=session_id,
                session_name=session_name
            )

            # Save deep_plot_report.json for resume support
            if result.get('summary'):
                session_info = session_store.get_session_info(session_id)
                report_path = session_info.folder_path / "deep_plot_report.json"
                try:
                    report_data = {
                        'summary': result.get('summary', ''),
                        'evidence_plots': result.get('evidence_plots', [])
                    }
                    report_path.write_text(json.dumps(report_data, indent=2), encoding='utf-8')
                    logger.info(f"Saved deep_plot_report.json to {report_path}")
                except Exception as e:
                    logger.warning(f"Failed to save deep_plot_report.json: {e}")

            # Note: session_info is sent early via on_event callback in DeepPlotAgent
            # This allows frontend to update pending tab before streaming completes

        # Send completion with stats (use current ctx from running_state)
        await running_state.ctx.send("deep_plot_complete", result=result)

        logger.info(f"Deep Plot complete: {result}")

    except Exception as e:
        logger.error(f"Deep Plot failed: {e}")
        await running_state.ctx.send_error(f"Deep Plot failed: {str(e)}")

    finally:
        # Remove from running registry
        if running_state.session_id and running_state.session_id in _running_deep_plots:
            del _running_deep_plots[running_state.session_id]
            logger.info(f"Unregistered running Deep Plot: {running_state.session_id}")
