#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ROOT_DIR="$SCRIPT_DIR"

if [ "$#" -lt 1 ]; then
  echo "Usage: ./prompt.sh \"your prompt here\"" >&2
  exit 1
fi

exec python3 -u "$ROOT_DIR/core/orchestrator.py" "$@"
