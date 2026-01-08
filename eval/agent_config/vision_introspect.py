"""VisionLint: + get_plot_json (self-verification)."""

from .base import BaseConfig


class VisionLint(BaseConfig):
    NAME = "vision_lint"
    TOOLS = [
        "Read",
        "mcp__plotly__show_plot",
        "mcp__plotly__get_plot_image",
        "mcp__plotly__get_plot_json",
    ]
    # HINT = """For Task 1: Create your figure, get the plot JSON to check exact values, compare with input.png, and refine. For Task 2: Get the plot JSON to check exact values."""
