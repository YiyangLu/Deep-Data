"""
Session Storage System

Implements the session-per-folder architecture for storing agent exploration sessions.
Each session is isolated in its own folder with:
- session.db (conversation, plots, interactions)
- transcript.txt (human-readable conversation)
- screenshots/ (per-plot interaction screenshots)

Design: docs/SESSION_STORAGE_DESIGN.md
Schema: src/core/schema/session_data.sql, session_index.sql
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from .queries import SessionQueriesMixin, _connect_session_db
from .export import SessionExportMixin
from ...utils.paths import get_logs_root
from ...utils.logging import create_logger

logger = create_logger(__name__)


class SessionStore(SessionQueriesMixin, SessionExportMixin):
    """
    Session storage manager following session-per-folder architecture.

    Each session is self-contained in its own folder for:
    - Easy export (zip folder)
    - Parallel processing (no lock contention)
    - Fast operations (smaller databases)

    Directory structure:
        logs/
          session_index.db
          sessions/
            {safe_cwd_name}/        # e.g., -path-to-sessionCWD
              {session_id}/
                session.db
                transcript.txt
                screenshots/
                  plot_1/
                    relayout_001.png
    """

    def __init__(self, logs_root: Path = None):
        """
        Initialize SessionStore.

        Args:
            logs_root: Root directory for logs (default: ./logs)
        """
        self.logs_root = logs_root or get_logs_root()
        self.sessions_dir = self.logs_root / "sessions"
        self.index_db_path = self.logs_root / "session_index.db"

        # Ensure directory structure exists
        self.logs_root.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(exist_ok=True)

        # Initialize global index
        self._init_index_db()

    def _init_index_db(self):
        """Initialize global session index database."""
        conn = sqlite3.connect(str(self.index_db_path))

        # Step 1: Create base sessions table (minimal columns)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                folder_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                init_cwd TEXT NOT NULL,
                current_cwd TEXT NOT NULL,
                transcript_file TEXT NOT NULL DEFAULT 'transcript.txt',
                latest_query TEXT,
                total_cost_usd REAL DEFAULT 0.0,
                duration_ms INTEGER DEFAULT 0,
                notes TEXT,
                tags TEXT
            )
        """)
        conn.commit()

        # Step 2: Run migrations to add columns (order matters)
        # Migration: Add session_name column
        try:
            cursor = conn.execute("SELECT session_name FROM sessions LIMIT 1")
            cursor.close()
        except sqlite3.OperationalError:
            try:
                conn.execute("ALTER TABLE sessions ADD COLUMN session_name TEXT DEFAULT 'Agent'")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already added by another worker

        # Migration: Add input_tokens and output_tokens columns
        try:
            cursor = conn.execute("SELECT input_tokens FROM sessions LIMIT 1")
            cursor.close()
        except sqlite3.OperationalError:
            try:
                conn.execute("ALTER TABLE sessions ADD COLUMN input_tokens INTEGER DEFAULT 0")
                conn.execute("ALTER TABLE sessions ADD COLUMN output_tokens INTEGER DEFAULT 0")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already added by another worker

        # Migration: Add parent_activity columns
        try:
            cursor = conn.execute("SELECT parent_activity_type FROM sessions LIMIT 1")
            cursor.close()
        except sqlite3.OperationalError:
            try:
                conn.execute("ALTER TABLE sessions ADD COLUMN parent_activity_type TEXT")
                conn.execute("ALTER TABLE sessions ADD COLUMN parent_activity_id TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already added by another worker

        # Step 3: Create activities table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT,
                cwd TEXT,
                status TEXT DEFAULT 'running',
                config TEXT,
                result TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()

        # Step 3b: Add cwd column to activities if missing (migration)
        cursor = conn.execute("PRAGMA table_info(activities)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'cwd' not in columns:
            try:
                conn.execute("ALTER TABLE activities ADD COLUMN cwd TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already added

        # Step 4: Create indexes (after all columns exist)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_init_cwd ON sessions(init_cwd)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_current_cwd ON sessions(current_cwd)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_activity ON sessions(parent_activity_type, parent_activity_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_updated ON activities(updated_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_type ON activities(type)")
        conn.commit()

        conn.close()

    def _init_session_db(self, session_folder: Path):
        """Initialize per-session database.

        Args:
            session_folder: Path to session folder
        """
        schema_path = Path(__file__).parent.parent / "schema" / "session_data.sql"

        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with open(schema_path) as f:
            schema_sql = f.read()

        session_db_path = session_folder / "session.db"
        conn = _connect_session_db(session_db_path)
        conn.executescript(schema_sql)
        conn.commit()

        # Run migrations
        self._migrate_session_db(conn)

        conn.close()

    def _migrate_session_db(self, conn: sqlite3.Connection):
        """
        Run migrations on session database.

        Args:
            conn: Database connection
        """
        # Migration: Add view_state column if it doesn't exist
        try:
            conn.execute("SELECT view_state FROM interactions LIMIT 1")
        except sqlite3.OperationalError:
            # Column doesn't exist, add it
            conn.execute("ALTER TABLE interactions ADD COLUMN view_state TEXT")
            conn.commit()

        # Migration: Add interaction_id column if it doesn't exist
        # (per-plot sequence: 1, 2, 3... for each plot)
        try:
            conn.execute("SELECT interaction_id FROM interactions LIMIT 1")
        except sqlite3.OperationalError:
            # Column doesn't exist, add it and populate with sequential numbers per plot
            conn.execute("ALTER TABLE interactions ADD COLUMN interaction_id INTEGER")
            # Populate existing rows with sequential numbers per plot
            conn.execute("""
                UPDATE interactions
                SET interaction_id = (
                    SELECT COUNT(*)
                    FROM interactions i2
                    WHERE i2.plot_id = interactions.plot_id
                    AND i2.id <= interactions.id
                )
            """)
            conn.commit()

    def _ensure_session_db_migrated(self, session_folder: Path):
        """
        Ensure session database has latest schema.

        Called before accessing session database.

        Args:
            session_folder: Path to session folder
        """
        session_db_path = session_folder / "session.db"
        if session_db_path.exists():
            conn = _connect_session_db(session_db_path)
            self._migrate_session_db(conn)
            conn.close()

    @staticmethod
    def _utc_now() -> str:
        """Get current UTC timestamp in ISO 8601 format."""
        return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    @staticmethod
    def _cwd_to_safe_name(cwd: Path) -> str:
        """
        Convert absolute path to safe directory name.

        Escapes '-' as '--' before converting '/' to '-'.
        This ensures no collisions between paths like:
        - /path/to-project/foo
        - /path/to/project-foo

        Args:
            cwd: Absolute path

        Returns:
            Safe directory name with '-' escaped and '/' replaced by '-'

        Example:
            >>> SessionStore._cwd_to_safe_name(Path("/path/to/project"))
            '-path-to-project'
            >>> SessionStore._cwd_to_safe_name(Path("/path/to-project"))
            '-path-to--project'
        """
        path_str = str(cwd.absolute())
        # First escape existing dashes: - → --
        escaped = path_str.replace('-', '--')
        # Then convert slashes: / → -
        return escaped.replace('/', '-')

    def create_session(
        self,
        session_id: str,
        cwd: Path,
        agent_id: str,
        notes: Optional[str] = None,
        tags: Optional[str] = None,
        session_name: Optional[str] = None,
        parent_activity_type: Optional[str] = None,
        parent_activity_id: Optional[str] = None,
    ) -> Path:
        """
        Create new session folder and databases.

        Args:
            session_id: SDK session ID
            cwd: Working directory path
            agent_id: Agent identifier
            notes: Optional user notes
            tags: Optional comma-separated tags
            session_name: Display name for the session (default: 'Agent')
            parent_activity_type: Type of parent activity ('mle', 'deep_plot', or None)
            parent_activity_id: ID of parent activity (run_id, analysis_id, or None)

        Returns:
            Path to session folder

        Example:
            >>> store = SessionStore()
            >>> folder = store.create_session(
            ...     session_id="sdk_abc123",
            ...     cwd=Path("/path/to/project"),
            ...     agent_id="agent_1",
            ...     tags="gpu,thermal"
            ... )
            >>> # Creates: logs/sessions/-path-to-project/sdk_abc123/
        """
        # Create hierarchical folder structure
        safe_cwd = self._cwd_to_safe_name(cwd)
        cwd_dir = self.sessions_dir / safe_cwd
        cwd_dir.mkdir(parents=True, exist_ok=True)

        session_folder = cwd_dir / session_id

        # Create folder structure
        session_folder.mkdir(parents=True, exist_ok=True)
        (session_folder / "screenshots").mkdir(exist_ok=True)

        # Initialize session database
        self._init_session_db(session_folder)

        # Create empty transcript file
        transcript_path = session_folder / "transcript.txt"
        transcript_path.touch()

        # Use provided name or default
        display_name = session_name or 'Agent'

        # Add to global index
        now = self._utc_now()
        cwd_str = str(cwd)
        conn = sqlite3.connect(str(self.index_db_path))
        conn.execute(
            """
            INSERT INTO sessions
            (session_id, folder_path, created_at, updated_at, agent_id, init_cwd, current_cwd,
             transcript_file, notes, tags, session_name,
             parent_activity_type, parent_activity_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                str(session_folder.relative_to(self.logs_root)),
                now,
                now,
                agent_id,
                cwd_str,
                cwd_str,  # current_cwd starts same as init_cwd
                "transcript.txt",
                notes,
                tags,
                display_name,
                parent_activity_type,
                parent_activity_id
            )
        )
        conn.commit()
        conn.close()

        return session_folder

    # ========== Activity Management ==========

    def create_activity(
        self,
        activity_id: str,
        activity_type: str,
        name: Optional[str] = None,
        cwd: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> None:
        """
        Create a new activity record.

        Args:
            activity_id: Unique activity identifier
            activity_type: Type of activity ('agent', 'deep_plot', 'mle')
            name: User-friendly name
            cwd: Working directory for the activity
            config: Activity-specific configuration (stored as JSON)
        """
        now = self._utc_now()
        conn = sqlite3.connect(str(self.index_db_path))
        conn.execute(
            """
            INSERT INTO activities (id, type, name, cwd, status, config, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'running', ?, ?, ?)
            """,
            (activity_id, activity_type, name, cwd, json.dumps(config) if config else None, now, now)
        )
        conn.commit()
        conn.close()

    def get_activity(self, activity_id: str) -> Optional[dict]:
        """Get activity by ID."""
        conn = sqlite3.connect(str(self.index_db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM activities WHERE id = ?",
            (activity_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            result = dict(row)
            if result.get('config'):
                result['config'] = json.loads(result['config'])
            if result.get('result'):
                result['result'] = json.loads(result['result'])
            return result
        return None

    def update_activity(
        self,
        activity_id: str,
        status: Optional[str] = None,
        name: Optional[str] = None,
        result: Optional[dict] = None,
    ) -> None:
        """
        Update activity status/result.

        Args:
            activity_id: Activity identifier
            status: New status ('running', 'paused', 'completed', 'failed')
            name: Updated name
            result: Activity-specific results (stored as JSON)
        """
        updates = []
        params = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if result is not None:
            updates.append("result = ?")
            params.append(json.dumps(result))

        if not updates:
            return

        updates.append("updated_at = ?")
        params.append(self._utc_now())
        params.append(activity_id)

        conn = sqlite3.connect(str(self.index_db_path))
        conn.execute(
            f"UPDATE activities SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()
        conn.close()

    def list_activities(
        self,
        activity_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        List activities with optional filtering.

        Args:
            activity_type: Filter by type ('agent', 'deep_plot', 'mle')
            status: Filter by status
            limit: Maximum number of results

        Returns:
            List of activity records, most recent first
        """
        conditions = []
        params = []

        if activity_type:
            conditions.append("type = ?")
            params.append(activity_type)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        conn = sqlite3.connect(str(self.index_db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            f"SELECT * FROM activities {where_clause} ORDER BY updated_at DESC LIMIT ?",
            params + [limit]
        )
        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            item = dict(row)
            if item.get('config'):
                item['config'] = json.loads(item['config'])
            if item.get('result'):
                item['result'] = json.loads(item['result'])
            results.append(item)

        return results

    def get_active_activity(self, activity_type: str) -> Optional[dict]:
        """Get the most recent running or paused activity of a given type."""
        # Check for running first, then paused
        activities = self.list_activities(activity_type=activity_type, status='running', limit=1)
        if activities:
            return activities[0]
        activities = self.list_activities(activity_type=activity_type, status='paused', limit=1)
        return activities[0] if activities else None

    def delete_activity(self, activity_id: str) -> None:
        """Delete an activity record."""
        conn = sqlite3.connect(str(self.index_db_path))
        conn.execute("DELETE FROM activities WHERE id = ?", (activity_id,))
        conn.commit()
        conn.close()

    def log_conversation_block(
        self,
        session_id: str,
        turn_number: int,
        block_index: int,
        block_data: dict,
        role: str  # 'user' or 'assistant'
    ):
        """
        Log conversation block (text, tool_use, or tool_result).

        Args:
            session_id: Session identifier
            turn_number: Conversation turn number (1, 2, 3, ...)
            block_index: Order within turn (0, 1, 2, ...)
            block_data: Full JSON block from Claude SDK
            role: Message role ('user' or 'assistant')

        Example:
            >>> store.log_conversation_block(
            ...     "abc123",
            ...     turn_number=1,
            ...     block_index=0,
            ...     block_data={"type": "text", "text": "Hello"},
            ...     role="assistant"
            ... )
        """
        session_folder = self._get_session_folder(session_id)
        session_db = session_folder / "session.db"

        conn = _connect_session_db(session_db)
        conn.execute(
            """
            INSERT INTO conversation_blocks
            (turn_number, block_index, timestamp, role, block_data)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                turn_number,
                block_index,
                self._utc_now(),
                role,
                json.dumps(block_data)
            )
        )
        conn.commit()
        conn.close()

        # Update index timestamp
        self._update_session_timestamp(session_id)

    def log_plot(
        self,
        session_id: str,
        plot_id: int,
        plotly_code: str,
        fig_json: str,
        description: Optional[str] = None
    ):
        """
        Log or update plot data.

        Saves fig_json to separate file for fast recovery.
        Keeps metadata in SQLite for queries.
        If plot_id already exists, overwrites both file and database record.

        Args:
            session_id: Session identifier
            plot_id: Plot identifier (can be new or existing for update)
            plotly_code: Python code that created the plot
            fig_json: Serialized Plotly figure (from fig.to_json())
            description: Optional plot description

        Example:
            >>> # Create new plot
            >>> store.log_plot(
            ...     "abc123",
            ...     plot_id=1,
            ...     plotly_code="import plotly.graph_objects as go\\n...",
            ...     fig_json='{"data": [...], "layout": {...}}',
            ...     description="GPU power consumption over time"
            ... )
            >>> # Update existing plot (same ID overwrites)
            >>> store.log_plot(
            ...     "abc123",
            ...     plot_id=1,
            ...     plotly_code="import plotly.express as px\\n...",
            ...     fig_json='{"data": [...], "layout": {...}}'
            ... )
        """
        session_folder = self._get_session_folder(session_id)
        session_db = session_folder / "session.db"

        # Save fig_json to separate file for fast recovery
        plots_folder = session_folder / "plots"
        plots_folder.mkdir(exist_ok=True)
        plot_file = plots_folder / f"{plot_id}.json"
        with open(plot_file, 'w') as f:
            f.write(fig_json)

        # Keep metadata in SQLite (fig_json stored in file)
        conn = _connect_session_db(session_db)

        # Check if this is an update (plot already exists)
        cursor = conn.execute(
            "SELECT 1 FROM plots WHERE plot_id = ?",
            (plot_id,)
        )
        is_update = cursor.fetchone() is not None

        # If updating, delete old interactions (they refer to old plot data)
        if is_update:
            conn.execute(
                "DELETE FROM interactions WHERE plot_id = ?",
                (plot_id,)
            )
            # Also clean up screenshot files for this plot
            screenshots_dir = session_folder / "screenshots" / str(plot_id)
            if screenshots_dir.exists():
                import shutil
                shutil.rmtree(screenshots_dir)

        conn.execute(
            """
            INSERT OR REPLACE INTO plots
            (plot_id, plotly_code, description)
            VALUES (?, ?, ?)
            """,
            (plot_id, plotly_code, description)
        )
        conn.commit()
        conn.close()

        # Update index timestamp
        self._update_session_timestamp(session_id)

    def get_plot_json(self, session_id: str, plot_id: int) -> Optional[str]:
        """
        Get plot JSON from file for recovery.

        Args:
            session_id: Session identifier
            plot_id: Plot identifier

        Returns:
            Plot JSON string or None if not found
        """
        session_folder = self._get_session_folder(session_id)
        plot_file = session_folder / "plots" / f"{plot_id}.json"

        if plot_file.exists():
            with open(plot_file, 'r') as f:
                return f.read()
        return None

    def log_interaction(
        self,
        session_id: str,
        plot_id: int,
        event_type: str,
        payload: dict,
        screenshot_path: Optional[str] = None,
        screenshot_size_kb: Optional[int] = None
    ) -> int:
        """
        Log user interaction with plot.

        Also computes and stores view state for state restoration.

        Args:
            session_id: Session identifier
            plot_id: Plot identifier
            event_type: Event type (relayout, click, hover, selected, etc.)
            payload: Event data as dict
            screenshot_path: Relative path to screenshot (e.g., "screenshots/1/3.png")
            screenshot_size_kb: Screenshot file size in KB

        Returns:
            interaction_id: Per-plot sequence number (1, 2, 3...)

        Example:
            >>> interaction_id = store.log_interaction(
            ...     "abc123",
            ...     plot_id=1,
            ...     event_type="relayout",
            ...     payload={"xaxis.range": ["2020-08-15", "2020-08-20"]},
            ... )
            >>> # Returns: 2 (second interaction for this plot)
        """
        session_folder = self._get_session_folder(session_id)
        session_db = session_folder / "session.db"

        # Ensure database has latest schema (migrations)
        self._ensure_session_db_migrated(session_folder)

        conn = _connect_session_db(session_db)

        # Get next interaction_id for this plot (per-plot sequence)
        cursor = conn.execute(
            "SELECT COALESCE(MAX(interaction_id), 0) + 1 FROM interactions WHERE plot_id = ?",
            (plot_id,)
        )
        interaction_id = cursor.fetchone()[0]

        # Get previous view state for this plot
        prev_state = self._get_last_view_state(conn, plot_id)

        # Compute new view state
        view_state = self._compute_view_state(prev_state, event_type, payload)

        conn.execute(
            """
            INSERT INTO interactions
            (plot_id, interaction_id, timestamp, event_type, payload, screenshot_path, screenshot_size_kb, view_state)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plot_id,
                interaction_id,
                self._utc_now(),
                event_type,
                json.dumps(payload),
                screenshot_path,
                screenshot_size_kb,
                json.dumps(view_state) if view_state else None
            )
        )
        conn.commit()
        conn.close()

        # Update index timestamp
        self._update_session_timestamp(session_id)

        return interaction_id

    def _get_last_view_state(self, conn: sqlite3.Connection, plot_id: int) -> Optional[dict]:
        """
        Get the last view state for a plot (for state restoration).

        Excludes init events since they reset state. This returns the state
        just before the session was closed, not the state after a reload.

        Args:
            conn: Database connection
            plot_id: Plot identifier

        Returns:
            Last view state dict or None
        """
        row = conn.execute(
            """
            SELECT view_state FROM interactions
            WHERE plot_id = ? AND view_state IS NOT NULL
              AND event_type != 'init'
            ORDER BY id DESC LIMIT 1
            """,
            (plot_id,)
        ).fetchone()

        if row and row[0]:
            return json.loads(row[0])
        return None

    def _compute_view_state(
        self,
        prev_state: Optional[dict],
        event_type: str,
        payload: dict
    ) -> Optional[dict]:
        """
        Compute new view state based on previous state and current event.

        View state represents the current visual state of the plot (what you see).
        Autorange and explicit range values are mutually exclusive.

        Args:
            prev_state: Previous view state (or None for first event)
            event_type: Current event type
            payload: Current event payload

        Returns:
            New view state dict
        """
        # Start with previous state or empty state
        state = prev_state.copy() if prev_state else {}

        # Initialize trace_visibility if not present
        if 'trace_visibility' not in state:
            state['trace_visibility'] = {}

        # Update state based on event type
        if event_type == 'init':
            # Reset to initial state
            state = {'trace_visibility': {}}

        elif event_type == 'relayout':
            # Image state semantics: autorange and explicit range are mutually exclusive
            # When autorange is set, remove range values (and vice versa)

            # X-axis: autorange vs explicit range
            if payload.get('xaxis.autorange') is True:
                # Autorange enabled - remove explicit range values
                for key in ['xaxis.range[0]', 'xaxis.range[1]', 'xaxis.range']:
                    state.pop(key, None)
                state['xaxis.autorange'] = True
            elif any(key in payload for key in ['xaxis.range[0]', 'xaxis.range[1]', 'xaxis.range']):
                # Explicit range set - remove autorange
                state.pop('xaxis.autorange', None)
                for key in ['xaxis.range[0]', 'xaxis.range[1]', 'xaxis.range']:
                    if key in payload:
                        state[key] = payload[key]

            # Y-axis: autorange vs explicit range
            if payload.get('yaxis.autorange') is True:
                # Autorange enabled - remove explicit range values
                for key in ['yaxis.range[0]', 'yaxis.range[1]', 'yaxis.range']:
                    state.pop(key, None)
                state['yaxis.autorange'] = True
            elif any(key in payload for key in ['yaxis.range[0]', 'yaxis.range[1]', 'yaxis.range']):
                # Explicit range set - remove autorange
                state.pop('yaxis.autorange', None)
                for key in ['yaxis.range[0]', 'yaxis.range[1]', 'yaxis.range']:
                    if key in payload:
                        state[key] = payload[key]

        elif event_type == 'legendclick':
            # Update trace visibility
            curve_number = payload.get('curve_number')
            visible = payload.get('visible')
            if curve_number is not None:
                state['trace_visibility'][str(curve_number)] = visible

        elif event_type == 'selected':
            # Store selection range if present
            if 'x_range' in payload:
                state['selection_x_range'] = payload['x_range']
            if 'y_range' in payload:
                state['selection_y_range'] = payload['y_range']
            if 'point_indices' in payload:
                state['selected_points'] = payload['point_indices']

        elif event_type == 'doubleclick':
            # Reset to autoscale (remove range constraints)
            for key in ['xaxis.range[0]', 'xaxis.range[1]', 'yaxis.range[0]', 'yaxis.range[1]',
                        'xaxis.range', 'yaxis.range']:
                state.pop(key, None)
            state['xaxis.autorange'] = True
            state['yaxis.autorange'] = True

        return state if state else None

    def get_plot_view_state(self, session_id: str, plot_id: int) -> Optional[dict]:
        """
        Get the latest view state for a plot.

        Used for restoring plot state on resume.

        Args:
            session_id: Session identifier
            plot_id: Plot identifier

        Returns:
            View state dict or None
        """
        session_folder = self._get_session_folder(session_id)
        session_db = session_folder / "session.db"

        # Ensure database has latest schema (migrations)
        self._ensure_session_db_migrated(session_folder)

        conn = _connect_session_db(session_db)
        state = self._get_last_view_state(conn, plot_id)
        conn.close()

        return state

    def update_interaction_screenshot(
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
        session_folder = self._get_session_folder(session_id)
        session_db = session_folder / "session.db"

        conn = _connect_session_db(session_db)
        conn.execute(
            """
            UPDATE interactions
            SET screenshot_path = ?, screenshot_size_kb = ?
            WHERE plot_id = ? AND interaction_id = ?
            """,
            (screenshot_path, screenshot_size_kb, plot_id, interaction_id)
        )
        conn.commit()
        conn.close()

    def update_transcript(self, session_id: str, text: str):
        """
        Append to transcript file.

        Args:
            session_id: Session identifier
            text: Text to append
        """
        session_folder = self._get_session_folder(session_id)
        transcript_path = session_folder / "transcript.txt"

        with open(transcript_path, 'a') as f:
            f.write(text)
            if not text.endswith('\n'):
                f.write('\n')

        # Update index timestamp
        self._update_session_timestamp(session_id)

    def update_current_cwd(self, session_id: str, current_cwd: str) -> bool:
        """
        Update current_cwd for a session.

        Args:
            session_id: Session identifier
            current_cwd: New current working directory

        Returns:
            True if cwd changed, False if same as before
        """
        conn = sqlite3.connect(str(self.index_db_path))

        # Check if cwd actually changed
        row = conn.execute(
            "SELECT current_cwd FROM sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()

        if not row:
            conn.close()
            return False

        if row[0] == current_cwd:
            conn.close()
            return False

        # Update current_cwd
        conn.execute(
            "UPDATE sessions SET current_cwd = ?, updated_at = ? WHERE session_id = ?",
            (current_cwd, self._utc_now(), session_id)
        )
        conn.commit()
        conn.close()
        return True

    def update_session_metadata(
        self,
        session_id: str,
        latest_query: Optional[str] = None,
        total_cost_usd: Optional[float] = None,
        duration_ms: Optional[int] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        notes: Optional[str] = None,
        tags: Optional[str] = None,
        session_name: Optional[str] = None
    ):
        """
        Update session metadata in global index.

        Args:
            session_id: Session identifier
            latest_query: Latest user query
            total_cost_usd: Total cost in USD
            duration_ms: Total duration in milliseconds
            input_tokens: Total input tokens used
            output_tokens: Total output tokens used
            notes: User notes
            tags: Comma-separated tags
            session_name: User-friendly session name
        """
        updates = []
        values = []

        if latest_query is not None:
            updates.append("latest_query = ?")
            values.append(latest_query)

        if total_cost_usd is not None:
            updates.append("total_cost_usd = ?")
            values.append(total_cost_usd)

        if duration_ms is not None:
            updates.append("duration_ms = ?")
            values.append(duration_ms)

        if input_tokens is not None:
            updates.append("input_tokens = ?")
            values.append(input_tokens)

        if output_tokens is not None:
            updates.append("output_tokens = ?")
            values.append(output_tokens)

        if notes is not None:
            updates.append("notes = ?")
            values.append(notes)

        if tags is not None:
            updates.append("tags = ?")
            values.append(tags)

        if session_name is not None:
            updates.append("session_name = ?")
            values.append(session_name)

        if not updates:
            return

        # Always update timestamp
        updates.append("updated_at = ?")
        values.append(self._utc_now())
        values.append(session_id)

        conn = sqlite3.connect(str(self.index_db_path))
        conn.execute(
            f"UPDATE sessions SET {', '.join(updates)} WHERE session_id = ?",
            values
        )
        conn.commit()
        conn.close()

    def _get_session_folder(self, session_id: str) -> Path:
        """Get session folder path from index."""
        conn = sqlite3.connect(str(self.index_db_path))
        row = conn.execute(
            "SELECT folder_path FROM sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()
        conn.close()

        if not row:
            raise ValueError(f"Session not found: {session_id}")

        return self.logs_root / row[0]

    def _update_session_timestamp(self, session_id: str):
        """Update session's updated_at timestamp."""
        conn = sqlite3.connect(str(self.index_db_path))
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
            (self._utc_now(), session_id)
        )
        conn.commit()
        conn.close()

    def finalize_plots(
        self,
        session_id: str,
        evidence_plots: list[int]
    ) -> dict[int, int]:
        """
        Finalize plots for a session by keeping only evidence plots and renumbering them.

        This method:
        1. Deletes all plots NOT in evidence_plots list
        2. Renumbers remaining plots to sequential IDs (1, 2, 3, ...)
        3. Updates all references (interactions table, screenshot folders, plot JSON files)

        Args:
            session_id: Session identifier
            evidence_plots: List of plot IDs to keep (in desired order)

        Returns:
            Mapping of old_plot_id -> new_plot_id

        Example:
            >>> # Agent created plots 1, 2, 3, 4, 5 but only 2 and 4 are evidence
            >>> mapping = store.finalize_plots("abc123", [2, 4])
            >>> # Returns: {2: 1, 4: 2}
            >>> # Plot 2 becomes Plot 1, Plot 4 becomes Plot 2
            >>> # Plots 1, 3, 5 are deleted
        """
        import shutil

        session_folder = self._get_session_folder(session_id)
        session_db = session_folder / "session.db"
        plots_folder = session_folder / "plots"
        screenshots_folder = session_folder / "screenshots"

        conn = _connect_session_db(session_db)

        # Get all existing plot IDs
        existing_plots = [
            row[0] for row in
            conn.execute("SELECT plot_id FROM plots ORDER BY plot_id").fetchall()
        ]

        # Remove duplicates while preserving order, and filter to only existing plots
        seen = set()
        valid_evidence_plots = []
        for plot_id in evidence_plots:
            if plot_id not in seen and plot_id in existing_plots:
                seen.add(plot_id)
                valid_evidence_plots.append(plot_id)
            elif plot_id not in existing_plots:
                logger.warning(f"Plot {plot_id} not found in session, skipping")
        evidence_plots = valid_evidence_plots

        if not evidence_plots:
            conn.close()
            logger.warning("No valid evidence plots to finalize")
            return {}

        # Determine plots to delete (not in evidence_plots)
        plots_to_delete = [pid for pid in existing_plots if pid not in evidence_plots]

        # Delete non-evidence plots (manually delete interactions since FK may be disabled)
        for plot_id in plots_to_delete:
            # Delete interactions first
            conn.execute("DELETE FROM interactions WHERE plot_id = ?", (plot_id,))
            # Delete from plots table
            conn.execute("DELETE FROM plots WHERE plot_id = ?", (plot_id,))

            # Delete plot JSON file
            plot_file = plots_folder / f"{plot_id}.json"
            if plot_file.exists():
                plot_file.unlink()

            # Delete screenshot folder
            screenshot_dir = screenshots_folder / str(plot_id)
            if screenshot_dir.exists():
                shutil.rmtree(screenshot_dir)

        conn.commit()

        # Create mapping: old_id -> new_id (1-indexed based on order in evidence_plots)
        id_mapping = {old_id: new_id for new_id, old_id in enumerate(evidence_plots, start=1)}

        # Renumber plots using temp IDs to avoid conflicts
        # Disable foreign keys during renumbering to allow updates
        conn.execute("PRAGMA foreign_keys = OFF")

        # Step 1: Rename all to temp IDs (old_id + 10000)
        max_id = max(existing_plots) if existing_plots else 0
        temp_base = max_id + 10000

        for old_id in evidence_plots:
            new_id = id_mapping[old_id]
            if old_id == new_id:
                continue  # No change needed

            temp_id = temp_base + old_id

            # Rename plot file: old_id.json -> temp_id.json
            old_plot_file = plots_folder / f"{old_id}.json"
            temp_plot_file = plots_folder / f"{temp_id}.json"
            if old_plot_file.exists():
                old_plot_file.rename(temp_plot_file)

            # Rename screenshot folder
            old_screenshot_dir = screenshots_folder / str(old_id)
            temp_screenshot_dir = screenshots_folder / str(temp_id)
            if old_screenshot_dir.exists():
                old_screenshot_dir.rename(temp_screenshot_dir)

            # Update database with temp ID
            conn.execute(
                "UPDATE plots SET plot_id = ? WHERE plot_id = ?",
                (temp_id, old_id)
            )
            conn.execute(
                "UPDATE interactions SET plot_id = ? WHERE plot_id = ?",
                (temp_id, old_id)
            )
            # Update screenshot_path in interactions
            conn.execute(
                """
                UPDATE interactions
                SET screenshot_path = REPLACE(screenshot_path, ?, ?)
                WHERE plot_id = ?
                """,
                (f"screenshots/{old_id}/", f"screenshots/{temp_id}/", temp_id)
            )

        conn.commit()

        # Step 2: Rename from temp IDs to final IDs
        for old_id, new_id in id_mapping.items():
            if old_id == new_id:
                continue

            temp_id = temp_base + old_id

            # Rename plot file: temp_id.json -> new_id.json
            temp_plot_file = plots_folder / f"{temp_id}.json"
            new_plot_file = plots_folder / f"{new_id}.json"
            if temp_plot_file.exists():
                temp_plot_file.rename(new_plot_file)

            # Rename screenshot folder
            temp_screenshot_dir = screenshots_folder / str(temp_id)
            new_screenshot_dir = screenshots_folder / str(new_id)
            if temp_screenshot_dir.exists():
                temp_screenshot_dir.rename(new_screenshot_dir)

            # Update database with final ID
            conn.execute(
                "UPDATE plots SET plot_id = ? WHERE plot_id = ?",
                (new_id, temp_id)
            )
            conn.execute(
                "UPDATE interactions SET plot_id = ? WHERE plot_id = ?",
                (new_id, temp_id)
            )
            # Update screenshot_path in interactions
            conn.execute(
                """
                UPDATE interactions
                SET screenshot_path = REPLACE(screenshot_path, ?, ?)
                WHERE plot_id = ?
                """,
                (f"screenshots/{temp_id}/", f"screenshots/{new_id}/", new_id)
            )

        # Re-enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")

        conn.commit()
        conn.close()

        # Update index timestamp
        self._update_session_timestamp(session_id)

        logger.info(
            f"Finalized plots for session {session_id}: "
            f"kept {len(evidence_plots)}, deleted {len(plots_to_delete)}, "
            f"mapping: {id_mapping}"
        )

        return id_mapping
