"""
Deep Data - Agent framework for data analysis, visualization, and ML automation.

Structure:
- core/: Framework components (Agent, session storage, event bus)
- web/: Web UI server with WebSocket streaming
- plotly/: Interactive visualization server
- mle/: MCTS-based ML solution search
- utils/: Shared utilities
"""

__version__ = "0.1.0"

from .core import Agent
from . import core

__all__ = ["Agent", "core", "__version__"]
