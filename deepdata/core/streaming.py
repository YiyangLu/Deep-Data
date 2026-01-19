"""
Event streaming for real-time agent interactions.

Provides event emission for web UIs and other streaming consumers.
"""

from typing import Callable, Awaitable

from ..utils.logging import create_logger

logger = create_logger(__name__)


class EventEmitter:
    """
    Emits events during agent execution for streaming use cases.

    Supports two modes:
    1. Per-query callback: Pass callback to emit() for single-query streaming
    2. Persistent subscribers: Use subscribe() for long-lived event consumers

    Event types:
    - 'started': Agent started
    - 'resumed': Agent resumed session
    - 'stopped': Agent stopped
    - 'query_start': Query began
    - 'text': Text block from assistant
    - 'tool_use': Tool call from assistant
    - 'tool_result': Tool execution result
    - 'plot_show': Plot created
    - 'plot_command': Plot interaction
    - 'complete': Query completed with statistics
    - 'error': Error occurred
    """

    def __init__(self):
        self._subscribers: list[Callable[[str, dict], Awaitable[None]]] = []

    def subscribe(self, callback: Callable[[str, dict], Awaitable[None]]):
        """
        Subscribe to all events from this emitter.

        Args:
            callback: Async function receiving (event_type, data)
        """
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable):
        """
        Unsubscribe from events.

        Args:
            callback: Previously subscribed callback
        """
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def clear(self):
        """Clear all subscribers."""
        self._subscribers.clear()

    async def emit(
        self,
        event_type: str,
        data: dict,
        callback: Callable[[str, dict], Awaitable[None]] | None = None
    ):
        """
        Emit event to subscribers and optional callback.

        Args:
            event_type: Type of event
            data: Event data dictionary
            callback: Optional per-query callback (in addition to subscribers)
        """
        # Emit to per-query callback
        if callback:
            try:
                await callback(event_type, data)
            except Exception as e:
                logger.error(f"Error in per-query callback: {e}")

        # Emit to persistent subscribers
        for subscriber in self._subscribers:
            try:
                await subscriber(event_type, data)
            except Exception as e:
                logger.error(f"Error in subscriber: {e}")
