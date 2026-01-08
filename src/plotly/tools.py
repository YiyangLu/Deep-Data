"""
Agent-friendly tools for plotly visualization and interaction analysis.

This module provides high-level functions for agents to:
1. Create and display plots (show_plot)
2. Query user interaction data [Future]

Design Philosophy:
- Simple, robust APIs for agent use
- Auto-manage server lifecycle
- Clear return types for agent parsing
- Events emitted through current agent's events emitter
"""

from typing import Any

import requests

from .client import check_server_status, start_server, upload_plot, PlotlyClientError
from ..config import get_plot_url, SERVER_PORT, PLOTLY_BASE_PATH
from ..core.event_bus import get_event_bus
from ..core.agent_context import get_current_agent
from ..core.session_registry import get_current_session
from ..utils.logging import create_logger
from ..utils.async_helpers import run_sync_in_thread

# Configure logger for debugging
logger = create_logger(__name__)


async def _emit_event(event_type: str, data: dict):
    """
    Emit event to current agent or fallback to event bus.

    Uses agent context if available (preferred), otherwise falls back
    to global event bus for backward compatibility.
    """
    agent = get_current_agent()
    if agent:
        # Emit through agent's events emitter
        await agent.events.emit(event_type, data)
        logger.debug(f"Event '{event_type}' emitted via agent.events")
    else:
        # Fallback to global event bus
        await get_event_bus().publish(event_type, data)
        logger.debug(f"Event '{event_type}' emitted via event_bus (no agent context)")


class PlotlyToolError(Exception):
    """Raised when plotly tool operations fail"""
    pass


