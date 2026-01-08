"""
Deep Plot WebSocket message handler.

Handles autonomous data analysis with visualization generation.
"""

import asyncio
import json
import uuid

from .base import WebSocketContext, get_session_store, logger


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

    try:
        from ...deep_plot import DeepPlotAgent

        # Stop current agent before starting Deep Plot
        await ctx.stop_current_agent()

        # Track message_id for streaming
        current_message_id = None

        # Event callback that converts agent events to frontend protocol
        async def on_event(event_type: str, event_data: dict):
            """Forward agent events to WebSocket with protocol conversion."""
            nonlocal current_message_id

            if event_type == 'query_start':
                # Generate new message_id for this query
                current_message_id = uuid.uuid4().hex[:12]

            elif event_type == 'text':
                # Convert 'text' event to streaming protocol
                message_id = current_message_id or uuid.uuid4().hex[:12]
                content = event_data.get('content', '')

                # Send text_start
                await ctx.send("text_start", message_id=message_id)

                # Send content in chunks for streaming effect
                chunk_size = 5
                for i in range(0, len(content), chunk_size):
                    chunk = content[i:i + chunk_size]
                    await ctx.send("text_chunk", content=chunk, message_id=message_id)
                    await asyncio.sleep(0.01)

                # Send text_end
                await ctx.send("text_end", message_id=message_id)

            elif event_type == 'tool_use':
                # Frontend expects 'tool_start' with tool_name/tool_input
                message_id = current_message_id or "unknown"
                await ctx.send("tool_start",
                    tool_name=event_data.get('name'),
                    tool_input=event_data.get('input'),
                    message_id=message_id
                )

            elif event_type == 'tool_result':
                # Tool results are not displayed in frontend currently
                pass

            elif event_type == 'plot_show':
                # Forward plot_show with session_name
                await ctx.send("plot_show",
                    session_name="Deep Plot",  # Include name directly
                    **event_data
                )

            elif event_type == 'plot_command':
                # Forward plot_command directly
                await ctx.send(event_type, **event_data)

            elif event_type == 'session_info':
                # Forward session_info to frontend (for immediate tab update)
                await ctx.send("session_info", **event_data)

            elif event_type == 'complete':
                message_id = current_message_id or "unknown"
                await ctx.send("complete",
                    message_id=message_id,
                    stats=event_data
                )

            elif event_type == 'error':
                message_id = current_message_id or "unknown"
                await ctx.send("error",
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
            session_name="Deep Plot"
        )

        logger.info(f"Starting Deep Plot: files={files}, timeout={timeout}s")

        # Run the agent (streaming happens via on_event callback)
        result = await deep_plot_agent.run()

        # Get session_id from result
        session_id = result.get('session_id')

        if session_id:
            # Update session_name in database
            session_store = get_session_store()
            session_store.update_session_metadata(
                session_id=session_id,
                session_name="Deep Plot"
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

        # Send completion with stats
        await ctx.send("deep_plot_complete", result=result)

        logger.info(f"Deep Plot complete: {result}")

    except Exception as e:
        logger.error(f"Deep Plot failed: {e}")
        await ctx.send_error(f"Deep Plot failed: {str(e)}")
