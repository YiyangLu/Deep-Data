"""
iPlotBench Agent Configs.

4 configs in 2x2 factorial design:
- Vision vs Vision-Lint: +get_plot_json for self-verification
- Static vs Interactive: +relayout, legendclick, selected, query_interactions

Base tools (all configs): Read, show_plot, get_plot_image
"""

from .base import BaseConfig
from .vision import Vision
from .vision_interactive import VisionInteractive
from .vision_introspect import VisionLint
from .vision_introspect_interactive import VisionLintInteractive

__all__ = [
    "BaseConfig",
    "Vision",
    "VisionInteractive",
    "VisionLint",
    "VisionLintInteractive",
    "CONFIGS",
]

CONFIGS = {
    "vision": Vision,
    "vision_interactive": VisionInteractive,
    "vision_lint": VisionLint,
    "vision_lint_interactive": VisionLintInteractive,
}
