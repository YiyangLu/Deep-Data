"""VisionLintInteractive: All tools."""

from .base import BaseConfig


class VisionLintInteractive(BaseConfig):
    NAME = "vision_lint_interactive"
    TOOLS = [
        "Read",
        "mcp__plotly__show_plot",
        "mcp__plotly__get_plot_image",
        "mcp__plotly__get_plot_json",
        "mcp__plotly__query_interactions",
        "mcp__plotly__relayout",
        "mcp__plotly__legendclick",
        "mcp__plotly__selected",
    ]
    # HINT = """For Task 1: Create your figure, interact with it (relayout, legendclick, selected), get the plot JSON to check exact values, compare with input.png, and refine. For Task 2: Interact with it (relayout, legendclick, selected) to check details and get the plot JSON to check exact values."""
