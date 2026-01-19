"""
Message utilities for saving and debugging.

Provides functions to save SDK messages to disk for debugging and analysis.
"""

import json
from pathlib import Path
from datetime import datetime

from ..config import CORE_LOGS_DIR


def message_to_dict(msg) -> dict:
    """
    Convert SDK message to JSON-serializable dictionary.

    Args:
        msg: SDK Message object

    Returns:
        Dictionary with message type, repr, and attributes
    """
    msg_dict = {
        "type": type(msg).__name__,
        "repr": repr(msg),
    }

    # Extract all attributes
    if hasattr(msg, '__dict__'):
        msg_dict["attributes"] = {}
        for key, value in msg.__dict__.items():
            try:
                # Try to serialize
                json.dumps(value)
                msg_dict["attributes"][key] = value
            except (TypeError, ValueError):
                # For non-serializable objects, use repr
                msg_dict["attributes"][key] = repr(value)

    return msg_dict


def save_messages(messages: list, log_dir: str | Path | None = None, prefix: str = "messages"):
    """
    Save messages to disk as JSON.

    Args:
        messages: List of SDK messages
        log_dir: Directory to save logs (default: uses CORE_LOGS_DIR from config)
        prefix: Filename prefix (default: "messages")

    Returns:
        Path to saved file
    """
    log_dir = Path(log_dir) if log_dir is not None else CORE_LOGS_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create timestamped filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.json"
    filepath = log_dir / filename

    # Convert messages to serializable format
    serializable_messages = [message_to_dict(msg) for msg in messages]

    # Save to file
    with open(filepath, "w") as f:
        json.dump(serializable_messages, f, indent=2)

    return filepath
