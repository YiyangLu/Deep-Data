"""
Plotly event capture configuration.

Defines which events to capture and whether to take screenshots.
"""

# Capture Strategy - ALL Available Plotly Events
CAPTURE_CONFIG = {
    "init": {
        "enabled": True,
        "screenshot": True,
        "description": "Initial plot state when loaded",
        "category": "system"
    },
    "click": {
        "enabled": True,
        "screenshot": True,
        "description": "User clicked on data point",
        "category": "interaction"
    },
    "doubleclick": {
        "enabled": True,
        "screenshot": True,
        "description": "User double-clicked (typically resets view)",
        "category": "interaction"
    },
    "selected": {
        "enabled": True,
        "screenshot": True,
        "description": "User completed selection (box/lasso)",
        "category": "interaction"
    },
    "selecting": {
        "enabled": False,
        "screenshot": False,
        "description": "User is actively selecting (drag in progress)",
        "category": "interaction"
    },
    "deselect": {
        "enabled": True,
        "screenshot": True,
        "description": "User deselected points",
        "category": "interaction"
    },
    "hover": {
        "enabled": True,
        "screenshot": False,
        "description": "User hovered over data point",
        "category": "hover"
    },
    "unhover": {
        "enabled": False,
        "screenshot": False,
        "description": "User moved cursor away from data point",
        "category": "hover"
    },
    "legendclick": {
        "enabled": True,
        "screenshot": True,
        "description": "User clicked legend (show/hide trace)",
        "category": "legend"
    },
    "legenddoubleclick": {
        "enabled": True,
        "screenshot": True,
        "description": "User double-clicked legend (isolate trace)",
        "category": "legend"
    },
    "relayout": {
        "enabled": True,
        "screenshot": False,
        "description": "User zoomed/panned/resized axes",
        "category": "layout"
    },
    "restyle": {
        "enabled": True,
        "screenshot": True,
        "description": "Trace style/data modified (programmatic or UI)",
        "category": "style"
    },
    "afterplot": {
        "enabled": False,
        "screenshot": False,
        "description": "Chart finished rendering",
        "category": "system"
    },
    "redraw": {
        "enabled": False,
        "screenshot": False,
        "description": "Chart redrawn",
        "category": "system"
    },
    "autosize": {
        "enabled": False,
        "screenshot": False,
        "description": "Chart auto-resized",
        "category": "system"
    },
    "animated": {
        "enabled": True,
        "screenshot": True,
        "description": "Animation completed",
        "category": "system"
    },
}

# Screenshot settings
SCREENSHOT_CONFIG = {
    "format": "png",
    "width": 1200,
    "height": 700,
    "scale": 1
}
