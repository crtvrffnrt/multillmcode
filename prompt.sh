#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ROOT_DIR="$SCRIPT_DIR"

export MULTILLM_ALLOW_ALL_TARGETS="${MULTILLM_ALLOW_ALL_TARGETS:-1}"
export MULTILLM_UNATTENDED="${MULTILLM_UNATTENDED:-1}"
export CI="${CI:-1}"
export NONINTERACTIVE="${NONINTERACTIVE:-1}"

if [ "$#" -lt 1 ]; then
  echo "Usage: ./prompt.sh \"your prompt here\"" >&2
  exit 1
fi

exec python3 -u "$ROOT_DIR/core/orchestrator.py" "$@"
