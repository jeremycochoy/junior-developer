import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from junior_dev.shinka.evaluate import evaluate_coding_agent_prompt
from dotenv import load_dotenv

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Test evaluate.py with real example")
    parser.add_argument(
        "--agent-type",
        type=str,
        default="pipeline",
        help="Agent type: pipeline (only supported type)"
    )
    parser.add_argument(
        "--agent-timeout",
        type=int,
        default=300,
        help="Agent timeout in seconds"
    )
    parser.add_argument(
        "--llm-judge-model",
        type=str,
        default="gpt-4o-mini",
        help="LLM model for judging"
    )
    parser.add_argument(
        "--num-comparisons",
        type=int,
        default=1,
        help="Number of pairwise comparisons (use 0 for first run)"
    )
    parser.add_argument(
        "--use-example-repo",
        action="store_true",
        help="Use the example_test_repo as target codebase"
    )
    parser.add_argument(
        "--target-codebase",
        type=str,
        default="",
        help="Path to target codebase (default: example_test_repo)"
    )
    parser.add_argument(
        "--program-path",
        type=str,
        default="",
        help="Path to program file (default: auto-detect test_prompt.py or initial.py)"
    )
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    
    if args.use_example_repo or not args.target_codebase:
        target_codebase = project_root / "results" / "test_repos" / "example_test_repo"
    else:
        target_codebase = Path(args.target_codebase).resolve()
    
    if not target_codebase.exists():
        print(f"ERROR: Target codebase not found: {target_codebase}")
        print("Run the example test first to create the repo:")
        print("  python3 examples/test_gm_conding_agent.py --agent-type mock")
        return 1
    
    if args.program_path:
        program_path = Path(args.program_path).resolve()
        if not program_path.exists():
            print(f"ERROR: Program file not found: {program_path}")
            return 1
    else:
        test_prompt_path = project_root / "examples" / "test_prompt.py"
        test_prompt_2_path = project_root / "examples" / "test_prompt_2.py"
        initial_path = project_root / "junior_dev" / "shinka" / "initial.py"
        
        if test_prompt_path.exists():
            program_path = test_prompt_path
        elif test_prompt_2_path.exists():
            program_path = test_prompt_2_path
        elif initial_path.exists():
            program_path = initial_path
        else:
            print(f"ERROR: No program file found")
            print("Please specify --program-path or create test_prompt.py")
            return 1
    
    results_dir = project_root / "results" / "evaluate_test"
    results_dir.mkdir(parents=True, exist_ok=True)
    
    db_path = project_root / "results" / "evaluate_test.db"
    
    print("="*70)
    print("TESTING evaluate.py")
    print("="*70)
    print(f"Program file: {program_path}")
    print(f"Target codebase: {target_codebase}")
    print(f"Results directory: {results_dir}")
    print(f"Database: {db_path}")
    print(f"Agent type: {args.agent_type}")
    print(f"LLM judge model: {args.llm_judge_model}")
    print(f"Number of comparisons: {args.num_comparisons}")
    print("="*70)
    print()
    
    task_spec = "Improve the example.py file by adding better documentation and error handling."
    
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("program", str(program_path))
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, 'get_task_spec'):
                task_spec = module.get_task_spec()
    except Exception:
        pass
    
    try:
        metrics = evaluate_coding_agent_prompt(
            program_path=str(program_path),
            results_dir=str(results_dir),
            target_codebase=str(target_codebase),
            task_spec=task_spec,
            bt_db_path=str(db_path),
            llm_judge_model=args.llm_judge_model,
            num_comparisons=args.num_comparisons,
            agent_type=args.agent_type,
            agent_timeout=args.agent_timeout,
            verbose=True,
        )
        
        print("\n" + "="*70)
        print("EVALUATION COMPLETE")
        print("="*70)
        print(f"Final Score: {metrics.get('combined_score', 0):.4f}")
        print(f"Runtime: {metrics.get('runtime', 0):.2f}s")
        if 'public' in metrics:
            pub = metrics['public']
            print(f"Wins: {pub.get('wins', 0)}")
            print(f"Losses: {pub.get('losses', 0)}")
            print(f"Ties: {pub.get('ties', 0)}")
        print("="*70)
        
        return 0
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

