"""
FastAPI WebSocket server for streaming agent interactions.

Provides real-time bidirectional communication between frontend and agent.
"""

import json
import asyncio
import os
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import shutil

from .connection import WebConnection
from .handlers import HANDLERS, WebSocketContext
from ..utils.logging import create_logger
from ..utils.paths import get_logs_root
from ..core.workspace_manager import WorkspaceManager
from ..core.session import SessionStore

# Import plotly router
from ..plotly.server.router import router as plotly_router

logger = create_logger(__name__)

# Global workspace manager (workspace persists across all sessions)
workspace_manager = WorkspaceManager(get_logs_root() / "workspace.json")

# Global session store (for activity tracking)
session_store = SessionStore()


# Create FastAPI app
app = FastAPI(title="Agent Web UI", version="1.0.0")

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins in development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active connections
active_connections: Dict[str, tuple[WebSocket, WebConnection]] = {}


def has_active_browser_connections() -> bool:
    """Check if there are any active browser WebSocket connections."""
    return len(active_connections) > 0

# Get path to frontend build directory
FRONTEND_DIR = Path(__file__).parent / "frontend" / "dist"

# Mount static files if frontend is built
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

# Mount plotly router (BEFORE catchall route)
app.include_router(plotly_router)

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "connections": len(active_connections)}


@app.get("/api/sessions/list")
async def list_sessions():
    """
    List recent sessions for dropdown.

    Returns:
        JSON with list of sessions, each containing:
        - id: session_id
        - query: first query or "New session"
        - updated_at: ISO timestamp
        - message_count: number of messages
        - cwd: working directory
    """
    from ..core.session_registry import get_session_store
    import sqlite3

    session_store = get_session_store(get_logs_root())
    sessions = session_store.list_sessions(limit=20)

    result = []
    for s in sessions:
        # Get message count from conversation_blocks
        try:
            session_folder = session_store._get_session_folder(s.session_id)
            session_db = session_folder / "session.db"
            conn = sqlite3.connect(str(session_db))
            message_count = conn.execute("SELECT COUNT(*) FROM conversation_blocks").fetchone()[0]
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to get message count for {s.session_id}: {e}")
            message_count = 0

        result.append({
            'id': s.session_id,
            'query': s.latest_query or 'New session',
            'updated_at': s.updated_at,
            'message_count': message_count,
            'cwd': s.cwd
        })

    return {'sessions': result}


@app.get("/api/plots/{session_id}")
async def list_session_plots(session_id: str):
    """
    List all plots for a session (for recovery dropdown).

    Args:
        session_id: Session identifier

    Returns:
        JSON with list of plots (id, type, has_data)
    """
    from ..core.session_registry import get_session_store
    from fastapi.responses import JSONResponse

    session_store = get_session_store(get_logs_root())

    try:
        # Get plots metadata from SQLite
        plots = session_store.get_plots(session_id)

        # Check which plots have recoverable JSON files
        result = []
        for p in plots:
            has_data = session_store.get_plot_json(session_id, p['plot_id']) is not None
            result.append({
                'plot_id': p['plot_id'],
                'description': p.get('description'),
                'has_data': has_data
            })

        return {'plots': result}

    except ValueError as e:
        return JSONResponse(
            status_code=404,
            content={"error": str(e)}
        )
    except Exception as e:
        logger.error(f"Failed to list plots: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to list plots: {str(e)}"}
        )


# Deep Plot task storage (for background tasks)
deep_plot_tasks: Dict[str, dict] = {}


