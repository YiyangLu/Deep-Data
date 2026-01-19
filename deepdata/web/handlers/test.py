"""
Test handlers for debugging reconnection feature.

These handlers verify WebSocket reconnection without polluting message history.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from .base import WebSocketContext, logger


@dataclass
class RunningHeartbeat:
    """Tracks a running heartbeat test for WebSocket reconnection."""
    session_id: str
    ctx: WebSocketContext  # Mutable - updated on reconnect
    reconnect_count: int = 0
    heartbeats_sent: int = 0


# Registry of running heartbeat tests by session_id
_running_heartbeats: dict[str, RunningHeartbeat] = {}


def get_running_heartbeat(session_id: str) -> Optional[RunningHeartbeat]:
    """Get running heartbeat test for a session (if any)."""
    return _running_heartbeats.get(session_id)


def update_heartbeat_websocket(session_id: str, ctx: WebSocketContext) -> bool:
    """
    Update the WebSocket context for a running heartbeat test.

    Returns True if there was a running test to update.
    """
    running = _running_heartbeats.get(session_id)
    if running:
        running.reconnect_count += 1
        logger.info(f"Re-attached WebSocket to heartbeat test: {session_id} (reconnect #{running.reconnect_count})")
        running.ctx = ctx
        return True
    return False


# Alias for backwards compatibility
update_test_stream_websocket = update_heartbeat_websocket


async def handle_test_heartbeat(data: dict, ctx: WebSocketContext) -> None:
    """
    Heartbeat test for verifying WebSocket reconnection.

    Sends periodic heartbeat messages for a duration. When you reconnect,
    the heartbeats continue to the new WebSocket, verifying reconnection works.

    Does NOT pollute session message history - only sends test_heartbeat messages.

    Expected data:
        session_id: The session to test (required - use current active session)
        duration: Total duration in seconds (default: 60)
        interval: Seconds between heartbeats (default: 3)

    Test procedure:
        1. Open browser DevTools console
        2. Note the current session_id from the URL or state
        3. In another terminal: curl to start the test (see below)
        4. Watch heartbeat messages in console
        5. Refresh the browser page
        6. Switch back to the same tab
        7. Heartbeats should continue with reconnect_count incremented

    Start test via curl:
        curl -X POST http://localhost:8000/api/test/heartbeat \\
             -H "Content-Type: application/json" \\
             -d '{"session_id": "YOUR_SESSION_ID", "duration": 60}'

    Check status:
        curl http://localhost:8000/api/test/running
    """
    session_id = data.get("session_id")
    if not session_id:
        await ctx.send("error", message="session_id is required for heartbeat test")
        return

    duration = data.get("duration", 60)
    interval = data.get("interval", 3)

    # Check if already running for this session
    if session_id in _running_heartbeats:
        await ctx.send("error", message=f"Heartbeat test already running for {session_id}")
        return

    # Create running state with mutable ctx reference
    running = RunningHeartbeat(session_id=session_id, ctx=ctx)

    # Register
    _running_heartbeats[session_id] = running
    logger.info(f"Starting heartbeat test: session_id={session_id}, duration={duration}s, interval={interval}s")

    try:
        await running.ctx.send("test_heartbeat",
            status="started",
            session_id=session_id,
            duration=duration,
            interval=interval
        )

        elapsed = 0
        while elapsed < duration:
            await asyncio.sleep(interval)
            elapsed += interval
            running.heartbeats_sent += 1

            # Use running.ctx which may have been updated on reconnect
            await running.ctx.send("test_heartbeat",
                status="heartbeat",
                session_id=session_id,
                heartbeat_num=running.heartbeats_sent,
                elapsed=elapsed,
                remaining=duration - elapsed,
                reconnect_count=running.reconnect_count
            )
            logger.debug(f"Heartbeat #{running.heartbeats_sent} for {session_id}, reconnects={running.reconnect_count}")

        await running.ctx.send("test_heartbeat",
            status="completed",
            session_id=session_id,
            total_heartbeats=running.heartbeats_sent,
            total_reconnects=running.reconnect_count
        )
        logger.info(f"Heartbeat test completed: {running.heartbeats_sent} heartbeats, {running.reconnect_count} reconnects")

    except Exception as e:
        logger.error(f"Heartbeat test error: {e}")
        await running.ctx.send("test_heartbeat", status="error", message=str(e))

    finally:
        if session_id in _running_heartbeats:
            del _running_heartbeats[session_id]
            logger.info(f"Unregistered heartbeat test: {session_id}")
