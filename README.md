# Junior Developer

Self-evolving coding agent: it evolves prompts with genetic algorithms and ranks them using pairwise LLM judging and Bradley–Terry (BT-MM) scoring.

---

## What it does

1. **Starts** from seed prompts (e.g. “Refactor visualization code”).
2. **Evolves** them via genetic algorithms (LLM-guided mutation).
3. **Evaluates** by running a coding agent per candidate and having an LLM judge compare two branches.
4. **Ranks** candidates with BT-MM in a SQLite DB. Judge “A vs B” decisions and short explanations are stored there.

**Flow:** ShinkaEvolve → `evaluate.py` (run agent, make branches, get diffs) → `judge.py` (LLM picks winner) → `scoring.py` (BT-MM in SQLite).

---

## Install and run (local)

Use a virtual environment. **scipy is required** for BT-MM scoring.

```bash
git clone https://github.com/yourusername/junior-developer.git
cd junior-developer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

**Quick check:** `pytest tests/`

**Run evaluation (needs API keys in `.env`):**

```bash
python examples/test_evaluate.py --num-comparisons 0
```

---

## Configuration and API keys

- **Config file:** `configs/agent_config.yaml` — agent type, timeouts, paths, judge model, task spec.
- **Environment:** Put secrets in a `.env` file in the project root. Scripts load it automatically.

**OpenAI (for the judge):**  
`OPENAI_API_KEY=sk-...` in `.env`.

**Cursor (for the pipeline agent):**  
The pipeline uses the Cursor CLI (`agent`). It needs a Cursor API key.

- **Where to get it:** [Cursor Dashboard](https://cursor.com/dashboard) → Integrations or Background Agents → create/copy a User API key.
- **Where to put it:** In `.env` in the project root: `CURSOR_API_KEY=your_key_here`.  
  Or run `agent login` in a terminal, or `export CURSOR_API_KEY=...` before running.

Do not commit `.env`. Keep it in `.gitignore`.

---

## Project layout

| Path | Role |
|------|------|
| `junior_dev/scoring.py` | BT-MM engine (scipy), SQLite |
| `junior_dev/judge.py` | Pairwise LLM judge |
| `junior_dev/shinka/evaluate.py` | End-to-end eval (agent + git + judge + scoring) |
| `junior_dev/coding_agent.py` | Runs `.agents/run_pipeline.sh` |
| `junior_dev/git_manager.py` | Git branches, diffs, commits |
| `configs/agent_config.yaml` | Main config |
| `.agents/run_pipeline.sh` | Coding agent script (Cursor/Claude) |
| `examples/` | `test_evaluate.py`, prompt modules |

---

## Deployment with Shinka

You use a **modified Shinka** (e.g. `../ShinkaEvolve`) with its own environment and LLM config. Your **private repo** holds your evolution runs.

**Layout:**

- **Shinka** — installed elsewhere (e.g. `../ShinkaEvolve`), own env and LLM config.
- **Private repo** — has `config/` and eval assets (e.g. `eval/`). You run Shinka with this repo as the config dir.

**What to have in the Shinka environment:**

- Install the **JuniorDeveloper** package so Shinka can import it:  
  `pip install -e /path/to/JuniorDeveloper` (or add it to `PYTHONPATH`).  
  That brings in `junior_dev` (scoring, judge, git_manager, coding_agent, evaluate).
- In your repo: **`evaluate.py`** (and any YAML you use) — e.g. copy `junior_dev/shinka/evaluate.py` into your repo’s eval flow, or point Shinka at it. Shinka will call your evaluator with `program_path` and `results_dir`; the evaluator uses `junior_dev`.

**How you run it:**

From your private repo (the dir that has `config/` and eval assets):

```bash
shinka_launch --config ./
```

(or your Shinka entrypoint, e.g. `python -m shinka.launch_hydra` with the right config path). The important part is that the **config directory** is this repo so Shinka uses your config and your eval entrypoint that uses `evaluate.py` / `junior_dev`.

**Coding agent path:**  
The agent is `.agents/run_pipeline.sh`. Its location is set in config (`coding_agent.agents_dir` in your YAML). You can keep `.agents/` in the private repo and point the config there.

| Piece | Where / how |
|-------|-------------|
| Shinka | Your install (e.g. `../ShinkaEvolve`), own env and LLM config |
| Config dir | Your repo; run `shinka_launch --config ./` from there |
| `evaluate.py` | In that repo (e.g. under `eval/`), used by Shinka as the eval entrypoint |
| `junior_dev` | Installed in the Shinka env so `evaluate.py` can import it |
| Agent script | Path in config (`agents_dir`), often `.agents/` in the repo |

---

## BT-MM and scipy

Scores maximize the likelihood of the observed “A beats B” outcomes. The engine uses **scipy** (`scipy.optimize`, L-BFGS-B). **scipy must be installed:** `pip install scipy` or `pip install -r requirements.txt`. If scipy is missing, a hand-rolled MM fallback is used so the package still runs (e.g. in a minimal venv).

---

## More detail

- **Cursor API key (full steps):** `docs/CURSOR_AUTH.md`
- **Deployment (copy-paste layout):** `docs/DEPLOYMENT.md`
- **Config options:** `docs/CONFIG_USAGE.md`
