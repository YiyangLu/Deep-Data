"""
Agent-friendly tools for plotly visualization and interaction analysis.

This module provides high-level functions for agents to:
1. Create and display plots (show_plot)
2. Query user interaction data (query_interactions, get_plot_image)
3. Interact with plots (relayout, legendclick, selected)

Design Philosophy:
- Simple, robust APIs for agent use
- Auto-manage server lifecycle
- Clear return types for agent parsing
- Events emitted through current agent's events emitter or event bus
"""

from dataclasses import dataclass
from typing import Any

import requests

from .client import check_server_status, start_server, upload_plot, PlotlyClientError
from ..config import get_plot_url, SERVER_PORT, PLOTLY_BASE_PATH
from ..core.event_bus import get_event_bus
from ..core.agent_context import get_current_agent
from ..core.session_registry import get_current_session
from ..utils.logging import create_logger
from ..utils.async_helpers import run_sync_in_thread

logger = create_logger(__name__)


class PlotlyToolError(Exception):
    """Raised when plotly tool operations fail."""
    pass


@dataclass
class SessionContext:
    """Bundle of session information needed for plot operations."""
    store: Any  # SessionStore
    session_id: str
    session_name: str | None


def _get_session_context() -> SessionContext:
    """
    Get current session context with all needed information.

    Returns:
        SessionContext with store, session_id, and session_name

    Raises:
        PlotlyToolError: If no active session
    """
    session_store, session_id = get_current_session()

    if not session_store or not session_id:
        raise PlotlyToolError(
            "No active session. Plot operations require an active session."
        )

    # Get session_name from database (authoritative source)
    session_name = None
    try:
        session_info = session_store.get_session_info(session_id)
        session_name = session_info.session_name
    except Exception as e:
        logger.warning(f"Failed to get session_name: {e}")

    return SessionContext(
        store=session_store,
        session_id=session_id,
        session_name=session_name
    )


async def _emit_event(event_type: str, data: dict):
    """
    Emit event to current agent or fallback to event bus.

    Uses agent context if available (preferred), otherwise falls back
    to global event bus for backward compatibility.
    """
    agent = get_current_agent()
    if agent:
        await agent.events.emit(event_type, data)
        logger.debug(f"Event '{event_type}' emitted via agent.events")
    else:
        await get_event_bus().publish(event_type, data)
        logger.debug(f"Event '{event_type}' emitted via event_bus")


async def _emit_plot_command(ctx: SessionContext, plot_id: int, command: str, args: dict):
    """
    Emit a plot_command event with session context.

    Args:
        ctx: Session context
        plot_id: Target plot ID
        command: Command name (relayout, legendclick, selected)
        args: Command arguments
    """
    await _emit_event('plot_command', {
        'session_id': ctx.session_id,
        'session_name': ctx.session_name,
        'plot_id': plot_id,
        'command': command,
        'args': args
    })


