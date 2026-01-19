"""
Global SessionStore registry for cross-module access.

This module provides two key features:

1. SessionStore Singleton Pattern
   - Provides get_session_store() helper to avoid duplicate instantiations
   - Maintains one SessionStore instance per logs_root
   - Reduces memory usage and ensures consistent state

2. Context-Local Session Tracking
   - Allows plotly tools and other modules to log to the current session
   - Uses contextvars for proper async context isolation
   - Enables multiple concurrent agents to maintain separate sessions
   - Falls back to environment variables when needed (e.g., tool execution contexts)

IMPORTANT: Parallel Agent Execution
   - Running multiple agents with asyncio.gather() in the same process will cause
     session collisions (env var fallback is shared across all async contexts)
   - For parallel agent execution, use subprocess isolation (ProcessPoolExecutor)
   - Each subprocess gets its own environment, avoiding session conflicts
   - See eval/run_parallel.py for the correct pattern
"""

import os
import asyncio
from contextvars import ContextVar
from pathlib import Path
from typing import Optional, Dict
from .session import SessionStore
from .event_bus import get_event_bus
from ..utils.paths import get_logs_root
from ..utils.logging import create_logger

logger = create_logger(__name__)


# Singleton registry: one SessionStore per logs_root
_session_stores: Dict[str, SessionStore] = {}


def get_session_store(logs_root: Path = None) -> SessionStore:
    """
    Get or create SessionStore singleton for given logs_root.

    This ensures we only have one SessionStore instance per logs_root,
    avoiding duplicate database connections and ensuring consistent state.

    Args:
        logs_root: Root directory for logs (default: ./logs)

    Returns:
        SessionStore instance (singleton per logs_root)

    Example:
        >>> # Multiple calls return same instance
        >>> store1 = get_session_store()  # Uses get_logs_root()
        >>> store2 = get_session_store()
        >>> assert store1 is store2
    """
    logs_root = logs_root or get_logs_root()
    key = str(logs_root.absolute())

    if key not in _session_stores:
        _session_stores[key] = SessionStore(logs_root=logs_root)

    return _session_stores[key]


# Context-local session storage (async-safe, supports multiple concurrent agents)
_current_session: ContextVar[tuple[SessionStore, str] | None] = ContextVar(
    'current_session',
    default=None
)


def register_session(session_store: SessionStore, storage_session_id: str):
    """
    Register the current session store for this async context.

    This is async-safe and context-local, meaning each agent running
    in a separate async task will have its own session registration.

    Also sets environment variables as fallback for tool execution contexts
    where contextvars may not propagate.

    Emits 'session_established' event via event bus for modules that need
    to know when the SDK session_id is available (e.g., Deep Plot frontend updates).

    Args:
        session_store: SessionStore instance
        storage_session_id: Current storage session ID
    """
    logger.info(f"register_session() called with session_id={storage_session_id}")
    _current_session.set((session_store, storage_session_id))

    # Set environment variables as fallback for tool execution contexts
    os.environ['_AGENT_SESSION_ID'] = storage_session_id
    if session_store.logs_root:
        os.environ['_AGENT_LOGS_ROOT'] = str(session_store.logs_root)

    # Emit session_established event via event bus
    # This allows modules (like web/server.py) to respond immediately
    # when the SDK session_id becomes known, rather than waiting for query completion
    try:
        loop = asyncio.get_running_loop()
        asyncio.create_task(get_event_bus().publish('session_established', {
            'session_id': storage_session_id
        }))
    except RuntimeError:
        # No event loop running - skip event emission
        # This can happen during testing or non-async initialization
        logger.debug("No event loop running, skipping session_established event")


def unregister_session():
    """
    Clear the current session store for this async context.

    Also clears environment variables.
    """
    _current_session.set(None)

    # Clear environment variables
    os.environ.pop('_AGENT_SESSION_ID', None)
    os.environ.pop('_AGENT_LOGS_ROOT', None)


def get_current_session() -> tuple[Optional[SessionStore], Optional[str]]:
    """
    Get the current session store and session ID for this async context.

    Falls back to environment variables if contextvar is not set (e.g., in
    tool execution contexts where contextvars don't propagate).

    Returns:
        Tuple of (session_store, storage_session_id), both may be None if no session is active
    """
    # Try contextvar first (preferred for async contexts)
    session = _current_session.get()
    if session is not None:
        logger.debug(f"get_current_session() returning contextvar session_id={session[1]}")
        return session

    # Fallback to environment variables (for tool execution contexts)
    session_id = os.environ.get('_AGENT_SESSION_ID')
    logs_root_str = os.environ.get('_AGENT_LOGS_ROOT')

    if session_id and logs_root_str:
        logger.debug(f"get_current_session() returning env var session_id={session_id}")
        # Use singleton to avoid duplicate SessionStore instances
        logs_root = Path(logs_root_str)
        session_store = get_session_store(logs_root)
        return (session_store, session_id)

    logger.warning("get_current_session() returning None - no session found")
    return (None, None)


def is_session_active() -> bool:
    """
    Check if a session is currently registered in this async context.

    Falls back to checking environment variables if contextvar is not set.

    Returns:
        True if a session is active, False otherwise
    """
    # Check contextvar first
    if _current_session.get() is not None:
        return True

    # Fallback to environment variables
    return (os.environ.get('_AGENT_SESSION_ID') is not None and
            os.environ.get('_AGENT_LOGS_ROOT') is not None)