async def show_plot(plotly_codes: str) -> tuple[int, str]:
    """
    Execute plotly code and display in capture server.

    This is the main function agents should use to create visualizations.
    It handles server lifecycle automatically and returns tracking information.

    Args:
        plotly_codes: Python code string that creates a plotly figure.
                     Must define a variable named 'fig' containing the plot.
                     Agent must provide all necessary imports.

    Returns:
        tuple[int, str]: (plot_id, url)
            - plot_id: Integer ID for tracking this plot (use for future queries)
            - url: Full URL where the plot can be viewed in browser

    Raises:
        PlotlyToolError: If code execution fails, server issues, or upload fails

    Example:
        >>> code = '''
        ... import plotly.express as px
        ... df = px.data.iris()
        ... fig = px.scatter(df, x='sepal_width', y='sepal_length',
        ...                  title='Iris Dataset')
        ... '''
        >>> plot_id, url = show_plot(code)
        >>> print(f"Plot {plot_id} available at {url}")
        Plot 1 available at http://localhost:8000

    Note:
        - Automatically starts server if not running
        - Server continues running for subsequent calls (efficient)
        - plot_id can be used later with query_interactions() to analyze user behavior
    """
    logger.debug(f"show_plot() called with code length: {len(plotly_codes)} characters")
    logger.debug(f"Code:\n{plotly_codes}")

    # Step 1: Ensure server is running
    try:
        server_running = await check_server_status()
        if not server_running:
            logger.info("Starting plotly capture server...")
            await start_server(wait_for_ready=True, timeout=10.0)
            logger.info("Server started successfully")
    except PlotlyClientError as e:
        logger.error(f"Failed to start server: {e}")
        raise PlotlyToolError(f"Failed to start capture server: {e}") from e

    # Step 2: Execute plotly code to create figure
    # We'll execute the code normally but suppress any exceptions from fig.show()
    # by wrapping in try-except within the exec namespace
    try:
        exec_namespace = {}

        # Inject a no-op show function to override fig.show()
        # This is safer than messing with renderers which can break things
        exec_namespace['__builtins__'] = __builtins__.copy() if isinstance(__builtins__, dict) else {k: getattr(__builtins__, k) for k in dir(__builtins__)}

        # Monkey-patch plotly.io.show to do nothing during execution
        import plotly.io as user_pio
        original_show = user_pio.show
        user_pio.show = lambda *_args, **_kwargs: None  # No-op function

        try:
            exec(plotly_codes, exec_namespace)
        finally:
            # Restore original show function
            user_pio.show = original_show

        # Extract the fig variable
        if 'fig' not in exec_namespace:
            logger.error(f"No 'fig' variable found. Available: {list(exec_namespace.keys())}")
            raise PlotlyToolError(
                "Code execution succeeded but no 'fig' variable was defined. "
                "Please ensure your code creates a variable named 'fig' with the plotly figure."
            )

        fig = exec_namespace['fig']
        logger.debug(f"Figure extracted: {type(fig).__name__}")

    except SyntaxError as e:
        logger.error(f"Syntax error in plotly code: {e}")
        raise PlotlyToolError(
            f"Syntax error in plotly code at line {e.lineno}: {e.msg}\n"
            f"Code: {e.text}"
        ) from e

    except Exception as e:
        logger.error(f"Runtime error during code execution: {type(e).__name__}: {e}")
        raise PlotlyToolError(
            f"Failed to execute plotly code: {type(e).__name__}: {str(e)}"
        ) from e

    # Step 3: Get current session for session-scoped plot IDs
    session_store, session_id = get_current_session()
    if not session_id:
        logger.error("No active session - cannot create plot")
        raise PlotlyToolError("No active session. Plot creation requires an active session.")

    # Step 4: Upload figure to server with session_id
    try:
        response = await upload_plot(fig, session_id=session_id)
        plot_id = response.get('plot_id')
        if plot_id is None:
            logger.error(f"No plot_id in response: {response}")
            raise PlotlyToolError(
                f"Server did not return plot_id. Response: {response}"
            )

        # Extract URL from response (new API returns plot-specific URL)
        url = response.get('url')
        if url is None:
            url = get_plot_url(plot_id)

        logger.info(f"Plot created: ID={plot_id}, URL={url}, Session={session_id}")

        # Log plot to SessionStore
        if session_store:
            try:
                fig_json = fig.to_json()
                session_store.log_plot(
                    session_id=session_id,
                    plot_id=plot_id,
                    plotly_code=plotly_codes,
                    fig_json=fig_json
                )
                logger.debug(f"Plot {plot_id} logged to session {session_id}")
            except Exception as e:
                logger.warning(f"Failed to log plot to session store: {e}")

    except PlotlyClientError as e:
        logger.error(f"Upload failed: {e}")
        raise PlotlyToolError(f"Failed to upload plot: {e}") from e

    # Step 5: Emit plot_show event (through agent or event bus)
    try:
        # Detect plot type from figure traces
        plot_type = 'plot'  # default
        if hasattr(fig, 'data') and len(fig.data) > 0:
            # Get the type of the first trace
            first_trace = fig.data[0]
            if hasattr(first_trace, 'type'):
                plot_type = first_trace.type

        await _emit_event('plot_show', {
            'plot_id': plot_id,
            'session_id': session_id,
            'url': url,
            'plot_type': plot_type
        })
        logger.debug(f"Plot event emitted (type: {plot_type}, session: {session_id})")
    except Exception as e:
        logger.warning(f"Failed to emit plot event: {e}")

    return (plot_id, url)


