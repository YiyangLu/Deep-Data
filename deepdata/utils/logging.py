"""
Centralized logging utilities.

Provides standardized logger creation with consistent formatting.
"""

import logging
import os
import sys


# Flag to indicate file-only logging mode (set by web server)
_file_only_logging = False

# Track loggers we've created so we can reconfigure them
_created_loggers: list[str] = []


def enable_file_only_logging():
    """
    Enable file-only logging mode. Called by web server setup.

    This removes console handlers from all loggers we've created
    and prevents new ones from being added.
    """
    global _file_only_logging
    _file_only_logging = True

    # Remove console handlers from all loggers we've created
    for name in _created_loggers:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True


def create_logger(name: str, level: int = logging.DEBUG):
    """
    Create a standardized logger with auto-generated prefix.

    The logger outputs to stderr with a prefix automatically derived from
    the module name. This ensures consistent logging format across the project.

    In file-only mode (web server), no console handler is added - logs go
    to file via root logger.

    Args:
        name: Logger name (typically __name__ from the calling module)
        level: Logging level (default: DEBUG)

    Returns:
        Configured logger instance

    Examples:
        >>> # In src/plotly/client.py
        >>> from deepdata.utils.logging import create_logger
        >>> logger = create_logger(__name__)
        >>> logger.info("Starting upload")
        [PLOTLY.CLIENT] INFO: Starting upload

        >>> # In src/core/agent.py
        >>> logger = create_logger(__name__)
        >>> logger.debug("Processing query")
        [CORE.AGENT] DEBUG: Processing query

    Format:
        - Module src.plotly.client -> Prefix [PLOTLY.CLIENT]
        - Module src.core.agent -> Prefix [CORE.AGENT]
        - Module __main__ -> Prefix [__MAIN__]
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Track this logger
    if name not in _created_loggers:
        _created_loggers.append(name)

    # In file-only mode, don't add console handler - use root logger's file handler
    if _file_only_logging:
        logger.propagate = True
        return logger

    # Avoid duplicate handlers if logger already configured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)

        # Auto-generate prefix from module name
        # Example: src.plotly.client -> PLOTLY.CLIENT
        parts = name.split('.')
        if parts[0] == 'src':
            parts = parts[1:]  # Remove 'src' prefix
        prefix = '.'.join(parts).upper()

        formatter = logging.Formatter(f'[{prefix}] %(levelname)s: %(message)s')
        handler.setFormatter(formatter)

        logger.addHandler(handler)

    return logger
