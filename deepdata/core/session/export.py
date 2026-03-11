"""
Session export and deletion mixin.

Handles session export, cloning, and cleanup operations.
"""

import sqlite3
import shutil
import uuid
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

    def resolve_session_id(self, prefix: str) -> str:
        """Resolve a session ID prefix to a full session ID."""
        conn = sqlite3.connect(str(self.index_db_path))
        rows = conn.execute(
            "SELECT session_id FROM sessions WHERE session_id LIKE ?",
            (prefix + '%',)
        ).fetchall()
        conn.close()

        if len(rows) == 0:
            raise ValueError(f"Session not found: {prefix}")
        if len(rows) > 1:
            raise ValueError(f"Ambiguous session prefix '{prefix}' — matches {len(rows)} sessions")
        return rows[0][0]

    def clone_session(self, template_session_id: str) -> str:
        """
        Clone a session for fork mode (user studies).

        Copies session folder (session.db, plots/, transcript) and SDK .jsonl file,
        then registers the clone in session_index.db with zeroed counters.

        Args:
            template_session_id: Session ID or prefix to clone from

        Returns:
            New session ID
        """
        # Resolve prefix to full ID
        template_session_id = self.resolve_session_id(template_session_id)
        new_id = str(uuid.uuid4())

        # Get template info
        template_folder = self._get_session_folder(template_session_id)
        session_info = self.get_session_info(template_session_id)
        init_cwd = session_info.init_cwd

        # Copy session folder (session.db, plots/, transcript.txt, screenshots/)
        new_folder = template_folder.parent / new_id
        shutil.copytree(template_folder, new_folder)

        # Copy SDK .jsonl file (Claude Code conversation transcript)
        sdk_dir = Path.home() / ".claude" / "projects" / self._cwd_to_sdk_name(init_cwd)
        src_jsonl = sdk_dir / f"{template_session_id}.jsonl"
        if src_jsonl.exists():
            shutil.copy2(src_jsonl, sdk_dir / f"{new_id}.jsonl")

        # Register in session_index.db (zeroed cost counters)
        now = self._utc_now()
        conn = sqlite3.connect(str(self.index_db_path))
        conn.execute(
            """
            INSERT INTO sessions
            (session_id, folder_path, created_at, updated_at, agent_id, init_cwd, current_cwd,
             transcript_file, session_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id,
                str(new_folder.relative_to(self.logs_root)),
                now,
                now,
                "fork",
                init_cwd,
                init_cwd,
                "transcript.txt",
                session_info.session_name or "Agent",
            )
        )
        conn.commit()
        conn.close()

        return new_id

    @staticmethod
    def _cwd_to_sdk_name(cwd: str) -> str:
        """Convert cwd path to Claude SDK project directory name (slash→dash)."""
        return cwd.replace("/", "-")

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
