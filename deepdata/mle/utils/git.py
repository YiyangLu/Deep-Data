"""
Git worktree management for parallel MCTS workers.

Uses Git worktrees to provide isolated environments for parallel workers.
Each worker gets its own branch and directory, enabling multi-file solutions
without conflicts.
"""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from git import Repo
from git.exc import GitCommandError


# Default: ~/agent_worktree (visible in home for easy debugging)
# Can override via environment variable
WORKTREE_ROOT = Path(os.environ.get("AGENT_WORKTREE_ROOT", Path.home() / "agent_worktree"))


class GitWorkspaceError(Exception):
    """Base exception for git workspace errors."""
    pass


class WorktreeExistsError(GitWorkspaceError):
    """Worktree already exists."""
    pass


class CommitError(GitWorkspaceError):
    """Failed to commit changes."""
    pass


class GitWorkspace:
    """Manages git repo and worktrees for parallel workers.

    Handles:
    - Git initialization with .gitignore from Context
    - Worktree creation/cleanup in external directory
    - Symlink setup for shared paths
    - Commit/checkout operations

    Example:
        gw = GitWorkspace(
            workspace=Path("/path/to/workspace"),
            gitignore=["data/", "submission/", ".memory/"],
            sync=["data/", ".memory/"],
        ).init()

        worktree = gw.create_worktree(0)
        # ... agent modifies files ...
        commit_hash = gw.commit(worktree, "Node 123")
    """

    def __init__(
        self,
        workspace: Path,
        gitignore: list[str],
        sync: list[str],
        worktree_root: Path | None = None,
        base_conda_env: str | None = None,
    ):
        """Initialize git workspace.

        Args:
            workspace: Main workspace directory
            gitignore: Patterns to ignore (from Context)
            sync: Paths to symlink into worktrees (from Context)
            worktree_root: Root for worktree directories (default: WORKTREE_ROOT)
            base_conda_env: Name of conda env to clone for each worktree (optional)
        """
        self.workspace = Path(workspace).resolve()
        self.gitignore = gitignore
        self.sync = sync
        self.base_conda_env = base_conda_env

        # Generate unique project ID from workspace path
        self.project_id = self._hash_path(self.workspace)

        # Resolve worktree root
        if worktree_root is None:
            worktree_root = WORKTREE_ROOT
        self.worktree_root = Path(worktree_root).resolve()
        self.worktree_dir = self.worktree_root / self.project_id

        self.repo: Repo | None = None

    @property
    def default_branch(self) -> str:
        """Get the default branch name (main or master)."""
        if self.repo is None:
            raise GitWorkspaceError("Git repo not initialized")
        return self.repo.active_branch.name

    @property
    def head_commit(self) -> str:
        """Get the HEAD commit hash."""
        if self.repo is None:
            raise GitWorkspaceError("Git repo not initialized")
        return self.repo.head.commit.hexsha

    @staticmethod
    def _hash_path(path: Path) -> str:
        """Generate short hash from path for unique project ID."""
        return hashlib.sha256(str(path).encode()).hexdigest()[:12]

    # --- Initialization ---

    def init(self) -> "GitWorkspace":
        """Initialize git repo in workspace.

        - Creates .memory directory
        - Saves workspace.json for cleanup
        - Creates .gitignore from Context.gitignore
        - Initializes git repo if not exists
        - Creates initial commit

        Returns:
            self for chaining
        """
        # Create .memory directory
        memory_dir = self.workspace / ".memory"
        memory_dir.mkdir(exist_ok=True)

        # Write .gitignore
        # For each pattern, we add both with and without trailing slash
        # to ensure both directories and symlinks are ignored
        gitignore_path = self.workspace / ".gitignore"
        seen: set[str] = set()
        patterns: list[str] = []

        # Add user patterns
        for pattern in self.gitignore:
            # Add original pattern
            if pattern not in seen:
                patterns.append(pattern)
                seen.add(pattern)
            # Add pattern without trailing slash to also ignore symlinks
            stripped = pattern.rstrip("/")
            if stripped != pattern and stripped not in seen:
                patterns.append(stripped)
                seen.add(stripped)

        # Add env/ for conda environment isolation (created per-worktree)
        if "env" not in seen:
            patterns.append("env/")
            patterns.append("env")
            seen.add("env")

        gitignore_content = "\n".join(patterns) + "\n"
        gitignore_path.write_text(gitignore_content)

        # Initialize repo
        if (self.workspace / ".git").exists():
            self.repo = Repo(self.workspace)
        else:
            self.repo = Repo.init(self.workspace)

        # Initial commit (if needed)
        if not self.repo.heads:
            self.repo.index.add([".gitignore"])
            self.repo.index.commit("Initial commit")

        # Save initial commit hash for reset capability
        initial_commit = self.repo.head.commit.hexsha
        self._save_workspace_json(initial_commit=initial_commit)

        return self

    def _save_workspace_json(self, initial_commit: str | None = None) -> None:
        """Save workspace state to .memory/workspace.json for cleanup.

        Args:
            initial_commit: The commit hash before search started (for reset)
        """
        workspace_json = self.workspace / ".memory" / "workspace.json"
        state = {
            "workspace": str(self.workspace),
            "project_id": self.project_id,
            "worktree_root": str(self.worktree_root),
            "worktree_dir": str(self.worktree_dir),
            "gitignore": self.gitignore,
            "sync": self.sync,
        }
        if initial_commit:
            state["initial_commit"] = initial_commit
        workspace_json.write_text(json.dumps(state, indent=2) + "\n")

    # --- Worktree Management ---

    def create_worktree(self, worker_id: int) -> Path:
        """Create isolated worktree for a worker.

        Args:
            worker_id: Unique worker identifier

        Returns:
            Path to worktree directory

        Raises:
            WorktreeExistsError: If worktree already exists
        """
        if self.repo is None:
            raise GitWorkspaceError("GitWorkspace not initialized. Call init() first.")

        worktree_path = self.worktree_dir / f"worker_{worker_id}"
        branch_name = f"worker_{worker_id}"

        # Check if worktree already exists
        if worktree_path.exists():
            raise WorktreeExistsError(f"Worktree already exists: {worktree_path}")

        # Create parent directory
        self.worktree_dir.mkdir(parents=True, exist_ok=True)

        # Create worktree with new branch from HEAD
        try:
            self.repo.git.worktree("add", str(worktree_path), "-b", branch_name)
        except GitCommandError as e:
            # Branch might already exist from previous run
            if "already exists" in str(e):
                # Delete the branch and try again
                try:
                    self.repo.git.branch("-D", branch_name)
                except GitCommandError:
                    pass
                self.repo.git.worktree("add", str(worktree_path), "-b", branch_name)
            else:
                raise

        # Setup symlinks for shared paths
        self._setup_symlinks(worktree_path)

        # Create isolated conda env if configured
        if self.base_conda_env:
            self._create_conda_env(worktree_path)

        return worktree_path

    def remove_worktree(self, worker_id: int) -> None:
        """Remove a worker's worktree.

        Args:
            worker_id: Worker identifier
        """
        if self.repo is None:
            return

        worktree_path = self.worktree_dir / f"worker_{worker_id}"

        if worktree_path.exists():
            try:
                # Remove worktree (git handles cleanup)
                self.repo.git.worktree("remove", str(worktree_path), "--force")
            except GitCommandError:
                # Fallback: manual removal
                shutil.rmtree(worktree_path, ignore_errors=True)
                try:
                    self.repo.git.worktree("prune")
                except GitCommandError:
                    pass

    def cleanup_all_worktrees(self) -> None:
        """Remove all worktrees for this project."""
        if self.repo is None:
            return

        if self.worktree_dir.exists():
            # List and remove all worktrees
            for entry in self.worktree_dir.iterdir():
                if entry.is_dir() and entry.name.startswith("worker_"):
                    try:
                        self.repo.git.worktree("remove", str(entry), "--force")
                    except GitCommandError:
                        # Fallback: manual removal
                        shutil.rmtree(entry, ignore_errors=True)

            # Remove project directory
            shutil.rmtree(self.worktree_dir, ignore_errors=True)

        # Prune stale worktree references
        try:
            self.repo.git.worktree("prune")
        except GitCommandError:
            pass

    # --- Symlink Management ---

    def _setup_symlinks(self, worktree_path: Path) -> None:
        """Create symlinks for shared paths in worktree.

        Uses absolute symlinks for reliability.

        Args:
            worktree_path: Target worktree directory
        """
        for sync_path in self.sync:
            # Normalize path (remove trailing slash)
            sync_path = sync_path.rstrip("/")

            source = self.workspace / sync_path
            target = worktree_path / sync_path

            # Remove if exists (from previous checkout or git)
            if target.exists() or target.is_symlink():
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink()

            # Create parent directories
            target.parent.mkdir(parents=True, exist_ok=True)

            # Create absolute symlink
            if source.exists():
                target.symlink_to(source.resolve())

    # --- Conda Environment Management ---

    def _create_conda_env(self, worktree_path: Path) -> None:
        """Create isolated conda env for worktree by cloning base env.

        Creates env at {worktree}/env using:
            conda create --prefix ./env --clone {base_env} --offline

        This provides isolation for pip installs while being fast (hardlinks on same fs).

        Args:
            worktree_path: Target worktree directory
        """
        env_path = worktree_path / "env"

        # Skip if already exists
        if env_path.exists():
            return

        # Clone base env
        cmd = [
            "conda", "create",
            "--prefix", str(env_path),
            "--clone", self.base_conda_env,
            "--yes",
            "--quiet",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 min timeout (network downloads may be slow)
            )
            if result.returncode != 0:
                raise GitWorkspaceError(
                    f"Failed to create conda env: {result.stderr}"
                )
        except subprocess.TimeoutExpired:
            # Cleanup partial env
            if env_path.exists():
                shutil.rmtree(env_path, ignore_errors=True)
            raise GitWorkspaceError("Conda env creation timed out (10 min)")

    def get_env_vars(self, worktree_path: Path) -> dict:
        """Get environment variables to activate worktree's conda env.

        Returns dict with PATH and CONDA_PREFIX set for the worktree's env.
        Can be merged with other env vars (like CUDA_VISIBLE_DEVICES).

        Args:
            worktree_path: Worktree directory

        Returns:
            Dict with PATH and CONDA_PREFIX, or empty dict if no conda env
        """
        if not self.base_conda_env:
            return {}

        env_path = worktree_path / "env"
        if not env_path.exists():
            return {}

        # Prepend env/bin to PATH and set CONDA_PREFIX
        current_path = os.environ.get("PATH", "")
        return {
            "PATH": f"{env_path}/bin:{current_path}",
            "CONDA_PREFIX": str(env_path),
        }

    # --- Git Operations ---

    def checkout(self, worktree_path: Path, commit_or_branch: str) -> None:
        """Checkout specific commit or branch in worktree.

        Uses detached HEAD to avoid conflicts with branches checked out elsewhere.

        Args:
            worktree_path: Worktree directory
            commit_or_branch: Commit hash or branch name to checkout
        """
        worktree_repo = Repo(worktree_path)

        # Resolve branch name to commit hash if needed
        try:
            # Try as branch first
            if commit_or_branch in [h.name for h in self.repo.heads]:
                commit_hash = self.repo.heads[commit_or_branch].commit.hexsha
            else:
                commit_hash = commit_or_branch
        except Exception:
            commit_hash = commit_or_branch

        # Use detached HEAD checkout to avoid branch conflicts
        worktree_repo.git.checkout("--detach", commit_hash)

        # Re-setup symlinks (checkout may have removed them)
        self._setup_symlinks(worktree_path)

    def commit(self, worktree_path: Path, message: str) -> str:
        """Commit all changes in worktree.

        Args:
            worktree_path: Worktree directory
            message: Commit message

        Returns:
            Commit hash

        Raises:
            CommitError: If commit fails
        """
        worktree_repo = Repo(worktree_path)

        try:
            # Add all tracked and new files (respects .gitignore)
            worktree_repo.git.add("-A")

            # Check if there are staged changes (compare index to HEAD)
            staged_changes = worktree_repo.index.diff("HEAD")
            if staged_changes:
                worktree_repo.index.commit(message)

            return worktree_repo.head.commit.hexsha
        except GitCommandError as e:
            raise CommitError(f"Failed to commit: {e}") from e

    def get_diff(self, commit_a: str, commit_b: str) -> str:
        """Get diff between two commits.

        Args:
            commit_a: First commit hash
            commit_b: Second commit hash

        Returns:
            Diff as string
        """
        if self.repo is None:
            raise GitWorkspaceError("GitWorkspace not initialized. Call init() first.")

        return self.repo.git.diff(commit_a, commit_b)

    def get_worktree_path(self, worker_id: int) -> Path:
        """Get path to a worker's worktree.

        Args:
            worker_id: Worker identifier

        Returns:
            Path to worktree directory
        """
        return self.worktree_dir / f"worker_{worker_id}"

    def save_best_to_main(self, commit_hash: str, worktree_path: Path) -> None:
        """Save best solution files to main workspace.

        Copies both tracked files (via git checkout) and untracked output
        files (via file copy) from the worktree to main workspace.

        Args:
            commit_hash: Commit hash of the best solution
            worktree_path: Path to worktree containing output files
        """
        if self.repo is None:
            raise GitWorkspaceError("GitWorkspace not initialized")

        # 1. Checkout tracked files (code) to main workspace
        try:
            self.repo.git.checkout(commit_hash, "--force")
        except GitCommandError as e:
            # Log but don't fail - we can still copy output files
            print(f"Warning: git checkout failed: {e}")

        # 2. Copy untracked output directories from worktree
        # These are in gitignore so not tracked by git
        output_dirs = ["submission", "model"]
        for output_dir in output_dirs:
            src = worktree_path / output_dir
            dst = self.workspace / output_dir

            if src.exists() and src.is_dir():
                # Check if there are actual files (not just empty dir)
                files = list(src.iterdir())
                if files:
                    # Remove existing and copy from worktree
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)

        # 3. Re-setup symlinks for shared paths (checkout may have affected them)
        for sync_path in self.sync:
            sync_path = sync_path.rstrip("/")
            target = self.workspace / sync_path
            source = self.workspace / sync_path

            # For main workspace, ensure sync paths exist as directories (not symlinks)
            if target.is_symlink():
                target.unlink()
                target.mkdir(parents=True, exist_ok=True)
