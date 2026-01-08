#!/bin/bash
# Run iPlotBench evaluation in Docker with read-only test/query mounts.
#
# Usage:
#   ./eval/run.sh [options]
#
# Examples:
#   ./eval/run.sh --build-index                    # Build index (required once)
#   ./eval/run.sh --stats                          # Show job statistics
#   ./eval/run.sh --limit-per-type 10 --workers 8  # Run 10 figures per type
#   ./eval/run.sh --resume --workers 8             # Resume interrupted run
#   ./eval/run.sh --model sonnet --workers 4       # Run with sonnet model
#   ./eval/run.sh --config vision --workers 4      # Run only vision config
#   ./eval/run.sh --dry-run                        # Show what would run
#
# Options:
#   --build-index       Build index from test folder (required once)
#   --stats             Show job statistics
#   --limit-per-type N  Limit figures per type (e.g., 10 for test set)
#   --workers N         Number of parallel workers (default: 4)
#   --model MODEL       Model to use: haiku, sonnet, opus (default: haiku)
#   --config CONFIG     Run only this config: vision, vision_interactive,
#                       vision_lint, vision_lint_interactive
#   --resume            Resume from pending jobs (reset stale running jobs)
#   --dry-run           Show what would run without executing
#
# Environment:
#   ENV_PATH            Path to iPlotBench/env (required)
#   AGENT_PATH          Path to this repo (default: script's parent directory)
#
# Index stored at: $AGENT_PATH/eval/index.db (shared between Docker and host)

set -e

# Default paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_PATH="${AGENT_PATH:-$(dirname "$SCRIPT_DIR")}"

if [ -z "${ENV_PATH:-}" ]; then
    echo "Error: ENV_PATH not set. Set it to your iPlotBench/env directory."
    echo "  export ENV_PATH=/path/to/iPlotBench/env"
    exit 1
fi

# Check paths exist
if [ ! -d "$ENV_PATH/test" ]; then
    echo "Error: $ENV_PATH/test not found"
    exit 1
fi

if [ ! -d "$AGENT_PATH" ]; then
    echo "Error: $AGENT_PATH not found"
    exit 1
fi

echo "Running iPlotBench evaluation..."
echo "  ENV_PATH: $ENV_PATH"
echo "  AGENT_PATH: $AGENT_PATH"
echo "  Args: $@"
echo ""

# Run with read-only mounts for test/ and query/
# Agent cwd is set to test directory in runner.py, so agent won't write there
docker run --rm \
    -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
    -v "$ENV_PATH/test:/data/test:ro" \
    -v "$ENV_PATH/query:/data/query:ro" \
    -v "$ENV_PATH/output:/data/output" \
    -v "$AGENT_PATH:/agent" \
    -v "$HOME/.claude:/root/.claude" \
    --entrypoint python \
    ccc-eval:latest -m eval.run_parallel "$@"