async def show_plot(plotly_codes: str, plot_id: int | None = None) -> tuple[int, str]:
    """
    Execute plotly code and display in capture server.

    This is the main function agents should use to create visualizations.
    It handles server lifecycle automatically and returns tracking information.

    Args:
        plotly_codes: Python code string that creates a plotly figure.
                     Must define a variable named 'fig' containing the plot.
        plot_id: Optional plot ID to overwrite. If None, creates new plot.
                 Use this to update an existing plot instead of creating a new one.

    Returns:
        tuple[int, str]: (plot_id, url)

    Raises:
        PlotlyToolError: If code execution fails, server issues, or upload fails

    Example:
        >>> # Create new plot
        >>> code = '''
        ... import plotly.express as px
        ... df = px.data.iris()
        ... fig = px.scatter(df, x='sepal_width', y='sepal_length')
        ... '''
        >>> plot_id, url = await show_plot(code)
        >>>
        >>> # Update existing plot
        >>> updated_code = '''
        ... import plotly.express as px
        ... df = px.data.iris()
        ... fig = px.scatter(df, x='petal_width', y='petal_length')
        ... '''
        >>> plot_id, url = await show_plot(updated_code, plot_id=1)
    """
    logger.debug(f"show_plot() called with code length: {len(plotly_codes)}")

    # Ensure server is running
    try:
        if not await check_server_status():
            logger.info("Starting plotly capture server...")
            await start_server(wait_for_ready=True, timeout=10.0)
    except PlotlyClientError as e:
        raise PlotlyToolError(f"Failed to start capture server: {e}") from e

    # Execute plotly code to create figure
    try:
        exec_namespace = {}
        exec_namespace['__builtins__'] = (
            __builtins__.copy() if isinstance(__builtins__, dict)
            else {k: getattr(__builtins__, k) for k in dir(__builtins__)}
        )

        # Suppress fig.show() during execution
        import plotly.io as pio
        original_show = pio.show
        pio.show = lambda *_args, **_kwargs: None

        try:
            exec(plotly_codes, exec_namespace)
        finally:
            pio.show = original_show

        if 'fig' not in exec_namespace:
            raise PlotlyToolError(
                "No 'fig' variable defined. Ensure code creates a 'fig' variable."
            )
        fig = exec_namespace['fig']

    except SyntaxError as e:
        raise PlotlyToolError(f"Syntax error at line {e.lineno}: {e.msg}") from e
    except PlotlyToolError:
        raise
    except Exception as e:
        raise PlotlyToolError(f"Code execution failed: {e}") from e

    # Get session context
    ctx = _get_session_context()

    # Upload figure to server
    try:
        response = await upload_plot(fig, session_id=ctx.session_id, plot_id=plot_id)
        result_plot_id = response.get('plot_id')
        if result_plot_id is None:
            raise PlotlyToolError(f"Server did not return plot_id: {response}")

        url = response.get('url') or get_plot_url(result_plot_id)
        is_update = response.get('updated', False)
        action = "updated" if is_update else "created"
        logger.info(f"Plot {action}: ID={result_plot_id}, session={ctx.session_id}")

        # Log plot to storage
        if ctx.store:
            try:
                ctx.store.log_plot(
                    session_id=ctx.session_id,
                    plot_id=result_plot_id,
                    plotly_code=plotly_codes,
                    fig_json=fig.to_json()
                )

                # Generate init screenshot server-side using Kaleido
                # This captures the initial plot state for later reference
                # and eliminates complex frontend screenshot timing issues
                # Note: We generate init screenshot for both new AND updated plots
                # because when a plot is replaced, old screenshots are cleaned up
                try:
                    from .server.services.headless_handler import get_headless_handler
                    handler = get_headless_handler()
                    handler.handle_init(ctx.session_id, result_plot_id)
                except Exception as e:
                    logger.warning(f"Failed to generate init screenshot: {e}")
            except Exception as e:
                logger.warning(f"Failed to log plot: {e}")

    except PlotlyClientError as e:
        raise PlotlyToolError(f"Failed to upload plot: {e}") from e

    # Emit plot_show event
    try:
        plot_type = 'plot'
        if hasattr(fig, 'data') and fig.data:
            first_trace = fig.data[0]
            if hasattr(first_trace, 'type'):
                plot_type = first_trace.type

        logger.info(f"Emitting plot_show for plot_id={result_plot_id}, session={ctx.session_id}")
        await _emit_event('plot_show', {
            'plot_id': result_plot_id,
            'session_id': ctx.session_id,
            'session_name': ctx.session_name,
            'url': url,
            'plot_type': plot_type,
            'updated': is_update
        })
        logger.info(f"Emitted plot_show for plot_id={result_plot_id}")
    except Exception as e:
        logger.warning(f"Failed to emit plot event for plot_id={result_plot_id}: {e}")

    return (result_plot_id, url)


def query_interactions(plot_id: int, event_type: str | None = None) -> list[dict[str, Any]]:
    """
    Query interaction events for a specific plot.

    Args:
        plot_id: The plot ID from show_plot()
        event_type: Optional filter (init, relayout, legendclick, selected)

    Returns:
        List of interaction dicts with interaction_id, event_type, payload, has_screenshot
        interaction_id is per-plot (1, 2, 3...) for intuitive referencing

    Raises:
        PlotlyToolError: If no active session or query fails
    """
    ctx = _get_session_context()

    try:
        interactions = ctx.store.get_interactions(ctx.session_id, plot_id=plot_id)

        if event_type is not None:
            interactions = [i for i in interactions if i['event_type'] == event_type]

        return [
            {
                'interaction_id': i['interaction_id'],
                'event_type': i['event_type'],
                'payload': i.get('payload', {}),
                'has_screenshot': bool(i.get('screenshot_path'))
            }
            for i in interactions
        ]
    except Exception as e:
        raise PlotlyToolError(f"Failed to query interactions: {e}") from e


async def get_plot_json(plot_id: int) -> dict:
    """
    Get plot JSON data and open the plot panel.

    Args:
        plot_id: The plot ID from show_plot()

    Returns:
        Dict with data, layout, frames, config, plot_id, session_id

    Raises:
        PlotlyToolError: If no active session or plot not found
    """
    ctx = _get_session_context()

    api_url = f"http://localhost:{SERVER_PORT}{PLOTLY_BASE_PATH}/api/view/{ctx.session_id}/{plot_id}?return_data=true"

    def _fetch():
        response = requests.get(api_url, timeout=5)
        response.raise_for_status()
        return response.json()

    try:
        return await run_sync_in_thread(_fetch)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            raise PlotlyToolError(f"Plot {plot_id} not found") from e
        raise PlotlyToolError(f"Failed to get plot: {e}") from e
    except Exception as e:
        raise PlotlyToolError(f"Failed to get plot JSON: {e}") from e


