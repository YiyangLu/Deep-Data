"""MCTS Journal - SQLite persistence layer.

Persists nodes for crash recovery and logging.
Tree structure is maintained in-memory on nodes.
"""

import sqlite3
from pathlib import Path
from typing import Optional

from .node import MCTSNode, MetricValue, WorstMetricValue


class Journal:
    """Persistence layer for MCTS nodes.

    Tree operations use in-memory nodes. Journal provides:
    1. Persistence for crash recovery
    2. Automatic step assignment
    3. Global state storage (best_node_id, etc.)

    Usage:
        journal = Journal(Path("./memory/journal.db"))
        journal.append(node)  # Assigns step, persists
        journal.set_state("best_node_id", node.id)
    """

    def __init__(self, db_path: Path):
        """Initialize journal with SQLite database.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        self.nodes: list[MCTSNode] = []  # In-memory list for step counting

    def _init_schema(self) -> None:
        """Initialize database schema."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                step INTEGER,
                stage TEXT,
                parent_id TEXT,
                commit_hash TEXT,

                -- Agent results (plan, run_command, analysis, error)
                plan TEXT,
                run_command TEXT,
                analysis TEXT,
                error_summary TEXT,

                -- Legacy field for debug prompts
                output TEXT,

                -- Metrics
                metric_value REAL,
                metric_maximize BOOLEAN,
                is_buggy BOOLEAN,

                -- MCTS stats
                visits INTEGER DEFAULT 0,
                total_reward REAL DEFAULT 0,
                is_terminal BOOLEAN DEFAULT FALSE,

                -- Tracking
                improve_failure_depth INTEGER DEFAULT 0,
                continue_improve BOOLEAN DEFAULT FALSE,
                is_debug_success BOOLEAN DEFAULT FALSE,
                local_best_node_id TEXT,

                -- Timestamps
                finish_time TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_nodes_step ON nodes(step);
            CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
        """)
        self.conn.commit()

    def append(self, node: MCTSNode) -> None:
        """Add node to journal. Assigns step automatically.

        Args:
            node: Node to persist
        """
        node.step = len(self.nodes)
        self.nodes.append(node)
        self._persist_node(node)

    def _persist_node(self, node: MCTSNode) -> None:
        """Write node to SQLite for persistence."""
        metric_value = None
        metric_maximize = None
        if node.metric is not None:
            metric_value = node.metric.value
            metric_maximize = node.metric.maximize

        self.conn.execute("""
            INSERT OR REPLACE INTO nodes (
                id, step, stage, parent_id, commit_hash,
                plan, run_command, analysis, error_summary,
                output,
                metric_value, metric_maximize, is_buggy,
                visits, total_reward, is_terminal,
                improve_failure_depth, continue_improve, is_debug_success,
                local_best_node_id, finish_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            node.id,
            node.step,
            node.stage,
            node.parent.id if node.parent else None,
            node.commit_hash,
            node.plan,
            node.run_command,
            node.analysis,
            node.error_summary,
            node.output,
            metric_value,
            metric_maximize,
            node.is_buggy,
            node.visits,
            node.total_reward,
            node.is_terminal,
            node.improve_failure_depth,
            node.continue_improve,
            node.is_debug_success,
            node.local_best_node.id if node.local_best_node else None,
            node.finish_time,
        ))
        self.conn.commit()

    def update_node(self, node: MCTSNode) -> None:
        """Update existing node in database.

        Use after modifying node fields (e.g., after evaluation).

        Args:
            node: Node to update
        """
        self._persist_node(node)

    def __len__(self) -> int:
        """Return number of nodes."""
        return len(self.nodes)

    def get_state(self, key: str) -> Optional[str]:
        """Get global state value.

        Args:
            key: State key

        Returns:
            Value or None if not found
        """
        cursor = self.conn.execute(
            "SELECT value FROM state WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        return row["value"] if row else None

    def set_state(self, key: str, value: str) -> None:
        """Set global state value.

        Args:
            key: State key
            value: Value to store
        """
        self.conn.execute(
            "INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)",
            (key, value)
        )
        self.conn.commit()

    def load_tree(self) -> Optional[MCTSNode]:
        """Reconstruct in-memory tree from SQLite.

        Used for crash recovery. Rebuilds parent/children links.

        Returns:
            Root node with full tree structure, or None if empty
        """
        cursor = self.conn.execute(
            "SELECT * FROM nodes ORDER BY step ASC"
        )
        rows = cursor.fetchall()

        if not rows:
            return None

        # Build node map
        node_map: dict[str, MCTSNode] = {}
        for row in rows:
            # Reconstruct metric
            metric = None
            if row["metric_value"] is not None:
                metric = MetricValue(
                    value=row["metric_value"],
                    maximize=bool(row["metric_maximize"]),
                )
            elif row["is_buggy"]:
                metric = WorstMetricValue()

            node = MCTSNode(
                id=row["id"],
                stage=row["stage"],
                parent=None,  # Will link below
                plan=row["plan"],
                run_command=row["run_command"],
                commit_hash=row["commit_hash"],
                metric=metric,
                is_buggy=row["is_buggy"],
                analysis=row["analysis"],
                error_summary=row["error_summary"],
                output=row["output"],
                step=row["step"],
                visits=row["visits"],
                total_reward=row["total_reward"],
                is_terminal=bool(row["is_terminal"]),
                improve_failure_depth=row["improve_failure_depth"],
                continue_improve=bool(row["continue_improve"]),
                is_debug_success=bool(row["is_debug_success"]),
                finish_time=row["finish_time"],
            )
            node_map[node.id] = node
            self.nodes.append(node)

        # Link parent/children
        for row in rows:
            node = node_map[row["id"]]
            if row["parent_id"] and row["parent_id"] in node_map:
                node.parent = node_map[row["parent_id"]]
                node.parent.children.append(node)
            if row["local_best_node_id"] and row["local_best_node_id"] in node_map:
                node.local_best_node = node_map[row["local_best_node_id"]]

        # Find root (node with no parent)
        for node in node_map.values():
            if node.parent is None:
                return node

        return None

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()