@app.post("/api/deep-plot")
async def start_deep_plot(
    files: str,
    timeout: int = 120,
    prompt: str = ""
):
    """
    Start a Deep Plot analysis task (HTTP API version).

    Note: This endpoint is for non-WebSocket usage. For WebSocket streaming,
    use the "deep_plot" message type instead.

    Args:
        files: Comma-separated filenames in the agent's working directory
        timeout: Analysis timeout in seconds (default: 120)
        prompt: Optional user prompt for additional instructions

    Returns:
        JSON with task_id to poll for status
    """
    import uuid
    from ..core.agent import Agent
    from ..deep_plot import DeepPlotAgent

    # Get agent CWD from environment
    agent_cwd = os.getenv('AGENT_CWD', os.getcwd())
    agent_model = os.getenv('AGENT_MODEL')

    # Parse comma-separated file list
    file_list = [f.strip() for f in files.split(',') if f.strip()]
    if not file_list:
        return JSONResponse(
            status_code=400,
            content={"error": "No files specified"}
        )

    # Verify all files exist
    missing_files = []
    for file in file_list:
        file_path = Path(agent_cwd) / file
        if not file_path.exists():
            missing_files.append(file)

    if missing_files:
        return JSONResponse(
            status_code=400,
            content={"error": f"File(s) not found: {', '.join(missing_files)}"}
        )

    # Generate task ID
    task_id = str(uuid.uuid4())

    # HTTP API not implemented - use WebSocket instead
    return JSONResponse(
        status_code=501,
        content={"error": "HTTP Deep Plot API not implemented. Use WebSocket instead."}
    )


@app.get("/api/deep-plot/{task_id}")
async def get_deep_plot_status(task_id: str):
    """
    Get status of a Deep Plot task.

    Args:
        task_id: Task ID from start_deep_plot

    Returns:
        JSON with status (running/completed/failed) and result if completed
    """
    if task_id not in deep_plot_tasks:
        return JSONResponse(
            status_code=404,
            content={"error": f"Task not found: {task_id}"}
        )

    task = deep_plot_tasks[task_id]
    return {
        "task_id": task_id,
        "status": task["status"],
        "result": task["result"]
    }


@app.post("/api/mle/discover")
async def mle_discover(request: Request):
    """
    Run discovery agent to fill MLE form context.

    Accepts optional partial_context from form to fill missing fields.
    """
    from ..mle import run_discovery_agent

    agent_cwd = os.getenv('AGENT_CWD', os.getcwd())
    workspace = Path(agent_cwd)

    # Get partial context and model from request body
    partial_context = None
    model = "opus"
    try:
        body = await request.json()
        partial_context = body.get("partial_context")
        model = body.get("model", "opus")
    except Exception:
        pass  # No body or invalid JSON, use defaults

    try:
        # Run discovery agent with partial context and selected model
        context = await run_discovery_agent(
            workspace, model=model, partial_context=partial_context
        )

        return {
            "context": {
                "goal": context.goal,
                "task_description": context.task_description,
                "data_paths": {k: str(v) for k, v in context.data_paths.items()},
                "output_paths": {k: str(v) for k, v in context.output_paths.items()},
                "output_requirements": context.output_requirements,
            },
            "git_worktree": {
                "gitignore": context.gitignore,
                "sync": context.sync,
            },
            # Default config values
            "config": {
                "time": 60,
                "workers": 2,
                "model": "haiku"
            }
        }

    except Exception as e:
        logger.error(f"MLE discovery failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Discovery failed: {str(e)}"}
        )


# MLE run state
_mle_runs: dict[str, dict] = {}
_mle_tasks: dict[str, asyncio.Task] = {}
_mle_stop_flags: dict[str, bool] = {}