def get_plot_image(plot_id: int, interaction_id: int | None = None) -> str:
    """
    Get file path to a plot screenshot.

    Args:
        plot_id: The plot ID from show_plot()
        interaction_id: Optional per-plot interaction number (default: latest)

    Returns:
        Absolute file path to the screenshot PNG

    Raises:
        PlotlyToolError: If no screenshots exist or not found
    """
    ctx = _get_session_context()

    try:
        interactions = ctx.store.get_interactions(ctx.session_id, plot_id=plot_id)
        with_screenshots = [i for i in interactions if i.get('screenshot_path')]

        if not with_screenshots:
            raise PlotlyToolError(f"No screenshots for plot {plot_id}")

        if interaction_id is not None:
            target = next((i for i in with_screenshots if i['interaction_id'] == interaction_id), None)
            if target is None:
                exists = any(i['interaction_id'] == interaction_id for i in interactions)
                if exists:
                    raise PlotlyToolError(f"Interaction {interaction_id} has no screenshot")
                raise PlotlyToolError(f"Interaction {interaction_id} not found")
        else:
            target = max(with_screenshots, key=lambda x: x['interaction_id'])

        session_info = ctx.store.get_session_info(ctx.session_id)
        absolute_path = session_info.folder_path / target['screenshot_path']

        if not absolute_path.exists():
            raise PlotlyToolError(f"Screenshot file not found: {absolute_path}")

        return str(absolute_path)

    except PlotlyToolError:
        raise
    except Exception as e:
        raise PlotlyToolError(f"Failed to get plot image: {e}") from e


def get_plot_code(plot_id: int) -> str:
    """
    Get the Python code that created a plot.

    Args:
        plot_id: The plot ID from show_plot()

    Returns:
        Python code string that was used to create the plot

    Raises:
        PlotlyToolError: If plot not found
    """
    ctx = _get_session_context()

    try:
        plots = ctx.store.get_plots(ctx.session_id)
        plot = next((p for p in plots if p['plot_id'] == plot_id), None)

        if plot is None:
            raise PlotlyToolError(f"Plot {plot_id} not found")

        return plot['plotly_code']

    except PlotlyToolError:
        raise
    except Exception as e:
        raise PlotlyToolError(f"Failed to get plot code: {e}") from e


async def relayout(
    plot_id: int,
    x_range: list[float] | None = None,
    y_range: list[float] | None = None
) -> dict:
    """
    Update plot layout (zoom/pan axis ranges).

    Args:
        plot_id: The plot ID from show_plot()
        x_range: Optional [min, max] for x-axis
        y_range: Optional [min, max] for y-axis

    Returns:
        Dict with success, plot_id, x_range, y_range

    Raises:
        PlotlyToolError: If no active session or command fails
    """
    if x_range is None and y_range is None:
        raise PlotlyToolError("At least one of x_range or y_range required")

    ctx = _get_session_context()

    args = {}
    if x_range is not None:
        if len(x_range) != 2:
            raise PlotlyToolError("x_range must be [min, max]")
        args["xaxis.range[0]"] = x_range[0]
        args["xaxis.range[1]"] = x_range[1]

    if y_range is not None:
        if len(y_range) != 2:
            raise PlotlyToolError("y_range must be [min, max]")
        args["yaxis.range[0]"] = y_range[0]
        args["yaxis.range[1]"] = y_range[1]

    try:
        await _emit_plot_command(ctx, plot_id, 'relayout', args)
        return {"success": True, "plot_id": plot_id, "x_range": x_range, "y_range": y_range}
    except Exception as e:
        raise PlotlyToolError(f"Failed to relayout: {e}") from e


async def legendclick(plot_id: int, curve_number: int) -> dict:
    """
    Toggle trace visibility by legend click.

    Args:
        plot_id: The plot ID from show_plot()
        curve_number: Trace index (0-based)

    Returns:
        Dict with success, plot_id, curve_number

    Raises:
        PlotlyToolError: If no active session or command fails
    """
    ctx = _get_session_context()

    try:
        await _emit_plot_command(ctx, plot_id, 'legendclick', {'curve_number': curve_number})
        return {"success": True, "plot_id": plot_id, "curve_number": curve_number}
    except Exception as e:
        raise PlotlyToolError(f"Failed to toggle legend: {e}") from e


async def selected(
    plot_id: int,
    x_range: list[float] | None = None,
    y_range: list[float] | None = None,
    point_indices: list[int] | None = None
) -> dict:
    """
    Select data points in the plot.

    Args:
        plot_id: The plot ID from show_plot()
        x_range: Optional [min, max] for x-axis selection
        y_range: Optional [min, max] for y-axis selection
        point_indices: Optional list of point indices to select

    Returns:
        Dict with success, plot_id, selection

    Raises:
        PlotlyToolError: If no active session or command fails
    """
    if x_range is None and y_range is None and point_indices is None:
        raise PlotlyToolError("At least one selection parameter required")

    ctx = _get_session_context()

    args = {}
    if x_range is not None:
        args['x_range'] = x_range
    if y_range is not None:
        args['y_range'] = y_range
    if point_indices is not None:
        args['point_indices'] = point_indices

    try:
        await _emit_plot_command(ctx, plot_id, 'selected', args)
        return {"success": True, "plot_id": plot_id, "selection": args}
    except Exception as e:
        raise PlotlyToolError(f"Failed to select: {e}") from e
