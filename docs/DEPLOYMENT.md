# Deployment with Shinka

This doc describes how to run the Junior Developer evaluation pipeline with your Shinka setup and your own repo.

---

## Big picture

- **Shinka** (your modified version, e.g. `../ShinkaEvolve`) runs the evolution: it has its own environment and LLM config.
- **Your private repo** holds your evolution runs: config, eval entrypoint, and (optionally) the agent script.
- **Junior Developer** is the `junior_dev` package. Shinka calls your evaluator; the evaluator uses `junior_dev` (scoring, judge, git, coding agent). So you install Junior Developer into the **same environment** Shinka uses.

---

## Layout

| Piece | Where it lives / what it does |
|-------|-------------------------------|
| **Shinka** | Installed elsewhere (e.g. `../ShinkaEvolve`). Own env and LLM config. |
| **Your repo** | Has `config/` (evolution/task YAML) and eval assets. You run `shinka_launch --config ./` from here. |
| **evaluate.py** | Your eval entrypoint. Lives in your repo (e.g. under `eval/`). Shinka calls it with `program_path` and `results_dir`. |
| **junior_dev** | The Junior Developer package. **Installed in the Shinka env** so your evaluator can `import` it (scoring, judge, git_manager, coding_agent). |
| **Agent script** | `.agents/run_pipeline.sh`. Path is set in config (`agents_dir`). Can live in your repo or next to the JuniorDeveloper install. |

---

## What to do

**1. Install Junior Developer in the Shinka environment**

From the Shinka env (the one you use to run `shinka_launch`):

```bash
pip install -e /path/to/JuniorDeveloper
```

Or add the JuniorDeveloper directory to `PYTHONPATH`. The goal is that `from junior_dev.shinka.evaluate import ...` and `from junior_dev.scoring import ...` work in that env.

**2. Point Shinka at your evaluator**

Your Shinka config (or job config) must run your evaluator for each program. That usually means calling something like:

```bash
python /path/to/your/evaluate.py --program_path <program> --results_dir <dir>
```

where `evaluate.py` is the script that uses `junior_dev` (e.g. it imports and calls `evaluate_coding_agent_prompt` or wraps it). So you either:

- Copy `junior_dev/shinka/evaluate.py` into your repo and run it, or  
- Have a small wrapper in your repo that imports `junior_dev.shinka.evaluate` and calls it with the right arguments.

**3. Config and YAML**

Use your own YAML (e.g. from `configs/agent_config.yaml` or a copy) so that:

- **Evolution objective** is set (e.g. `evaluation.task_spec`: “Implement a double auction engine in C++…”). The judge uses this.
- **Agent path** is correct: `coding_agent.agents_dir` points to the folder that contains `run_pipeline.sh` (e.g. `.agents` in your repo).

**4. Run Shinka**

From your private repo (the dir with `config/` and eval assets):

```bash
shinka_launch --config ./
```

(or your Shinka entrypoint, e.g. `python -m shinka.launch_hydra` with the right config path). Shinka will use your config and call your evaluator; the evaluator uses `junior_dev` and writes `metrics.json` (and optionally `correct.json`) so Shinka can read scores.

---

## Summary

- **Shinka** = evolution loop (your install, your env).
- **Your repo** = config + eval entrypoint; you run `shinka_launch --config ./` from there.
- **junior_dev** = installed in that same env; your evaluator imports it and uses it for scoring, judging, git, and the coding agent.
- **Evolution objective** = set in config (`evaluation.task_spec`) so the judge knows the high-level task.

For a one-page overview of the project and install, see the main **README.md**.
