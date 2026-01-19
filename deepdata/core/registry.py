"""
Global registry of active agents.

Enables automatic discovery of agents created anywhere in the codebase.
Web UI, MLE monitor, or other consumers can subscribe to agent lifecycle events.
"""

from typing import TYPE_CHECKING, Callable

from ..utils.logging import create_logger

if TYPE_CHECKING:
    from .agent import Agent

logger = create_logger(__name__)


class AgentRegistry:
    """
    Global registry of active agents.

    Features:
    - Tracks all Agent instances that call start()
    - Notifies subscribers when agents register/unregister
    - Enables discovery of agents created anywhere

    Usage:
        # Subscribe to agent lifecycle
        def on_agent(event: str, agent: Agent):
            if event == "registered":
                agent.events.subscribe(my_handler)

        get_registry().subscribe(on_agent)

        # Agent self-registers
        agent = Agent(...)
        await agent.start()  # Appears in registry
    """

    _instance: "AgentRegistry | None" = None

    def __init__(self):
        self._agents: dict[str, "Agent"] = {}
        self._listeners: list[Callable[[str, "Agent"], None]] = []

    @classmethod
    def get(cls) -> "AgentRegistry":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        """Reset singleton (for testing)."""
        cls._instance = None

    def register(self, agent: "Agent"):
        """
        Register an agent. Called by Agent.start().

        Args:
            agent: Agent instance to register
        """
        self._agents[agent.agent_id] = agent
        logger.debug(f"Agent registered: {agent.agent_id} ({agent.agent_type})")
        self._notify("registered", agent)

    def unregister(self, agent_id: str):
        """
        Unregister an agent. Called by Agent.stop().

        Args:
            agent_id: ID of agent to unregister
        """
        agent = self._agents.pop(agent_id, None)
        if agent:
            logger.debug(f"Agent unregistered: {agent_id}")
            self._notify("unregistered", agent)

    def get_agent(self, agent_id: str) -> "Agent | None":
        """Get agent by ID."""
        return self._agents.get(agent_id)

    def list_agents(self) -> list["Agent"]:
        """Get all registered agents."""
        return list(self._agents.values())

    def subscribe(self, callback: Callable[[str, "Agent"], None]):
        """
        Subscribe to agent lifecycle events.

        Callback receives:
        - ("registered", agent) when agent starts
        - ("unregistered", agent) when agent stops

        Also immediately notifies about existing agents.

        Args:
            callback: Function to call on lifecycle events
        """
        self._listeners.append(callback)
        # Notify about existing agents
        for agent in self._agents.values():
            try:
                callback("registered", agent)
            except Exception as e:
                logger.warning(f"Error notifying about existing agent: {e}")

    def unsubscribe(self, callback: Callable):
        """Remove a lifecycle subscriber."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self, event: str, agent: "Agent"):
        """Notify all listeners about an event."""
        for listener in self._listeners:
            try:
                listener(event, agent)
            except Exception as e:
                logger.warning(f"Error in registry listener: {e}")


def get_registry() -> AgentRegistry:
    """Get the global agent registry."""
    return AgentRegistry.get()