async def _run_mle_pipeline(run_id: str, workspace: Path, context, config):
    """Background task to run the MLE pipeline."""
    from ..mle import MCTSOrchestrator
    import logging

    run = _mle_runs[run_id]

    # Setup file logging to .memory/run.log (captures all framework logging)
    memory_dir = workspace / ".memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    log_file = memory_dir / "run.log"

    file_handler = logging.FileHandler(log_file, mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter('%(name)s %(levelname)s: %(message)s'))

    # Add to root logger to capture all module logs
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)

    try:
        orchestrator = MCTSOrchestrator(workspace, context, config, run_id=run_id)
        run["orchestrator"] = orchestrator
        run["status"] = "running"
        session_store.update_activity(run_id, status="running")

        results = await orchestrator.run()

        run["status"] = "completed"
        session_store.update_activity(run_id, status="completed", result={
            "best_score": orchestrator.best_node.metric.value if orchestrator.best_node and orchestrator.best_node.metric else None,
            "steps": orchestrator.current_step,
        })
        run["results"] = results

    except asyncio.CancelledError:
        run["status"] = "stopped"
        session_store.update_activity(run_id, status="paused")  # Cancelled = paused (can be resumed)
        logger.info(f"MLE run {run_id}: Cancelled")
        raise

    except Exception as e:
        run["status"] = "error"
        run["error"] = str(e)
        session_store.update_activity(run_id, status="failed", result={"error": str(e)})
        logger.error(f"MLE run {run_id}: Error: {e}")

    finally:
        root_logger.removeHandler(file_handler)
        file_handler.close()


def _build_tree_from_orchestrator(orchestrator) -> dict:
    """Build tree structure from orchestrator for frontend."""
    if orchestrator is None:
        return {"nodes": [], "best_path": [], "in_progress": []}

    nodes = []
    best_path = []

    def traverse(node, parent_id=None):
        node_data = {
            "id": node.id,
            "parent_id": parent_id,
            "score": node.metric.value if node.metric and node.metric.value is not None else None,
            "status": "completed" if node.finish_time else ("running" if node.visits > 0 else "pending"),
            "name": node.stage,
            "is_buggy": node.is_buggy,
            "plan": node.plan[:100] if node.plan else None,
        }
        nodes.append(node_data)

        for child in node.children:
            traverse(child, node.id)

    # Start from virtual root
    traverse(orchestrator.virtual_root)

    # Build best path
    if orchestrator.best_node:
        current = orchestrator.best_node
        while current:
            best_path.insert(0, current.id)
            current = current.parent

    # Add in-progress nodes (not yet in tree)
    in_progress = []
    if hasattr(orchestrator, 'get_in_progress_nodes'):
        for ip_node in orchestrator.get_in_progress_nodes():
            # Add to nodes list with "running" status
            nodes.append({
                "id": ip_node["id"],
                "parent_id": ip_node["parent_id"],
                "score": None,
                "status": ip_node["status"],  # "expanding" | "executing" | "evaluating"
                "name": ip_node["stage"],
                "is_buggy": None,
                "plan": ip_node["plan"][:100] if ip_node["plan"] else None,
                "session_id": ip_node.get("session_id"),  # For real-time log streaming
            })
            in_progress.append(ip_node)

    return {"nodes": nodes, "best_path": best_path, "in_progress": in_progress}


@app.post("/api/mle/start")
async def mle_start(request: Request):
    """
    Start an MLE run with the given configuration.
    """
    import uuid
    from ..mle import MCTSConfig
    from ..mle.context import resolve_context

    data = await request.json()
    run_id = str(uuid.uuid4())

    agent_cwd = os.getenv('AGENT_CWD', os.getcwd())
    workspace = Path(agent_cwd)

    # Build Context from form data (resolve_context handles path resolution)
    ctx_data = {
        **data.get("context", {}),
        **data.get("git_worktree", {}),  # gitignore, sync
    }
    context = resolve_context(workspace, ctx_data)

    # Build MCTSConfig from form config
    cfg_data = data.get("config", {})

    # Map form values to MCTSConfig
    # Form sends: time_limit (seconds), parallel_workers, model, max_steps
    config = MCTSConfig(
        time_limit=cfg_data.get("time_limit", 21600),  # Already in seconds from form
        parallel_workers=cfg_data.get("parallel_workers", 3),
        model=cfg_data.get("model", "opus"),
        max_steps=cfg_data.get("max_steps", 100),
    )

    # Store run state
    _mle_runs[run_id] = {
        "config": data,
        "status": "starting",
        "orchestrator": None,
        "workspace": str(workspace),
        "start_time": None,
    }
    _mle_stop_flags[run_id] = False

    # Create activity record for this MLE run
    activity_name = f"MLE: {workspace.name}"
    session_store.create_activity(
        activity_id=run_id,
        activity_type="mle",
        name=activity_name,
        config={
            "workspace": str(workspace),
            "goal": context.goal if context else None,
            "workers": config.parallel_workers,
            "max_steps": config.max_steps,
        }
    )

    # Start background task
    import time
    _mle_runs[run_id]["start_time"] = time.time()
    task = asyncio.create_task(_run_mle_pipeline(run_id, workspace, context, config))
    _mle_tasks[run_id] = task

    logger.info(f"MLE run started: {run_id}")
    return {"run_id": run_id, "status": "started"}


