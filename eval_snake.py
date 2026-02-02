import os
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from junior_dev.shinka.evaluate import evaluate_coding_agent_prompt


def main():
    parser = argparse.ArgumentParser(description="Evaluate snake game prompt")
    parser.add_argument("--program_path", type=str, required=True)
    parser.add_argument("--results_dir", type=str, required=True)
    args = parser.parse_args()
    
    project_dir = Path(__file__).parent
    target_codebase = os.environ.get(
        "TARGET_CODEBASE", 
        str(project_dir / "results" / "snake_codebase")
    )
    config_path = os.environ.get(
        "EVALUATOR_CONFIG_PATH",
        str(project_dir / "configs" / "agent_config.yaml")
    )
    bt_db_path = os.environ.get(
        "BT_DB_PATH",
        str(project_dir / "results" / "snake_evolution" / "bt_scores.db")
    )
    
    Path(args.results_dir).mkdir(parents=True, exist_ok=True)
    
    print(f"Evaluating: {args.program_path}")
    
    evaluate_coding_agent_prompt(
        program_path=args.program_path,
        results_dir=args.results_dir,
        target_codebase=target_codebase,
        config_path=config_path,
        bt_db_path=bt_db_path,
        verbose=True,
    )


if __name__ == "__main__":
    main()
