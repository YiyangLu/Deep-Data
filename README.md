<h1 align="center">
  🌠Deep Data
</h1>

<p align="center">
  <i>An agent framework built on Claude SDK for data analysis, visualization, and ML automation.</i>
</p>

## Features

1. **Agent** - Coding agent with Visualization State API (IVG) for interactive chart creation and verification
2. **Deep Plot** - Autonomous data analysis agent with iterative exploration and explanation
3. **MLE** - MCTS-based ML solution search with parallel workers

## Requirements

- **Python**: 3.10+
- **Node.js**: 18.x+ (for frontend development only)
- **Claude API**: Via [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)

## Setup

```bash
# Create conda environment
conda create -n agent python=3.10
conda activate agent

# Install dependencies
pip install -r requirements.txt
pip install -r requirements_ml.txt  # Optional, for ML tasks
```

## Quick Start

```bash
# Start web server
python -m src.web.run_server

# Or use the helper script
./bin/run_server
```

Visit `http://localhost:8000` for the Web UI.

## Paper

Our paper describing the IVG framework benchmark is coming soon on arXiv.