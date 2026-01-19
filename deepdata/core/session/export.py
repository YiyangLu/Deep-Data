"""
Session export and deletion mixin.

Handles session export and cleanup operations.
"""

import sqlite3
import shutil
from pathlib import Path


class SessionExportMixin:
    """Mixin class providing export and deletion methods for SessionStore."""

    def export_session(self, session_id: str, output_path: Path):
        """
        Export session as self-contained zip archive.

        Args:
            session_id: Session identifier
            output_path: Output directory for zip file

        Returns:
            Path to created zip file

        Example:
            >>> store.export_session("abc123", Path("/exports"))
            >>> # Creates: /exports/abc123.zip
        """
        session_folder = self._get_session_folder(session_id)

        output_path.mkdir(parents=True, exist_ok=True)
        zip_path = output_path / session_id

        # Create zip (without .zip extension, shutil adds it)
        shutil.make_archive(
            str(zip_path),
            'zip',
            root_dir=session_folder.parent,
            base_dir=session_folder.name
        )

        return Path(f"{zip_path}.zip")

    def delete_session(self, session_id: str):
        """
        Delete session and all associated data.

        Args:
            session_id: Session identifier

        Warning:
            This permanently deletes all session data including:
            - Database
            - Transcript
            - Screenshots
        """
        session_folder = self._get_session_folder(session_id)

        # Delete from index
        conn = sqlite3.connect(str(self.index_db_path))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()

        # Delete folder
        shutil.rmtree(session_folder)
