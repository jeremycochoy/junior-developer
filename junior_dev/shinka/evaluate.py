import os
import json
import sqlite3
import subprocess
import time
import argparse
import importlib.util
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from junior_dev.scoring import BTMMScoringEngine
from junior_dev.judge import PairwiseJudge
from junior_dev.git_manager import GitManager
from junior_dev.coding_agent import CodingAgent, AgentResult
from junior_dev.config import load_config, get_config_value


def _extract_json_from_evolve_block(content: str) -> str:
    start_marker = "EVOLVE-BLOCK-START"
    end_marker = "EVOLVE-BLOCK-END"
    if start_marker not in content or end_marker not in content:
        return content.strip()
    start_idx = content.find(start_marker) + len(start_marker)
    end_idx = content.find(end_marker)
    if start_idx >= end_idx:
        return content.strip()
    block = content[start_idx:end_idx].strip()
    lines = [line for line in block.splitlines() if line.strip() and not line.strip().startswith("//")]
    return "\n".join(lines)


def _load_program(program_path: str) -> Tuple[str, str, Optional[str]]:
    path = Path(program_path).resolve()
    # Use parent dir + stem so each Shinka job (e.g. gen_0/main.json, gen_1/main.json) has a
    # unique candidate_id; otherwise path.stem is always "main" and we get no comparisons.
    candidate_id = f"{path.parent.name}_{path.stem}"
    
    if program_path.endswith('.json'):
        with open(program_path, 'r', encoding='utf-8') as f:
            raw = f.read()
        json_str = _extract_json_from_evolve_block(raw)
        data = json.loads(json_str)
        evolved_prompt = data.get('prompt', '')
        if not evolved_prompt:
            raise ValueError(f"JSON program must have 'prompt' field: {program_path}")
        parent_branch = data.get('parent_branch')
        return evolved_prompt, candidate_id, parent_branch
    
    spec = importlib.util.spec_from_file_location("program", program_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load program from {program_path}")
    
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    evolved_prompt = module.get_evolved_prompt()
    parent_branch = getattr(module, 'PARENT_BRANCH', None)
    if hasattr(module, 'CANDIDATE_ID'):
        candidate_id = module.CANDIDATE_ID
    
    return evolved_prompt, candidate_id, parent_branch


def _sync_bt_scores_to_shinka_db(
    run_root: Path,
    all_scores: List[Tuple[str, float, Dict[str, Any]]],
    branch_prefix: str,
    verbose: bool = True,
) -> None:
    db_path = run_root / "evolution_db.sqlite"
    if not db_path.exists():
        return
    score_by_candidate = {candidate_id: score for candidate_id, score, _ in all_scores}
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT id, public_metrics FROM programs WHERE public_metrics IS NOT NULL AND public_metrics != ''"
        )
        rows = cur.fetchall()
        updated = 0
        for row in rows:
            program_id = row["id"]
            try:
                pm = json.loads(row["public_metrics"]) if row["public_metrics"] else {}
            except (json.JSONDecodeError, TypeError):
                continue
            branch_name = pm.get("branch_name") or pm.get("branch_for_checkout")
            if not branch_name or not isinstance(branch_name, str):
                continue
            if branch_name.startswith(branch_prefix):
                candidate_id = branch_name[len(branch_prefix) :].strip()
            else:
                candidate_id = branch_name
            if candidate_id not in score_by_candidate:
                continue
            score = score_by_candidate[candidate_id]
            conn.execute("UPDATE programs SET combined_score = ? WHERE id = ?", (score, program_id))
            updated += 1
        conn.commit()
        conn.close()
        if verbose and updated:
            print(f"Synced BT-MM scores to Shinka DB: updated {updated} program(s).")
    except Exception as e:
        if verbose:
            print(f"Warning: could not sync BT scores to Shinka DB: {e}")


def _ensure_target_codebase(target_codebase: str, verbose: bool = True) -> None:
    path = Path(target_codebase).resolve()
    path.mkdir(parents=True, exist_ok=True)
    index_html = path / "index.html"
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
    git_dir = path / ".git"
    if not git_dir.exists():
        subprocess.run(["git", "init"], cwd=path, check=True)
        subprocess.run(["git", "add", "."], cwd=path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=path, check=True)
        if verbose:
            print(f"Initialized git repo: {path}")


