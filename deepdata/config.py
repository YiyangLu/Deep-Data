"""
Centralized configuration.

All paths are relative to project root with environment variable overrides.
This eliminates hardcoded values and makes the codebase portable.
"""

from pathlib import Path
import os

# ============================================================
# Path Configuration
# ============================================================

# Project root (where this repository lives)
PROJECT_ROOT = Path(__file__).parent.parent

# Logs directory (can override with CCC_LOGS_DIR environment variable)
LOGS_ROOT = Path(os.getenv('CCC_LOGS_DIR', PROJECT_ROOT / 'logs'))

# Core logs (for message_utils and debugging)
CORE_LOGS_DIR = LOGS_ROOT

# Ensure directories exist on import
CORE_LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# Unified Server Configuration (Web + Plotly)
# ============================================================

# Single server port (default 8000)
SERVER_PORT = int(os.getenv('SERVER_PORT', '8000'))
SERVER_HOST = os.getenv('SERVER_HOST', '127.0.0.1')
SERVER_DEBUG = os.getenv('SERVER_DEBUG', 'False').lower() == 'true'

# Plotly URL configuration
PLOTLY_BASE_PATH = "/plot"  # Path prefix for plotly routes
PLOTLY_BASE_URL = f"http://localhost:{SERVER_PORT}{PLOTLY_BASE_PATH}"
PLOTLY_API_CREATE = f"{PLOTLY_BASE_URL}/api/create"
PLOTLY_API_LOGS = f"{PLOTLY_BASE_URL}/api/logs"
PLOTLY_API_HEALTH = f"http://localhost:{SERVER_PORT}/health"  # Main server health check

# Helper functions for URL building
def get_plot_url(plot_id: int) -> str:
    """Get relative URL for a specific plot (same-origin)"""
    return f"{PLOTLY_BASE_PATH}/{plot_id}"

def get_plot_api_url(endpoint: str) -> str:
    """Get full URL for plotly API endpoint"""
    return f"http://localhost:{SERVER_PORT}{PLOTLY_BASE_PATH}/api/{endpoint}"

# ============================================================
# Plotly Test Configuration
# ============================================================

# Timing constants for Playwright tests (in seconds)
PLOTLY_PAGE_LOAD_WAIT = 2.0      # Wait for initial page load
PLOTLY_PLOT_RENDER_WAIT = 1.0    # Wait for plot to render
PLOTLY_ACTION_WAIT = 0.5         # Wait after user action
PLOTLY_ANIMATION_DURATION = 12.0 # Wait for animation to complete
PLOTLY_DEBOUNCE_WAIT = 1.5       # Wait for debounced events (zoom/pan)
