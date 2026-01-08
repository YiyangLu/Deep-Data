#!/usr/bin/env bash
# Clean up evaluation artifacts and optionally stop running containers.
#
# Usage:
#   ./eval/clean_artifacts.sh          # Clean artifacts only
#   ./eval/clean_artifacts.sh --stop   # Stop containers first, then clean
#
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
data_root="${ENV_PATH:-${IPLOTBENCH_ENV:-}}"

# Stop running containers if --stop flag provided
if [[ "${1:-}" == "--stop" ]]; then
  echo "Stopping ccc-eval containers..."
  docker ps -q --filter ancestor=ccc-eval:latest | xargs -r docker stop
  echo "Containers stopped."
fi

shopt -s nullglob
paths=(
  "$repo_root/eval/index.db"
  "$repo_root/eval/index.db-wal"
  "$repo_root/eval/index.db-shm"
  "$repo_root/.pytest_cache"
  "$repo_root"/logs_*
  "$repo_root"/eval_task*.log
)

removed_any=false
for path in "${paths[@]}"; do
  if [ -e "$path" ]; then
    rm -rf "$path"
    echo "Removed: $path"
    removed_any=true
  fi
done

if [ "$removed_any" = false ]; then
  echo "No artifacts found."
fi

if [ -d "$repo_root/logs" ]; then
  echo "Removing eval logs under repo via Docker: $repo_root/logs"
  docker run --rm \
    -v "$repo_root":/agent \
    --entrypoint rm \
    ccc-eval:latest -rf /agent/logs
fi

if [ -n "$data_root" ] && [ -d "$data_root" ]; then
  echo "Removing eval outputs in Docker volume: $data_root/output"
  docker run --rm \
    -v "$data_root":/data \
    --entrypoint rm \
    ccc-eval:latest -rf /data/output
  echo "Removing eval logs in Docker volume: $data_root/logs"
  docker run --rm \
    -v "$data_root":/data \
    --entrypoint rm \
    ccc-eval:latest -rf /data/logs
else
  echo "Skip Docker cleanup; data root not found: $data_root"
fi
