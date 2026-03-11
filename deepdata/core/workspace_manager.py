"""
Global workspace manager for storing UI state across all sessions.

This module manages a GLOBAL workspace.json file that stores:
- Agent tabs (active agent sessions with display names)
- Plot tabs (visualizations across all sessions)
- Active tab indices (both agent and plot)
- UI layout preferences

DESIGN PRINCIPLE:
- Workspace is GLOBAL (not per-session)
- Agent and plot tabs persist when switching sessions or refreshing page
- Located at: logs/workspace.json
- Version 2 format (auto-migrates from version 1)

This is separate from per-session data (conversation, session metadata).
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone


class WorkspaceManager:
    """Manages the global workspace file for UI state persistence."""

    def __init__(self, workspace_path: Path):
        """
        Initialize workspace manager.

        Args:
            workspace_path: Path to workspace.json file (e.g., logs/workspace.json)
        """
        self.workspace_path = workspace_path
        self._ensure_workspace_exists()

    def _ensure_workspace_exists(self):
        """Create workspace file if it doesn't exist."""
        if not self.workspace_path.exists():
            self.workspace_path.parent.mkdir(parents=True, exist_ok=True)
            default_workspace = {
                "version": 2,
                "agent_tabs": [],
                "active_agent_tab": None,
                "plot_tabs": [],
                "active_plot_tab": None
            }
            self.save_workspace(default_workspace)

    def load_workspace(self) -> Dict[str, Any]:
        """
        Load workspace from file with automatic migration.

        Returns:
            Workspace data dictionary (version 2 format)
        """
        try:
            with open(self.workspace_path, 'r') as f:
                workspace = json.load(f)

            # Migrate version 1 to version 2
            if workspace.get('version') == 1:
                workspace['version'] = 2
                workspace['agent_tabs'] = []
                workspace['active_agent_tab'] = None
                # Save migrated version
                self.save_workspace(workspace)

            # Ensure all required fields exist (defensive)
            workspace.setdefault('agent_tabs', [])
            workspace.setdefault('active_agent_tab', None)
            workspace.setdefault('plot_tabs', [])
            workspace.setdefault('active_plot_tab', None)

            return workspace
        except (json.JSONDecodeError, FileNotFoundError):
            # Return default workspace if file is corrupted or missing
            return {
                "version": 2,
                "agent_tabs": [],
                "active_agent_tab": None,
                "plot_tabs": [],
                "active_plot_tab": None
            }

    def save_workspace(self, workspace: Dict[str, Any]):
        """
        Save workspace to file.

        Args:
            workspace: Workspace data dictionary
        """
        with open(self.workspace_path, 'w') as f:
            json.dump(workspace, f, indent=2)

    def add_plot_tab(
        self,
        plot_id: str,
        session_id: str,
        plot_type: str,
        plot_url: str
    ) -> Dict[str, Any]:
        """
        Add a new plot tab to workspace.

        Args:
            plot_id: Plot identifier
            session_id: Session that created the plot
            plot_type: Type of plot (scatter, line, etc.)
            plot_url: URL to access the plot

        Returns:
            Updated workspace
        """
        workspace = self.load_workspace()

        # Check for duplicate (same session_id + plot_id)
        existing_tabs = workspace.get('plot_tabs', [])
        for idx, tab in enumerate(existing_tabs):
            if tab.get('plot_id') == plot_id and tab.get('session_id') == session_id:
                # Tab already exists, just activate it
                workspace['active_plot_tab'] = idx
                self.save_workspace(workspace)
                return workspace

        # Create new tab
        new_tab = {
            "plot_id": plot_id,
            "session_id": session_id,
            "plot_type": plot_type,
            "plot_url": plot_url,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        workspace['plot_tabs'].append(new_tab)
        workspace['active_plot_tab'] = len(workspace['plot_tabs']) - 1

        # Auto-remove oldest tab if limit exceeded
        if len(workspace['plot_tabs']) > 30:
            workspace['plot_tabs'].pop(0)
            workspace['active_plot_tab'] = max(0, workspace['active_plot_tab'] - 1)

        self.save_workspace(workspace)
        return workspace

    def remove_plot_tab(self, index: int):
        """
        Remove a plot tab from workspace.

        Args:
            index: Index of tab to remove
        """
        workspace = self.load_workspace()
        plot_tabs = workspace.get('plot_tabs', [])

        if 0 <= index < len(plot_tabs):
            plot_tabs.pop(index)
            workspace['plot_tabs'] = plot_tabs

            # Adjust active index
            active_idx = workspace.get('active_plot_tab')
            if active_idx is not None:
                if len(plot_tabs) == 0:
                    workspace['active_plot_tab'] = None
                elif index == active_idx:
                    # Removed active tab - activate previous or first
                    workspace['active_plot_tab'] = max(0, index - 1) if index > 0 else 0
                elif index < active_idx:
                    # Removed tab before active - shift active index
                    workspace['active_plot_tab'] = active_idx - 1

            self.save_workspace(workspace)

    def set_active_plot_tab(self, index: Optional[int]):
        """
        Set the active plot tab index.

        Args:
            index: Index of tab to activate (None to deactivate all)
        """
        workspace = self.load_workspace()
        workspace['active_plot_tab'] = index
        self.save_workspace(workspace)

    # Agent tab management methods

    def add_agent_tab(
        self,
        session_id: str,
        session_name: str
    ) -> Dict[str, Any]:
        """
        Add a new agent tab to workspace.

        Args:
            session_id: Session identifier
            session_name: Display name for the tab

        Returns:
            Updated workspace
        """
        workspace = self.load_workspace()

        # Check for duplicate (same session_id)
        existing_tabs = workspace.get('agent_tabs', [])
        for idx, tab in enumerate(existing_tabs):
            if tab.get('session_id') == session_id:
                # Tab already exists, just activate it
                workspace['active_agent_tab'] = idx
                self.save_workspace(workspace)
                return workspace

        # Create new tab
        new_tab = {
            "session_id": session_id,
            "session_name": session_name,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        workspace['agent_tabs'].append(new_tab)
        workspace['active_agent_tab'] = len(workspace['agent_tabs']) - 1

        # No tab limit - allow unlimited agent tabs

        self.save_workspace(workspace)
        return workspace

    def remove_agent_tab(self, index: int):
        """
        Remove an agent tab from workspace.

        Args:
            index: Index of tab to remove
        """
        workspace = self.load_workspace()
        agent_tabs = workspace.get('agent_tabs', [])

        if 0 <= index < len(agent_tabs):
            agent_tabs.pop(index)
            workspace['agent_tabs'] = agent_tabs

            # Adjust active index
            active_idx = workspace.get('active_agent_tab')
            if active_idx is not None:
                if len(agent_tabs) == 0:
                    workspace['active_agent_tab'] = None
                elif index == active_idx:
                    # Removed active tab - activate previous or first
                    workspace['active_agent_tab'] = max(0, index - 1) if index > 0 else 0
                elif index < active_idx:
                    # Removed tab before active - shift active index
                    workspace['active_agent_tab'] = active_idx - 1

            self.save_workspace(workspace)

    def set_active_agent_tab(self, index: Optional[int]):
        """
        Set the active agent tab index.

        Args:
            index: Index of tab to activate (None to deactivate all)
        """
        workspace = self.load_workspace()
        workspace['active_agent_tab'] = index
        self.save_workspace(workspace)

    def update_agent_tab_name(self, session_id: str, new_name: str):
        """
        Update the display name of an agent tab.

        Args:
            session_id: Session identifier
            new_name: New display name
        """
        workspace = self.load_workspace()
        agent_tabs = workspace.get('agent_tabs', [])

        for tab in agent_tabs:
            if tab.get('session_id') == session_id:
                tab['session_name'] = new_name
                break

        self.save_workspace(workspace)
