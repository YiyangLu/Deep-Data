"""Vision: Read + show_plot + get_plot_image."""

from .base import BaseConfig


class Vision(BaseConfig):
    NAME = "vision"
    TOOLS = [
        "Read",
    ]
    # No HINT - baseline config uses tools naturally
