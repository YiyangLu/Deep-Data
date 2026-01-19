"""
Entry point for running the web UI server or MLE CLI.

Usage:
    # Web UI mode (default)
    deepdata serve
    deepdata serve --host 0.0.0.0 --port 8000
    deepdata serve --cwd /path/to/project

    # MLE CLI mode (no browser needed)
    deepdata serve --mle --preset mlebench --cwd /path/to/project
    deepdata serve --mle --auto --cwd /path/to/project
"""

import argparse
import asyncio
import logging
import uvicorn
import os
import sys
from pathlib import Path
from datetime import datetime

from ..mle.config import MCTSConfig


def setup_web_logging(logs_dir: Path):
    """
    Setup logging for web server mode.

    All logs go to file, console is silenced except for startup message.
    """
    from ..utils.logging import enable_file_only_logging

    # Enable file-only mode for create_logger
    enable_file_only_logging()

    # Create log file with timestamp in server subdirectory
    server_logs_dir = logs_dir / "server"
    server_logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = server_logs_dir / f"{timestamp}.log"

    # Configure root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Remove any existing handlers from root
    root.handlers.clear()

    # File handler only (DEBUG level) - all logs to file
    file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    ))
    root.addHandler(file_handler)

    # Clear handlers from all existing loggers (they may have been created before this)
    for name in list(logging.Logger.manager.loggerDict.keys()):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True  # Let root handle it

    # Silence uvicorn access logs on console (they still go to file)
    logging.getLogger("uvicorn.access").propagate = True
    logging.getLogger("uvicorn.error").propagate = True

    return log_file


