# ccc Agent for iPlotBench Evaluation
#
# Build:
#   docker build -t ccc-eval:latest -f eval/Dockerfile .
#
# Recommended: Use eval/run.sh wrapper script
#   ./eval/run.sh --build-index                    # Build index (required once)
#   ./eval/run.sh --stats                          # Show job statistics
#   ./eval/run.sh --limit-per-type 10 --workers 8  # Run evaluation
#   ./eval/run.sh --resume --workers 8             # Resume interrupted run
#
# Or run Docker directly:
#   docker run --rm \
#     -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
#     -v /path/to/iPlotBench/env/test:/data/test:ro \
#     -v /path/to/iPlotBench/env/query:/data/query:ro \
#     -v /path/to/iPlotBench/env/output:/data/output \
#     -v /path/to/ccc:/agent \
#     -v ~/.claude:/root/.claude \
#     --entrypoint python \
#     ccc-eval:latest -m eval.run_parallel --build-index
#
# Local commands (no Docker needed):
#   python -m eval.run_parallel --stats            # Check stats from host
#
# NOTE: test/ and query/ are mounted read-only (:ro) to prevent agent writes
#       agent/ is writable for logs and index.db

FROM iplotbench:latest

# Install system dependencies
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Common data libraries
RUN pip install --no-cache-dir numpy

# Project mounted at /agent
WORKDIR /agent

# Entry point
ENTRYPOINT ["python", "-m", "eval.runner"]
