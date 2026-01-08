"""
Parallel runner for iPlotBench evaluation.

Runs jobs in parallel using a flat job pool with configurable workers.
Each job runs in its own process for isolation.

Each job: one (figure_id, config, model) combination
  - Single query: Recreation + QA with structured output

Usage:
    # Build index (required once)
    python -m eval.run_parallel --build-index --data-root /path/to/env

    # Run evaluation
    python -m eval.run_parallel --limit-per-type 10 --workers 8

    # Resume interrupted run
    python -m eval.run_parallel --resume --workers 32
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

# Setup logging before imports that use it
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _run_single_job(
    figure_id: str,
    config_name: str,
    model: str,
    data_root: str,
) -> dict:
    """
    Run a single job in isolated subprocess.

    This function runs in a separate process with its own state.
    Updates job status in the shared SQLite database.
    """
    import asyncio
    from pathlib import Path

    # Import inside function to ensure fresh state in subprocess
    from .index import open_index

    # Open index for status updates (uses default eval/index.db)
    index = open_index()

    try:
        # Mark as running
        index.set_job_running(figure_id, config_name, model)

        # Override data paths for this subprocess
        import eval.runner as runner
        data_root_path = Path(data_root)
        runner.DATA_ROOT = data_root_path
        runner.TEST_ROOT = data_root_path / "test"
        runner.QUERY_ROOT = data_root_path / "query"
        runner.OUTPUT_ROOT = data_root_path / "output"

        from .runner import run_env

        result = asyncio.run(run_env(figure_id, config_name, model=model, display=False))

        # Check validation - only mark completed if output is valid
        task1_valid = result.get("task1_valid", False)
        task2_valid = result.get("task2_valid", False)

        if task1_valid and task2_valid:
            index.set_job_completed(figure_id, config_name, model)
            index.close()
            return {"success": True, "figure_id": figure_id, "config": config_name, "model": model, "result": result}
        else:
            # Invalid output - mark as failed
            errors = []
            if not task1_valid:
                errors.append("Task1 invalid")
            if not task2_valid:
                errors.append("Task2 invalid")
            error_msg = "; ".join(errors)
            index.set_job_failed(figure_id, config_name, model, error_msg)
            index.close()
            return {"success": False, "figure_id": figure_id, "config": config_name, "model": model, "error": error_msg}

    except Exception as e:
        # Mark as failed
        error_msg = str(e)
        index.set_job_failed(figure_id, config_name, model, error_msg)
        index.close()

        return {"success": False, "figure_id": figure_id, "config": config_name, "model": model, "error": error_msg}


async def run_jobs(
    jobs: list[tuple[str, str]],
    model: str,
    data_root: Path,
    workers: int,
) -> list[dict]:
    """
    Run jobs in parallel using a flat job pool.

    Args:
        jobs: List of (figure_id, config) tuples
        model: Model to use (opus, sonnet, haiku)
        data_root: Path to data root (contains test/, query/, output/)
        workers: Number of parallel workers

    Returns:
        List of result dicts
    """
    if not jobs:
        logger.info("No jobs to run")
        return []

    logger.info(f"Running {len(jobs)} jobs with {workers} workers (model={model})")

    loop = asyncio.get_running_loop()

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [
            loop.run_in_executor(
                executor,
                _run_single_job,
                figure_id,
                config_name,
                model,
                str(data_root),
            )
            for figure_id, config_name in jobs
        ]
        results = await asyncio.gather(*futures, return_exceptions=True)

    # Log summary
    success = 0
    failed = 0
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"[subprocess] Exception: {result}")
            failed += 1
        elif result.get("success"):
            logger.debug(f"[{result['figure_id']}:{result['config']}] OK")
            success += 1
        else:
            logger.warning(f"[{result['figure_id']}:{result['config']}] FAILED: {result['error']}")
            failed += 1

    logger.info(f"Completed: {success} succeeded, {failed} failed")

    return results


def main():
    from .agent_config import CONFIGS
    from .index import build_index, open_index

    parser = argparse.ArgumentParser(
        description="Parallel runner for iPlotBench evaluation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Build index (required once)
  python -m eval.run_parallel --build-index

  # Run evaluation
  python -m eval.run_parallel --limit-per-type 10 --workers 8

  # Run with haiku (default)
  python -m eval.run_parallel --model haiku --limit-per-type 10

  # Run specific figure type
  python -m eval.run_parallel --figure-type dot_line --limit-per-type 10

  # Resume interrupted run
  python -m eval.run_parallel --resume --workers 32

  # Show stats
  python -m eval.run_parallel --stats
        """
    )

    # Actions
    parser.add_argument("--build-index", action="store_true",
                        help="Build index from test folder")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from pending jobs (skip completed)")
    parser.add_argument("--stats", action="store_true",
                        help="Show job statistics and exit")

    # Model selection
    parser.add_argument("--model", type=str, default="haiku",
                        choices=["opus", "sonnet", "haiku"],
                        help="Model to use (default: haiku)")

    # Filters
    parser.add_argument("--figure-type", type=str,
                        help="Run only this figure type (e.g., dot_line)")
    parser.add_argument("--limit-per-type", type=int,
                        help="Limit figures per type (e.g., 10 for test set)")
    parser.add_argument("--config", type=str,
                        help="Run only this config (e.g., vision)")

    # Execution
    parser.add_argument("--workers", type=int, default=4,
                        help="Number of parallel workers (default: 4)")
    parser.add_argument("--data-root", type=str, default="/data",
                        help="Data root path (default: /data for Docker)")

    # Debug
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose logging")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would run without executing")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    data_root = Path(args.data_root)
    model = args.model

    # --- Build index ---
    if args.build_index:
        test_folder = data_root / "test"
        query_folder = data_root / "query"
        logger.info(f"Building index from {test_folder}")
        index = build_index(test_folder, query_folder)  # Stores in eval/index.db
        stats = index.count_figures()
        total = sum(stats.values())
        q_count = index.count_questions()
        logger.info(f"Index built: {total} figures, {q_count} questions")
        logger.info(f"  Jobs per model: {total * len(CONFIGS)}")
        logger.info(f"Index saved to: {index.db_path}")
        index.close()
        return

    # --- Open existing index ---
    try:
        index = open_index()  # Opens eval/index.db
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    # --- Show stats ---
    if args.stats:
        fig_stats = index.count_figures()
        q_count = index.count_questions()

        print("\nFigure counts by type:")
        for ft, cnt in sorted(fig_stats.items()):
            print(f"  {ft}: {cnt}")
        print(f"  Total: {sum(fig_stats.values())}")
        print(f"  Questions: {q_count}")

        print("\nJob status by model:")
        job_stats_by_model = index.get_job_stats_by_model()
        for model_name, stats in sorted(job_stats_by_model.items()):
            print(f"  {model_name}:")
            for status, cnt in sorted(stats.items()):
                print(f"    {status}: {cnt}")

        index.close()
        return

    # --- Select figures ---
    if args.figure_type:
        figures = index.get_figures(
            figure_type=args.figure_type,
            limit=args.limit_per_type
        )
    else:
        figures = index.get_figures(limit=args.limit_per_type)

    if not figures:
        logger.error("No figures found. Check --figure-type or run --build-index")
        index.close()
        sys.exit(1)

    logger.info(f"Selected {len(figures)} figures")

    # --- Initialize jobs ---
    if args.config:
        if args.config not in CONFIGS:
            logger.error(f"Unknown config: {args.config}. Available: {list(CONFIGS.keys())}")
            index.close()
            sys.exit(1)
        configs = [args.config]
    else:
        configs = list(CONFIGS.keys())
    index.init_jobs(figures, configs, model)

    # --- Resume: reset stale running and failed jobs ---
    if args.resume:
        index.reset_running_jobs(model)
        failed_count = index.reset_failed_jobs(model)
        logger.info(f"Resume mode: reset stale running jobs for model={model}")
        if failed_count:
            logger.info(f"Resume mode: reset {failed_count} failed jobs for retry")

    # Get pending jobs (returns list of (figure_id, config))
    pending_jobs = index.get_pending_jobs(model)

    # Filter to only jobs for selected figures and configs
    figure_set = set(figures)
    config_set = set(configs)
    jobs = [(fig, cfg) for fig, cfg in pending_jobs if fig in figure_set and cfg in config_set]

    if not jobs:
        logger.info(f"No pending jobs to run for model={model}")
        job_stats = index.get_job_stats(model)
        logger.info(f"Job status for {model}: {job_stats}")
        index.close()
        return

    logger.info(f"Jobs to run: {len(jobs)} ({len(figures)} figures × {len(configs)} configs) [model={model}]")

    # --- Dry run ---
    if args.dry_run:
        print(f"\nWould run (model={model}):")
        for fig, cfg in jobs[:20]:
            print(f"  {fig} : {cfg}")
        if len(jobs) > 20:
            print(f"  ... and {len(jobs) - 20} more")
        index.close()
        return

    # --- Execute ---
    index.close()  # Close before forking

    results = asyncio.run(run_jobs(
        jobs,
        model=model,
        data_root=data_root,
        workers=args.workers,
    ))

    # --- Final stats ---
    try:
        index = open_index()
        job_stats = index.get_job_stats(model)
        logger.info(f"Final status for {model}: {job_stats}")
        index.close()
    except FileNotFoundError:
        logger.warning("Index not found for final stats (jobs completed successfully)")


if __name__ == "__main__":
    main()
