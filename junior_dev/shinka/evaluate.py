import os
import json
import time
import argparse
import importlib.util
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any

from junior_dev.scoring import BTMMScoringEngine
from junior_dev.judge import PairwiseJudge


def evaluate_coding_agent_prompt(
    program_path: str,
    results_dir: str,
    target_codebase: str = "./example_codebase",
    task_spec: str = "Refactor and improve the code quality",
    bt_db_path: str = "./bt_scores.db",
    llm_judge_model: str = "gpt-4o",
    num_comparisons: int = 3,
    verbose: bool = True,
):
    spec = importlib.util.spec_from_file_location("program", program_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load program from {program_path}")
    
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    start_t = time.time()
    error = ""
    correct = True
    
    try:
        candidate_id = getattr(module, 'CANDIDATE_ID', Path(program_path).stem)
        evolved_prompt = module.get_evolved_prompt()
        
        if verbose:
            print(f"\n{'='*70}")
            print(f"Evaluating Candidate: {candidate_id}")
            print(f"{'='*70}")
            print(f"Evolved Prompt:\n{evolved_prompt[:200]}...")
        
        branch_name, changes_applied = execute_coding_agent(
            prompt=evolved_prompt,
            codebase_path=target_codebase,
            candidate_id=candidate_id,
        )
        
        if not changes_applied:
            print(f"Warning: No changes were applied by the coding agent")
        
        engine = BTMMScoringEngine(db_path=bt_db_path)
        judge = PairwiseJudge(llm_model=llm_judge_model, temperature=0.0)
        
        previous_candidates = engine.get_random_candidates(
            n=num_comparisons, 
            exclude=[candidate_id]
        )
        
        if verbose:
            print(f"\nRunning {len(previous_candidates)} pairwise comparisons...")
        
        wins = 0
        losses = 0
        ties = 0
        
        for opponent_id in previous_candidates:
            diff_current = get_git_diff("master", branch_name, target_codebase)
            diff_opponent = get_git_diff("master", f"candidate_{opponent_id}", target_codebase)
            
            winner, reasoning = judge.compare(
                task_spec=task_spec,
                candidate_a=diff_current,
                candidate_b=diff_opponent,
                context={"branch_a": branch_name, "branch_b": f"candidate_{opponent_id}"}
            )
            
            score_a, score_b = engine.record_comparison(
                candidate_id, 
                opponent_id, 
                winner, 
                reasoning
            )
            
            if winner == 'a':
                wins += 1
            elif winner == 'b':
                losses += 1
            else:
                ties += 1
            
            if verbose:
                print(f"  vs {opponent_id}: {winner} (scores: {score_a:.2f} vs {score_b:.2f})")
        
        final_score = engine.get_score(candidate_id)
        stats = engine.get_stats(candidate_id)
        judge_stats = judge.get_statistics()
        
        metrics = {
            "combined_score": float(final_score),
            "runtime": time.time() - start_t,
            "public": {
                "bt_score": float(final_score),
                "wins": wins,
                "losses": losses,
                "ties": ties,
                "win_rate": stats.win_rate if stats else 0.0,
                "total_comparisons": stats.num_comparisons if stats else 0,
                "branch_name": branch_name,
                "changes_applied": changes_applied,
            },
            "private": {
                "evaluation_cost": judge_stats['total_cost'],
                "llm_calls": judge_stats['total_comparisons'],
            }
        }
        
        engine.close()
        
        if verbose:
            print(f"\n{'='*70}")
            print(f"Final BT-MM Score: {final_score:.2f}")
            print(f"Record: {wins}W-{losses}L-{ties}T")
            print(f"{'='*70}\n")
        
    except Exception as e:
        print(f"Error during evaluation: {e}")
        import traceback
        traceback.print_exc()
        
        metrics = {
            "combined_score": 0.0,
            "public": {},
            "private": {},
            "runtime": time.time() - start_t,
        }
        error = str(e)
        correct = False
    
    correct_file = os.path.join(results_dir, "correct.json")
    with open(correct_file, "w") as f:
        json.dump({"correct": correct, "error": error}, f, indent=4)
    
    metrics_file = os.path.join(results_dir, "metrics.json")
    with open(metrics_file, "w") as f:
        json.dump(metrics, f, indent=4)
    
    elapsed = metrics["runtime"]
    hours = int(elapsed // 3600)
    minutes = int((elapsed % 3600) // 60)
    seconds = int(elapsed % 60)
    print(f"Evaluation completed in {hours}h {minutes}m {seconds}s")
    print(f"Results saved to {results_dir}")
    
    return metrics


def execute_coding_agent(prompt: str, codebase_path: str, candidate_id: str) -> tuple[str, bool]:
    import subprocess
    
    branch_name = f"candidate_{candidate_id}"
    
    try:
        subprocess.run(
            ["git", "checkout", "-b", branch_name, "master"],
            cwd=codebase_path,
            capture_output=True,
            check=True
        )
        
        # TODO: Call actual coding agent (aider, claude-code, etc.)
        # subprocess.run(["aider", "--message", prompt], cwd=codebase_path)
        
        placeholder_file = Path(codebase_path) / f".evolution_{candidate_id}.txt"
        placeholder_file.write_text(f"Evolution step: {candidate_id}\nPrompt: {prompt}")
        
        subprocess.run(["git", "add", "."], cwd=codebase_path, capture_output=True)
        
        result = subprocess.run(
            ["git", "commit", "-m", f"Evolution: {candidate_id}"],
            cwd=codebase_path,
            capture_output=True
        )
        
        return branch_name, result.returncode == 0
        
    except subprocess.CalledProcessError as e:
        print(f"Git error: {e}")
        return branch_name, False


def get_git_diff(base_branch: str, compare_branch: str, codebase_path: str) -> str:
    import subprocess
    
    try:
        result = subprocess.run(
            ["git", "diff", f"{base_branch}..{compare_branch}"],
            cwd=codebase_path,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error getting diff: {e}")
        return f"Error: Could not get diff between {base_branch} and {compare_branch}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluate evolved coding agent prompts using BT-MM scoring"
    )
    parser.add_argument(
        "--program_path",
        type=str,
        default="initial.py",
        help="Path to the program containing evolved prompt"
    )
    parser.add_argument(
        "--results_dir",
        type=str,
        default="results",
        help="Directory to save evaluation results"
    )
    parser.add_argument(
        "--target_codebase",
        type=str,
        default="./example_codebase",
        help="Path to the codebase to refactor"
    )
    parser.add_argument(
        "--task_spec",
        type=str,
        default="Refactor and improve code quality",
        help="Task specification for the coding agent"
    )
    parser.add_argument(
        "--bt_db_path",
        type=str,
        default="./bt_scores.db",
        help="Path to BT-MM scoring database"
    )
    parser.add_argument(
        "--llm_judge_model",
        type=str,
        default="gpt-4",
        help="LLM model for pairwise judging"
    )
    parser.add_argument(
        "--num_comparisons",
        type=int,
        default=3,
        help="Number of pairwise comparisons per evaluation"
    )
    
    args = parser.parse_args()
    Path(args.results_dir).mkdir(parents=True, exist_ok=True)
    
    evaluate_coding_agent_prompt(
        program_path=args.program_path,
        results_dir=args.results_dir,
        target_codebase=args.target_codebase,
        task_spec=args.task_spec,
        bt_db_path=args.bt_db_path,
        llm_judge_model=args.llm_judge_model,
        num_comparisons=args.num_comparisons,
    )

