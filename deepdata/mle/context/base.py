"""Base context module for ML agent.

Context provides environment information that agents need to understand the task.
ContextProvider is the abstract base class for different environment types.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Context:
    """Environment context - what the agent needs to know.

    Note: metric_name and metric_maximize are NOT in Context.
    These are extracted at runtime by the evaluate agent from execution output.
    This allows flexibility for custom metrics and avoids parsing errors.

    Paths are stored as relative strings (e.g., "./data/train.csv") for isolation.
    This ensures agents use relative paths and enables worktree isolation.
    """

    # Workspace root
    workspace: Path  # Main workspace directory

    # Task
    goal: str  # High-level objective
    task_description: str  # What to achieve (from description.md)

    # Data
    data_report_path: Path  # Always .memory/data_report.md
    data_paths: dict[str, str]  # {"train": "./data/train.csv", ...} - relative paths

    # Output
    output_paths: dict[str, str]  # {"prediction": "./results/pred.csv", ...} - relative
    output_requirements: str  # Natural language: format, structure, constraints

    # Workspace layout (for git worktree management)
    gitignore: list[str] = field(default_factory=list)  # Patterns to ignore in git
    sync: list[str] = field(default_factory=list)  # Paths to symlink across worktrees

    @property
    def data_report(self) -> str:
        """Load data report content."""
        if self.data_report_path.exists():
            return self.data_report_path.read_text()
        return ""

    def __post_init__(self) -> None:
        """Validate context."""
        # Validate .memory/ is in sync
        sync_normalized = [s.rstrip("/") for s in self.sync]
        if ".memory" not in sync_normalized:
            raise ValueError(".memory/ must be in sync list")

        # Validate all paths are relative (start with ./)
        for name, path in self.data_paths.items():
            if not path.startswith("./"):
                raise ValueError(f"data_path '{name}' must be relative (start with ./): {path}")
        for name, path in self.output_paths.items():
            if not path.startswith("./"):
                raise ValueError(f"output_path '{name}' must be relative (start with ./): {path}")


class ContextProvider(ABC):
    """Produces Context for an environment."""

    @abstractmethod
    async def get_context(self, workspace: Path) -> Context:
        """Generate context for the given workspace.

        Args:
            workspace: Path to the workspace directory

        Returns:
            Context object with all required information
        """
        pass


def _load_text_or_file(
    workspace: Path,
    text: str,
    max_path_len: int = 255,
    allowed_extensions: tuple = (".md", ".txt"),
) -> str:
    """Load text content, reading from file if it's a valid path.

    Logic:
    1. If contains newlines or too long → definitely content
    2. If valid file path under workspace with allowed extension → read file
    3. Otherwise → return as-is

    Args:
        workspace: Safe root directory
        text: User input (path or content)
        max_path_len: Max length for path (default 255)
        allowed_extensions: Only read files with these extensions

    Returns:
        Resolved text content
    """
    if not text or not isinstance(text, str):
        return ""

    # Early exit: newlines or too long → definitely content
    if "\n" in text or len(text) > max_path_len:
        return text

    try:
        # Path traversal protection: check before resolving (symlinks are OK)
        if text.startswith("..") or text.startswith("/"):
            return text

        target_path = workspace / text

        # Only allow specific extensions
        if target_path.suffix.lower() not in allowed_extensions:
            return text

        # Read if file exists (resolve for actual reading)
        if target_path.exists() and target_path.is_file():
            return target_path.read_text(encoding="utf-8")

    except (OSError, UnicodeDecodeError):
        pass

    # Fallback: treat as content
    return text


def resolve_context(workspace: Path, data: dict) -> Context:
    """Resolve raw context data into a Context object.

    Handles:
    - task_description: if path exists, read file content
    - data_paths/output_paths: resolve relative paths against workspace
    - Ensures .memory/ in gitignore and sync

    Args:
        workspace: Workspace directory
        data: Raw context dict (from preset JSON, discovery, or form)

    Returns:
        Resolved Context object
    """
    workspace = Path(workspace).resolve()

    # task_description: load from file if it's a path
    task_description = _load_text_or_file(workspace, data.get("task_description", ""))

    # Convert paths to relative strings with ./ prefix
    def to_relative(p: str) -> str:
        """Convert path to relative string, validating it's under workspace."""
        path = Path(p)
        if path.is_absolute():
            # Validate path is under workspace
            try:
                rel = path.relative_to(workspace)
            except ValueError:
                raise ValueError(f"Path is outside workspace: {path}")
            return f"./{rel}"
        else:
            # Already relative, just ensure ./ prefix
            p_str = str(path)
            return p_str if p_str.startswith("./") else f"./{p_str}"

    data_paths = {k: to_relative(v) for k, v in data.get("data_paths", {}).items()}
    output_paths = {k: to_relative(v) for k, v in data.get("output_paths", {}).items()}

    # Ensure .memory/ in gitignore and sync
    # Note: Must add both ".memory/" (directory) and ".memory" (symlink) to gitignore
    gitignore = list(data.get("gitignore", []))
    sync = list(data.get("sync", []))

    gitignore_normalized = {g.rstrip("/") for g in gitignore}
    if ".memory" not in gitignore_normalized:
        gitignore.append(".memory/")  # Directory pattern
        gitignore.append(".memory")   # Symlink pattern (no trailing slash)
    if not any(s.rstrip("/") == ".memory" for s in sync):
        sync.append(".memory/")

    # Create output directories (convert relative back to absolute for mkdir)
    memory_dir = workspace / ".memory"
    memory_dir.mkdir(exist_ok=True)
    for rel_path in output_paths.values():
        abs_path = workspace / rel_path.lstrip("./")
        abs_path.parent.mkdir(parents=True, exist_ok=True)

    return Context(
        workspace=workspace,
        goal=data.get("goal", ""),
        task_description=task_description,
        data_report_path=memory_dir / "data_report.md",
        data_paths=data_paths,
        output_paths=output_paths,
        output_requirements=data.get("output_requirements", ""),
        gitignore=gitignore,
        sync=sync,
    )