def setup_mle_logging(log_file: Path | None = None):
    """Setup logging for MLE CLI mode."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Console handler (INFO level)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter('[%(name)s] %(levelname)s: %(message)s'))
    root.addHandler(console)

    # File handler (DEBUG level)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, mode='w')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter('%(name)s %(levelname)s: %(message)s'))
        root.addHandler(file_handler)


def print_context(data: dict, title: str = "Context"):
    """Pretty print context data."""
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)
    print(f"Goal: {data.get('goal', '')}")
    desc = data.get('task_description', '')
    print(f"Task: {desc[:200]}..." if len(desc) > 200 else f"Task: {desc}")
    print(f"Data paths: {list(data.get('data_paths', {}).keys())}")
    print(f"Output paths: {list(data.get('output_paths', {}).keys())}")
    print(f"Gitignore: {data.get('gitignore', [])}")
    print(f"Sync: {data.get('sync', [])}")
    print('='*60)


def print_config(config):
    """Pretty print config."""
    print(f"\n{'='*60}")
    print(" Config")
    print('='*60)
    print(f"  time_limit: {config.time_limit}s ({config.time_limit/3600:.1f}h)")
    print(f"  max_steps: {config.max_steps}")
    print(f"  model: {config.model}")
    print(f"  parallel_workers: {config.parallel_workers}")
    print('='*60)


async def run_mle_cli(args):
    """Run MLE in CLI mode."""
    from ..mle.context import resolve_context, load_preset, list_presets, run_discovery_agent
    from ..mle.orchestrator import MCTSOrchestrator
    from ..mle.config import MCTSConfig

    workspace = Path(args.cwd or os.getcwd()).resolve()

    if not workspace.exists():
        print(f"Error: Workspace not found: {workspace}")
        return

    print(f"Workspace: {workspace}")

    # Setup logging
    log_file = workspace / ".memory" / "run.log"
    setup_mle_logging(log_file)
    print(f"Log file: {log_file}")

    # Build config
    config = MCTSConfig(
        time_limit=args.time_limit,
        parallel_workers=args.workers,
        model=args.model or "opus",
        max_steps=args.max_steps,
    )

    # Get context
    if args.preset:
        print(f"\nLoading preset: {args.preset}")
        try:
            preset_data = load_preset(args.preset)
        except FileNotFoundError:
            print(f"Error: Preset not found: {args.preset}")
            print(f"Available presets: {list_presets()}")
            return
        print_context(preset_data, f"Preset: {args.preset}")
        context = resolve_context(workspace, preset_data)
        print(f"\nTask description loaded: {len(context.task_description)} chars")

    elif args.auto:
        print("\nRunning discovery agent...")
        model = args.model or "opus"
        print(f"Model: {model}")

        discovery_result = await run_discovery_agent(workspace, model=model)

        data = {
            "goal": discovery_result.goal,
            "task_description": discovery_result.task_description,
            "data_paths": {k: str(v) for k, v in discovery_result.data_paths.items()},
            "output_paths": {k: str(v) for k, v in discovery_result.output_paths.items()},
            "output_requirements": discovery_result.output_requirements,
            "gitignore": discovery_result.gitignore,
            "sync": discovery_result.sync,
        }

        print_context(data, "Discovered Context")

        print("\nProceed with this context? [y/N] ", end="")
        response = input().strip().lower()
        if response != 'y':
            print("Aborted.")
            return

        context = resolve_context(workspace, data)

    else:
        print("Error: Must specify --preset or --auto in MLE mode")
        return

    # Run MCTS
    print_config(config)

    print(f"\n{'='*60}")
    print(" Starting MCTS")
    print('='*60)

    orchestrator = MCTSOrchestrator(workspace, context, config)

    try:
        results = await orchestrator.run()

        print(f"\n{'='*60}")
        print(" Results")
        print('='*60)
        print(f"Total steps: {results.get('total_steps', 0)}")
        print(f"Time elapsed: {results.get('time_elapsed', 0):.1f}s")
        print(f"Best metric: {results.get('best_metric')}")

        if results.get('best_plan'):
            print(f"\nBest plan:\n{results['best_plan'][:500]}...")

    except KeyboardInterrupt:
        print("\nInterrupted by user")


def main():
    """Run the web UI server or MLE CLI"""
    parser = argparse.ArgumentParser(
        description="Agent Web UI Server / MLE CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Web UI mode
  deepdata serve
  deepdata serve --cwd ./my-project

  # MLE CLI mode
  deepdata serve --mle --preset mlebench --cwd ./my-project
  deepdata serve --mle --auto --cwd ./my-project
  deepdata serve --mle --preset mlebench -t 3600 -n 3 -m opus
        """
    )

    # Common options
    parser.add_argument(
        "--cwd",
        default=None,
        help="Working directory (default: current directory)"
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default=None,
        help="Model to use (e.g., 'sonnet', 'opus', 'haiku')"
    )

    # MLE mode
    parser.add_argument(
        "--mle",
        action="store_true",
        help="Run MLE in CLI mode (no web server)"
    )
    parser.add_argument(
        "--preset", "-p",
        type=str,
        help="[MLE] Use a preset (e.g., 'mlebench')"
    )
    parser.add_argument(
        "--auto", "-a",
        action="store_true",
        help="[MLE] Auto-discover context (interactive)"
    )
    parser.add_argument(
        "--time-limit", "-t",
        type=int,
        default=21600,
        help="[MLE] Time limit in seconds (default: 21600 = 6h)"
    )
    parser.add_argument(
        "--workers", "-n",
        type=int,
        default=MCTSConfig.DEFAULT_WORKERS,
        help=f"[MLE] Number of parallel workers (default: {MCTSConfig.DEFAULT_WORKERS})"
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=100,
        help="[MLE] Maximum MCTS steps (default: 100)"
    )

    # Web server options
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="[Web] Host to bind (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="[Web] Port to bind (default: 8000)"
    )
    parser.add_argument(
        "--resume",
        type=str,
        metavar="SESSION_ID",
        help="[Web] Resume a specific session by session_id"
    )
    parser.add_argument(
        "--continue",
        dest="continue_last",
        action="store_true",
        help="[Web] Resume the last session for this directory"
    )

    args = parser.parse_args()

    # MLE CLI mode
    if args.mle:
        if not args.preset and not args.auto:
            parser.error("MLE mode requires --preset or --auto")
        if args.preset and args.auto:
            parser.error("Cannot use both --preset and --auto")
        asyncio.run(run_mle_cli(args))
        return

    # Web server mode
    if args.resume and args.continue_last:
        parser.error("Cannot use both --resume and --continue at the same time")

    # Use current directory if --cwd not specified
    cwd = args.cwd or os.getcwd()

    # Store arguments in environment variables so server.py can access them
    os.environ['AGENT_CWD'] = cwd
    if args.resume:
        os.environ['AGENT_RESUME_SESSION_ID'] = args.resume
    if args.continue_last:
        os.environ['AGENT_CONTINUE_LAST'] = '1'
    if args.model:
        os.environ['AGENT_MODEL'] = args.model

    # Setup logging BEFORE importing server - all logs to file, minimal console output
    from ..utils.paths import get_logs_root
    logs_dir = get_logs_root()
    log_file = setup_web_logging(logs_dir)

    # Print minimal startup info
    url = f"http://{'localhost' if args.host == '0.0.0.0' else args.host}:{args.port}"
    print(f"\n  Server: {url}")
    print(f"  Logs:   {log_file}\n", flush=True)

    # Import app AFTER setting up logging so loggers are configured correctly
    from .server import app

    # Configure uvicorn to not reconfigure logging (use our setup)
    # Setting log_config=None prevents uvicorn from overriding our logging
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="warning",  # Only show warnings/errors on console
        log_config=None  # Don't let uvicorn reconfigure logging
    )


if __name__ == "__main__":
    main()
