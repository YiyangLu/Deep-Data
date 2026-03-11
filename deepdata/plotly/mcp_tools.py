"""
MCP tool wrappers for plotly visualization functions.

This module provides MCP-compatible tools that agents can use to create
and analyze plotly visualizations. These wrappers adapt the Python functions
from tools.py to the MCP format expected by Claude SDK.

All tools return JSON-structured output for easy parsing and type-safe access:
- show_plot: Returns {plot_id}
- query_interactions: Returns {events: [...]} or {message: "..."}
- get_plot_json: Returns {data, layout, plot_id, session_id}
- get_plot_image: Returns {image_path} - file path to latest screenshot
- get_plot_code: Returns {code} - Python code that created the plot
"""

from typing import Any, Callable, Awaitable
import json
from functools import wraps

from claude_agent_sdk import tool, create_sdk_mcp_server
from .tools import (
    show_plot,
    query_interactions,
    get_plot_json,
    get_plot_image,
    get_plot_code,
    relayout,
    legendclick,
    selected,
    PlotlyToolError
)


def mcp_error_handler(func: Callable[[dict[str, Any]], Awaitable[Any]]) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """
    Decorator to standardize MCP tool error handling.

    Wraps tool functions to:
    1. Format successful results as MCP responses with JSON content
    2. Catch exceptions and format as MCP error responses
    3. Provide consistent error structure across all MCP tools

    Args:
        func: Async function that returns a result dict

    Returns:
        Decorated function that returns MCP-formatted response

    Example:
        @tool("my_tool", "Description", {"arg": str})
        @mcp_error_handler
        async def _mcp_my_tool(args: dict[str, Any]) -> Any:
            result = await my_function(args["arg"])
            return {"result": result}  # Will be auto-formatted as MCP response
    """
    @wraps(func)
    async def wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            # Call the wrapped function
            result = await func(args)

            # If result is already an MCP response (has 'content' key), return as-is
            if isinstance(result, dict) and 'content' in result:
                return result

            # Otherwise, format as MCP response
            return {
                "content": [{
                    "type": "text",
                    "text": json.dumps(result, indent=2)
                }]
            }

        except PlotlyToolError as e:
            # Plotly-specific errors
            return _format_mcp_error(str(e), "PlotlyToolError")

        except Exception as e:
            # Generic errors
            return _format_mcp_error(str(e), type(e).__name__)

    return wrapper


def _format_mcp_error(error: str, error_type: str) -> dict[str, Any]:
    """
    Format error response for MCP tools.

    Args:
        error: Error message string
        error_type: Error type/class name

    Returns:
        MCP error response dict
    """
    error_result = {
        "success": False,
        "error": error,
        "error_type": error_type
    }
    return {
        "content": [{
            "type": "text",
            "text": json.dumps(error_result, indent=2)
        }],
        "is_error": True
    }


@tool(
    "show_plot",
    "Create or update Plotly figure from code. Returns {plot_id}.",
    {
        "type": "object",
        "properties": {
            "plotly_codes": {
                "type": "string",
                "description": "Python code defining 'fig' (Plotly figure). Include imports."
            },
            "plot_id": {
                "type": "integer",
                "description": "Optional. Existing plot ID to overwrite. If omitted, creates new plot."
            }
        },
        "required": ["plotly_codes"]
    }
)
@mcp_error_handler
async def _mcp_show_plot(args: dict[str, Any]) -> dict[str, Any]:
    """
    MCP wrapper for show_plot().

    Args:
        args["plotly_codes"]: Python code string that creates a plotly figure
        args["plot_id"]: Optional plot ID to overwrite (for updating existing plot)

    Returns:
        Result dict (decorator formats as MCP response):
        {
            "plot_id": int
        }
    """
    existing_plot_id = args.get("plot_id")  # Optional
    result_plot_id, _ = await show_plot(args["plotly_codes"], plot_id=existing_plot_id)
    return {"plot_id": result_plot_id}


@tool(
    "query_interactions",
    "Get interaction history. Returns [{interaction_id, event_type, payload, has_screenshot}].",
    {
        "type": "object",
        "properties": {
            "plot_id": {
                "type": "integer",
                "description": "Plot ID from show_plot."
            },
            "event_type": {
                "type": "string",
                "description": "Optional filter: init, relayout, legendclick, selected."
            }
        },
        "required": ["plot_id"]
    }
)
@mcp_error_handler
async def _mcp_query_interactions(args: dict[str, Any]) -> dict[str, Any]:
    """
    MCP wrapper for query_interactions().

    Args:
        args["plot_id"]: The plot ID to query
        args["event_type"]: Optional event type filter (init, relayout, legendclick, selected)

    Returns:
        Result dict:
        {
            "events": [
                {
                    "interaction_id": int,  # Per-plot sequence (1, 2, 3...)
                    "event_type": str,          # init, relayout, legendclick, selected
                    "payload": dict,            # Event details (zoom range, trace visibility, etc.)
                    "has_screenshot": bool
                },
                ...
            ]
        }
    """
    plot_id = args["plot_id"]
    event_type = args.get("event_type")  # Optional
    # Treat empty string as None (no filter)
    if event_type == "":
        event_type = None

    # query_interactions will raise PlotlyToolError if no active session
    events = query_interactions(plot_id, event_type=event_type)
    return {"events": events}