@app.post("/api/mle/pause")
async def mle_pause(request: Request):
    """
    Pause an MLE run. Can be resumed later with additional time/steps.
    """
    data = await request.json()
    run_id = data.get("run_id")

    if run_id not in _mle_runs:
        return JSONResponse(status_code=404, content={"error": "Run not found"})

    run = _mle_runs[run_id]
    if run["status"] != "running":
        return JSONResponse(status_code=400, content={"error": f"Cannot pause: status is {run['status']}"})

    # Set stop flag
    _mle_stop_flags[run_id] = True

    # Cancel the background task with timeout to prevent blocking
    if run_id in _mle_tasks:
        task = _mle_tasks[run_id]
        if not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                logger.warning(f"Task cancellation timed out for {run_id}")

    _mle_runs[run_id]["status"] = "paused"
    session_store.update_activity(run_id, status="paused")
    logger.info(f"MLE run paused: {run_id}")

    # Return current progress for resume
    orchestrator = run.get("orchestrator")
    return {
        "status": "paused",
        "current_step": orchestrator.current_step if orchestrator else 0,
        "best_score": orchestrator.best_node.metric.value if orchestrator and orchestrator.best_node and orchestrator.best_node.metric else None,
    }


@app.post("/api/mle/resume")
async def mle_resume(request: Request):
    """
    Resume a paused MLE run with additional time/steps.
    """
    from ..mle import MCTSOrchestrator, MCTSConfig
    from ..mle.context import resolve_context
    import time

    data = await request.json()
    run_id = data.get("run_id")
    additional_time = data.get("additional_time", 3600)  # Default 1 hour
    additional_steps = data.get("additional_steps", 50)  # Default 50 steps

    if run_id not in _mle_runs:
        return JSONResponse(status_code=404, content={"error": "Run not found"})

    run = _mle_runs[run_id]
    if run["status"] != "paused":
        return JSONResponse(status_code=400, content={"error": f"Cannot resume: status is {run['status']}"})

    orchestrator = run.get("orchestrator")
    if not orchestrator:
        return JSONResponse(status_code=400, content={"error": "No orchestrator state to resume"})

    # Update config with new budgets
    orchestrator.config.time_limit = additional_time
    orchestrator.config.max_steps = orchestrator.current_step + additional_steps

    # Reset timing for new budget
    orchestrator.start_time = time.time()

    # Clear stop flag
    _mle_stop_flags[run_id] = False

    # Create new background task to continue
    async def _continue_mle(run_id: str, orch):
        import logging

        run = _mle_runs[run_id]
        workspace = Path(run["workspace"])

        # Setup file logging
        memory_dir = workspace / ".memory"
        log_file = memory_dir / "run.log"

        file_handler = logging.FileHandler(log_file, mode='a')  # Append mode
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter('%(name)s %(levelname)s: %(message)s'))

        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)

        try:
            run["status"] = "running"
            session_store.update_activity(run_id, status="running")
            # Use continue_search() instead of run() to skip initialization
            results = await orch.continue_search()
            run["status"] = "completed"
            session_store.update_activity(run_id, status="completed", result={
                "best_score": orch.best_node.metric.value if orch.best_node and orch.best_node.metric else None,
                "steps": orch.current_step,
            })
            run["results"] = results
        except asyncio.CancelledError:
            run["status"] = "paused"
            session_store.update_activity(run_id, status="paused")
            raise
        except Exception as e:
            run["status"] = "error"
            run["error"] = str(e)
            session_store.update_activity(run_id, status="failed", result={"error": str(e)})
            logger.error(f"MLE resume {run_id}: Error: {e}")
        finally:
            root_logger.removeHandler(file_handler)
            file_handler.close()

    run["start_time"] = time.time()
    task = asyncio.create_task(_continue_mle(run_id, orchestrator))
    _mle_tasks[run_id] = task

    logger.info(f"MLE run resumed: {run_id} (+{additional_time}s, +{additional_steps} steps)")
    return {
        "status": "resumed",
        "additional_time": additional_time,
        "additional_steps": additional_steps,
    }


