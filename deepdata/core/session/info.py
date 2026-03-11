"""
Session metadata dataclass.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class SessionInfo:
    """Session metadata from index."""
    session_id: str
    folder_path: Path
    created_at: str
    updated_at: str
    agent_id: str
    init_cwd: str
    current_cwd: str
    transcript_file: str
    latest_query: Optional[str]
    total_cost_usd: float
    duration_ms: int
    input_tokens: int
    output_tokens: int
    notes: Optional[str]
    tags: Optional[str]
    session_name: str = 'Agent'
