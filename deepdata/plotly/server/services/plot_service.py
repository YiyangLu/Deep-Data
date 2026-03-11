"""
Plot storage and retrieval service.

Manages in-memory plot storage with unique IDs.
"""

import plotly.io as pio
from typing import Any

from ....utils.logging import create_logger

logger = create_logger(__name__)


class PlotStore:
    """
    In-memory plot storage with session-scoped IDs.

    Each session has its own plot counter starting from 1.
    Plots are keyed by (session_id, plot_id) tuple.

    This is a simple in-memory store. For production use, consider:
    - Redis for distributed storage
    - SQLite for persistence
    - File system with serialization
    """

    def __init__(self):
        """Initialize empty plot store."""
        self._plots: dict[tuple[str, int], Any] = {}
        self._session_counters: dict[str, int] = {}

    def _get_max_plot_id_from_db(self, session_id: str) -> int:
        """
        Get the maximum plot_id from database for a session.

        Used to sync the in-memory counter with existing plots on disk
        when a session is resumed.

        Returns:
            Maximum plot_id, or 0 if no plots exist
        """
        try:
            from ....core.session_registry import get_session_store
            from ....utils.paths import get_logs_root

            session_store = get_session_store(get_logs_root())
            plots = session_store.get_plots(session_id)

            if plots:
                max_id = max(p['plot_id'] for p in plots)
                return max_id
        except Exception as e:
            logger.warning(f"Failed to get max plot_id from DB for {session_id}: {e}")

        return 0

    def add_plot(self, session_id: str, fig_json: str, plot_id: int | None = None) -> tuple[int, Any]:
        """
        Add or update a plot and return its session-scoped ID.

        Args:
            session_id: Session identifier
            fig_json: Plot JSON string (from fig.to_json())
            plot_id: Optional plot ID to overwrite. If None, creates new plot.

        Returns:
            tuple: (plot_id, Figure object)

        Raises:
            Exception: If JSON parsing fails
        """
        # Reconstruct Figure from JSON
        fig = pio.from_json(fig_json)

        if plot_id is not None:
            # Update existing plot
            self._plots[(session_id, plot_id)] = fig
            logger.info(f"Updated plot {plot_id} in session {session_id}")
            return plot_id, fig

        # Create new plot - get or initialize session counter
        if session_id not in self._session_counters:
            # Check database for existing plots to avoid ID collision
            max_existing_id = self._get_max_plot_id_from_db(session_id)
            self._session_counters[session_id] = max_existing_id + 1
            if max_existing_id > 0:
                logger.info(f"Synced plot counter for session {session_id}: starting at {max_existing_id + 1}")

        plot_id = self._session_counters[session_id]
        self._session_counters[session_id] += 1

        # Store with (session_id, plot_id) key
        self._plots[(session_id, plot_id)] = fig

        return plot_id, fig

    def get_plot(self, session_id: str, plot_id: int) -> Any | None:
        """
        Retrieve plot by session ID and plot ID.

        Args:
            session_id: Session identifier
            plot_id: Plot identifier (session-scoped)

        Returns:
            Figure object or None if not found
        """
        return self._plots.get((session_id, plot_id))

    def exists(self, session_id: str, plot_id: int) -> bool:
        """
        Check if plot exists.

        Args:
            session_id: Session identifier
            plot_id: Plot identifier (session-scoped)

        Returns:
            True if plot exists, False otherwise
        """
        return (session_id, plot_id) in self._plots

    def count(self) -> int:
        """
        Return total number of plots.

        Returns:
            Number of stored plots
        """
        return len(self._plots)

    def clear(self):
        """Clear all plots (for testing)."""
        self._plots.clear()
        self._session_counters.clear()

    def clear_session(self, session_id: str):
        """Clear all plots for a session (e.g., after finalization)."""
        keys_to_remove = [k for k in self._plots if k[0] == session_id]
        for key in keys_to_remove:
            del self._plots[key]
        if session_id in self._session_counters:
            del self._session_counters[session_id]
        logger.info(f"Cleared {len(keys_to_remove)} plots for session {session_id}")


# Global singleton instance
_plot_store = PlotStore()


def get_plot_store() -> PlotStore:
    """
    Get the global plot store instance.

    Returns:
        PlotStore singleton
    """
    return _plot_store
