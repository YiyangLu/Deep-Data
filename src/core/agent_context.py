"""
Context variable for tracking the currently executing agent.

Used by tools (e.g., plotly) to emit events to the correct agent
without global event bus coupling.
"""

from contextvars import ContextVar
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .agent import Agent

_current_agent: ContextVar["Agent | None"] = ContextVar('current_agent', default=None)


def get_current_agent() -> "Agent | None":
    """
    Get the agent currently executing a query.

    Returns None if called outside of an agent query context.
    Used by tools (e.g., plotly) to emit events to the correct agent.

    Returns:
        Current Agent or None
    """
    return _current_agent.get()


@contextmanager
def agent_context(agent: "Agent"):
    """
    Context manager to set the current agent.

    Used by Agent.query() to establish context for tool execution.

    Args:
        agent: Agent executing the query

    Example:
        with agent_context(self):
            await self._execute_query(prompt)
    """
    token = _current_agent.set(agent)
    try:
        yield
    finally:
        _current_agent.reset(token)
