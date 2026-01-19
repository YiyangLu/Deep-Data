"""
Headless event subscriber for plot events.

Subscribes to plot_show and plot_command events and handles them server-side
when no browser is connected (fallback mode).

- plot_show: Generates init event with screenshot (matches browser first-render)
- plot_command: Handles relayout, legendclick, selected commands
"""

from pathlib import Path
from typing import Optional

from ....core.event_bus import get_event_bus, Event
from ....utils.logging import create_logger
from .headless_handler import get_headless_handler

logger = create_logger(__name__)


def _has_browser_connection() -> bool:
    """
    Check if there are active browser connections.

    Imports lazily to avoid circular dependency.
    """
    try:
        from ....web.server import has_active_browser_connections
        return has_active_browser_connections()
    except ImportError:
        # Web server not available (e.g., pure headless mode)
        return False

# Track if subscriber is registered
_subscriber_registered = False


async def handle_plot_show_headless(event: Event):
    """
    Handle plot_show events in headless mode (fallback).

    Generates init event with screenshot when a new plot is created.
    This matches browser behavior where init is logged when plot first renders.
    """
    # Skip if browser is connected - browser handles init
    if _has_browser_connection():
        logger.debug("Browser connected, skipping headless init")
        return

    session_id = event.data.get('session_id')
    plot_id = event.data.get('plot_id')

    if not all([session_id, plot_id]):
        logger.warning(f"Invalid plot_show event: {event.data}")
        return

    logger.info(f"Headless fallback handling: init on plot {plot_id}")

    # Use the headless handler to generate init event
    handler = get_headless_handler()
    result = handler.handle_init(session_id, plot_id)

    if result.get('success'):
        logger.info(f"Headless init complete: {result}")
    else:
        logger.error(f"Headless init failed: {result.get('error')}")


async def handle_plot_command_headless(event: Event):
    """
    Handle plot_command events in headless mode (fallback).

    This handler processes commands server-side when no browser is connected.
    If a browser is connected, it skips handling (browser handles the command).
    """
    # Skip if browser is connected - browser handles plot commands
    if _has_browser_connection():
        logger.debug("Browser connected, skipping headless handler")
        return

    session_id = event.data.get('session_id')
    plot_id = event.data.get('plot_id')
    command = event.data.get('command')
    args = event.data.get('args', {})

    if not all([session_id, plot_id, command]):
        logger.warning(f"Invalid plot_command event: {event.data}")
        return

    logger.info(f"Headless fallback handling: {command} on plot {plot_id}")

    # Use the headless handler
    handler = get_headless_handler()
    result = handler.handle_command(session_id, plot_id, command, args)

    if result.get('success'):
        logger.info(f"Headless command complete: {result}")
    else:
        logger.error(f"Headless command failed: {result.get('error')}")


def register_headless_subscriber():
    """
    Register the headless subscriber for plot events.

    Subscribes to:
    - plot_show: Generate init event with screenshot
    - plot_command: Handle relayout, legendclick, selected

    Should be called once during server/agent initialization.
    Safe to call multiple times - will only register once.
    """
    global _subscriber_registered

    if _subscriber_registered:
        logger.debug("Headless subscriber already registered")
        return

    get_event_bus().subscribe('plot_show', handle_plot_show_headless)
    get_event_bus().subscribe('plot_command', handle_plot_command_headless)
    _subscriber_registered = True
    logger.info("Headless plot subscribers registered (plot_show + plot_command)")


def unregister_headless_subscriber():
    """
    Unregister the headless subscriber.

    Useful for cleanup or when browser takes over.
    """
    global _subscriber_registered

    if not _subscriber_registered:
        return

    get_event_bus().unsubscribe('plot_show', handle_plot_show_headless)
    get_event_bus().unsubscribe('plot_command', handle_plot_command_headless)
    _subscriber_registered = False
    logger.info("Headless plot subscribers unregistered")


def is_headless_subscriber_registered() -> bool:
    """Check if headless subscriber is currently registered."""
    return _subscriber_registered
