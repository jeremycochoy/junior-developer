import os
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, "/home/ShinkaEvolve")

from shinka.core import EvolutionRunner, EvolutionConfig
from shinka.database import DatabaseConfig
from shinka.launch import LocalJobConfig

PROJECT_DIR = Path(__file__).parent
RESULTS_DIR = PROJECT_DIR / "results" / "snake_evolution"
TARGET_CODEBASE = PROJECT_DIR / "results" / "snake_codebase"
INIT_PROGRAM = PROJECT_DIR / "junior_dev" / "shinka" / "initial_snake.py"
EVALUATOR_CONFIG = PROJECT_DIR / "configs" / "agent_config.yaml"

NUM_GENERATIONS = 12


# Shinka configuration

job_config = LocalJobConfig(
    eval_program_path=str(PROJECT_DIR / "eval_snake.py"),
)

db_config = DatabaseConfig(
    db_path="evolution_db.sqlite",
    num_islands=2,
    archive_size=20,
    elite_selection_ratio=0.3,
    num_archive_inspirations=3,
    num_top_k_inspirations=2,
    parent_selection_strategy="power_law",
    exploitation_alpha=1.0,
)

task_sys_msg = """You are evolving prompts for a coding agent that creates snake games.

**Task:** Create a snake game in a self-contained HTML file.
- Runs in any web browser
- Simple, clean code  
- Appealing visual style

**What you evolve:** The prompt inside EVOLVE-BLOCK markers.

**Tips for better prompts:**
- Be specific about visuals (colors, animations)
- Specify controls (arrow keys, touch)
- Request responsive design
- Ask for clean code structure

**Scoring:** Pairwise LLM judging compares code changes."""

evo_config = EvolutionConfig(
    task_sys_msg=task_sys_msg,
    patch_types=["full"],
    patch_type_probs=[1.0],
    num_generations=NUM_GENERATIONS,
    max_parallel_jobs=1,
    max_patch_attempts=5,
    job_type="local",
    language="python",
    llm_models=["gpt-4o-mini"],
    llm_kwargs={"temperatures": [0.7, 1.0]},
    embedding_model="text-embedding-3-small",
    init_program_path=str(INIT_PROGRAM),
    results_dir=str(RESULTS_DIR),
)

# Setup functions

def setup_snake_codebase():
    """Create snake codebase as a git repo with empty index.html."""
    TARGET_CODEBASE.mkdir(parents=True, exist_ok=True)
    
    index_html = TARGET_CODEBASE / "index.html"
    if not index_html.exists():
        index_html.write_text("""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Snake</title>
</head>
<body>
</body>
</html>
""")
    
    git_dir = TARGET_CODEBASE / ".git"
    if not git_dir.exists():
        subprocess.run(["git", "init"], cwd=TARGET_CODEBASE, check=True)
        subprocess.run(["git", "add", "."], cwd=TARGET_CODEBASE, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=TARGET_CODEBASE, check=True)
        print(f"Initialized git repo: {TARGET_CODEBASE}")


def main():
    print("=" * 60)
    print("Snake Game Prompt Evolution")
    print("=" * 60)
    print(f"Generations: {NUM_GENERATIONS}")
    print(f"Results: {RESULTS_DIR}")
    print("=" * 60)
    
    setup_snake_codebase()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    os.environ["EVALUATOR_CONFIG_PATH"] = str(EVALUATOR_CONFIG)
    os.environ["TARGET_CODEBASE"] = str(TARGET_CODEBASE)
    os.environ["BT_DB_PATH"] = str(RESULTS_DIR / "bt_scores.db")
    
    runner = EvolutionRunner(
        evo_config=evo_config,
        job_config=job_config,
        db_config=db_config,
        verbose=True,
    )
    runner.run()
    
    print("\n" + "=" * 60)
    print("Evolution complete!")
    print(f"Results: {RESULTS_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
