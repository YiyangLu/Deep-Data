"""iPlotBench Evaluation.

Agent Configs (2x2 factorial):
- vision: Read + show_plot + get_plot_image
- vision_interactive: + relayout, legendclick, selected
- vision_lint: + get_plot_json (self-verification)
- vision_lint_interactive: All tools

Pipeline:
1. Task 1: Recreation query → parse figure JSON
2. Task 2: One query per question → parse 0/1 answer

All queries in same session (agent remembers context).
"""

from .agent_config import (
    BaseConfig,
    Vision,
    VisionInteractive,
    VisionLint,
    VisionLintInteractive,
    CONFIGS,
)
from .prompts import (
    TASK1_PROMPT,
    TASK2_PROMPT,
    get_task1_prompt,
    get_task2_prompt,
)
from .parser import parse_figure, parse_answer
from .validator import validate_task1, validate_task2
from .runner import run_env, run_task

__all__ = [
    # Configs
    "BaseConfig",
    "Vision",
    "VisionInteractive",
    "VisionLint",
    "VisionLintInteractive",
    "CONFIGS",
    # Prompts
    "TASK1_PROMPT",
    "TASK2_PROMPT",
    "get_task1_prompt",
    "get_task2_prompt",
    # Parser
    "parse_figure",
    "parse_answer",
    # Validator
    "validate_task1",
    "validate_task2",
    # Runner
    "run_env",
    "run_task",
]
