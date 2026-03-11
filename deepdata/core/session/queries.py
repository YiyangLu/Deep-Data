"""
Session query methods mixin.

Provides read-only query operations for sessions.
"""

import sqlite3
import json
from pathlib import Path
from typing import Optional
from .info import SessionInfo

# Default timeout for SQLite connections (seconds)
SQLITE_TIMEOUT = 30.0


def _connect_session_db(db_path: Path | str) -> sqlite3.Connection:
    """
    Create SQLite connection with WAL mode and timeout.

    WAL (Write-Ahead Logging) mode allows concurrent reads while writing,
    reducing "database is locked" errors during concurrent access.

    Args:
        db_path: Path to the session database file

    Returns:
        SQLite connection configured for concurrent access
    """
    conn = sqlite3.connect(str(db_path), timeout=SQLITE_TIMEOUT)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


class SessionQueriesMixin:
    """Mixin class providing query methods for SessionStore."""

    def get_all_session_names(self) -> list[str]:
        """
        Get all session names for deduplication purposes.

        Returns:
            List of all session names
        """
        conn = sqlite3.connect(str(self.index_db_path))
        rows = conn.execute("SELECT session_name FROM sessions WHERE session_name IS NOT NULL").fetchall()
        conn.close()
        return [row[0] for row in rows]

    def get_session_info(self, session_id: str) -> SessionInfo:
        """
        Get session metadata from global index.

        Args:
            session_id: Session identifier

        Returns:
            SessionInfo object
        """
        conn = sqlite3.connect(str(self.index_db_path))
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()
        conn.close()

        if not row:
            raise ValueError(f"Session not found: {session_id}")

        return SessionInfo(
            session_id=row['session_id'],
            folder_path=self.logs_root / row['folder_path'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            agent_id=row['agent_id'],
            init_cwd=row['init_cwd'],
            current_cwd=row['current_cwd'],
            transcript_file=row['transcript_file'],
            latest_query=row['latest_query'],
            total_cost_usd=row['total_cost_usd'],
            duration_ms=row['duration_ms'],
            input_tokens=row['input_tokens'] if 'input_tokens' in row.keys() else 0,
            output_tokens=row['output_tokens'] if 'output_tokens' in row.keys() else 0,
            notes=row['notes'],
            tags=row['tags'],
            session_name=row['session_name'] if 'session_name' in row.keys() else 'Agent'
        )

    def list_sessions(
        self,
        cwd: Optional[Path] = None,
        limit: Optional[int] = None,
        standalone_only: bool = True
    ) -> list[SessionInfo]:
        """
        List sessions from global index.

        Args:
            cwd: Filter by working directory
            limit: Maximum number of sessions to return
            standalone_only: If True, exclude sessions that are children of activities (MLE, deep_plot)

        Returns:
            List of SessionInfo objects, ordered by updated_at DESC
        """
        conn = sqlite3.connect(str(self.index_db_path))
        conn.row_factory = sqlite3.Row

        query = "SELECT * FROM sessions"
        conditions = []
        params = []

        if cwd:
            conditions.append("init_cwd = ?")
            params.append(str(cwd))

        if standalone_only:
            conditions.append("parent_activity_type IS NULL")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY updated_at DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        rows = conn.execute(query, params).fetchall()
        conn.close()

        return [
            SessionInfo(
                session_id=row['session_id'],
                folder_path=self.logs_root / row['folder_path'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                agent_id=row['agent_id'],
                init_cwd=row['init_cwd'],
                current_cwd=row['current_cwd'],
                transcript_file=row['transcript_file'],
                latest_query=row['latest_query'],
                total_cost_usd=row['total_cost_usd'],
                duration_ms=row['duration_ms'],
                input_tokens=row['input_tokens'] if 'input_tokens' in row.keys() else 0,
                output_tokens=row['output_tokens'] if 'output_tokens' in row.keys() else 0,
                notes=row['notes'],
                tags=row['tags'],
                session_name=row['session_name'] if 'session_name' in row.keys() else 'Agent'
            )
            for row in rows
        ]

    def get_conversation(self, session_id: str) -> list[dict]:
        """
        Get all conversation blocks for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of conversation block dicts with metadata, ordered by turn_number, block_index
            Each dict contains: turn_number, block_index, timestamp, role, type, and block-specific fields
        """
        session_folder = self._get_session_folder(session_id)
        session_db = session_folder / "session.db"

        conn = _connect_session_db(session_db)

        # Query conversation blocks with role column
        query = """
            SELECT turn_number, block_index, timestamp, role, block_data
            FROM conversation_blocks
            ORDER BY turn_number, block_index
        """
        rows = conn.execute(query).fetchall()
        conn.close()

        result = []
        for row in rows:
            block_dict = json.loads(row[4])
            block_dict['turn_number'] = row[0]
            block_dict['block_index'] = row[1]
            block_dict['timestamp'] = row[2]
            block_dict['role'] = row[3]
            result.append(block_dict)
        return result

    def get_plots(self, session_id: str) -> list[dict]:
        """
        Get all plots for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of plot dicts with keys: plot_id, plotly_code, description, created_at
        """
        session_folder = self._get_session_folder(session_id)
        session_db = session_folder / "session.db"

        conn = _connect_session_db(session_db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM plots ORDER BY plot_id").fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_interactions(
        self,
        session_id: str,
        plot_id: Optional[int] = None
    ) -> list[dict]:
        """
        Get interactions for a session or specific plot.

        Args:
            session_id: Session identifier
            plot_id: Optional plot_id filter

        Returns:
            List of interaction dicts, ordered by timestamp
        """
        session_folder = self._get_session_folder(session_id)
        session_db = session_folder / "session.db"

        conn = _connect_session_db(session_db)
        conn.row_factory = sqlite3.Row

        if plot_id is not None:
            rows = conn.execute(
                """
                SELECT * FROM interactions
                WHERE plot_id = ?
                ORDER BY timestamp
                """,
                (plot_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM interactions ORDER BY timestamp"
            ).fetchall()

        conn.close()

        # Parse JSON payload
        result = []
        for row in rows:
            data = dict(row)
            data['payload'] = json.loads(data['payload'])
            result.append(data)

        return result

    def search_conversation(self, session_id: str, query: str) -> list[dict]:
        """
        Full-text search on conversation content.

        Args:
            session_id: Session identifier
            query: Search query (FTS5 syntax)

        Returns:
            List of matching blocks with turn_number, text_content

        Example:
            >>> results = store.search_conversation("abc123", "GPU OR temperature")
            >>> # Returns blocks containing "GPU" or "temperature"
        """
        session_folder = self._get_session_folder(session_id)
        session_db = session_folder / "session.db"

        conn = _connect_session_db(session_db)
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT c.turn_number, c.text_content, c.block_data
            FROM conversation_fts f
            JOIN conversation_blocks c ON f.rowid = c.id
            WHERE conversation_fts MATCH ?
            ORDER BY rank
            """,
            (query,)
        ).fetchall()
        conn.close()

        return [
            {
                'turn_number': row['turn_number'],
                'text_content': row['text_content'],
                'block_data': json.loads(row['block_data'])
            }
            for row in rows
        ]

    def get_session_stats(self, session_id: str) -> dict:
        """
        Get computed statistics for a session.

        Args:
            session_id: Session identifier

        Returns:
            Dict with num_plots, num_interactions, num_conversation_blocks
        """
        session_folder = self._get_session_folder(session_id)
        session_db = session_folder / "session.db"

        conn = _connect_session_db(session_db)

        num_plots = conn.execute("SELECT COUNT(*) FROM plots").fetchone()[0]
        num_interactions = conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0]
        num_blocks = conn.execute("SELECT COUNT(*) FROM conversation_blocks").fetchone()[0]

        conn.close()

        return {
            'num_plots': num_plots,
            'num_interactions': num_interactions,
            'num_conversation_blocks': num_blocks
        }
