"""MLE Storage System.

Stores MLE run data in logs/mle/{run_id}/ for persistence and recovery.

Design:
- journal.db: MCTS tree, nodes, metrics
- context.json: Task context (goal, data paths, outputs, gitignore, sync)
- data_report.md: Data analysis report
- run_state.json: Git state, config, and resume history

The workspace's .memory/ directory can be completely regenerated from logs/.
"""

import json
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .context import Context
from ..utils.paths import get_logs_root


class MLEStore:
    """MLE run data storage manager.

    Each MLE run is stored in its own folder:
        logs/mle/{run_id}/
            journal.db
            context.json
            data_report.md
            run_state.json

    Usage:
        store = MLEStore()
        run_dir = store.create_run("run-123", context, workspace)
        journal_path = store.get_journal_path("run-123")
    """

    def __init__(self, logs_root: Path = None):
        """Initialize MLEStore.

        Args:
            logs_root: Root directory for logs (default: ./logs)
        """
        self.logs_root = logs_root or get_logs_root()
        self.mle_dir = self.logs_root / "mle"
        self.mle_dir.mkdir(parents=True, exist_ok=True)

    def create_run(
        self,
        run_id: str,
        context: Context,
        workspace: Path,
        initial_commit: Optional[str] = None,
    ) -> Path:
        """Create storage for a new MLE run.

        Args:
            run_id: Unique run identifier
            context: Task context
            workspace: Workspace path
            initial_commit: Git commit hash before MLE started (for reset)

        Returns:
            Path to run directory
        """
        run_dir = self.mle_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Save context.json
        self._save_context(run_dir, context)

        # Save run_state.json
        self._save_run_state(run_dir, workspace, initial_commit)

        # Copy data_report.md if exists
        if context.data_report_path.exists():
            shutil.copy2(context.data_report_path, run_dir / "data_report.md")

        return run_dir

    def get_run_dir(self, run_id: str) -> Path:
        """Get run directory path.

        Args:
            run_id: Run identifier

        Returns:
            Path to run directory

        Raises:
            ValueError: If run not found
        """
        run_dir = self.mle_dir / run_id
        if not run_dir.exists():
            raise ValueError(f"MLE run not found: {run_id}")
        return run_dir

    def get_journal_path(self, run_id: str) -> Path:
        """Get path to journal.db for a run.

        Args:
            run_id: Run identifier

        Returns:
            Path to journal.db (may not exist yet)
        """
        return self.mle_dir / run_id / "journal.db"

    def load_context(self, run_id: str) -> Context:
        """Load context from stored context.json.

        Args:
            run_id: Run identifier

        Returns:
            Context object

        Raises:
            ValueError: If run not found
            FileNotFoundError: If context.json not found
        """
        run_dir = self.get_run_dir(run_id)
        context_path = run_dir / "context.json"

        if not context_path.exists():
            raise FileNotFoundError(f"context.json not found for run: {run_id}")

        with open(context_path) as f:
            data = json.load(f)

        # Convert paths back to Path objects (only workspace and data_report_path)
        # data_paths and output_paths are relative strings
        return Context(
            workspace=Path(data["workspace"]),
            goal=data["goal"],
            task_description=data["task_description"],
            data_report_path=Path(data["data_report_path"]),
            data_paths=data["data_paths"],  # Already relative strings
            output_paths=data["output_paths"],  # Already relative strings
            output_requirements=data["output_requirements"],
            gitignore=data.get("gitignore", []),
            sync=data.get("sync", []),
        )

    def load_run_state(self, run_id: str) -> dict:
        """Load run state (workspace, initial_commit).

        Args:
            run_id: Run identifier

        Returns:
            Dict with workspace, initial_commit

        Raises:
            ValueError: If run not found
            FileNotFoundError: If run_state.json not found
        """
        run_dir = self.get_run_dir(run_id)
        state_path = run_dir / "run_state.json"

        if not state_path.exists():
            raise FileNotFoundError(f"run_state.json not found for run: {run_id}")

        with open(state_path) as f:
            return json.load(f)

    def update_run_state(
        self,
        run_id: str,
        initial_commit: Optional[str] = None,
    ) -> None:
        """Update run state (e.g., after git init).

        Args:
            run_id: Run identifier
            initial_commit: Git commit hash to save
        """
        run_dir = self.get_run_dir(run_id)
        state_path = run_dir / "run_state.json"

        # Load existing state
        state = {}
        if state_path.exists():
            with open(state_path) as f:
                state = json.load(f)

        # Update
        if initial_commit is not None:
            state["initial_commit"] = initial_commit

        # Save
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

    def save_initial_config(
        self,
        run_id: str,
        time_limit: int,
        max_steps: int,
        workers: int,
        model: str,
    ) -> None:
        """Save initial MCTS config when run starts.

        Args:
            run_id: Run identifier
            time_limit: Time limit in seconds
            max_steps: Maximum MCTS steps
            workers: Number of parallel workers
            model: Model name (e.g., 'opus', 'sonnet')
        """
        run_dir = self.get_run_dir(run_id)
        state_path = run_dir / "run_state.json"

        # Load existing state
        state = {}
        if state_path.exists():
            with open(state_path) as f:
                state = json.load(f)

        # Set initial config (only if not already set)
        if "initial_config" not in state:
            state["initial_config"] = {
                "time_limit": time_limit,
                "max_steps": max_steps,
                "workers": workers,
                "model": model,
            }
            # Initialize resumes list
            state["resumes"] = []

        # Save
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

    def add_resume_event(
        self,
        run_id: str,
        additional_time: int,
        additional_steps: int,
    ) -> None:
        """Add a resume event to the history.

        Args:
            run_id: Run identifier
            additional_time: Additional time in seconds
            additional_steps: Additional steps allowed
        """
        run_dir = self.get_run_dir(run_id)
        state_path = run_dir / "run_state.json"

        # Load existing state
        state = {}
        if state_path.exists():
            with open(state_path) as f:
                state = json.load(f)

        # Add resume event
        if "resumes" not in state:
            state["resumes"] = []

        state["resumes"].append({
            "timestamp": datetime.now().isoformat(),
            "additional_time": additional_time,
            "additional_steps": additional_steps,
        })

        # Save
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

    def get_effective_limits(self, run_id: str) -> dict:
        """Calculate effective time/step limits including all resumes.

        Args:
            run_id: Run identifier

        Returns:
            Dict with time_limit, max_steps (sum of initial + all resumes)

        Raises:
            ValueError: If initial_config not found (old runs not supported)
        """
        state = self.load_run_state(run_id)

        if "initial_config" not in state:
            raise ValueError(f"Run {run_id} missing initial_config - old runs not supported for resume")

        initial = state["initial_config"]
        resumes = state.get("resumes", [])

        time_limit = initial["time_limit"]
        max_steps = initial["max_steps"]

        for resume in resumes:
            time_limit += resume["additional_time"]
            max_steps += resume["additional_steps"]

        return {
            "time_limit": time_limit,
            "max_steps": max_steps,
        }

    def save_data_report(self, run_id: str, content: str) -> None:
        """Save data report to run directory.

        Args:
            run_id: Run identifier
            content: Report content
        """
        run_dir = self.get_run_dir(run_id)
        report_path = run_dir / "data_report.md"
        report_path.write_text(content)

    def get_data_report(self, run_id: str) -> str:
        """Get data report content.

        Args:
            run_id: Run identifier

        Returns:
            Report content or empty string if not found
        """
        run_dir = self.mle_dir / run_id
        report_path = run_dir / "data_report.md"
        if report_path.exists():
            return report_path.read_text()
        return ""

    def list_runs(self, limit: int = 50) -> list[str]:
        """List all run IDs, most recent first.

        Args:
            limit: Maximum number of runs to return

        Returns:
            List of run IDs
        """
        runs = []
        for run_dir in sorted(
            self.mle_dir.iterdir(),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        ):
            if run_dir.is_dir() and (run_dir / "journal.db").exists():
                runs.append(run_dir.name)
                if len(runs) >= limit:
                    break
        return runs

    def delete_run(self, run_id: str) -> bool:
        """Delete a run and all its data.

        Args:
            run_id: Run identifier

        Returns:
            True if deleted, False if not found
        """
        run_dir = self.mle_dir / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir)
            return True
        return False

    def _save_context(self, run_dir: Path, context: Context) -> None:
        """Save context to JSON file.

        Args:
            run_dir: Run directory
            context: Context to save
        """
        # Convert to dict (data_paths/output_paths are already strings)
        data = {
            "workspace": str(context.workspace),
            "goal": context.goal,
            "task_description": context.task_description,
            "data_report_path": str(context.data_report_path),
            "data_paths": context.data_paths,  # Already relative strings
            "output_paths": context.output_paths,  # Already relative strings
            "output_requirements": context.output_requirements,
            "gitignore": context.gitignore,
            "sync": context.sync,
        }

        context_path = run_dir / "context.json"
        with open(context_path, "w") as f:
            json.dump(data, f, indent=2)

    def _save_run_state(
        self,
        run_dir: Path,
        workspace: Path,
        initial_commit: Optional[str],
    ) -> None:
        """Save run state to JSON file.

        Args:
            run_dir: Run directory
            workspace: Workspace path
            initial_commit: Initial git commit hash
        """
        state = {
            "workspace": str(workspace),
            "initial_commit": initial_commit,
        }

        state_path = run_dir / "run_state.json"
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)


# Global instance
_mle_store: Optional[MLEStore] = None


def get_mle_store() -> MLEStore:
    """Get or create global MLEStore instance."""
    global _mle_store
    if _mle_store is None:
        _mle_store = MLEStore()
    return _mle_store
