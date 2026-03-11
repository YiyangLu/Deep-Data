"""
Plotly visualization and interaction capture system.

Usage:
    from deepdata.plotly import show_plot

    plot_id, url = show_plot(plotly_code_string)

Available modules:
- tools: Agent-friendly functions (show_plot, query functions)
- client: Low-level server interaction API
- server: Flask server application

To avoid circular imports, we don't import submodules at package level.
Import directly from submodules:
    from deepdata.plotly.tools import show_plot
    from deepdata.plotly.client import upload_plot, start_server
"""

# Do NOT import submodules here to avoid circular imports
# Flask server imports plotly.io which would trigger our imports

__all__ = []
