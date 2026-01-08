"""
WebConnection - Manages agent and streaming for a WebSocket connection.

Replaces AgentManager and StreamHandler with a simpler, more direct design.
Uses Agent directly instead of wrapping it.

Events flow:
1. Agent.events -> WebConnection._on_agent_event -> WebSocket
2. EventBus (MCP tools) -> WebConnection._on_event_bus -> WebSocket
"""

import uuid
import asyncio
from typing import Any, Callable, Awaitable
from pathlib import Path

from fastapi import WebSocket

from ..core.agent import Agent
from ..core.event_bus import get_event_bus, Event
from ..core.session_registry import get_session_store
from ..utils.paths import get_logs_root
from ..utils.logging import create_logger
from ..plotly.mcp_tools import create_plotly_mcp_server, PLOTLY_TOOLS

logger = create_logger(__name__)


class WebConnection:
    """
    Manages agent and streaming for a WebSocket connection.

    This class:
    - Creates and manages Agent instances directly
    - Forwards agent events to WebSocket
    - Subscribes to event bus for MCP tool events
    - Handles session resume logic

    Example:
        conn = WebConnection(websocket, cwd=Path("/workspace"))
        agent = await conn.ensure_agent()
        await conn.query("Hello")
        await conn.close()
    """

    def __init__(
        self,
        websocket: WebSocket,
        cwd: Path,
        resume_session_id: str | None = None,
        continue_last: bool = False,
        model: str | None = None,
    ):
        """
        Initialize WebConnection.

        Args:
            websocket: FastAPI WebSocket instance
            cwd: Working directory for agents
            resume_session_id: Specific session ID to resume
            continue_last: If True, resume the last session for this cwd
            model: Model to use (e.g., "sonnet", "opus", "haiku")
        """
        self.websocket = websocket
        self.cwd = cwd.resolve() if cwd else Path.cwd().resolve()
        self.resume_session_id = resume_session_id
        self.continue_last = continue_last
        self.model = model

        # Agent instance
        self.agent: Agent | None = None

        # Streaming state
        self._message_id: str | None = None
        self._session_info_sent = False
        self._initial_session_id: str | None = None  # Track ID before SDK assigns
        self._session_name: str = "Agent"  # Display name for session

        # Event bus handlers for cleanup
        self._event_bus_handlers: dict = {}

    @property
    def current_session_id(self) -> str | None:
        """Get the current session ID for tagging events."""
        if self.agent and self.agent.session_id:
            return self.agent.session_id
        return self._initial_session_id

    async def ensure_agent(
        self,
        extra_mcp_servers: dict | None = None,
        extra_tools: list[str] | None = None,
        session_name: str | None = None
    ) -> Agent:
        """
        Get or create agent for this connection.

        Args:
            extra_mcp_servers: Additional MCP servers (e.g., deep_plot)
            extra_tools: Additional tools to allow
            session_name: Display name for session (e.g., "Agent", "Deep Plot").
                          If None, uses existing _session_name or defaults to "Agent".

        Returns:
            Agent instance
        """
        if self.agent:
            return self.agent

        # Use provided session_name if given, otherwise keep existing _session_name
        if session_name is not None:
            self._session_name = session_name
        # _session_name defaults to "Agent" in __init__, can be set before calling ensure_agent

        # Determine session to resume
        session_id = None
        if self.continue_last:
            session_id = self._find_last_session()
            if session_id:
                logger.info(f"Resuming last session: {session_id}")
        elif self.resume_session_id:
            session_id = self.resume_session_id
            logger.info(f"Resuming session: {session_id}")

        # Generate agent_id (becomes session_id for new sessions)
        agent_id = session_id or str(uuid.uuid4())
        self._initial_session_id = agent_id

        # Create plotly MCP server (tuple: server_config, cleanup_fn)
        # WebConnection handles its own EventBus subscription, so no on_event here
        plotly_server, _ = create_plotly_mcp_server(enable_headless=True)

        # Build MCP servers dict
        mcp_servers = {"plotly": plotly_server}
        if extra_mcp_servers:
            mcp_servers.update(extra_mcp_servers)

        # Build allowed tools list
        allowed_tools = list(PLOTLY_TOOLS)
        if extra_tools:
            allowed_tools.extend(extra_tools)

        # Create agent
        self.agent = Agent(
            agent_id=agent_id,
            agent_type="chat",
            name=session_name,
            cwd=self.cwd,
            session_id=session_id,
            enable_storage=True,
            logs_root=get_logs_root(),
            mcp_servers=mcp_servers,
            allowed_tools=allowed_tools,
            permission_mode="bypassPermissions",
            model=self.model,
        )

        # Subscribe to agent events
        self.agent.events.subscribe(self._on_agent_event)

        # Subscribe to event bus for MCP tool events
        self._subscribe_to_event_bus()

        # Start or resume
        if session_id:
            await self.agent.resume()
        else:
            await self.agent.start()

        return self.agent

    def _find_last_session(self) -> str | None:
        """Find the most recent session for this cwd."""
        store = get_session_store(get_logs_root())
        sessions = store.list_sessions(cwd=self.cwd, limit=1)
        return sessions[0].session_id if sessions else None

    async def _on_agent_event(self, event_type: str, data: dict):
        """Forward agent events to WebSocket."""
        message_id = self._message_id or "unknown"
        logger.debug(f"_on_agent_event received: {event_type}")

        try:
            if event_type == 'query_start':
                # Generate new message ID for each query
                self._message_id = uuid.uuid4().hex[:12]

            elif event_type in ('started', 'resumed'):
                # These events fire before session_id is assigned
                # session_info is sent when we receive 'session_info' event from agent
                pass

            elif event_type == 'session_info':
                # Send session_info to frontend so it can link pending tab
                if not self._session_info_sent:
                    await self._send("session_info",
                        session_id=data.get('session_id'),
                        session_name=self._session_name
                    )
                    self._session_info_sent = True

            elif event_type == 'text':
                # Stream text in chunks for typing effect
                logger.debug(f"Handling text event, data keys: {data.keys()}")
                await self._stream_text(data['content'], self._message_id or "unknown")

            elif event_type == 'tool_use':
                await self._send("tool_use",
                    name=data['name'],
                    input=data['input'],
                    message_id=message_id,
                    session_id=self.current_session_id
                )

            elif event_type == 'tool_result':
                await self._send("tool_result",
                    name=data['name'],
                    result=data['result'],
                    message_id=message_id,
                    session_id=self.current_session_id
                )

            elif event_type == 'plot_show':
                await self._send("plot_show",
                    plot_id=data['plot_id'],
                    session_id=data['session_id'],
                    session_name=self._session_name,  # Include name directly
                    url=data['url'],
                    plot_type=data.get('plot_type', 'plot')
                )

            elif event_type == 'plot_command':
                await self._send("plot_command",
                    session_id=data['session_id'],
                    plot_id=data['plot_id'],
                    command=data['command'],
                    args=data['args']
                )

            elif event_type == 'complete':
                # session_info is sent at 'started'/'resumed' for early availability
                await self._send("complete",
                    message_id=message_id,
                    stats=data,
                    session_id=self.current_session_id
                )

            elif event_type == 'error':
                await self._send("error",
                    error=data['error'],
                    message_id=message_id,
                    session_id=self.current_session_id
                )

        except Exception as e:
            logger.error(f"Error handling agent event {event_type}: {e}")

    def _subscribe_to_event_bus(self):
        """Subscribe to event bus for MCP tool events."""
        event_bus = get_event_bus()

        async def handle_plot_show(event: Event):
            """Forward plot_show from event bus."""
            data = event.data
            await self._send("plot_show",
                plot_id=data['plot_id'],
                session_id=data['session_id'],
                session_name=self._session_name,  # Include name directly
                url=data['url'],
                plot_type=data.get('plot_type', 'plot')
            )

        async def handle_plot_command(event: Event):
            """Forward plot_command from event bus."""
            data = event.data
            await self._send("plot_command",
                session_id=data['session_id'],
                plot_id=data['plot_id'],
                command=data['command'],
                args=data['args']
            )

        self._event_bus_handlers = {
            'plot_show': handle_plot_show,
            'plot_command': handle_plot_command
        }

        event_bus.subscribe('plot_show', handle_plot_show)
        event_bus.subscribe('plot_command', handle_plot_command)
        logger.debug("Subscribed to event bus for plot events")

    def _unsubscribe_from_event_bus(self):
        """Unsubscribe from event bus."""
        if self._event_bus_handlers:
            event_bus = get_event_bus()
            for event_type, handler in self._event_bus_handlers.items():
                event_bus.unsubscribe(event_type, handler)
            self._event_bus_handlers = {}
            logger.debug("Unsubscribed from event bus")

    async def _send(self, msg_type: str, **data: Any):
        """Send JSON message to WebSocket."""
        try:
            await self.websocket.send_json({"type": msg_type, **data})
        except Exception as e:
            logger.error(f"Error sending {msg_type}: {e}")

    async def _stream_text(self, content: str, message_id: str, chunk_size: int = 5):
        """Stream text content in chunks for typing effect."""
        logger.debug(f"_stream_text called: content_len={len(content)}, message_id={message_id}")
        session_id = self.current_session_id

        # Send text_start
        await self._send("text_start", message_id=message_id, session_id=session_id)

        # Send content in chunks
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i + chunk_size]
            await self._send("text_chunk", content=chunk, message_id=message_id, session_id=session_id)
            await asyncio.sleep(0.01)  # Small delay for streaming effect

        # Send text_end
        await self._send("text_end", message_id=message_id, session_id=session_id)

    async def query(self, prompt: str, hidden: bool = False) -> dict[str, Any]:
        """
        Execute query on agent.

        Args:
            prompt: User query
            hidden: If True, don't store in conversation history

        Returns:
            Query statistics
        """
        agent = await self.ensure_agent()

        try:
            await agent.query(prompt, display=False, hidden=hidden)
            return {
                'success': True,
                'duration_ms': agent.duration_ms,
                'num_turns': agent.num_turns,
                'total_cost_usd': agent.total_cost_usd
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def get_conversation_history(self) -> list[dict]:
        """Get conversation history from storage."""
        if self.agent:
            return self.agent.get_conversation_history()
        return []

    def get_stats(self) -> dict[str, Any]:
        """Get agent statistics."""
        if self.agent:
            return {
                'session_id': self.agent.session_id,
                'num_turns': self.agent.num_turns,
                'total_cost_usd': self.agent.total_cost_usd,
                'duration_ms': self.agent.duration_ms,
            }
        return {}

    async def stop_agent(self):
        """Stop current agent."""
        self._unsubscribe_from_event_bus()
        if self.agent:
            await self.agent.stop()  # Clears event subscribers automatically
            self.agent = None

    async def close(self):
        """Close connection and cleanup."""
        await self.stop_agent()

    # Methods for session switching (used by handlers)

    def reset_for_new_session(self, session_name: str = "Agent"):
        """
        Reset state for creating a new session.

        Call this before ensure_agent() when switching sessions.
        """
        self._session_info_sent = False
        self._initial_session_id = None
        self._session_name = session_name
        self.resume_session_id = None
        self.continue_last = False

    def configure_resume(self, session_id: str):
        """
        Configure to resume a specific session.

        Call this before ensure_agent() to resume a session.
        """
        self._session_info_sent = False
        self._initial_session_id = session_id
        self.resume_session_id = session_id
        self.continue_last = False
