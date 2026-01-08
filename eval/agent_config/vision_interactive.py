"""VisionInteractive: + relayout, legendclick, selected."""

from .base import BaseConfig


class VisionInteractive(BaseConfig):
    NAME = "vision_interactive"
    TOOLS = [
        "Read",
        "mcp__plotly__show_plot",
        "mcp__plotly__get_plot_image",
        "mcp__plotly__query_interactions",
        "mcp__plotly__relayout",
        "mcp__plotly__legendclick",
        "mcp__plotly__selected",
    ]
    # HINT = """For Task 1: Create your figure, interact with it (relayout, legendclick, selected) to check details, compare with input.png, and refine. For Task 2: Interact with it (relayout, legendclick, selected) to check details."""
