# Configuration guide

The evaluation system reads defaults from **`configs/agent_config.yaml`**. You can override them with function arguments or the `--config` flag.

---

## Where config is loaded

- **Default file:** `configs/agent_config.yaml` (relative to the project root).
- **Custom file:** Pass `--config /path/to/your.yaml` when running `evaluate.py` or test scripts.

Arguments and CLI flags override values from the config file.

---

## What each section does

### `coding_agent`

Controls how the coding agent runs (the pipeline script).

| Key | Meaning |
|-----|--------|
| `agent_type` | Only **`pipeline`** is supported. It runs `.agents/run_pipeline.sh`. |
| `timeout` | Max seconds per agent run (e.g. `600`). |
| `working_dir` | Directory where the agent edits code. `null` = use the target codebase path. |
| `agents_dir` | Folder that contains `run_pipeline.sh`. Default `".agents"` (under project root). |
| `pipeline_backend` | Backend used by the pipeline: `"cursor"` or `"claude"`. |

### `git`

Controls branch names and prefixes.

| Key | Meaning |
|-----|--------|
| `default_branch` | Base branch (e.g. `master`, `main`). |
| `branch_prefix` | Prefix for candidate branches (e.g. `candidate_` → `candidate_test_001`). |
| `auto_cleanup` | Reserved; not used yet. |

### `evaluation`

Controls the judge and how many comparisons run.

| Key | Meaning |
|-----|--------|
| `num_comparisons` | How many other candidates to compare against per evaluation. |
| `llm_judge_model` | Model used for pairwise judging (e.g. `gpt-4o`, `gpt-4o-mini`). |
| `llm_judge_temperature` | Judge LLM temperature. **0.0** = more deterministic (recommended). |
| `task_spec` | **Evolution objective** — the high-level task the judge uses (e.g. “Implement a double auction engine in C++…”). |

### `scoring`

BT-MM database and algorithm (scipy is used when available).

| Key | Meaning |
|-----|--------|
| `db_path` | Path to the SQLite file (e.g. `./bt_scores.db`). |
| `convergence_tol` | Convergence tolerance for BT-MM. |
| `max_iterations` | Max iterations for BT-MM. |

---

## How override order works

1. **Function or CLI argument** (e.g. `task_spec="..."` or `--task_spec "..."`) wins.
2. If not set, the value from **the config file** is used.
3. If not in config, a **built-in default** is used.

---

## Examples

**Use config defaults:**

```python
from junior_dev.shinka.evaluate import evaluate_coding_agent_prompt

evaluate_coding_agent_prompt(
    program_path="initial.py",
    results_dir="results",
    target_codebase="./my_codebase",
)
```

**Override a few values:**

```python
evaluate_coding_agent_prompt(
    program_path="initial.py",
    results_dir="results",
    target_codebase="./my_codebase",
    task_spec="Implement a double auction engine in C++...",
    agent_timeout=900,
)
```

**From the command line:**

```bash
# Default config
python -m junior_dev.shinka.evaluate --program_path initial.py --results_dir results

# Override task and timeout
python -m junior_dev.shinka.evaluate --program_path initial.py --results_dir results \
  --task_spec "Implement a double auction engine in C++..." \
  --agent_timeout 900

# Use a different config file
python -m junior_dev.shinka.evaluate --program_path initial.py --results_dir results \
  --config configs/my_config.yaml
```

**In the test script:**

```bash
python examples/test_evaluate.py --num-comparisons 0
python examples/test_evaluate.py --llm-judge-model gpt-4o-mini --agent-timeout 600
```

---

## Example config file (current layout)

```yaml
coding_agent:
  agent_type: "pipeline"
  timeout: 600
  working_dir: null
  agents_dir: ".agents"
  pipeline_backend: "cursor"

git:
  default_branch: "master"
  auto_cleanup: false
  branch_prefix: "candidate_"

evaluation:
  num_comparisons: 3
  llm_judge_model: "gpt-4o"
  llm_judge_temperature: 0.0
  task_spec: "Refactor and improve code quality"

scoring:
  db_path: "./bt_scores.db"
  convergence_tol: 1e-6
  max_iterations: 100
```

Put your evolution objective (the task the judge should use) in **`evaluation.task_spec`** so the judge knows what the coding agent was asked to achieve.
