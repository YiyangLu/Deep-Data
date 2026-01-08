# iPlotBench Evaluation

Agent-based evaluation for iPlotBench.

## Setup

```bash
# Build Docker image
docker build -t ccc-eval:latest -f eval/Dockerfile .
```

## Quick Start

```bash
# 1. Build index (required once)
./eval/run.sh --build-index

# 2. Run evaluation
./eval/run.sh --limit-per-type 10 --workers 8

# 3. Check progress
./eval/run.sh --stats
```

## Commands

| Command | Description |
|---------|-------------|
| `./eval/run.sh --build-index` | Build index from test folder (required once) |
| `./eval/run.sh --stats` | Show job statistics |
| `./eval/run.sh --limit-per-type N` | Run N figures per type |
| `./eval/run.sh --workers N` | Set parallel workers (default: 4) |
| `./eval/run.sh --model MODEL` | Use model: haiku, sonnet, opus (default: haiku) |
| `./eval/run.sh --config CONFIG` | Run single config only |
| `./eval/run.sh --resume` | Resume interrupted run |
| `./eval/run.sh --dry-run` | Show what would run |

## Agent Configs (2x2 Factorial)

| Config | Tools | Description |
|--------|-------|-------------|
| `vision` | Read, show_plot, get_plot_image | Base config |
| `vision_interactive` | + relayout, legendclick, selected | Interactive tools |
| `vision_lint` | + get_plot_json | Self-verification |
| `vision_lint_interactive` | All tools | Full capability |

## Task

Single combined query per figure:
- **Task 1 (Recreation)**: Recreate plot using Plotly
- **Task 2 (QA)**: Answer yes/no questions about the chart

Output format (structured):
```json
{
  "figure": { /* Plotly JSON */ },
  "answers": [0, 1, 0, ...]  // 0=No, 1=Yes
}
```

**Job counts** (per model): 1,000 figures × 4 configs = 4,000 jobs

## Output Structure

```
output/{model}/{figure_id}/
  output_{config}_task1.json      # Plotly figure JSON
  output_{config}_task2_q0.json   # QA answer for question 0
  output_{config}_task2_q1.json   # QA answer for question 1
  ...
```

## Files

| File | Description |
|------|-------------|
| `run.sh` | Docker wrapper script |
| `run_parallel.py` | Parallel job runner |
| `runner.py` | Single figure evaluation |
| `index.py` | SQLite job tracking |
| `prompts.py` | Prompt templates and schema |
| `agent_config/` | Agent tool configurations |
| `index.db` | Job tracking database |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENV_PATH` | (required) | Path to iPlotBench/env |
| `AGENT_PATH` | (auto-detected) | Path to this repo |
| `ANTHROPIC_API_KEY` | (required) | Anthropic API key |

## Local Commands (No Docker)

```bash
# Check stats
python -m eval.run_parallel --stats

# Query index directly
sqlite3 eval/index.db "SELECT status, COUNT(*) FROM jobs GROUP BY status"
```

## Stop and Clean

```bash
# Stop running containers
docker ps -q --filter ancestor=ccc-eval:latest | xargs -r docker stop

# Clean artifacts (index, logs, outputs)
./eval/clean_artifacts.sh

# Stop and clean in one command
./eval/clean_artifacts.sh --stop
```

What gets cleaned:
- `eval/index.db` (job tracking)
- `eval/index.db-wal`, `eval/index.db-shm` (SQLite WAL files)
- `logs/` (agent session logs)
- `output/` in iPlotBench/env (evaluation outputs)

## Security

Agent is restricted to read-only operations:
- `disallowed_tools`: Write, Edit, Bash, Task, Glob, Grep, WebFetch, etc.
- Docker mounts: test/ and query/ are read-only (`:ro`)
- Only allowed: Read + MCP plotly tools
