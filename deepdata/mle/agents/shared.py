"""Shared utilities for MLE agents.

Common constants, models, and helper functions used across all agents.
"""

import random
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..context import Context


# Available ML packages (shuffled to avoid position bias)
AVAILABLE_PACKAGES = [
    "numpy", "pandas", "scikit-learn", "statsmodels",
    "xgboost", "lightGBM", "torch", "torchvision",
    "torch-geometric", "bayesian-optimization", "timm",
    "transformers", "nltk", "spacy",
]


@dataclass
class PromptContext:
    """Runtime context for agent prompts.

    Provides time/step budget info for strategic decisions.
    """
    time_remaining: int      # Seconds remaining in total budget
    steps_remaining: int     # MCTS steps remaining
    current_step: int        # Current step number
    gpu_id: int | None = None  # Assigned GPU (None if no GPU assignment)


class AgentResult(BaseModel):
    """Result from draft/improve/debug agent execution.

    Agent writes code, runs it, and reports results.
    No 'code' field - agent modifies worktree directly,
    code is tracked via git commit_hash by orchestrator.
    """
    # Code description
    plan: str = Field(description="Natural language description of approach (3-5 sentences)")
    run_command: str = Field(description="Command to execute, e.g., 'python main.py'")

    # Execution results (agent runs code and reports)
    is_success: bool = Field(description="True if code ran without errors AND meets output requirements")
    metric_value: float | None = Field(default=None, description="Validation metric score observed (null if not available)")
    lower_is_better: bool | None = Field(default=None, description="True if metric should be minimized (e.g., RMSE), False if maximized (e.g., accuracy)")
    error_summary: str | None = Field(default=None, description="Error description if is_success=False")
    analysis: str | None = Field(default=None, description="Brief analysis of what the solution achieved")
    output: str | None = Field(default=None, description="Captured stdout/stderr from code execution")


def format_time(seconds: int) -> str:
    """Format seconds into human-readable string.

    Examples:
        format_time(3600) -> "1h 0m"
        format_time(90) -> "1m 30s"
        format_time(45) -> "45s"
    """
    if seconds >= 3600:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"
    elif seconds >= 60:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    else:
        return f"{seconds}s"


def trim_long_string(s: str, max_length: int = 5000) -> str:
    """Trim long strings for prompt inclusion.

    Keeps first and last portions, indicating truncation.

    Args:
        s: String to trim
        max_length: Maximum length (default 5000 chars)

    Returns:
        Trimmed string with truncation indicator if needed
    """
    if len(s) <= max_length:
        return s

    half = max_length // 2
    return s[:half] + "\n\n... [TRUNCATED] ...\n\n" + s[-half:]


def read_file(path: Path) -> str:
    """Read file contents, returning empty string if not exists.

    Args:
        path: Path to file

    Returns:
        File contents or empty string
    """
    path = Path(path)
    if path.exists():
        return path.read_text()
    return ""


def get_package_list() -> str:
    """Get shuffled list of available packages (avoid position bias).

    Returns:
        Formatted string for conda env description
    """
    pkgs = AVAILABLE_PACKAGES.copy()
    random.shuffle(pkgs)
    pkg_str = ", ".join(pkgs)
    return f"conda env with ML packages such as {pkg_str}, etc."


def check_output_paths(worktree: Path, output_paths: dict[str, str]) -> dict[str, bool]:
    """Check which output files exist.

    Args:
        worktree: Worktree directory
        output_paths: Dict of output name -> relative path string (e.g., "./results/pred.csv")

    Returns:
        Dict of output name -> exists boolean
    """
    result = {}
    for name, rel_path in output_paths.items():
        # Strip ./ prefix and join with worktree
        path = worktree / rel_path.lstrip("./")
        result[name] = path.exists()
    return result


def get_gpu_instructions(gpu_id: int | None) -> str:
    """Generate GPU line for prompt.

    Args:
        gpu_id: Assigned GPU ID, or None if no GPU

    Returns:
        GPU line for Environment section
    """
    if gpu_id is None:
        return "- GPU: not available"
    return f"- GPU: CUDA_VISIBLE_DEVICES={gpu_id}"
