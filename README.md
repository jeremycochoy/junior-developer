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
shinka_launch --config-path=configs task=snake_game evo_config.num_generations=12
```

## Project Structure

```
JuniorDeveloper/
├── configs/
│   ├── config.yaml                  # Main config (defines output structure)
│   ├── task/snake_game.yaml         # Shinka task configuration
│   ├── evolution/small_budget.yaml  # Evolution parameters
│   ├── database/island_small.yaml   # Island configuration
│   └── cluster/local.yaml           # Local job configuration
├── junior_dev/
│   ├── shinka/
│   │   ├── evaluate.py         # Evaluation logic (called by Shinka)
│   │   └── initial.json        # Initial program (JSON with EVOLVE-BLOCK)
│   ├── coding_agent.py         # Runs coding pipeline
│   ├── judge.py                # Pairwise LLM judge
│   ├── scoring.py              # BT-MM scoring engine with smart comparison selection
│   └── git_manager.py          # Git operations
├── .agents/                    # Coding agent scripts
│   └── run_pipeline.sh
└── results/
    └── snake_game/
        └── {timestamp}_default/
            ├── code/           # Git repo (isolated per run)
            │   └── index.html
            └── data/           # Evolution data
                ├── gen_0/
                ├── gen_1/
                ├── ...
                ├── best/
                ├── evolution_db.sqlite
                └── bt_scores.db
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
Shinka → evolves prompt → evaluate.py → coding agent → git diff → judge → BT-MM score
```

1. Shinka generates new prompt variations
2. `junior_dev/shinka/evaluate.py` runs the coding agent with each prompt
3. Git diffs are compared using pairwise LLM judging
4. BT-MM scores with smart comparison selection (3 random + 4 quartiles + 3 neighbors)

### Comparison Selection Strategy

The scoring engine uses a two-phase comparison strategy for each candidate:

**Phase 1: Exploration** (3 random + 4 quartiles)
- 3 random opponents for global connectivity
- 4 quartile representatives for ranking discovery

**Phase 2: Refinement** (3 neighbors)
- 3 nearest-rank opponents to break ties and refine local ranking

This approach combines speed (quartiles) with noise-resistance (random + neighbors).

### Configuration

**`configs/task/snake_game.yaml`** - Main configuration:
- `evo_config.task_sys_msg` - System prompt for evolution
- `evo_config.init_program_path` - Initial program path
- `distributed_job_config.eval_program_path` - Path to evaluate.py

## Results (12 Generations, 13 Nodes)

Each run creates an isolated experiment directory:

```
results/snake_game/{timestamp}_default/
├── code/                    # Git repo for this run
│   └── index.html          # Evolved snake game
└── data/                   # Evolution data
    ├── gen_0/main.json     # Initial prompt
    ├── gen_1/main.json     # First evolved prompt
    ├── ...
    ├── gen_N/
    │   ├── main.json       # Evolved prompt
    │   └── results/
    │       ├── metrics.json      # BT-MM score + branch name
    │       └── correct.json      # Success/error status
    ├── best/               # Best program snapshot
    ├── evolution_db.sqlite # Shinka database
    └── bt_scores.db        # BT-MM scores
```

Git branches in `code/`: `candidate_gen_N_main` (one per node). View any version:
```bash
cd results/snake_game/{timestamp}_default/code
git checkout candidate_best_main  # Or any other branch
open index.html
```

The completed evolution shows prompt improvement:

**Gen 0 (Initial):**
> "Create a simple snake game..."

**Gen 11 (Evolved):**
> "Create a visually appealing snake game with touch controls, gradients, responsive design..."

**Branch name for next node:** Each evaluation writes `public.branch_name` in `metrics.json`. Shinka stores this in the program's `public_metrics`, so the next node's LLM sees it and can set `parent_branch` to build on that node.

**Scores in Shinka DB:** After each evaluation, all existing nodes' BT-MM scores are synced back to Shinka's `evolution_db.sqlite` via the `_sync_bt_scores_to_shinka_db` function. This ensures parent selection uses current rankings.

**API cost:** With cheap models (e.g. gpt-4o-mini), typical cost is under ~$1 per run.

## Tests

```bash
source venv/bin/activate
pytest tests/
```