@tool(
    "get_plot_json",
    "Get Plotly figure data. Returns {data, layout}.",
    {
        "type": "object",
        "properties": {
            "plot_id": {
                "type": "integer",
                "description": "Plot ID from show_plot."
            }
        },
        "required": ["plot_id"]
    }
)
@mcp_error_handler
async def _mcp_get_plot_json(args: dict[str, Any]) -> dict[str, Any]:
    """
    MCP wrapper for get_plot_json().

    Args:
        args["plot_id"]: The plot ID to retrieve

    Returns:
        Result dict with plot data and layout
    """
    plot_data = await get_plot_json(args["plot_id"])
    return plot_data


@tool(
    "get_plot_image",
    "Get screenshot of a plot. Returns {image_path}.",
    {
        "type": "object",
        "properties": {
            "plot_id": {
                "type": "integer",
                "description": "Plot ID from show_plot."
            },
            "interaction_id": {
                "type": "integer",
                "description": "Optional. Per-plot interaction number (1, 2, 3...) for past state."
            }
        },
        "required": ["plot_id"]
    }
)
@mcp_error_handler
async def _mcp_get_plot_image(args: dict[str, Any]) -> dict[str, Any]:
    """
    MCP wrapper for get_plot_image().

    Args:
        args["plot_id"]: The plot ID to get screenshot for
        args["interaction_id"]: Optional per-plot interaction number (from query_interactions)

    Returns:
        Result dict:
        {
            "image_path": str  # Absolute path to the PNG file
        }
    """
    plot_id = args["plot_id"]
    interaction_id = args.get("interaction_id")  # Optional
    # Treat 0 or negative as None (get latest screenshot)
    if interaction_id is not None and interaction_id <= 0:
        interaction_id = None
    image_path = get_plot_image(plot_id, interaction_id=interaction_id)
    return {"image_path": image_path}


@tool(
    "get_plot_code",
    "Get Python code that created a plot. Returns {code}.",
    {
        "type": "object",
        "properties": {
            "plot_id": {
                "type": "integer",
                "description": "Plot ID from show_plot."
            }
        },
        "required": ["plot_id"]
    }
)
@mcp_error_handler
async def _mcp_get_plot_code(args: dict[str, Any]) -> dict[str, Any]:
    """
    MCP wrapper for get_plot_code().

    Args:
        args["plot_id"]: The plot ID to get code for

    Returns:
        Result dict:
        {
            "code": str  # Python code that created the plot
        }
    """
    code = get_plot_code(args["plot_id"])
    return {"code": code}


@tool(
    "relayout",
    "Zoom/pan plot by setting axis ranges.",
    {
        "type": "object",
        "properties": {
            "plot_id": {
                "type": "integer",
                "description": "Plot ID from show_plot."
            },
            "x_min": {
                "type": "number",
                "description": "X-axis range minimum."
            },
            "x_max": {
                "type": "number",
                "description": "X-axis range maximum."
            },
            "y_min": {
                "type": "number",
                "description": "Y-axis range minimum."
            },
            "y_max": {
                "type": "number",
                "description": "Y-axis range maximum."
            }
        },
        "required": ["plot_id"]
    }
)
@mcp_error_handler
async def _mcp_relayout(args: dict[str, Any]) -> dict[str, Any]:
    """
    MCP wrapper for relayout().

    Args:
        args["plot_id"]: The plot ID to modify
        args["x_min"]: Optional minimum x-axis value
        args["x_max"]: Optional maximum x-axis value
        args["y_min"]: Optional minimum y-axis value
        args["y_max"]: Optional maximum y-axis value

    Returns:
        Result dict with success status
    """
    plot_id = args["plot_id"]

    # Build ranges from min/max params
    x_range = None
    y_range = None
    if args.get("x_min") is not None and args.get("x_max") is not None:
        x_range = [args["x_min"], args["x_max"]]
    if args.get("y_min") is not None and args.get("y_max") is not None:
        y_range = [args["y_min"], args["y_max"]]

    result = await relayout(plot_id, x_range=x_range, y_range=y_range)
    return result


@tool(
    "legendclick",
    "Toggle trace visibility.",
    {
        "type": "object",
        "properties": {
            "plot_id": {
                "type": "integer",
                "description": "Plot ID from show_plot."
            },
            "curve_number": {
                "type": "integer",
                "description": "Trace index (0-based)."
            }
        },
        "required": ["plot_id", "curve_number"]
    }
)
@mcp_error_handler
async def _mcp_legendclick(args: dict[str, Any]) -> dict[str, Any]:
    """
    MCP wrapper for legendclick().

    Args:
        args["plot_id"]: The plot ID to modify
        args["curve_number"]: Index of the trace to toggle (0-based)

    Returns:
        Result dict with success status
    """
    result = await legendclick(args["plot_id"], args["curve_number"])
    return result


