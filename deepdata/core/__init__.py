"""
Core framework components for building Claude agents.

This module provides the fundamental building blocks:
- Agent: Base agent class with session and transcript
- AgentRegistry: Global registry for discovering agents
- agent_context: Context for tracking current agent in tools
- EventSink: Protocol for receiving streaming events
- Display utilities for terminal output
- Message utilities for debugging and error handling
"""

from .agent import Agent
from .registry import AgentRegistry, get_registry
from .agent_context import get_current_agent, agent_context
from .event_sink import (
    EventSink,
    NullSink,
    FileSink,
    MultiSink,
    CallbackSink,
)
from .display import display_query, display_response
from .message_utils import message_to_dict, save_messages

__all__ = [
    "Agent",
    "AgentRegistry",
    "get_registry",
    "get_current_agent",
    "agent_context",
    "EventSink",
    "NullSink",
    "FileSink",
    "MultiSink",
    "CallbackSink",
    "display_query",
    "display_response",
    "message_to_dict",
    "save_messages",
]
