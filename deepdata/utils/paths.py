"""
Path utilities for consistent file locations.

All deepdata data lives under ~/.deepdata/
"""

from pathlib import Path


def get_deepdata_home() -> Path:
    """
    Get the deepdata home directory (~/.deepdata).

    Returns:
        Path to ~/.deepdata
    """
    return Path.home() / ".deepdata"


def get_logs_root() -> Path:
    """
    Get the logs directory path (~/.deepdata/logs).

    Returns:
        Path to logs directory
    """
    return get_deepdata_home() / "logs"


# Backward compat alias
get_project_root = get_deepdata_home
