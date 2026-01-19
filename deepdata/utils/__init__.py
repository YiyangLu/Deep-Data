"""
Shared utilities for the project.

Available utilities:
- logging: Centralized logger creation
- benchmark: Agent benchmarking infrastructure
- paths: Project path utilities
"""

from .logging import create_logger
from .paths import get_project_root, get_logs_root

__all__ = [
    'create_logger',
    'benchmark',
    'get_project_root',
    'get_logs_root',
]