@app.post("/api/mle/restore")
async def mle_restore(request: Request):
    """
    Restore an MLE run from journal after server restart.

    Use this when resuming a paused run that was interrupted by server shutdown.
    Reconstructs the MCTS tree from journal.db and makes it available for status polling.
    """
    from ..mle import MCTSOrchestrator, MCTSConfig
    from ..mle.storage import get_mle_store
    import time

    data = await request.json()
    run_id = data.get("run_id")

    if not run_id:
        return JSONResponse(status_code=400, content={"error": "run_id required"})

    # If already loaded in memory, just return success
    if run_id in _mle_runs:
        return {"status": "already_loaded", "run_id": run_id}

    # Get activity info from database
    activity = session_store.get_activity(run_id)
    if not activity:
        return JSONResponse(status_code=404, content={"error": "Activity not found"})

    # Check if journal exists in storage
    store = get_mle_store()
    journal_path = store.get_journal_path(run_id)
    if not journal_path.exists():
        return JSONResponse(status_code=404, content={"error": "Journal not found - cannot restore"})

    try:
        # Build config (use defaults, will be updated on resume)
        config = MCTSConfig(
            time_limit=0,  # Paused, no budget until resume
            parallel_workers=activity.get("config", {}).get("workers", 3),
            max_steps=activity.get("config", {}).get("max_steps", 100),
        )

        # Restore orchestrator from journal (loads context and workspace from storage)
        orchestrator = MCTSOrchestrator.from_journal(
            run_id=run_id,
            config=config,
        )

        workspace = orchestrator.workspace

        # Store in memory for status polling
        _mle_runs[run_id] = {
            "config": activity.get("config", {}),
            "status": activity.get("status", "paused"),
            "orchestrator": orchestrator,
            "workspace": str(workspace),
            "start_time": time.time(),
        }
        _mle_stop_flags[run_id] = True  # Paused until resume

        logger.info(f"MLE run restored from journal: {run_id} (steps: {orchestrator.current_step})")

        return {
            "status": "restored",
            "run_id": run_id,
            "current_step": orchestrator.current_step,
            "time_elapsed": orchestrator.get_total_elapsed(),
            "best_score": orchestrator.best_node.metric.value if orchestrator.best_node and orchestrator.best_node.metric else None,
        }

    except FileNotFoundError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except Exception as e:
        logger.error(f"Failed to restore MLE run: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/mle/stop")
async def mle_stop(request: Request):
    """
    Stop an MLE run (legacy endpoint, use /pause instead).
    """
    data = await request.json()
    run_id = data.get("run_id")

    if run_id not in _mle_runs:
        return JSONResponse(status_code=404, content={"error": "Run not found"})

    # Set stop flag
    _mle_stop_flags[run_id] = True

    # Cancel the background task with timeout to prevent blocking
    if run_id in _mle_tasks:
        task = _mle_tasks[run_id]
        if not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                logger.warning(f"Task cancellation timed out for {run_id}")

    _mle_runs[run_id]["status"] = "stopped"
    logger.info(f"MLE run stopped: {run_id}")
    return {"status": "stopped"}


