"""
Web UI module for streaming agent interactions.

Provides FastAPI WebSocket server for real-time agent communication.
"""

from .server import app
from .connection import WebConnection

__all__ = ['app', 'WebConnection']
