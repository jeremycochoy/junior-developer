#!/usr/bin/env bash
# Multi-Agent Automated Pipeline

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
CLAUDE_CMD="claude -p --system-prompt-file"

CURSOR_CMD="${CURSOR_CMD:-agent -p --output-format text}"

run_agent() {
  local role_file="$1"   # e.g. .agents/01_implement.md
  local task_prompt="$2"

  case "$BACKEND" in
    claude)
      # Claude Code supports --system-prompt-file
      $CLAUDE_CMD "$role_file" "$task_prompt"
      ;;

    cursor)
      # Cursor CLI: no --system-prompt-file, so inline the role prompt
      local prompt_content
      prompt_content="$(cat "$role_file")"

      # We pass the role instructions + original task together as a single prompt
      $CURSOR_CMD "$prompt_content

Original Human Task Prompt:
$task_prompt"
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
echo "=== Agent 2: Correctness Review =========================="
run_agent "$AGENTS_DIR/02_correctness_review.md" "$TASK_PROMPT"

echo ""
echo "=== Agent 3: Simplification =============================="
run_agent "$AGENTS_DIR/03_simplify.md" "$TASK_PROMPT"

echo ""
echo "=== Agent 4: Final Correctness Check ====================="
run_agent "$AGENTS_DIR/04_final_check.md" "$TASK_PROMPT"

echo ""
echo "===================================================="
echo "Pipeline complete. Review the git diff before committing."
echo "===================================================="