def query_interactions(plot_id: int, event_type: str | None = None) -> list[dict[str, Any]]:
    """
    Query interaction events for a specific plot from the current session.

    Returns all events (init, relayout, legendclick, selected) that occurred
    on the specified plot. Use this to understand the interaction history
    and get interaction IDs for retrieving specific screenshots.

    IMPORTANT: This function requires an active session (agent with enable_storage=True).
    If no active session, raises PlotlyToolError.

    Args:
        plot_id: The plot ID returned from show_plot()
        event_type: Optional filter for specific event type (e.g., 'relayout', 'legendclick').
                   If None, returns all events.

    Returns:
        List of interaction event dictionaries, each containing:
        - id: Interaction ID (use with get_plot_image to get screenshot)
        - event_type: Type of event (init, relayout, legendclick, selected)
        - payload: Event details (zoom range, trace visibility, etc.)
        - has_screenshot: Boolean indicating if screenshot exists

    Raises:
        PlotlyToolError: If no active session or query fails

    Example:
        >>> # Get all interactions for a plot
        >>> events = query_interactions(plot_id=1)
        >>> for event in events:
        ...     print(f"ID {event['id']}: {event['event_type']}, screenshot: {event['has_screenshot']}")

        >>> # Get screenshot for a specific interaction
        >>> image_path = get_plot_image(plot_id=1, interaction_id=2)
    """
    # Get current session
    session_store, session_id = get_current_session()

    if not session_store or not session_id:
        raise PlotlyToolError(
            "No active session. Enable storage with Agent(enable_storage=True) to query interactions."
        )

    try:
        # Get interactions from SessionStore
        interactions = session_store.get_interactions(session_id, plot_id=plot_id)

        # Filter by event_type if specified
        if event_type is not None:
            interactions = [i for i in interactions if i['event_type'] == event_type]

        # Simplify response for agent - only essential fields
        simplified = []
        for i in interactions:
            simplified.append({
                'id': i['id'],
                'event_type': i['event_type'],
                'payload': i.get('payload', {}),
                'has_screenshot': bool(i.get('screenshot_path'))
            })

        return simplified

    except Exception as e:
        raise PlotlyToolError(f"Failed to query interactions: {e}") from e


async def get_plot_json(plot_id: int) -> dict:
    """
    Get plot JSON and open the plot panel (like PlotHistoryDropdown).

    This function:
    1. Loads plot into memory (if not already)
    2. Opens/focuses the plot panel in the UI
    3. Returns the plot's data and layout

    Uses the unified /api/view endpoint which handles loading, caching,
    and panel opening in a single request.

    Args:
        plot_id: The plot ID returned from show_plot()

    Returns:
        Dictionary containing:
        - data: List of trace data
        - layout: Plot layout configuration
        - frames: Animation frames (if any)
        - config: Plotly config (if any)
        - plot_id: The plot ID
        - session_id: The session ID

    Raises:
        PlotlyToolError: If no active session or plot not found

    Example:
        >>> plot_id, url = await show_plot(code)
        >>> # Later, to view and get the plot data:
        >>> plot_data = await get_plot_json(plot_id)
        >>> print(f"Plot has {len(plot_data['data'])} traces")
    """
    # Get current session
    session_store, session_id = get_current_session()

    if not session_store or not session_id:
        raise PlotlyToolError(
            "No active session. Enable storage with Agent(enable_storage=True) to get plot data."
        )

    # Use unified /api/view endpoint (loads, caches, opens panel, returns data)
    api_url = f"http://localhost:{SERVER_PORT}{PLOTLY_BASE_PATH}/api/view/{session_id}/{plot_id}?return_data=true"

    def _fetch():
        response = requests.get(api_url, timeout=5)
        response.raise_for_status()
        return response.json()

    try:
        data = await run_sync_in_thread(_fetch)
        logger.debug(f"Viewed plot {plot_id} via /api/view (session: {session_id})")
        return data
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            raise PlotlyToolError(f"Plot {plot_id} not found in session {session_id}") from e
        raise PlotlyToolError(f"Failed to view plot: {e}") from e
    except Exception as e:
        raise PlotlyToolError(f"Failed to get plot JSON: {e}") from e


