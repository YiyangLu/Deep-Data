"""
Disk space utilities for project management.

Provides functions to check directory sizes and available disk space.
"""

import shutil
from pathlib import Path


def get_directory_size(path: Path) -> int:
    """
    Get total size of directory in bytes.

    Args:
        path: Directory path to measure

    Returns:
        Total size in bytes
    """
    total = 0
    for entry in path.rglob('*'):
        if entry.is_file():
            total += entry.stat().st_size
    return total


def get_available_disk_space(path: Path) -> int:
    """
    Get available disk space in bytes.

    Args:
        path: Path to check disk space for

    Returns:
        Available space in bytes
    """
    stat = shutil.disk_usage(path)
    return stat.free
