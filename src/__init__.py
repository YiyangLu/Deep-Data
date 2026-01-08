"""
Agent system using Claude SDK.

Structure:
- core/: Framework components (Agent, session storage, event bus)
- web/: Web UI server with WebSocket streaming
- plotly/: Interactive visualization server
- utils/: Shared utilities
"""

from .core import Agent
from . import core

__all__ = ["Agent", "core"]