def get_plot_image(plot_id: int, interaction_id: int | None = None) -> str:
    """
    Get the file path to a screenshot for a plot.

    Returns the absolute path to a screenshot. If interaction_id is provided,
    returns that specific interaction's screenshot. Otherwise returns the
    most recent screenshot.

    Screenshots are captured automatically on init, legendclick, relayout, and selected events.

    Args:
        plot_id: The plot ID returned from show_plot()
        interaction_id: Optional specific interaction ID to get screenshot for.
                       Use query_interactions() to get available interaction IDs.
                       If None, returns the latest screenshot.

    Returns:
        Absolute file path to the screenshot PNG file.
        Example: "logs/sessions/.../screenshots/1/3.png"

    Raises:
        PlotlyToolError: If no active session, plot not found, interaction not found,
                        or no screenshots exist

    Example:
        >>> # Get latest screenshot
        >>> image_path = get_plot_image(plot_id=1)

        >>> # Get screenshot for specific interaction
        >>> events = query_interactions(plot_id=1)
        >>> image_path = get_plot_image(plot_id=1, interaction_id=events[1]['id'])
    """
    # Get current session
    session_store, session_id = get_current_session()

    if not session_store or not session_id:
        raise PlotlyToolError(
            "No active session. Enable storage with Agent(enable_storage=True) to get plot images."
        )

    try:
        # Query database for interactions with screenshots
        interactions = session_store.get_interactions(session_id, plot_id=plot_id)

        # Filter for interactions that have screenshots
        with_screenshots = [i for i in interactions if i.get('screenshot_path')]

        if not with_screenshots:
            raise PlotlyToolError(f"No screenshots found for plot {plot_id}")

        # Find the target interaction
        if interaction_id is not None:
            # Get specific interaction
            target = next((i for i in with_screenshots if i['id'] == interaction_id), None)
            if target is None:
                # Check if interaction exists but has no screenshot
                any_match = next((i for i in interactions if i['id'] == interaction_id), None)
                if any_match:
                    raise PlotlyToolError(
                        f"Interaction {interaction_id} exists but has no screenshot"
                    )
                else:
                    raise PlotlyToolError(
                        f"Interaction {interaction_id} not found for plot {plot_id}"
                    )
        else:
            # Get the one with highest id (most recent)
            target = max(with_screenshots, key=lambda x: x['id'])

        # Build absolute path
        session_info = session_store.get_session_info(session_id)
        absolute_path = session_info.folder_path / target['screenshot_path']

        if not absolute_path.exists():
            raise PlotlyToolError(f"Screenshot file not found: {absolute_path}")

        return str(absolute_path)

    except PlotlyToolError:
        raise
    except Exception as e:
        raise PlotlyToolError(f"Failed to get plot image: {e}") from e


async def relayout(
    plot_id: int,
    x_range: list[float] | None = None,
    y_range: list[float] | None = None
) -> dict:
    """
    Update plot layout (zoom/pan axis ranges).

    This allows the agent to programmatically explore a visualization
    by zooming to specific regions or panning across the data.
    A screenshot is automatically captured after the view change.

    Args:
        plot_id: The plot ID returned from show_plot()
        x_range: Optional [min, max] for x-axis. None keeps current range.
        y_range: Optional [min, max] for y-axis. None keeps current range.

    Returns:
        Dictionary with status:
        {
            "success": True,
            "plot_id": int,
            "x_range": [min, max] or None,
            "y_range": [min, max] or None
        }

    Raises:
        PlotlyToolError: If no active session or command fails

    Example:
        >>> plot_id, url = await show_plot(code)
        >>> # Zoom to specific region
        >>> await relayout(plot_id, x_range=[10, 50], y_range=[0, 100])
        >>> # Pan by setting new ranges
        >>> await relayout(plot_id, x_range=[60, 100])
    """
    # Get current session
    session_store, session_id = get_current_session()

    if not session_store or not session_id:
        raise PlotlyToolError(
            "No active session. Enable storage with Agent(enable_storage=True) to control plots."
        )

    if x_range is None and y_range is None:
        raise PlotlyToolError("At least one of x_range or y_range must be provided")

    # Build relayout args
    relayout_args = {}
    if x_range is not None:
        if len(x_range) != 2:
            raise PlotlyToolError("x_range must be [min, max]")
        relayout_args["xaxis.range[0]"] = x_range[0]
        relayout_args["xaxis.range[1]"] = x_range[1]

    if y_range is not None:
        if len(y_range) != 2:
            raise PlotlyToolError("y_range must be [min, max]")
        relayout_args["yaxis.range[0]"] = y_range[0]
        relayout_args["yaxis.range[1]"] = y_range[1]

    # Emit plot command (through agent or event bus)
    try:
        logger.info(f"Emitting plot_command event: plot_id={plot_id}, session_id={session_id}, args={relayout_args}")
        await _emit_event('plot_command', {
            'session_id': session_id,
            'plot_id': plot_id,
            'command': 'relayout',
            'args': relayout_args
        })
        logger.info("plot_command event emitted successfully")

        return {
            "success": True,
            "plot_id": plot_id,
            "x_range": x_range,
            "y_range": y_range
        }

    except Exception as e:
        raise PlotlyToolError(f"Failed to set axis range: {e}") from e


