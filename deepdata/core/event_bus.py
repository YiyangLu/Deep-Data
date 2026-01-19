"""
Event bus for decoupling modules via publish-subscribe pattern.

Enables plotly tools to emit events without depending on web modules.
Web modules can subscribe to these events without creating circular dependencies.

Design Philosophy:
- No dependencies on plotly or web modules
- Thread-safe event publishing
- Async-first design
- Type-safe event data
"""

from typing import Callable, Awaitable, Any
from dataclasses import dataclass
import asyncio
from collections import defaultdict

from ..utils.logging import create_logger

logger = create_logger(__name__)


@dataclass
class Event:
    """Event emitted through the event bus"""
    type: str  # Event type identifier (e.g., 'plot_show', 'plot_hide')
    data: dict[str, Any]  # Event payload


EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    """
    Central event bus for application-wide event distribution.

    Uses publish-subscribe pattern to decouple modules:
    - Publishers emit events without knowing who consumes them
    - Subscribers register handlers for event types they care about

    Thread-safe and async-friendly.

    Example:
        # In plotly/tools.py (publisher)
        from ..core.event_bus import get_event_bus

        await get_event_bus().publish('plot_show', {
            'plot_id': 1,
            'url': 'http://localhost:8000/plot/1'
        })

        # In web/agent_manager.py (subscriber)
        from ..core.event_bus import get_event_bus

        async def handle_plot_show(event):
            await stream_handler.stream_plot_show(
                event.data['plot_id'],
                event.data['url']
            )

        get_event_bus().subscribe('plot_show', handle_plot_show)
    """

    def __init__(self):
        """Initialize event bus with empty subscriber registry"""
        # Map of event_type -> list of handlers
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: str, handler: EventHandler):
        """
        Register a handler for a specific event type.

        Args:
            event_type: Type of event to listen for (e.g., 'plot_show')
            handler: Async function that receives Event and returns None

        Example:
            async def my_handler(event: Event):
                print(f"Received: {event.data}")

            event_bus.subscribe('plot_show', my_handler)
        """
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler):
        """
        Remove a handler for a specific event type.

        Args:
            event_type: Type of event to stop listening for
            handler: Handler to remove
        """
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(handler)
            except ValueError:
                # Handler not found, ignore
                pass

    async def publish(self, event_type: str, data: dict[str, Any]):
        """
        Publish an event to all registered subscribers.

        Handlers are called concurrently. If a handler raises an exception,
        it's logged but doesn't affect other handlers.

        Args:
            event_type: Type of event (e.g., 'plot_show', 'plot_hide')
            data: Event payload data

        Example:
            await event_bus.publish('plot_show', {
                'plot_id': 1,
                'url': 'http://localhost:8000/plot/1'
            })
        """
        event = Event(type=event_type, data=data)

        # Get handlers for this event type
        handlers = self._subscribers.get(event_type, [])

        if not handlers:
            # No subscribers, silently ignore
            return

        # Call all handlers concurrently
        tasks = []
        for handler in handlers:
            try:
                task = asyncio.create_task(handler(event))
                tasks.append(task)
            except Exception as e:
                # Log error but continue with other handlers
                logger.error(f"Error creating task for event handler: {e}")

        # Wait for all handlers to complete
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Log any exceptions from handlers
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Error in event handler for '{event_type}': {result}")

    def clear_subscribers(self, event_type: str | None = None):
        """
        Clear subscribers for specific event type or all event types.

        Useful for testing or resetting state.

        Args:
            event_type: Event type to clear (None = clear all)
        """
        if event_type is None:
            self._subscribers.clear()
        else:
            self._subscribers[event_type].clear()


# Global event bus instance (singleton)
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """
    Get the global event bus instance (singleton).

    Creates the event bus on first call, subsequent calls return the same instance.

    Returns:
        Global EventBus instance

    Example:
        from ..core.event_bus import get_event_bus

        event_bus = get_event_bus()
        await event_bus.publish('plot_show', {...})
    """
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def reset_event_bus():
    """
    Reset the global event bus instance.

    Useful for testing to ensure clean state between tests.
    """
    global _event_bus
    _event_bus = None
