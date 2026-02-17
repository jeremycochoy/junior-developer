#!/usr/bin/env bash
# Two-agent pipeline: Implement, then Test.

set -e

if [ -z "$1" ]; then
  echo "ERROR: You must provide the original task prompt as the first argument."
  echo "Usage: ./run_pipeline.sh \"your task prompt here\""
  exit 1
fi

TASK_PROMPT="$1"

# -------------------------------------------
# Where are the agent prompt files?
# Use AGENTS_DIR env var if set, otherwise .agents/ relative to CWD
# -------------------------------------------
if [ -z "$AGENTS_DIR" ]; then
  AGENTS_DIR=".agents"
fi

if [ ! -d "$AGENTS_DIR" ]; then
  echo "ERROR: Could not find .agents/ directory: $AGENTS_DIR (CWD: $(pwd))"
  exit 1
fi

# Ensure Cursor CLI (~/.local/bin) is on PATH (official installer puts "agent" there)
export PATH="${HOME}/.local/bin:${PATH}"

# -------------------------------------------
# Backend selection: claude | cursor
# Default: cursor
# Override with: AGENT_BACKEND=claude ./run_pipeline.sh "task ..."
# -------------------------------------------
BACKEND="${AGENT_BACKEND:-cursor}"

# Commands for each backend
# -f = full permissions (allows command execution)
CLAUDE_CMD="claude -p --system-prompt-file"

CURSOR_MODEL="${CURSOR_MODEL:-auto}"
CURSOR_CMD="${CURSOR_CMD:-agent -f -p --output-format text --model ${CURSOR_MODEL}}"

run_agent() {
  local role_file="$1"   # e.g. .agents/01_implement.md
  local task_prompt="$2"

  case "$BACKEND" in
    claude)
      $CLAUDE_CMD "$role_file" "$task_prompt"
      ;;

    cursor)
      local prompt_content
      prompt_content="$(cat "$role_file")"
      # Escape so any " in role file or task prompt don't break the outer quoted string
      local safe_content safe_task
      safe_content="${prompt_content//\\/\\\\}"
      safe_content="${safe_content//\"/\\\"}"
      safe_task="${task_prompt//\\/\\\\}"
      safe_task="${safe_task//\"/\\\"}"

      $CURSOR_CMD "$safe_content

Original Human Task Prompt:
$safe_task"
      ;;

    *)
      echo "ERROR: Unknown backend '$BACKEND'. Use AGENT_BACKEND=claude or AGENT_BACKEND=cursor."
      exit 1
      ;;
  esac
}

echo "===================================================="
echo "Running multi-agent pipeline"
echo "Backend: $BACKEND"
echo "Project directory: $(pwd)"
echo "Agents directory: $AGENTS_DIR"
echo "===================================================="
echo ""

echo "=== Agent 1: Implement =================================="
run_agent "$AGENTS_DIR/01_implement.md" "$TASK_PROMPT"

echo ""
echo "=== Agent 2: Test Runner ================================="
run_agent "$AGENTS_DIR/02_test_runner.md" "$TASK_PROMPT"

echo ""
echo "===================================================="
echo "Pipeline complete."
echo "===================================================="
