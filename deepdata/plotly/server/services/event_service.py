"""
Event logging service.

Handles interaction event logging to SessionStore.
"""

import json
from pathlib import Path
from typing import Any

from ....core.session_registry import get_session_store, get_current_session
from ....utils.logging import create_logger
from ....utils.paths import get_logs_root

logger = create_logger(__name__)


class EventService:
    """
    Manages interaction event logging to SessionStore.

    Responsibilities:
    - Log interaction events to specified session
    - Format event logs for display
    """

    def __init__(self, logs_root: Path = None):
        """
        Initialize event service.

        Args:
            logs_root: Root directory for logs (default: ./logs)
        """
        self.logs_root = logs_root or get_logs_root()

    def log_event(
        self,
        session_id: str,
        plot_id: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> int:
        """
        Log an interaction event to SessionStore.

        Args:
            session_id: Session identifier
            plot_id: Plot identifier
            event_type: Type of event (click, hover, etc.)
            payload: Event payload data

        Returns:
            The per-plot interaction_id (1, 2, 3...)
        """
        try:
            session_store = get_session_store(self.logs_root)
            interaction_id = session_store.log_interaction(
                session_id=session_id,
                plot_id=plot_id,
                event_type=event_type,
                payload=payload,
            )
            logger.debug(f"Interaction logged to session {session_id}: {event_type} on plot {plot_id}")
            return interaction_id
        except Exception as e:
            logger.error(f"Failed to log interaction to session store: {e}")
            return 0

    def update_screenshot(
        self,
        session_id: str,
        plot_id: int,
        interaction_id: int,
        screenshot_path: str,
        screenshot_size_kb: int
    ):
        """
        Update screenshot info for an existing interaction.

        Args:
            session_id: Session identifier
            plot_id: Plot identifier
            interaction_id: Per-plot interaction id (1, 2, 3...)
            screenshot_path: Relative path to screenshot
            screenshot_size_kb: Screenshot file size in KB
        """
        try:
            session_store = get_session_store(self.logs_root)
            session_store.update_interaction_screenshot(
                session_id=session_id,
                plot_id=plot_id,
                interaction_id=interaction_id,
                screenshot_path=screenshot_path,
                screenshot_size_kb=screenshot_size_kb
            )
        except Exception as e:
            logger.error(f"Failed to update screenshot: {e}")

    def get_events(
        self,
        plot_id: int | None = None,
        event_type: str | None = None,
        limit: int = 100
    ) -> list[tuple]:
        """
        Retrieve interaction events from current session.

        Args:
            plot_id: Optional filter by plot_id
            event_type: Optional filter by event_type
            limit: Maximum number of events to return

        Returns:
            List of tuples: (id, plot_id, timestamp, event_type, screenshot_path, size_kb)
        """
        session_store, session_id = get_current_session()
        if not session_store or not session_id:
            return []

        try:
            interactions = session_store.get_interactions(session_id, limit=limit)

            # Convert to expected tuple format
            result = []
            for interaction in interactions:
                result.append((
                    interaction['id'],
                    interaction['plot_id'],
                    interaction['timestamp'],
                    interaction['event_type'],
                    interaction.get('screenshot_path'),
                    interaction.get('screenshot_size_kb', 0)
                ))

            # Apply filters if specified
            if plot_id is not None:
                result = [r for r in result if r[1] == plot_id]
            if event_type is not None:
                result = [r for r in result if r[3] == event_type]

            return result[:limit]
        except Exception as e:
            logger.error(f"Failed to get events from session store: {e}")
            return []

    def get_statistics(self) -> dict[str, Any]:
        """
        Get aggregate statistics from current session.

        Returns:
            Dictionary with event statistics
        """
        session_store, session_id = get_current_session()
        if not session_store or not session_id:
            return {
                'total_events': 0,
                'total_screenshots': 0,
                'total_size_kb': 0,
                'unique_plots': 0
            }

        try:
            stats = session_store.get_session_stats(session_id)
            return {
                'total_events': stats.get('total_interactions', 0),
                'total_screenshots': stats.get('total_screenshots', 0),
                'total_size_kb': stats.get('total_screenshot_size_kb', 0),
                'unique_plots': stats.get('total_plots', 0)
            }
        except Exception as e:
            logger.error(f"Failed to get statistics from session store: {e}")
            return {
                'total_events': 0,
                'total_screenshots': 0,
                'total_size_kb': 0,
                'unique_plots': 0
            }

    def format_log_message(
        self,
        event_id: int,
        plot_id: int,
        event_type: str,
        screenshot_path: str | None,
        screenshot_size_kb: int | None
    ) -> str:
        """
        Format a log message for console output.

        Args:
            event_id: Event ID
            plot_id: Plot ID
            event_type: Event type
            screenshot_path: Screenshot path (if any)
            screenshot_size_kb: Screenshot size (if any)

        Returns:
            Formatted log message string
        """
        log_message = f"[{event_type:8s}]"
        if screenshot_path:
            log_message += f" 📸 {screenshot_size_kb}KB"
        else:
            log_message += f" 📝 event"
        log_message += f"  (id={event_id}, plot={plot_id})"
        return log_message
