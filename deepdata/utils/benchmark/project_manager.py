"""
Project management utilities for testing.

Handles project copying, disk space checking, and cleanup of old test copies.
"""

import shutil
from pathlib import Path

from .disk import get_directory_size, get_available_disk_space


class ProjectManager:
    """Manages project copies and disk space for testing."""

    def __init__(
        self,
        project_path: Path,
        min_free_space_multiplier: float = 10.0
    ):
        """
        Initialize the project manager.

        Args:
            project_path: Path to the source project
            min_free_space_multiplier: Minimum free space required as multiple of project size
        """
        self.project_path = project_path
        self.min_free_space_multiplier = min_free_space_multiplier
        self._project_size = None

    def _cleanup_old_copies(self):
        """
        Remove old project copies to free up disk space.
        Removes oldest copies first until sufficient space is available.
        """
        copy_base = Path(f"{self.project_path}.copy")
        if not copy_base.exists():
            return

        # Get all test directories sorted by modification time (oldest first)
        test_dirs = [d for d in copy_base.iterdir() if d.is_dir()]
        if not test_dirs:
            return

        # Sort by modification time (oldest first)
        test_dirs.sort(key=lambda d: d.stat().st_mtime)

        # Calculate required space
        required = self._project_size * self.min_free_space_multiplier

        # Remove old copies until we have enough space
        for old_dir in test_dirs:
            available = get_available_disk_space(self.project_path.parent)
            if available >= required:
                break

            print(f"Removing old copy: {old_dir.name}")
            shutil.rmtree(old_dir)

    def _check_disk_space(self):
        """
        Check if there's enough disk space for project copy.
        Automatically cleans up old copies if space is insufficient.

        Raises:
            RuntimeError: If insufficient disk space even after cleanup
        """
        # Calculate project size if not cached
        if self._project_size is None:
            print("Calculating project size...")
            self._project_size = get_directory_size(self.project_path)
            size_mb = self._project_size / (1024 * 1024)
            print(f"Project size: {size_mb:.1f} MB")

        # Get available disk space
        available = get_available_disk_space(self.project_path.parent)
        available_mb = available / (1024 * 1024)

        # Calculate required space
        required = self._project_size * self.min_free_space_multiplier
        required_mb = required / (1024 * 1024)

        # Check if enough space
        if available < required:
            print("⚠ Insufficient space - cleaning up old copies...")
            self._cleanup_old_copies()

            # Check again after cleanup
            available = get_available_disk_space(self.project_path.parent)
            available_mb = available / (1024 * 1024)
            print(f"Available disk space after cleanup: {available_mb:.1f} MB")

            if available < required:
                raise RuntimeError(
                    f"Insufficient disk space: {available_mb:.1f} MB available, "
                    f"but {required_mb:.1f} MB required "
                    f"({self.min_free_space_multiplier}x project size). "
                    f"Cleaned up old copies but still not enough space."
                )

        print("✓ Sufficient disk space")

    def create_project_copy(self, test_id: str) -> Path:
        """
        Create a fresh copy of the project for testing.

        Args:
            test_id: Unique identifier for this test

        Returns:
            Path to the copied project

        Raises:
            RuntimeError: If insufficient disk space
        """
        # Check disk space before copying
        self._check_disk_space()

        # Create copy in .copy subdirectory
        copy_base = Path(f"{self.project_path}.copy")
        copy_base.mkdir(exist_ok=True)
        project_copy = copy_base / test_id

        # Remove existing copy if it exists
        if project_copy.exists():
            shutil.rmtree(project_copy)

        # Copy the project (excluding common ignore patterns)
        shutil.copytree(
            self.project_path,
            project_copy,
            ignore=shutil.ignore_patterns(
                '.git', '__pycache__', '*.pyc', '.pytest_cache',
                'node_modules', '.venv', 'venv', '*.egg-info',
                '.claude', 'checkpoints', 'logs', 'exp', 'cache'
            )
        )

        return project_copy