@app.get("/api/mle/status/{run_id}")
async def mle_status(run_id: str):
    """
    Get status of an MLE run including tree structure.
    """
    import time

    if run_id not in _mle_runs:
        return JSONResponse(status_code=404, content={"error": "Run not found"})

    run = _mle_runs[run_id]
    orchestrator = run.get("orchestrator")

    # Build tree from orchestrator
    tree = _build_tree_from_orchestrator(orchestrator)

    # Get status info
    status_info = {
        "status": run["status"],
        "workers": orchestrator.config.parallel_workers if orchestrator else 0,
        "total_workers": orchestrator.config.parallel_workers if orchestrator else 0,
        "best_score": orchestrator.best_node.metric.value if orchestrator and orchestrator.best_node and orchestrator.best_node.metric else None,
        "steps": orchestrator.current_step if orchestrator else 0,
        "max_steps": orchestrator.config.max_steps if orchestrator else 100,
        "elapsed": int(orchestrator.get_total_elapsed()) if orchestrator else 0,
        "tree": tree,
    }

    return status_info


@app.get("/api/mle/node/{node_id}/logs")
async def mle_node_logs(node_id: str, run_id: str = None):
    """
    Get logs for a specific MCTS node.

    For running nodes, fetches real-time conversation history from the agent session.
    For completed nodes, returns the final summary (plan, command, output, metric).
    """
    if run_id and run_id in _mle_runs:
        run = _mle_runs[run_id]
        orchestrator = run.get("orchestrator")

        if orchestrator:
            # First, check in-progress nodes for real-time logs
            if hasattr(orchestrator, 'get_in_progress_nodes'):
                for ip_node in orchestrator.get_in_progress_nodes():
                    if ip_node["id"] == node_id and ip_node.get("session_id"):
                        # Fetch real-time conversation from session
                        session_id = ip_node["session_id"]
                        logs = []

                        # Add status info
                        logs.append({
                            "timestamp": "",
                            "level": "info",
                            "message": f"Status: {ip_node['status']} ({ip_node['stage']})"
                        })

                        # Fetch conversation history from session
                        try:
                            conversation = session_store.get_conversation(session_id)
                            for block in conversation:
                                if block.get("type") == "text":
                                    role = block.get("role", "assistant")
                                    text = block.get("text", "")[:500]
                                    logs.append({
                                        "timestamp": block.get("timestamp", ""),
                                        "level": "info" if role == "assistant" else "debug",
                                        "message": f"[{role}] {text}"
                                    })
                                elif block.get("type") == "tool_use":
                                    tool_name = block.get("name", "unknown")
                                    logs.append({
                                        "timestamp": block.get("timestamp", ""),
                                        "level": "debug",
                                        "message": f"[tool] {tool_name}"
                                    })
                        except Exception as e:
                            logs.append({
                                "timestamp": "",
                                "level": "warning",
                                "message": f"Could not fetch session logs: {e}"
                            })

                        return {"node_id": node_id, "logs": logs, "is_running": True}

            # Find completed node in tree
            def find_node(node, target_id):
                if node.id == target_id:
                    return node
                for child in node.children:
                    found = find_node(child, target_id)
                    if found:
                        return found
                return None

            node = find_node(orchestrator.virtual_root, node_id)
            if node:
                logs = []
                if node.plan:
                    logs.append({"timestamp": node.finish_time or "", "level": "info", "message": f"Plan: {node.plan}"})
                if node.run_command:
                    logs.append({"timestamp": node.finish_time or "", "level": "info", "message": f"Command: {node.run_command}"})
                if node.output:
                    logs.append({"timestamp": node.finish_time or "", "level": "info", "message": f"Output: {node.output[:500]}"})
                if node.error_summary:
                    logs.append({"timestamp": node.finish_time or "", "level": "error", "message": f"Error: {node.error_summary[:500]}"})
                if node.metric and node.metric.value is not None:
                    logs.append({"timestamp": node.finish_time or "", "level": "success", "message": f"Metric: {node.metric.value}"})

                return {"node_id": node_id, "logs": logs, "is_running": False}

    return {"node_id": node_id, "logs": [], "is_running": False}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a file to the agent's working directory.

    The file is saved to the CWD specified when starting the server.
    Returns the filename that can be referenced by the agent.
    """
    # Get agent CWD from environment
    agent_cwd = os.getenv('AGENT_CWD', os.getcwd())
    cwd_path = Path(agent_cwd)

    # Ensure CWD exists
    if not cwd_path.exists():
        cwd_path.mkdir(parents=True, exist_ok=True)

    # Sanitize filename (keep original name but remove path components)
    filename = Path(file.filename).name if file.filename else "uploaded_file"

    # If file already exists, add a number suffix
    dest_path = cwd_path / filename
    if dest_path.exists():
        stem = dest_path.stem
        suffix = dest_path.suffix
        counter = 1
        while dest_path.exists():
            dest_path = cwd_path / f"{stem}_{counter}{suffix}"
            counter += 1
        filename = dest_path.name

    try:
        # Save the file
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info(f"Uploaded file: {filename} to {dest_path}")

        return {"success": True, "filename": filename, "path": str(dest_path)}

    except Exception as e:
        logger.error(f"Failed to upload file: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for agent communication.

    Protocol:
        Client -> Server:
            {"type": "message", "content": string}
            {"type": "ping"}

        Server -> Client:
            {"type": "connected", "session_id": string}
            {"type": "text_start", "message_id": string}
            {"type": "text_chunk", "message_id": string, "content": string}
            {"type": "text_end", "message_id": string}
            {"type": "tool_start", "message_id": string, "tool_name": string, "tool_input": dict}
            {"type": "tool_result", "message_id": string, "tool_name": string, "result": string}
            {"type": "plot_show", "plot_id": int, "url": string}
            {"type": "plot_hide"}
            {"type": "complete", "message_id": string, "stats": dict}
            {"type": "error", "message_id": string, "error": string}
            {"type": "pong"}
    """
    await websocket.accept()

    # Create connection ID
    connection_id = str(id(websocket))

    # Get agent configuration from environment (set by run_server.py)
    agent_cwd = os.getenv('AGENT_CWD')
    resume_session_id = os.getenv('AGENT_RESUME_SESSION_ID')
    continue_last = os.getenv('AGENT_CONTINUE_LAST') == '1'
    agent_model = os.getenv('AGENT_MODEL')  # Per-agent model (e.g., "sonnet", "opus")

    # Create WebConnection (replaces AgentManager)
    connection = WebConnection(
        websocket=websocket,
        cwd=Path(agent_cwd) if agent_cwd else Path.cwd(),
        resume_session_id=resume_session_id,
        continue_last=continue_last,
        model=agent_model
    )

    # Create WebSocketContext for handlers
    ctx = WebSocketContext(
        websocket=websocket,
        connection_id=connection_id,
        connection=connection,
        agent_cwd=agent_cwd,
        agent_model=agent_model,
        workspace_manager=workspace_manager,
        active_connections=active_connections
    )

    # Store connection
    active_connections[connection_id] = (websocket, connection)

    try:
        # DO NOT start agent on connection (lazy creation)

        # Send connection confirmation (no session_id)
        await ctx.send("connected")

        # Load workspace and verify agent tabs against database
        from ..core.session_registry import get_session_store
        session_store = get_session_store(get_logs_root())

        workspace = workspace_manager.load_workspace()

        # Verify agent tabs exist in database (remove ghost tabs)
        verified_tabs = []
        for tab in workspace.get('agent_tabs', []):
            try:
                session_store.get_session_info(tab['session_id'])
                verified_tabs.append(tab)
            except:
                # Ghost tab - skip it
                logger.info(f"Removing ghost tab: {tab['session_id']}")

        workspace['agent_tabs'] = verified_tabs

        # Adjust active_agent_tab index if needed
        active_idx = workspace.get('active_agent_tab')
        if active_idx is not None and active_idx >= len(verified_tabs):
            workspace['active_agent_tab'] = max(0, len(verified_tabs) - 1) if verified_tabs else None

        # Save cleaned workspace
        workspace_manager.save_workspace(workspace)

        # Send verified workspace to frontend
        await ctx.send("workspace_loaded", workspace=workspace)

        # Message loop - dispatch to handlers
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            handler = HANDLERS.get(msg_type)
            if handler:
                await handler(data, ctx)
            else:
                logger.warning(f"Unknown message type: {msg_type}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket {connection_id} disconnected")

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "error": str(e)
            })
        except:
            pass

    finally:
        # Cleanup - use ctx.connection in case it was replaced by handlers
        await ctx.connection.close()
        if connection_id in active_connections:
            del active_connections[connection_id]