async def legendclick(
    plot_id: int,
    curve_number: int
) -> dict:
    """
    Toggle trace visibility by clicking on legend.

    This allows the agent to show/hide specific traces in the plot,
    useful for focusing on particular data series.
    A screenshot is automatically captured after the visibility change.

    Args:
        plot_id: The plot ID returned from show_plot()
        curve_number: Index of the trace to toggle (0-based)

    Returns:
        Dictionary with status:
        {
            "success": True,
            "plot_id": int,
            "curve_number": int
        }

    Raises:
        PlotlyToolError: If no active session or command fails

    Example:
        >>> plot_id, url = await show_plot(code)
        >>> # Hide the first trace
        >>> await legendclick(plot_id, curve_number=0)
        >>> # Toggle the second trace
        >>> await legendclick(plot_id, curve_number=1)
    """
    session_store, session_id = get_current_session()

    if not session_store or not session_id:
        raise PlotlyToolError(
            "No active session. Enable storage with Agent(enable_storage=True) to control plots."
        )

    try:
        await _emit_event('plot_command', {
            'session_id': session_id,
            'plot_id': plot_id,
            'command': 'legendclick',
            'args': {'curve_number': curve_number}
        })

        return {
            "success": True,
            "plot_id": plot_id,
            "curve_number": curve_number
        }

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

    This allows the agent to programmatically select data points,
    either by specifying a rectangular region or specific point indices.
    A screenshot is automatically captured after the selection.

    Args:
        plot_id: The plot ID returned from show_plot()
        x_range: Optional [min, max] for x-axis selection box
        y_range: Optional [min, max] for y-axis selection box
        point_indices: Optional list of point indices to select directly

    Returns:
        Dictionary with status:
        {
            "success": True,
            "plot_id": int,
            "selection": {...}
        }

    Raises:
        PlotlyToolError: If no active session or command fails

    Example:
        >>> plot_id, url = await show_plot(code)
        >>> # Select points in a region
        >>> await selected(plot_id, x_range=[10, 50], y_range=[0, 100])
        >>> # Select specific points by index
        >>> await selected(plot_id, point_indices=[0, 5, 10])
    """
    session_store, session_id = get_current_session()

    if not session_store or not session_id:
        raise PlotlyToolError(
            "No active session. Enable storage with Agent(enable_storage=True) to control plots."
        )

    if x_range is None and y_range is None and point_indices is None:
        raise PlotlyToolError("At least one of x_range, y_range, or point_indices must be provided")

    # Build selection args
    selection_args = {}
    if x_range is not None:
        selection_args['x_range'] = x_range
    if y_range is not None:
        selection_args['y_range'] = y_range
    if point_indices is not None:
        selection_args['point_indices'] = point_indices

    try:
        await _emit_event('plot_command', {
            'session_id': session_id,
            'plot_id': plot_id,
            'command': 'selected',
            'args': selection_args
        })

        return {
            "success": True,
            "plot_id": plot_id,
            "selection": selection_args
        }

    except Exception as e:
        raise PlotlyToolError(f"Failed to select data: {e}") from e
