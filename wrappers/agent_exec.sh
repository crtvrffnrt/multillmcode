#!/bin/bash
# wrappers/agent_exec.sh
# Audited execution wrapper for CLI agents.

AGENT_NAME="$1"
COMMAND="$2"
RUN_ID="$3"
RUN_DIR="${4:-}"

# Find root dir based on script location (one level up from wrappers/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ROOT_DIR="$( dirname "$SCRIPT_DIR" )"
LOG_DIR="${ROOT_DIR}/logs"
SKILLS_DIR="${MULTILLM_SKILLS_DIR:-$HOME/.agents/skills}"

# Ensure logs dir exists
mkdir -p "$LOG_DIR"
if [ -z "$RUN_DIR" ]; then
    RUN_DIR="${LOG_DIR}/runs/${RUN_ID}"
fi
mkdir -p "$RUN_DIR"
STDOUT_FILE="${RUN_DIR}/${AGENT_NAME}.stdout"
STDERR_FILE="${RUN_DIR}/${AGENT_NAME}.stderr"
LOG_FILE="${RUN_DIR}/${AGENT_NAME}.audit.log"
EVENT_LOG="${RUN_DIR}/events.log"
export MULTILLM_SKILLS_DIR="$SKILLS_DIR"
export MULTILLM_RUN_DIR="$RUN_DIR"

START_TIME=$(date +%s%N)

echo "[$(date)] STARTING AGENT: $AGENT_NAME" > "$LOG_FILE"
echo "TARGET COMMAND: $COMMAND" >> "$LOG_FILE"
echo "SKILLS_DIR: $SKILLS_DIR" >> "$LOG_FILE"
echo "---" >> "$LOG_FILE"
echo "$(date -Is) | START | agent=${AGENT_NAME} | run_id=${RUN_ID}" >> "$EVENT_LOG"

# Execute agent command and capture streams
# We use bash -lc to allow the command to contain quoted arguments cleanly.
bash -lc "$COMMAND" > >(tee "$STDOUT_FILE") 2> "$STDERR_FILE"
EXIT_CODE=$?

END_TIME=$(date +%s%N)
DURATION_MS=$(( (END_TIME - START_TIME) / 1000000 ))

if grep -qiE 'quota|rate limit|resource_exhausted|exhausted your capacity|out of tokens|token limit|context length|context window|backenderror|internal error|service unavailable|temporarily unavailable|too many requests|command not found|permission denied|429|500' "$STDERR_FILE"; then
    RETRYABLE=true
    FAILURE_REASON="$(grep -iE 'quota|rate limit|resource_exhausted|exhausted your capacity|out of tokens|token limit|context length|context window|backenderror|internal error|service unavailable|temporarily unavailable|too many requests|command not found|permission denied|429|500' "$STDERR_FILE" | head -n 1 | tr -d '\r' | cut -c1-240)"
else
    RETRYABLE=false
    FAILURE_REASON=""
fi

echo "---" >> "$LOG_FILE"
echo "EXIT_CODE: $EXIT_CODE" >> "$LOG_FILE"
echo "DURATION_MS: $DURATION_MS" >> "$LOG_FILE"
echo "RETRYABLE: $RETRYABLE" >> "$LOG_FILE"
if [ -n "$FAILURE_REASON" ]; then
    echo "FAILURE_REASON: $FAILURE_REASON" >> "$LOG_FILE"
fi
echo "[$(date)] FINISHED" >> "$LOG_FILE"
echo "$(date -Is) | END | agent=${AGENT_NAME} | exit_code=${EXIT_CODE} | duration_ms=${DURATION_MS} | retryable=${RETRYABLE} | reason=${FAILURE_REASON}" >> "$EVENT_LOG"

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
  "audit_log": "$LOG_FILE",
  "event_log": "$EVENT_LOG",
  "retryable": $RETRYABLE,
  "failure_reason": $(printf '%s' "$FAILURE_REASON" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')
}
EOF
echo "___FRAMEWORK_METADATA_END___"
