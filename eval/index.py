"""
SQLite index for iPlotBench dataset.

Tracks figures and job status for parallel execution with resume support.
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import Literal

logger = logging.getLogger(__name__)

Status = Literal["pending", "running", "completed", "failed"]

SCHEMA_FIGURES = """
-- Static index (built once from test folder)
CREATE TABLE IF NOT EXISTS figures (
    figure_id TEXT PRIMARY KEY,
    figure_type TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_figure_type ON figures(figure_type);
"""

SCHEMA_QUESTIONS = """
-- Questions for QA (built once from query folder)
CREATE TABLE IF NOT EXISTS questions (
    figure_id TEXT NOT NULL,
    question_idx INTEGER NOT NULL,
    question_id INTEGER,
    question_string TEXT NOT NULL,
    PRIMARY KEY (figure_id, question_idx),
    FOREIGN KEY (figure_id) REFERENCES figures(figure_id)
);
"""

SCHEMA_JOBS = """
-- Job tracking (updated during runs)
-- One job per (figure_id, config, model)
CREATE TABLE IF NOT EXISTS jobs (
    figure_id TEXT NOT NULL,
    config TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT 'haiku',
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    started_at TEXT,
    completed_at TEXT,
    PRIMARY KEY (figure_id, config, model),
    FOREIGN KEY (figure_id) REFERENCES figures(figure_id)
);
CREATE INDEX IF NOT EXISTS idx_job_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_job_model ON jobs(model);
"""


class Index:
    """SQLite index for tracking figures and job status."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrent access
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema."""
        self.conn.executescript(SCHEMA_FIGURES)
        self.conn.executescript(SCHEMA_QUESTIONS)
        self.conn.executescript(SCHEMA_JOBS)
        self.conn.commit()

    def close(self):
        """Close database connection."""
        self.conn.close()

    # --- Build index ---

    def build_from_folder(self, test_folder: Path) -> int:
        """
        Build index by scanning test folder.

        Returns number of figures indexed.
        Note: Only rebuilds figures table, preserves jobs table.
        """
        if not test_folder.exists():
            raise FileNotFoundError(f"Test folder not found: {test_folder}")

        # Clear only figures (preserve jobs for resume)
        self.conn.execute("DELETE FROM figures")

        # Scan folders
        figures = []
        for item in sorted(test_folder.iterdir()):
            if item.is_dir():
                figure_id = item.name
                # Extract figure_type: "dot_line_16000" -> "dot_line"
                parts = figure_id.rsplit("_", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    figure_type = parts[0]
                else:
                    figure_type = figure_id  # fallback
                figures.append((figure_id, figure_type))

        # Batch insert
        self.conn.executemany(
            "INSERT INTO figures (figure_id, figure_type) VALUES (?, ?)",
            figures
        )
        self.conn.commit()

        logger.info(f"Indexed {len(figures)} figures from {test_folder}")
        return len(figures)

    # --- Query figures ---

    def get_figure_types(self) -> list[str]:
        """Get list of unique figure types."""
        cursor = self.conn.execute(
            "SELECT DISTINCT figure_type FROM figures ORDER BY figure_type"
        )
        return [row[0] for row in cursor.fetchall()]

    def get_figures(
        self,
        figure_type: str | None = None,
        limit: int | None = None,
    ) -> list[str]:
        """
        Get figure_ids, optionally filtered by type and limited.

        Args:
            figure_type: Filter by figure type (e.g., "dot_line")
            limit: Max figures to return (per type if figure_type is None)
        """
        if figure_type:
            query = "SELECT figure_id FROM figures WHERE figure_type = ? ORDER BY figure_id"
            params = [figure_type]
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            cursor = self.conn.execute(query, params)
            return [row[0] for row in cursor.fetchall()]
        else:
            # Get limit per type
            if limit:
                figures = []
                for ft in self.get_figure_types():
                    figures.extend(self.get_figures(figure_type=ft, limit=limit))
                return figures
            else:
                cursor = self.conn.execute(
                    "SELECT figure_id FROM figures ORDER BY figure_type, figure_id"
                )
                return [row[0] for row in cursor.fetchall()]

    def count_figures(self) -> dict[str, int]:
        """Count figures by type."""
        cursor = self.conn.execute(
            "SELECT figure_type, COUNT(*) FROM figures GROUP BY figure_type"
        )
        return dict(cursor.fetchall())

    # --- Questions index ---

    def build_questions_from_folder(self, query_folder: Path) -> int:
        """
        Build questions index from query folder.

        Returns number of questions indexed.
        """
        import json

        if not query_folder.exists():
            logger.warning(f"Query folder not found: {query_folder}")
            return 0

        # Clear existing questions
        self.conn.execute("DELETE FROM questions")

        questions = []
        for item in sorted(query_folder.iterdir()):
            if item.is_dir():
                questions_file = item / "questions.json"
                if questions_file.exists():
                    figure_id = item.name
                    data = json.loads(questions_file.read_text())
                    for idx, q in enumerate(data):
                        questions.append((
                            figure_id,
                            idx,
                            q.get("question_id"),
                            q["question_string"],
                        ))

        # Batch insert
        self.conn.executemany(
            """INSERT INTO questions (figure_id, question_idx, question_id, question_string)
               VALUES (?, ?, ?, ?)""",
            questions
        )
        self.conn.commit()

        logger.info(f"Indexed {len(questions)} questions from {query_folder}")
        return len(questions)

    def get_questions(self, figure_id: str) -> list[tuple[int, str]]:
        """Get questions for a figure as [(question_idx, question_string), ...]."""
        cursor = self.conn.execute(
            "SELECT question_idx, question_string FROM questions WHERE figure_id = ? ORDER BY question_idx",
            (figure_id,)
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def count_questions(self) -> int:
        """Get total question count."""
        cursor = self.conn.execute("SELECT COUNT(*) FROM questions")
        return cursor.fetchone()[0]

    # --- Job management ---

    def init_jobs(self, figure_ids: list[str], configs: list[str], model: str):
        """
        Initialize jobs for given figures, configs, and model.

        Creates one job per (figure, config, model).
        Only creates jobs that don't already exist (for resume support).
        """
        for figure_id in figure_ids:
            for config in configs:
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO jobs (figure_id, config, model, status)
                    VALUES (?, ?, ?, 'pending')
                    """,
                    (figure_id, config, model)
                )
        self.conn.commit()

    def get_pending_jobs(self, model: str) -> list[tuple[str, str]]:
        """
        Get pending jobs for a specific model.

        Returns: [(figure_id, config), ...]
        """
        cursor = self.conn.execute(
            "SELECT figure_id, config FROM jobs WHERE status = 'pending' AND model = ?",
            (model,)
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def set_job_running(self, figure_id: str, config: str, model: str):
        """Mark job as running."""
        self.conn.execute(
            """
            UPDATE jobs SET status = 'running', started_at = ?
            WHERE figure_id = ? AND config = ? AND model = ?
            """,
            (datetime.now().isoformat(), figure_id, config, model)
        )
        self.conn.commit()

    def set_job_completed(self, figure_id: str, config: str, model: str):
        """Mark job as completed."""
        self.conn.execute(
            """
            UPDATE jobs SET status = 'completed', completed_at = ?
            WHERE figure_id = ? AND config = ? AND model = ?
            """,
            (datetime.now().isoformat(), figure_id, config, model)
        )
        self.conn.commit()

    def set_job_failed(self, figure_id: str, config: str, model: str, error: str):
        """Mark job as failed with error message."""
        self.conn.execute(
            """
            UPDATE jobs SET status = 'failed', error = ?, completed_at = ?
            WHERE figure_id = ? AND config = ? AND model = ?
            """,
            (error, datetime.now().isoformat(), figure_id, config, model)
        )
        self.conn.commit()

    def get_job_stats(self, model: str | None = None) -> dict[str, int]:
        """Get job counts by status, optionally filtered by model."""
        if model:
            cursor = self.conn.execute(
                "SELECT status, COUNT(*) FROM jobs WHERE model = ? GROUP BY status",
                (model,)
            )
        else:
            cursor = self.conn.execute(
                "SELECT status, COUNT(*) FROM jobs GROUP BY status"
            )
        return dict(cursor.fetchall())

    def get_job_stats_by_model(self) -> dict[str, dict[str, int]]:
        """Get job counts grouped by model and status."""
        cursor = self.conn.execute(
            "SELECT model, status, COUNT(*) FROM jobs GROUP BY model, status"
        )
        result = {}
        for row in cursor.fetchall():
            model, status, count = row
            if model not in result:
                result[model] = {}
            result[model][status] = count
        return result

    def reset_running_jobs(self, model: str):
        """Reset running jobs to pending for a specific model (for crash recovery)."""
        self.conn.execute(
            "UPDATE jobs SET status = 'pending', started_at = NULL WHERE status = 'running' AND model = ?",
            (model,)
        )
        self.conn.commit()

    def reset_failed_jobs(self, model: str) -> int:
        """Reset failed jobs to pending for retry. Returns count of reset jobs."""
        cursor = self.conn.execute(
            "UPDATE jobs SET status = 'pending', error = NULL, started_at = NULL, completed_at = NULL "
            "WHERE status = 'failed' AND model = ?",
            (model,)
        )
        self.conn.commit()
        return cursor.rowcount


def get_default_db_path() -> Path:
    """Get default index.db path.

    Always uses /agent/eval/index.db (in Docker) or eval/index.db (local).
    This ensures a single source of truth.
    """
    return Path(__file__).parent / "index.db"


def build_index(
    test_folder: Path,
    query_folder: Path | None = None,
    db_path: Path | None = None,
) -> Index:
    """
    Build index from test folder (and optionally query folder).

    Args:
        test_folder: Path to test folder containing figure directories
        query_folder: Path to query folder containing questions (optional)
        db_path: Path to index.db (default: eval/index.db)
    """
    if db_path is None:
        db_path = get_default_db_path()

    index = Index(db_path)
    count = index.build_from_folder(test_folder)

    # Print summary
    stats = index.count_figures()
    logger.info("Figure types:")
    for ft, cnt in sorted(stats.items()):
        logger.info(f"  {ft}: {cnt}")

    # Build questions index if query folder provided
    if query_folder:
        q_count = index.build_questions_from_folder(query_folder)
        logger.info(f"Questions: {q_count}")

    return index


def open_index(db_path: Path | None = None) -> Index:
    """
    Open existing index.

    Args:
        db_path: Path to index.db (default: eval/index.db)
    """
    if db_path is None:
        db_path = get_default_db_path()

    if not db_path.exists():
        raise FileNotFoundError(
            f"Index not found: {db_path}\n"
            "Run with --build-index first."
        )
    return Index(db_path)
