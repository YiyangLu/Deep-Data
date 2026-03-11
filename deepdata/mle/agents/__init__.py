"""MLE Agents.

Agent functions for the MCTS-based ML engineering system.

Each agent follows the same pattern:
- Takes workspace/worktree, context, and optional event_sink
- Returns structured output via output_format (AgentResult)
- Uses Agent class with appropriate tools
- Agent runs code and reports results (is_success, metric_value, etc.)

Available agents:
- run_data_report_agent: Generates initial data analysis
- run_draft_agent: Creates new ML solutions from scratch
- run_improve_agent: Refines working solutions
- run_debug_agent: Fixes buggy solutions
"""

from .data_report import run_data_report_agent, DataReportResult
from .debug import run_debug_agent
from .draft import run_draft_agent
from .improve import run_improve_agent
from .shared import AgentResult, PromptContext, format_time, trim_long_string

__all__ = [
    # Agent functions
    "run_data_report_agent",
    "run_draft_agent",
    "run_improve_agent",
    "run_debug_agent",
    # Shared types
    "AgentResult",
    "DataReportResult",
    "PromptContext",
    # Utilities
    "format_time",
    "trim_long_string",
]
