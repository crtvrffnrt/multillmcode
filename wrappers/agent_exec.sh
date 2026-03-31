#!/bin/bash
# wrappers/agent_exec.sh
# Audited execution wrapper for CLI agents.

AGENT_NAME="$1"
COMMAND="$2"
RUN_ID="$3"

# Find root dir based on script location (one level up from wrappers/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ROOT_DIR="$( dirname "$SCRIPT_DIR" )"
LOG_DIR="${ROOT_DIR}/logs"

# Ensure logs dir exists
mkdir -p "$LOG_DIR"
STDOUT_FILE="${LOG_DIR}/${RUN_ID}_${AGENT_NAME}.stdout"
STDERR_FILE="${LOG_DIR}/${RUN_ID}_${AGENT_NAME}.stderr"
LOG_FILE="${LOG_DIR}/${RUN_ID}_${AGENT_NAME}.audit.log"

START_TIME=$(date +%s%N)

echo "[$(date)] STARTING AGENT: $AGENT_NAME" > "$LOG_FILE"
echo "TARGET COMMAND: $COMMAND" >> "$LOG_FILE"
echo "---" >> "$LOG_FILE"

# Execute agent command and capture streams
# We use eval to allow the command to contain arguments and redirection if needed.
eval "$COMMAND" > >(tee "$STDOUT_FILE") 2> >(tee "$STDERR_FILE" >&2)
EXIT_CODE=$?

END_TIME=$(date +%s%N)
DURATION_MS=$(( (END_TIME - START_TIME) / 1000000 ))

echo "---" >> "$LOG_FILE"
echo "EXIT_CODE: $EXIT_CODE" >> "$LOG_FILE"
echo "DURATION_MS: $DURATION_MS" >> "$LOG_FILE"
echo "[$(date)] FINISHED" >> "$LOG_FILE"

# Output structured metadata for orchestrator consumption
# Wrapped in markers to allow extraction from conversational agent noise
echo "___FRAMEWORK_METADATA_START___"
cat <<EOF
{
  "agent": "$AGENT_NAME",
  "exit_code": $EXIT_CODE,
  "duration_ms": $DURATION_MS,
  "stdout_path": "$STDOUT_FILE",
  "stderr_path": "$STDERR_FILE",
  "audit_log": "$LOG_FILE"
}
EOF
echo "___FRAMEWORK_METADATA_END___"
