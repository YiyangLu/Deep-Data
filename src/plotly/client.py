"""
Clean client API for Plotly capture server.

Provides simple functions for agents to interact with the capture server
without dealing with HTTP details, serialization, or URL management.

Agent workflow:
    1. Check if server is running: check_server_status()
    2. Start server if needed: start_server()
    3. Upload plot: upload_plot(fig)
"""

import subprocess
import time
import requests
from typing import Any
import asyncio

from ..config import PLOTLY_API_CREATE, PLOTLY_API_HEALTH, SERVER_PORT
from ..utils.logging import create_logger
from ..utils.async_helpers import run_sync_in_thread

# Configure logger for debugging
logger = create_logger(__name__)


class PlotlyClientError(Exception):
    """Raised when client operations fail"""
    pass


async def upload_plot(fig, session_id: str, server_url: str | None = None) -> dict[str, Any]:
    """
    Upload a Plotly figure to the capture server.

    This is the main function agents should use. Simply pass a Plotly figure
    object and it will be serialized and uploaded to the server.

    Args:
        fig: Plotly figure object (e.g., from px.scatter() or go.Figure())
        session_id: Session identifier for session-scoped plot IDs
        server_url: Optional custom server URL (default: uses config)

    Returns:
        Server response dict with plot_id, session_id, and url

    Raises:
        PlotlyClientError: If upload fails

    Example:
        >>> import plotly.express as px
        >>> from src.plotly.client import upload_plot
        >>>
        >>> # Create a figure
        >>> df = px.data.iris()
        >>> fig = px.scatter(df, x='sepal_width', y='sepal_length')
        >>>
        >>> # Upload to server
        >>> result = upload_plot(fig, session_id='abc123')
        >>> print(result)
        {'plot_id': 1, 'session_id': 'abc123', 'url': '/plot/abc123/1'}
    """
    url = server_url or PLOTLY_API_CREATE
    logger.info(f"upload_plot() called for session {session_id}")
    logger.info(f"Target URL: {url}")

    def _do_upload():
        """Synchronous upload logic"""
        # Serialize figure to JSON
        logger.info("Serializing figure to JSON...")
        fig_json = fig.to_json()
        logger.info(f"Serialized JSON length: {len(fig_json)} characters")

        # Upload to server with session_id
        logger.info(f"Sending POST request to {url}...")
        response = requests.post(
            url,
            json={'fig_json': fig_json, 'session_id': session_id},
            timeout=5
        )
        logger.info(f"Response status: {response.status_code}")

        # Check for errors
        response.raise_for_status()

        result = response.json()
        logger.info(f"Upload successful: {result}")
        return result

    # Run blocking I/O in thread pool with unified error handling
    try:
        return await run_sync_in_thread(_do_upload)
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error: {e}")
        raise PlotlyClientError(
            f"Could not connect to server at {url}. "
            "Is the web server running? (python -m src.web.run_server)"
        ) from e
    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout error: {e}")
        raise PlotlyClientError(
            f"Server request timed out at {url}"
        ) from e
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error: {response.status_code}")
        raise PlotlyClientError(
            f"Server returned error {response.status_code}"
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error: {type(e).__name__}: {e}")
        raise PlotlyClientError(
            f"Failed to upload plot: {str(e)}"
        ) from e


async def check_server_status(server_url: str | None = None) -> bool:
    """
    Check if the capture server is running and responsive.

    Args:
        server_url: Optional custom server URL (default: uses config health endpoint)

    Returns:
        True if server is running, False otherwise

    Example:
        >>> from src.plotly.client import check_server_status
        >>> if await check_server_status():
        ...     print("Server is running")
        ... else:
        ...     print("Server is not available")
    """
    url = server_url or PLOTLY_API_HEALTH
    logger.debug(f"check_server_status() - checking {url}")

    def _do_check():
        """Synchronous check logic"""
        response = requests.get(url, timeout=2)
        is_running = response.status_code == 200
        logger.debug(f"Server status: {is_running} (status code: {response.status_code})")
        return is_running

    # Run blocking I/O in thread pool
    try:
        return await run_sync_in_thread(_do_check)
    except Exception as e:
        logger.debug(f"Server not available: {type(e).__name__}: {e}")
        return False


async def start_server(wait_for_ready: bool = True, timeout: float = 10.0) -> subprocess.Popen:
    """
    Start the Plotly capture server in the background.

    This function starts the server as a subprocess and optionally waits for it
    to be ready to accept connections.

    Args:
        wait_for_ready: If True, waits for server to be ready before returning
        timeout: Maximum seconds to wait for server to be ready (default: 10)

    Returns:
        subprocess.Popen object for the server process

    Raises:
        PlotlyClientError: If server fails to start or doesn't become ready in time

    Example:
        >>> from src.plotly.client import start_server, check_server_status, upload_plot
        >>> import plotly.express as px
        >>>
        >>> # Start server if not running
        >>> if not check_server_status():
        ...     start_server()
        >>>
        >>> # Upload plot
        >>> fig = px.scatter(px.data.iris(), x='sepal_width', y='sepal_length')
        >>> upload_plot(fig)
    """
    # Check if already running
    if await check_server_status():
        raise PlotlyClientError("Server is already running")

    try:
        # Start unified web server as subprocess
        import os
        env = os.environ.copy()
        env['SERVER_DEBUG'] = 'False'

        process = subprocess.Popen(
            ["python", "-m", "src.web.run_server"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=True  # Detach from parent
        )

        if wait_for_ready:
            # Wait for server to be ready
            start_time = time.time()
            while time.time() - start_time < timeout:
                if await check_server_status():
                    return process
                await asyncio.sleep(0.2)  # Use async sleep

            # Timeout - kill process and raise error
            process.terminate()
            raise PlotlyClientError(
                f"Server failed to become ready within {timeout} seconds"
            )

        return process

    except FileNotFoundError as e:
        raise PlotlyClientError(
            "Failed to start server. Make sure you're in the project root directory."
        ) from e

    except Exception as e:
        raise PlotlyClientError(f"Failed to start server: {str(e)}") from e