# =============================================================================
# Activities API
# =============================================================================

@app.get("/api/activities")
async def list_activities(
    activity_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50
):
    """List activities with optional filtering"""
    activities = session_store.list_activities(
        activity_type=activity_type,
        status=status,
        limit=limit
    )
    return {"activities": activities}


@app.get("/api/activities/active/{activity_type}")
async def get_active_activity(activity_type: str):
    """Get the currently active (running/paused) activity of a given type"""
    activity = session_store.get_active_activity(activity_type)
    return {"activity": activity}


@app.get("/api/activities/{activity_id}")
async def get_activity(activity_id: str):
    """Get a specific activity by ID"""
    activity = session_store.get_activity(activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return {"activity": activity}


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    """Serve frontend for all other routes (SPA support)"""
    if FRONTEND_DIR.exists():
        # Serve index.html for all routes (React Router)
        return FileResponse(FRONTEND_DIR / "index.html")
    else:
        return {"message": "Frontend not built. Run 'npm run build' in src/web/frontend/"}


@app.on_event("startup")
async def startup_event():
    """Mark stale running activities as paused on server startup.

    If the server was killed while MLE runs were active, those runs
    are now orphaned. Mark them as paused so they can be resumed.
    """
    stale_activities = session_store.list_activities(
        activity_type="mle",
        status="running"
    )

    for activity in stale_activities:
        activity_id = activity['id']
        logger.info(f"Marking stale MLE activity as paused: {activity_id}")
        session_store.update_activity(activity_id, status="paused")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown - save MLE progress and close connections."""
    logger.info("Server shutting down - saving MLE progress...")

    # Save and pause all running MLE tasks
    for run_id, run in list(_mle_runs.items()):
        try:
            # Cancel the background task if running
            if run_id in _mle_tasks:
                task = _mle_tasks[run_id]
                if not task.done():
                    task.cancel()
                    try:
                        await asyncio.wait_for(task, timeout=2.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass

            # Save orchestrator state
            orchestrator = run.get("orchestrator")
            if orchestrator:
                orchestrator.save_progress()
                # Close journal connection cleanly
                try:
                    orchestrator.journal.close()
                except:
                    pass
                logger.info(f"Saved MLE progress for {run_id} (step {orchestrator.current_step})")

            # Mark as paused in database if was running
            if run["status"] == "running":
                session_store.update_activity(run_id, status="paused")

        except Exception as e:
            logger.error(f"Error saving MLE run {run_id}: {e}")

    # Clear MLE state
    _mle_runs.clear()
    _mle_tasks.clear()
    _mle_stop_flags.clear()

    # Close all WebSocket connections
    for connection_id, (ws, conn) in list(active_connections.items()):
        try:
            await conn.close()
        except:
            pass
    active_connections.clear()

    logger.info("Shutdown complete")


# Export OpenAPI schema (after all routes defined)
_docs_dir = Path("docs")
_docs_dir.mkdir(exist_ok=True)
(_docs_dir / "api.json").write_text(json.dumps(app.openapi(), indent=2))


