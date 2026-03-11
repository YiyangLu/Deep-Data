"""
Screenshot management service.

Handles screenshot decoding, storage, and file operations.
"""

import base64
from pathlib import Path

from ....core.session_registry import get_session_store
from ....utils.logging import create_logger
from ....utils.paths import get_logs_root

logger = create_logger(__name__)


class ScreenshotService:
    """
    Manages screenshot storage and retrieval.

    Responsibilities:
    - Decode base64 screenshot data
    - Generate unique filenames
    - Save screenshots to session folder
    - Retrieve screenshot paths
    """

    def __init__(self, logs_root: Path = None):
        """Initialize screenshot service."""
        self.logs_root = logs_root or get_logs_root()

    def _get_screenshots_dir(self, session_id: str, plot_id: int) -> Path:
        """
        Get screenshots directory for specified session and plot.

        Args:
            session_id: Session identifier
            plot_id: Plot identifier

        Returns:
            Path to screenshots directory (e.g., session_folder/screenshots/{plot_id}/)

        Raises:
            ValueError: If session not found
        """
        session_store = get_session_store(self.logs_root)
        session_info = session_store.get_session_info(session_id)

        # Create plot-specific screenshot folder
        screenshots_dir = session_info.folder_path / "screenshots" / str(plot_id)
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        return screenshots_dir

    def save_screenshot(
        self,
        session_id: str,
        plot_id: int,
        interaction_id: int,
        screenshot_data: str,
    ) -> tuple[str, int]:
        """
        Save screenshot from base64 data to session's screenshots folder.

        Args:
            session_id: Session identifier
            plot_id: Plot identifier
            interaction_id: Interaction id (used as filename for uniqueness)
            screenshot_data: Base64-encoded PNG data URL

        Returns:
            tuple: (relative_screenshot_path, size_in_kb)
                  Path is relative to session folder (e.g., "screenshots/1/3.png")

        Raises:
            ValueError: If screenshot data is invalid or session not found
        """
        if not screenshot_data.startswith('data:image/png;base64,'):
            raise ValueError("Invalid screenshot data format")

        # Get session's screenshots directory for this plot
        screenshots_dir = self._get_screenshots_dir(session_id, plot_id)

        # Decode base64 data
        base64_data = screenshot_data.split(',', 1)[1]
        image_bytes = base64.b64decode(base64_data)
        size_kb = len(image_bytes) // 1024

        # Use interaction_id as filename for uniqueness
        filename = f"{interaction_id}.png"
        full_path = screenshots_dir / filename

        # Save to disk
        with open(full_path, 'wb') as f:
            f.write(image_bytes)

        # Return relative path from session folder
        relative_path = f"screenshots/{plot_id}/{filename}"
        logger.debug(f"Screenshot saved: {full_path} (size: {size_kb}KB)")

        return relative_path, size_kb

    def get_screenshot_path(self, session_id: str, plot_id: int, interaction_id: int) -> Path:
        """
        Get full path for screenshot file in specified session.

        Args:
            session_id: Session identifier
            plot_id: Plot identifier
            interaction_id: Interaction id (filename without .png)

        Returns:
            Path object for the screenshot, or None if session not found
        """
        try:
            session_store = get_session_store(self.logs_root)
            session_info = session_store.get_session_info(session_id)
            return session_info.folder_path / "screenshots" / str(plot_id) / f"{interaction_id}.png"
        except Exception:
            return None

    def screenshot_exists(self, session_id: str, plot_id: int, interaction_id: int) -> bool:
        """
        Check if screenshot file exists for specified session and plot.

        Args:
            session_id: Session identifier
            plot_id: Plot identifier
            interaction_id: Interaction id

        Returns:
            True if file exists, False otherwise
        """
        path = self.get_screenshot_path(session_id, plot_id, interaction_id)
        return path is not None and path.exists()