def evaluate_coding_agent_prompt(
    program_path: str,
    results_dir: str,
    target_codebase: str = "./example_codebase",
    task_spec: Optional[str] = None,
    bt_db_path: Optional[str] = None,
    llm_judge_model: Optional[str] = None,
    num_comparisons: Optional[int] = None,
    agent_type: Optional[str] = None,
    agent_timeout: Optional[int] = None,
    llm_judge_temperature: Optional[float] = None,
    verbose: bool = True,
    config_path: Optional[str] = None,
):
    config = load_config(config_path)
    
    task_spec = task_spec or get_config_value(config, "evaluation.task_spec", "Refactor and improve the code quality")
    bt_db_path = bt_db_path or get_config_value(config, "scoring.db_path", "./bt_scores.db")
    # Use run-specific BT DB when inside a Shinka run (results_dir = .../gen_N/results) so
    # all jobs in the run share one DB and pairwise comparisons accumulate; otherwise all get initial_score 1.0.
    run_root = Path(results_dir).resolve().parent.parent
    if (run_root / "evolution_db.sqlite").exists():
        bt_db_path = str(run_root / "bt_scores.db")
        if verbose:
            print(f"Using run-specific BT DB: {bt_db_path}")
    llm_judge_model = llm_judge_model or get_config_value(config, "evaluation.llm_judge_model", "gpt-4o")
    num_comparisons = num_comparisons if num_comparisons is not None else get_config_value(config, "evaluation.num_comparisons", 3)
    agent_type = agent_type or get_config_value(config, "coding_agent.agent_type", "pipeline")
    agent_timeout = agent_timeout if agent_timeout is not None else get_config_value(config, "coding_agent.timeout", 600)
    judge_temp = llm_judge_temperature if llm_judge_temperature is not None else get_config_value(config, "evaluation.llm_judge_temperature", 0.0)
    evolved_prompt, candidate_id, parent_branch = _load_program(program_path)
    start_t = time.time()
    error = ""
    correct = True
    sync_all_scores: Optional[List[Tuple[str, float, Dict[str, Any]]]] = None
    sync_branch_prefix: Optional[str] = None

    if program_path.endswith('.json'):
        if parent_branch is None or (isinstance(parent_branch, str) and not parent_branch.strip()):
            correct = False
            error = "JSON program missing required 'parent_branch'; LLM output is malformed."
            if verbose:
                print(f"Invalid program: {error}")
            metrics = {
                "combined_score": 0.0,
                "runtime": time.time() - start_t,
                "public": {"branch_name": "", "error": error},
                "private": {},
            }
            Path(results_dir).mkdir(parents=True, exist_ok=True)
            with open(os.path.join(results_dir, "correct.json"), "w") as f:
                json.dump({"correct": False, "error": error}, f, indent=4)
            with open(os.path.join(results_dir, "metrics.json"), "w") as f:
                json.dump(metrics, f, indent=4)
            return metrics
    
    try:
        
        if verbose:
            print(f"\n{'='*70}")
            print(f"Evaluating Candidate: {candidate_id}")
            print(f"{'='*70}")
            print(f"Evolved Prompt:\n{evolved_prompt[:200]}...")
        
        _ensure_target_codebase(target_codebase, verbose=verbose)
        git_manager = GitManager(target_codebase)
        working_dir = get_config_value(config, "coding_agent.working_dir") or target_codebase
        agents_dir = get_config_value(config, "coding_agent.agents_dir", ".agents")
        pipeline_backend = get_config_value(config, "coding_agent.pipeline_backend", "cursor")
        coding_agent = CodingAgent(
            agent_type=agent_type,
            timeout=agent_timeout,
            working_dir=working_dir,
            agents_dir=agents_dir,
            pipeline_backend=pipeline_backend
        )
        
        branch_prefix = get_config_value(config, "git.branch_prefix", "candidate_")
        default_branch = get_config_value(config, "git.default_branch", "master")
        branch_name = f"{branch_prefix}{candidate_id}"
        
        # Determine which branch to start from:
        # - If parent_branch is specified in the program, use that
        # - Otherwise, use the default_branch (e.g., master)
        from_branch = parent_branch if parent_branch else default_branch
        
        if verbose and parent_branch:
            print(f"Starting from parent branch: {parent_branch}")
        
        if not git_manager.create_branch(branch_name, from_branch=from_branch):
            if verbose:
                print(f"Branch {branch_name} already exists, checking it out...")
            git_manager.checkout_branch(branch_name)
        
        agent_result = coding_agent.execute(prompt=evolved_prompt)
        
        if not agent_result.success:
            print(f"Warning: Coding agent failed: {agent_result.error}")
        
        if agent_result.changes_made:
            git_manager.stage_all()
            git_manager.commit(f"Evolution: {candidate_id}", allow_empty=False)
        
        changes_applied = agent_result.changes_made
        
        engine = BTMMScoringEngine(db_path=bt_db_path)
        judge = PairwiseJudge(llm_model=llm_judge_model, temperature=judge_temp)

        n_random = max(1, (3 * num_comparisons) // 10)
        n_quartile = min(4, max(1, (4 * num_comparisons) // 10))
        n_neighbors = max(1, num_comparisons - n_random - n_quartile)
        random_ids = engine.get_random_candidates(n=n_random, exclude=[candidate_id])
        quartile_ids = engine.get_quartile_candidates(n_quartiles=n_quartile, exclude=[candidate_id])
        phase1_opponents = list(dict.fromkeys([*random_ids, *quartile_ids]))
        if verbose:
            print(f"\nPhase 1: {len(phase1_opponents)} opponents (random + quartiles)...")

        wins = 0
        losses = 0
        ties = 0

        def run_comparisons(opponent_ids: List[str]) -> None:
            nonlocal wins, losses, ties
            for opponent_id in opponent_ids:
                opponent_branch = f"{branch_prefix}{opponent_id}"
                if not git_manager.branch_exists(opponent_branch):
                    if verbose:
                        print(f"  Skipping {opponent_id}: branch {opponent_branch} does not exist")
                    continue
                diff_current = git_manager.get_diff(default_branch, branch_name)
                diff_opponent = git_manager.get_diff(default_branch, opponent_branch)
                judge_context = {
                    "evolution_objective": task_spec,
                    "branch_a": branch_name,
                    "branch_b": f"{branch_prefix}{opponent_id}",
                }
                winner, reasoning = judge.compare(
                    task_spec=task_spec,
                    candidate_a=diff_current,
                    candidate_b=diff_opponent,
                    context=judge_context,
                )
                score_a, score_b = engine.record_comparison(
                    candidate_id, opponent_id, winner, reasoning
                )
                if winner == "a":
                    wins += 1
                elif winner == "b":
                    losses += 1
                else:
                    ties += 1
                if verbose:
                    print(f"  vs {opponent_id}: {winner} (scores: {score_a:.2f} vs {score_b:.2f})")

        run_comparisons(phase1_opponents)
        neighbor_ids = engine.get_neighbor_candidates(candidate_id, n=n_neighbors)
        if neighbor_ids and verbose:
            print(f"\nPhase 2: {len(neighbor_ids)} neighbors (break ties)...")
        run_comparisons(neighbor_ids)
        if verbose:
            print(f"\nTotal: {wins}W-{losses}L-{ties}T")

        final_score = engine.get_score(candidate_id)
        stats = engine.get_stats(candidate_id)
        judge_stats = judge.get_statistics()
        sync_all_scores = engine.get_rankings()
        sync_branch_prefix = branch_prefix
        
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
                "branch_for_checkout": branch_name,  # so evolution LLM sees which branch to use as parent_branch
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

    if sync_all_scores is not None and sync_branch_prefix is not None:
        evo_db = run_root / "evolution_db.sqlite"
        if evo_db.exists():
            _sync_bt_scores_to_shinka_db(
                run_root, sync_all_scores, sync_branch_prefix, verbose=verbose
            )

    elapsed = metrics["runtime"]
    hours = int(elapsed // 3600)
    minutes = int((elapsed % 3600) // 60)
    seconds = int(elapsed % 60)
    print(f"Evaluation completed in {hours}h {minutes}m {seconds}s")
    print(f"Results saved to {results_dir}")
    if metrics.get("public") and "branch_name" in metrics["public"]:
        print(f"Branch for checkout (use as parent_branch): {metrics['public']['branch_name']}")
    
    return metrics


def main(
    program_path: str,
    results_dir: str,
    target_codebase: str = "./example_codebase",
    config: Optional[str] = None,
    bt_db_path: Optional[str] = None,
    **kwargs,
):
    return evaluate_coding_agent_prompt(
        program_path=program_path,
        results_dir=results_dir,
        target_codebase=target_codebase,
        config_path=config,
        bt_db_path=bt_db_path,
        **kwargs,
    )


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
        "--llm_judge_temperature",
        type=float,
        default=None,
        help="Judge LLM temperature (default 0 from config; 0 = more deterministic)"
    )
    parser.add_argument(
        "--num_comparisons",
        type=int,
        default=3,
        help="Number of pairwise comparisons per evaluation"
    )
    parser.add_argument(
        "--agent_type",
        type=str,
        default="pipeline",
        help="Coding agent type (only 'pipeline' is supported)"
    )
    parser.add_argument(
        "--agent_timeout",
        type=int,
        default=None,
        help="Timeout for coding agent execution in seconds (overrides config)"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config YAML file (default: configs/agent_config.yaml)"
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
        agent_type=args.agent_type,
        agent_timeout=args.agent_timeout,
        llm_judge_temperature=args.llm_judge_temperature,
        config_path=args.config,
    )

