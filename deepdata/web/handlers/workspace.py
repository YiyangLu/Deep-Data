"""
Workspace WebSocket message handlers.

Handlers for loading and saving global workspace UI state.
"""

import os
from pathlib import Path

from .base import WebSocketContext, logger


def get_cwd_info() -> dict:
    """Get current working directory info with shortened version."""
    agent_cwd = os.getenv('AGENT_CWD', os.getcwd())
    home = str(Path.home())

    # Create shortened version (replace home with ~)
    shortened = agent_cwd
    if agent_cwd.startswith(home):
        shortened = "~" + agent_cwd[len(home):]

    return {"cwd": agent_cwd, "shortened": shortened}


async def handle_load_workspace(data: dict, ctx: WebSocketContext) -> None:
    """
    Handle load_workspace message - return global workspace UI state.

    Workspace includes agent tabs, plot tabs, active indices, and cwd.
    """
    workspace = ctx.workspace_manager.load_workspace()
    cwd_info = get_cwd_info()
    await ctx.send("workspace_loaded", workspace=workspace, cwd=cwd_info)


async def handle_save_workspace(data: dict, ctx: WebSocketContext) -> None:
    """
    Handle save_workspace message - persist workspace UI state.

    Merges incoming data with current workspace (supports partial updates).

    Expected data:
        workspace: Dict with optional keys:
            - agent_tabs: List of agent tab objects
            - active_agent_tab: Index of active agent tab
            - plot_tabs: List of plot tab objects
            - active_plot_tab: Index of active plot tab
    """
    workspace_data = data.get("workspace")

    if not workspace_data:
        logger.warning("save_workspace missing workspace data")
        return

    # Load current workspace
    current_workspace = ctx.workspace_manager.load_workspace()

    # Merge incoming data with current workspace
    # Frontend may send partial updates (only agent_tabs or only plot_tabs)
    if 'agent_tabs' in workspace_data:
        current_workspace['agent_tabs'] = workspace_data['agent_tabs']
        current_workspace['active_agent_tab'] = workspace_data.get('active_agent_tab')

    if 'plot_tabs' in workspace_data:
        current_workspace['plot_tabs'] = workspace_data['plot_tabs']
        current_workspace['active_plot_tab'] = workspace_data.get('active_plot_tab')

    # Ensure version is set
    current_workspace['version'] = 2

    ctx.workspace_manager.save_workspace(current_workspace)
    logger.debug(
        f"Saved global workspace "
        f"(agent_tabs: {len(current_workspace.get('agent_tabs', []))}, "
        f"plot_tabs: {len(current_workspace.get('plot_tabs', []))})"
    )
