"""
Base classes and utilities for WebSocket message handlers.
"""

from dataclasses import dataclass
from typing import Any, Dict

from fastapi import WebSocket

from ..connection import WebConnection
from ...core.workspace_manager import WorkspaceManager
from ...utils.logging import create_logger

logger = create_logger(__name__)


@dataclass
class WebSocketContext:
    """
    Shared state passed to all WebSocket message handlers.

    Uses WebConnection for agent management (replaces AgentManager).
    """
    websocket: WebSocket
    connection_id: str
    connection: WebConnection
    agent_cwd: str
    agent_model: str | None
    workspace_manager: WorkspaceManager
    active_connections: Dict[str, tuple]

    async def send(self, msg_type: str, **data: Any) -> bool:
        """
        Send JSON message to WebSocket.

        Args:
            msg_type: Message type (e.g., "connected", "error", "session_info")
            **data: Additional data to include in message

        Returns:
            True if message was sent successfully, False otherwise
        """
        try:
            # Check if WebSocket is still connected before sending
            if self.websocket.client_state.name != "CONNECTED":
                logger.debug(f"Skipping send {msg_type}: WebSocket not connected")
                return False
            await self.websocket.send_json({"type": msg_type, **data})
            return True
        except Exception as e:
            logger.error(f"Error sending {msg_type}: {e}")
            return False

    async def send_error(self, error: str) -> None:
        """
        Send error message to WebSocket.

        Args:
            error: Error message string
        """
        await self.send("error", error=error)

    async def stop_current_agent(self) -> None:
        """Stop current agent if running."""
        await self.connection.stop_agent()

    async def create_new_connection(self, session_name: str = "Agent") -> WebConnection:
        """
        Create a new WebConnection for a new session.

        Stops current agent and creates fresh connection state.
        Used when switching to a new session (e.g., Deep Plot).

        Args:
            session_name: Display name for the session

        Returns:
            New WebConnection instance (also updates self.connection)
        """
        # Stop current agent
        await self.connection.stop_agent()

        # Create new connection with same config
        new_conn = WebConnection(
            websocket=self.websocket,
            cwd=self.connection.cwd,
            model=self.agent_model,
        )
        new_conn._session_name = session_name

        # Update context and active_connections
        self.connection = new_conn
        self.active_connections[self.connection_id] = (self.websocket, new_conn)

        return new_conn


def get_session_store():
    """Get session store singleton (lazy import to avoid cycles)."""
    from ...core.session_registry import get_session_store as _get_session_store
    from ...utils.paths import get_logs_root
    return _get_session_store(get_logs_root())
