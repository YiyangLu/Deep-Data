"""
Path utilities for consistent file locations across the project.

The project root is determined by finding the directory containing 'src/'.
This works regardless of where the command is run from.
"""

from pathlib import Path


def get_project_root() -> Path:
    """
    Get the project root directory.

    Finds the root by looking for the 'src' directory, starting from
    this file's location and moving up.

    Returns:
        Path to project root
    """
    current = Path(__file__).resolve()

    # Walk up until we find a directory that contains 'src/'
    for parent in current.parents:
        if (parent / "src").is_dir():
            return parent

    # Fallback: use the parent of 'src' from this file's path
    # This file is at src/utils/paths.py, so go up 2 levels
    return current.parent.parent.parent


def get_logs_root() -> Path:
    """
    Get the logs directory path.

    Always returns {project_root}/logs regardless of current working directory.

    Returns:
        Path to logs directory
    """
    return get_project_root() / "logs"