@tool(
    "selected",
    "Select data points by region.",
    {
        "type": "object",
        "properties": {
            "plot_id": {
                "type": "integer",
                "description": "Plot ID from show_plot."
            },
            "x_min": {
                "type": "number",
                "description": "X-axis selection minimum."
            },
            "x_max": {
                "type": "number",
                "description": "X-axis selection maximum."
            },
            "y_min": {
                "type": "number",
                "description": "Y-axis selection minimum."
            },
            "y_max": {
                "type": "number",
                "description": "Y-axis selection maximum."
            }
        },
        "required": ["plot_id"]
    }
)
@mcp_error_handler
async def _mcp_selected(args: dict[str, Any]) -> dict[str, Any]:
    """
    MCP wrapper for selected().

    Args:
        args["plot_id"]: The plot ID to modify
        args["x_min"]: Optional minimum x for selection box
        args["x_max"]: Optional maximum x for selection box
        args["y_min"]: Optional minimum y for selection box
        args["y_max"]: Optional maximum y for selection box

    Returns:
        Result dict with selection info
    """
    # Build ranges from min/max params
    x_range = None
    y_range = None
    if args.get("x_min") is not None and args.get("x_max") is not None:
        x_range = [args["x_min"], args["x_max"]]
    if args.get("y_min") is not None and args.get("y_max") is not None:
        y_range = [args["y_min"], args["y_max"]]

    result = await selected(
        args["plot_id"],
        x_range=x_range,
        y_range=y_range
    )
    return result


def create_plotly_mcp_server(
    enable_headless: bool = True,
    on_event: Callable[[str, dict], Awaitable[None]] | None = None,
    allowed_tools: list[str] | None = None
) -> tuple:
    """
    Create MCP server with plotly visualization tools.

    Args:
        enable_headless: If True, register headless subscriber to handle
                        plot commands when no browser is connected.
                        Default True for autonomous/headless agent usage.
        on_event: Optional callback for plot events (plot_show, plot_command).
                 If provided, automatically subscribes to EventBus.
        allowed_tools: Optional list of tool names to include. If None, all tools
                      are included. Use mcp__plotly__<name> format.

    Returns:
        (server_config, cleanup_fn) tuple:
        - server_config: McpSdkServerConfig for ClaudeAgentOptions.mcp_servers
        - cleanup_fn: Function to unsubscribe from events (None if no on_event)

    Example:
        >>> from deepdata.plotly.mcp_tools import create_plotly_mcp_server
        >>> from deepdata.core.agent import Agent
        >>>
        >>> # All tools
        >>> server, _ = create_plotly_mcp_server()
        >>>
        >>> # Only specific tools
        >>> server, _ = create_plotly_mcp_server(
        ...     allowed_tools=["mcp__plotly__show_plot", "mcp__plotly__get_plot_image"]
        ... )
    """
    # Register headless subscriber for handling plot commands without browser
    if enable_headless:
        from .server.services.headless_subscriber import register_headless_subscriber
        register_headless_subscriber()

    # All available tools with their MCP names
    all_tools = {
        "mcp__plotly__show_plot": _mcp_show_plot,
        "mcp__plotly__query_interactions": _mcp_query_interactions,
        "mcp__plotly__get_plot_json": _mcp_get_plot_json,
        "mcp__plotly__get_plot_image": _mcp_get_plot_image,
        "mcp__plotly__get_plot_code": _mcp_get_plot_code,
        "mcp__plotly__relayout": _mcp_relayout,
        "mcp__plotly__legendclick": _mcp_legendclick,
        "mcp__plotly__selected": _mcp_selected,
    }

    # Filter tools if allowed_tools specified
    if allowed_tools is not None:
        tools = [all_tools[name] for name in allowed_tools if name in all_tools]
    else:
        tools = list(all_tools.values())

    server_config = create_sdk_mcp_server(
        name="plotly",
        version="1.0.0",
        tools=tools
    )

    # Subscribe to EventBus if callback provided
    cleanup_fn = None
    if on_event:
        from ..core.event_bus import get_event_bus, Event

        event_bus = get_event_bus()
        handlers = {}

        async def handle_plot_show(event: Event):
            await on_event('plot_show', event.data)

        async def handle_plot_command(event: Event):
            await on_event('plot_command', event.data)

        handlers['plot_show'] = handle_plot_show
        handlers['plot_command'] = handle_plot_command

        event_bus.subscribe('plot_show', handle_plot_show)
        event_bus.subscribe('plot_command', handle_plot_command)

        def cleanup():
            for event_type, handler in handlers.items():
                event_bus.unsubscribe(event_type, handler)

        cleanup_fn = cleanup

    return server_config, cleanup_fn


# Tool name constants for convenience
PLOTLY_TOOLS = [
    "mcp__plotly__show_plot",
    "mcp__plotly__query_interactions",
    "mcp__plotly__get_plot_json",
    "mcp__plotly__get_plot_image",
    "mcp__plotly__get_plot_code",
    "mcp__plotly__relayout",
    "mcp__plotly__legendclick",
    "mcp__plotly__selected",
]
