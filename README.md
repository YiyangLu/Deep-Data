<h1 align="center">
  🌠Deep Data
</h1>

<p align="center">
  <i>An agent framework built on Claude SDK for data analysis, visualization, and ML automation.</i>
</p>

https://github.com/user-attachments/assets/facf50b3-5d07-4003-9c63-3cb01925784f

## Features

1. **Agent** - Coding agent with Visualization State API (IVG) for interactive chart creation and verification

   <p align="center">
     <img src="assets/agent.png" alt="Deep Plot Banner" width="70%">
   </p>


2. **Deep Plot** - Autonomous data analysis agent with iterative exploration and explanation
   
   <p align="center">
     <img src="assets/deepplot.png" alt="Deep Plot Banner" width="70%">
   </p>

3. **MLE** - MCTS-based ML solution search with parallel workers (isolated in Git worktrees)

   <p align="center">
     <img src="assets/mle.png" alt="Deep Plot Banner" width="70%">
   </p>

## Requirements

- **Python**: 3.10+
- **Claude API**: Via [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)

## Installation

```bash
pip install claude-deepdata
```

With ML dependencies (for MLE feature):
```bash
pip install claude-deepdata[ml]
```

## Quick Start

```bash
# Start web server
deepdata

# With custom port
deepdata --port 8080

# Set working directory
deepdata --cwd /path/to/project
```

Visit `http://localhost:8000` for the Web UI.

## Development Setup

For contributors who want to modify the code:

```bash
# Clone the repository
git clone https://github.com/YiyangLu/Deep-Data.git
cd Deep-Data

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in editable mode with dev dependencies
pip install -e ".[dev,ml]"

# Build frontend (requires Node.js 18+)
cd deepdata/web/frontend
npm install
npm run build
cd ../../..

# Run the server
deepdata
```

## Paper

Our paper describing the IVG framework benchmark is coming soon on arXiv.
