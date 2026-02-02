# JuniorDeveloper

Evolve coding agent prompts using genetic algorithms + LLM judging.

## What It Does

1. **Evolves prompts** - Shinka mutates prompts using LLM-guided evolution
2. **Runs coding agent** - Each prompt is given to a coding agent (Cursor/Claude)
3. **Judges results** - LLM compares code changes from different prompts
4. **Ranks with BT-MM** - Bradley-Terry scoring in SQLite

## Quick Start

### 1. Install

```bash
git clone <repo>
cd JuniorDeveloper
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### 2. Set API Keys

Create `.env` file:
```
OPENAI_API_KEY=sk-...
CURSOR_API_KEY=...
```

### 3. Run Snake Game Evolution

```bash
# Install in Shinka environment
cd /path/to/ShinkaEvolve
source venv/bin/activate
pip install -e /path/to/JuniorDeveloper

# Run evolution (12 generations, 13 nodes)
cd /path/to/JuniorDeveloper
python run_snake_evolution.py
```

## Project Structure

```
JuniorDeveloper/
├── run_snake_evolution.py      # Main script to run evolution
├── eval_snake.py               # Evaluation script for Shinka
├── configs/
│   ├── agent_config.yaml       # Agent, judge, scoring settings
│   └── task/snake_game.yaml    # Shinka task configuration
├── junior_dev/
│   ├── shinka/
│   │   ├── evaluate.py         # Evaluation logic
│   │   └── initial_snake.json  # Initial program (JSON with EVOLVE-BLOCK)
│   ├── coding_agent.py         # Runs coding pipeline
│   ├── judge.py                # Pairwise LLM judge
│   ├── scoring.py              # BT-MM scoring engine
│   └── git_manager.py          # Git operations
├── .agents/                    # Coding agent scripts
│   └── run_pipeline.sh
└── results/
    └── snake_evolution/        # Evolution results (13 nodes)
```

## How It Works

### Program Format

Programs are **JSON** files with JSON5-style comment blocks (`// EVOLVE-BLOCK-START` / `// EVOLVE-BLOCK-END`). The LLM must always output `parent_branch` and `prompt`; missing `parent_branch` is treated as malformed (invalid node).

```json
// EVOLVE-BLOCK-START
{
  "parent_branch": "master",
  "prompt": "Create a snake game with canvas, arrow keys, score..."
}
// EVOLVE-BLOCK-END
```

Shinka mutates the JSON between the markers. The evaluator writes `branch_name` to `metrics.json` (under `public`) so the next node can use it as `parent_branch`.

### Evolution Flow

```
Shinka → evolves prompt → eval_snake.py → coding agent → git diff → judge → BT-MM score
```

1. Shinka generates new prompt variations
2. `eval_snake.py` runs the coding agent with each prompt
3. Git diffs are compared using pairwise LLM judging
4. BT-MM scores determine parent selection

### Configuration

**`configs/agent_config.yaml`** - Local settings:
- `coding_agent.timeout` - Agent execution timeout
- `evaluation.llm_judge_model` - Judge model (gpt-4o)
- `evaluation.num_comparisons` - Comparisons per candidate

**`configs/task/snake_game.yaml`** - Shinka task:
- `evo_config.task_sys_msg` - System prompt for evolution
- `evo_config.init_program_path` - Initial program path

## Results (12 Generations, 13 Nodes)

The completed evolution shows prompt improvement:

**Gen 0 (Initial):**
> "Create a simple snake game..."

**Gen 11 (Evolved):**
> "Create a visually appealing snake game with touch controls, gradients, responsive design..."

Results in `results/snake_evolution/`:
- `gen_*/main.json` - Evolved programs
- `evolution_db.sqlite` - Shinka database
- `bt_scores.db` - BT-MM scores

**Branch name for next node:** Each evaluation writes `public.branch_name` in `metrics.json`. Shinka stores this in the program's `public_metrics`, so the next node's LLM sees it and can set `parent_branch` to build on that node.

**Scores in Shinka DB:** The current node's score is written to Shinka via `metrics.json`. Full recompute of all nodes' BT-MM scores after each new branch would require a Shinka-side hook to read updated scores and update all programs; currently only the new node's score is set.

**API cost:** With cheap models (e.g. gpt-4o-mini), typical cost is under ~$1 per run; can be included in final payment if needed.

## Tests

```bash
source venv/bin/activate
pytest tests/
```

