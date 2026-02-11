"""Evaluation entry point for ShinkaEvolve integration.

Flow:
  1. Load the evolved prompt from main.json (with fallback to original.json)
  2. Create a git branch and run the CodingAgent to apply the prompt
  3. Compare the result against other candidates via pairwise LLM judging
  4. Score candidates using Bradley-Terry (BT-MM) rankings
  5. Sync scores back to Shinka's evolution DB
"""

import os
import sys
import json
import sqlite3
import subprocess
import time
import argparse
import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from junior_dev.scoring import BTMMScoringEngine
from junior_dev.judge import PairwiseJudge
from junior_dev.git_manager import GitManager
from junior_dev.coding_agent import CodingAgent
from junior_dev.config import load_config, get_config_value

# ── Constants ───────────────────────────────────────────────────────

EVOLVE_BLOCK_START = "EVOLVE-BLOCK-START"
EVOLVE_BLOCK_END = "EVOLVE-BLOCK-END"

MAX_DIFF_CHARS = 200_000

RANDOM_FRACTION = 0.3
QUARTILE_FRACTION = 0.4

DEFAULT_TASK_SPEC = "Refactor and improve the code quality"
DEFAULT_JUDGE_MODEL = "gpt-4o-2024-08-06"
DEFAULT_NUM_COMPARISONS = 10
DEFAULT_AGENT_TIMEOUT = 600
DEFAULT_BRANCH_PREFIX = "candidate_"
DEFAULT_BRANCH = "master"

SCAFFOLD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Snake</title>
</head>
<body>
</body>
</html>
"""

# ── Program loading ─────────────────────────────────────────────────

def _extract_json_from_evolve_block(content: str) -> str:
    if EVOLVE_BLOCK_START not in content or EVOLVE_BLOCK_END not in content:
        return content.strip()
    start_idx = content.find(EVOLVE_BLOCK_START) + len(EVOLVE_BLOCK_START)
    end_idx = content.find(EVOLVE_BLOCK_END)
    if start_idx >= end_idx:
        return content.strip()
    block = content[start_idx:end_idx].strip()
    lines = [line for line in block.splitlines() if line.strip() and not line.strip().startswith("//")]
    return "\n".join(lines)


def _find_parent_program_path(gen_dir: Path) -> Optional[Path]:
    run_root = gen_dir.parent
    db_path = run_root / "evolution_db.sqlite"
    if not db_path.exists():
        return None

    gen_name = gen_dir.name
    if not gen_name.startswith("gen_"):
        return None
    try:
        gen_num = int(gen_name.split("_", 1)[1])
    except (ValueError, IndexError):
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            """SELECT p_parent.generation AS parent_gen
               FROM programs p
               JOIN programs p_parent ON p.parent_id = p_parent.id
               WHERE p.generation = ?
               LIMIT 1""",
            (gen_num,),
        ).fetchone()
        conn.close()

        if row is None:
            return None

        parent_gen = row["parent_gen"]
        parent_main = run_root / f"gen_{parent_gen}" / "main.json"
        if parent_main.exists():
            return parent_main
    except Exception:
        pass

    return None


def _load_json_program(program_path: Path, candidate_id: str) -> Tuple[str, str, Optional[str]]:
    if not program_path.exists():
        gen_dir = program_path.parent

        original_path = gen_dir / "original.json"
        if original_path.exists():
            print(f"Warning: main.json not found for {candidate_id} (patch likely failed)")
            print(f"         Using parent prompt from original.json as fallback")
            program_path = original_path
            candidate_id = f"{candidate_id}_failed_patch"

        else:
            parent_path = _find_parent_program_path(gen_dir)
            if parent_path is not None:
                print(f"Warning: main.json not found for {candidate_id} (full-patch extraction failed)")
                print(f"         Using parent generation's prompt from {parent_path.parent.name}/main.json")
                program_path = parent_path
                candidate_id = f"{candidate_id}_failed_patch"
            else:
                print(f"Error: No fallback found for {candidate_id} (no main.json, original.json, or parent)")
                print(f"       Cannot evaluate this generation")
                return "", candidate_id, None

    raw = program_path.read_text(encoding="utf-8")
    json_str = _extract_json_from_evolve_block(raw)
    data = json.loads(json_str)

    evolved_prompt = data.get("prompt", "")
    if not evolved_prompt:
        raise ValueError(f"JSON program must have 'prompt' field: {program_path}")

    parent_branch = data.get("parent_branch")
    return evolved_prompt, candidate_id, parent_branch


def _load_python_program(program_path: str, candidate_id: str) -> Tuple[str, str, Optional[str]]:
    spec = importlib.util.spec_from_file_location("program", program_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load program from {program_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    evolved_prompt = module.get_evolved_prompt()
    parent_branch = getattr(module, "PARENT_BRANCH", None)
    if hasattr(module, "CANDIDATE_ID"):
        candidate_id = module.CANDIDATE_ID

    return evolved_prompt, candidate_id, parent_branch


def load_program(program_path: str) -> Tuple[str, str, Optional[str]]:
    path = Path(program_path).resolve()
    candidate_id = f"{path.parent.name}_{path.stem}"

    if program_path.endswith(".json"):
        return _load_json_program(path, candidate_id)
    return _load_python_program(program_path, candidate_id)


# ── Diff utilities ──────────────────────────────────────────────────

def truncate_diff(diff: str, max_chars: int = MAX_DIFF_CHARS) -> str:
    if len(diff) <= max_chars:
        return diff
    keep_each = max_chars // 2
    removed = len(diff) - max_chars
    return (
        diff[:keep_each]
        + f"\n\n... [TRUNCATED {removed:,} characters / {removed // 1024}KB for brevity] ...\n\n"
        + diff[-keep_each:]
    )


# ── Shinka DB sync ──────────────────────────────────────────────────

def _sync_bt_scores_to_shinka_db(
    run_root: Path,
    all_scores: List[Tuple[str, float, Dict[str, Any]]],
    branch_prefix: str,
    verbose: bool = True,
) -> None:
    db_path = run_root / "evolution_db.sqlite"
    if not db_path.exists():
        return

    score_by_candidate = {cid: score for cid, score, _ in all_scores}
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, public_metrics FROM programs WHERE public_metrics IS NOT NULL AND public_metrics != ''"
        ).fetchall()

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

            candidate_id = branch_name[len(branch_prefix):].strip() if branch_name.startswith(branch_prefix) else branch_name
            if candidate_id not in score_by_candidate:
                continue

            conn.execute("UPDATE programs SET combined_score = ? WHERE id = ?", (score_by_candidate[candidate_id], program_id))
            updated += 1

        conn.commit()
        conn.close()
        if verbose and updated:
            print(f"Synced BT-MM scores to Shinka DB: updated {updated} program(s).")
    except Exception as e:
        if verbose:
            print(f"Warning: could not sync BT scores to Shinka DB: {e}")


# ── Target codebase bootstrap ──────────────────────────────────────

def _ensure_target_codebase(target_codebase: str, verbose: bool = True) -> None:
    path = Path(target_codebase).resolve()
    path.mkdir(parents=True, exist_ok=True)

    index_html = path / "index.html"
    if not index_html.exists():
        index_html.write_text(SCAFFOLD_HTML)

    if not (path / ".git").exists():
        subprocess.run(["git", "init"], cwd=path, check=True)
        subprocess.run(["git", "add", "."], cwd=path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=path, check=True)
        if verbose:
            print(f"Initialized git repo: {path}")


# ── Metrics / result files ──────────────────────────────────────────

def _write_results(results_dir: str, metrics: Dict[str, Any], correct: bool, error: str) -> None:
    results_path = Path(results_dir)
    results_path.mkdir(parents=True, exist_ok=True)

    with open(results_path / "correct.json", "w") as f:
        json.dump({"correct": correct, "error": error}, f, indent=4)
    with open(results_path / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=4)


def _failure_metrics(error: str, start_time: float) -> Dict[str, Any]:
    return {
        "combined_score": 0.0,
        "runtime": time.time() - start_time,
        "public": {"branch_name": "", "error": error},
        "private": {},
    }


def _format_elapsed(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h}h {m}m {s}s"


# ── Opponent selection ──────────────────────────────────────────────

def _select_opponents(
    engine: BTMMScoringEngine,
    candidate_id: str,
    num_comparisons: int,
) -> Tuple[List[str], int]:
    n_random = max(1, int(RANDOM_FRACTION * num_comparisons))
    n_quartile = min(4, max(1, int(QUARTILE_FRACTION * num_comparisons)))
    n_neighbors = max(1, num_comparisons - n_random - n_quartile)

    random_ids = engine.get_random_candidates(n=n_random, exclude=[candidate_id])
    quartile_ids = engine.get_quartile_candidates(n_quartiles=n_quartile, exclude=[candidate_id])

    phase1 = list(dict.fromkeys([*random_ids, *quartile_ids]))

    phase1 = [opp for opp in phase1 if not engine.comparison_exists(candidate_id, opp)]

    return phase1, n_neighbors


# ── Pairwise comparison loop ───────────────────────────────────────

def _run_comparisons(
    opponent_ids: List[str],
    candidate_id: str,
    branch_name: str,
    branch_prefix: str,
    default_branch: str,
    git_manager: GitManager,
    judge: PairwiseJudge,
    engine: BTMMScoringEngine,
    task_spec: str,
    verbose: bool,
) -> Tuple[int, int]:
    
    wins = 0
    losses = 0

    for opponent_id in opponent_ids:
        opponent_branch = f"{branch_prefix}{opponent_id}"
        if not git_manager.branch_exists(opponent_branch):
            if verbose:
                print(f"  Skipping {opponent_id}: branch {opponent_branch} does not exist")
            continue

        # Get full diffs from master
        diff_current = git_manager.get_diff(default_branch, branch_name)
        diff_opponent = git_manager.get_diff(default_branch, opponent_branch)

        original_current_len = len(diff_current)
        original_opponent_len = len(diff_opponent)
        diff_current = truncate_diff(diff_current)
        diff_opponent = truncate_diff(diff_opponent)

        if verbose and (original_current_len > MAX_DIFF_CHARS or original_opponent_len > MAX_DIFF_CHARS):
            print(
                f"  Note: Truncated diffs "
                f"(current: {original_current_len // 1024}KB -> {len(diff_current) // 1024}KB, "
                f"opponent: {original_opponent_len // 1024}KB -> {len(diff_opponent) // 1024}KB)"
            )

        judge_context = {
            "evolution_objective": task_spec,
            "branch_a": branch_name,
            "branch_b": opponent_branch,
        }

        winner, reasoning = judge.compare(
            task_spec=task_spec,
            candidate_a=diff_current,
            candidate_b=diff_opponent,
            context=judge_context,
        )
        score_a, score_b = engine.record_comparison(candidate_id, opponent_id, winner, reasoning)

        if winner == "a":
            wins += 1
        elif winner == "b":
            losses += 1

        if verbose:
            print(f"  vs {opponent_id}: {winner} (scores: {score_a:.2f} vs {score_b:.2f})")

    return wins, losses


# ── Config resolution ───────────────────────────────────────────────

def _resolve_config(
    config: Dict[str, Any],
    *,
    task_spec: Optional[str],
    bt_db_path: Optional[str],
    llm_judge_model: Optional[str],
    num_comparisons: Optional[int],
    agent_type: Optional[str],
    agent_timeout: Optional[int],
    llm_judge_temperature: Optional[float],
) -> Dict[str, Any]:
    return {
        "task_spec": task_spec or get_config_value(config, "evaluation.task_spec", DEFAULT_TASK_SPEC),
        "bt_db_path": bt_db_path or get_config_value(config, "scoring.db_path", "./bt_scores.db"),
        "llm_judge_model": llm_judge_model or get_config_value(config, "evaluation.llm_judge_model", DEFAULT_JUDGE_MODEL),
        "num_comparisons": num_comparisons if num_comparisons is not None else get_config_value(config, "evaluation.num_comparisons", DEFAULT_NUM_COMPARISONS),
        "agent_type": agent_type or get_config_value(config, "coding_agent.agent_type", "pipeline"),
        "agent_timeout": agent_timeout if agent_timeout is not None else get_config_value(config, "coding_agent.timeout", DEFAULT_AGENT_TIMEOUT),
        "judge_temperature": llm_judge_temperature if llm_judge_temperature is not None else get_config_value(config, "evaluation.llm_judge_temperature", 0.0),
        "working_dir": get_config_value(config, "coding_agent.working_dir"),
        "agents_dir": get_config_value(config, "coding_agent.agents_dir", ".agents"),
        "pipeline_backend": get_config_value(config, "coding_agent.pipeline_backend", "cursor"),
        "branch_prefix": get_config_value(config, "git.branch_prefix", DEFAULT_BRANCH_PREFIX),
        "default_branch": get_config_value(config, "git.default_branch", DEFAULT_BRANCH),
    }


# ── Main evaluation ────────────────────────────────────────────────

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
    settings = _resolve_config(
        config,
        task_spec=task_spec, bt_db_path=bt_db_path, llm_judge_model=llm_judge_model,
        num_comparisons=num_comparisons, agent_type=agent_type, agent_timeout=agent_timeout,
        llm_judge_temperature=llm_judge_temperature,
    )

    start_time = time.time()

    # ── Step 1: Load the evolved prompt ─────────────────────────
    evolved_prompt, candidate_id, parent_branch = load_program(program_path)

    if not evolved_prompt:
        error = "Patch application failed and no fallback available (missing main.json and original.json)"
        print(f"Skipping evaluation for {candidate_id}: {error}")
        metrics = _failure_metrics(error, start_time)
        _write_results(results_dir, metrics, correct=False, error=error)
        return metrics

    if program_path.endswith(".json"):
        if parent_branch is None or (isinstance(parent_branch, str) and not parent_branch.strip()):
            error = "JSON program missing required 'parent_branch'; LLM output is malformed."
            if verbose:
                print(f"Invalid program: {error}")
            metrics = _failure_metrics(error, start_time)
            _write_results(results_dir, metrics, correct=False, error=error)
            return metrics

    run_root = Path(results_dir).resolve().parent.parent
    if (run_root / "evolution_db.sqlite").exists():
        settings["bt_db_path"] = str(run_root / "bt_scores.db")
        if verbose:
            print(f"Using run-specific BT DB: {settings['bt_db_path']}")

    try:
        if verbose:
            print(f"\n{'=' * 70}")
            print(f"Evaluating Candidate: {candidate_id}")
            print(f"{'=' * 70}")
            print(f"Evolved Prompt:\n{evolved_prompt[:200]}...")

        # ── Step 2: Prepare codebase and run agent ──────────────
        _ensure_target_codebase(target_codebase, verbose=verbose)
        git_manager = GitManager(target_codebase)

        coding_agent = CodingAgent(
            agent_type=settings["agent_type"],
            timeout=settings["agent_timeout"],
            working_dir=settings["working_dir"] or target_codebase,
            agents_dir=settings["agents_dir"],
            pipeline_backend=settings["pipeline_backend"],
        )

        branch_prefix = settings["branch_prefix"]
        default_branch = settings["default_branch"]
        branch_name = f"{branch_prefix}{candidate_id}"
        from_branch = parent_branch or default_branch

        if verbose and parent_branch:
            print(f"Starting from parent branch: {parent_branch}")

        if not git_manager.create_branch(branch_name, from_branch=from_branch):
            if verbose:
                print(f"Branch {branch_name} already exists, checking it out...")
            git_manager.checkout_branch(branch_name)

        agent_result = coding_agent.execute(prompt=evolved_prompt)
        if not agent_result.success:
            print(f"Warning: Coding agent failed: {agent_result.error}")

        changes_applied = agent_result.changes_made
        if changes_applied:
            git_manager.stage_all()
            git_manager.commit(f"Evolution: {candidate_id}", allow_empty=False)

        # ── Step 3: Pairwise comparisons ────────────────────────
        engine = BTMMScoringEngine(db_path=settings["bt_db_path"])
        judge = PairwiseJudge(llm_model=settings["llm_judge_model"], temperature=settings["judge_temperature"])

        phase1_opponents, n_neighbors = _select_opponents(engine, candidate_id, settings["num_comparisons"])

        if verbose:
            print(f"\nPhase 1: {len(phase1_opponents)} opponents (random + quartiles)...")

        wins, losses = _run_comparisons(
            phase1_opponents, candidate_id, branch_name, branch_prefix,
            default_branch, git_manager, judge, engine, settings["task_spec"], verbose,
        )

        neighbor_ids = engine.get_neighbor_candidates(candidate_id, n=n_neighbors)
        neighbor_ids = [opp for opp in neighbor_ids if not engine.comparison_exists(candidate_id, opp)]

        if neighbor_ids and verbose:
            print(f"\nPhase 2: {len(neighbor_ids)} neighbors...")

        w2, l2 = _run_comparisons(
            neighbor_ids, candidate_id, branch_name, branch_prefix,
            default_branch, git_manager, judge, engine, settings["task_spec"], verbose,
        )
        wins += w2
        losses += l2

        if verbose:
            print(f"\nTotal: {wins}W-{losses}L")

        # ── Step 4: Collect final scores and build metrics ──────
        final_score = engine.get_score(candidate_id)
        stats = engine.get_stats(candidate_id)
        judge_stats = judge.get_statistics()
        sync_all_scores = engine.get_rankings()
        engine.close()

        metrics = {
            "combined_score": float(final_score),
            "runtime": time.time() - start_time,
            "public": {
                "bt_score": float(final_score),
                "wins": wins,
                "losses": losses,
                "win_rate": stats.win_rate if stats else 0.0,
                "total_comparisons": stats.num_comparisons if stats else 0,
                "branch_name": branch_name,
                "branch_for_checkout": branch_name,
                "changes_applied": changes_applied,
            },
            "private": {
                "evaluation_cost": judge_stats["total_cost"],
                "llm_calls": judge_stats["total_comparisons"],
            },
        }

        if verbose:
            print(f"\n{'=' * 70}")
            print(f"Final BT-MM Score: {final_score:.2f}")
            print(f"Record: {wins}W-{losses}L")
            print(f"{'=' * 70}\n")

    except Exception as e:
        print(f"Error during evaluation: {e}")
        import traceback
        traceback.print_exc()

        metrics = _failure_metrics(str(e), start_time)
        sync_all_scores = None
        branch_prefix = settings["branch_prefix"]

    # ── Write results and sync scores ───────────────────────────
    error = metrics.get("public", {}).get("error", "")
    correct = not error
    _write_results(results_dir, metrics, correct, error)

    if sync_all_scores is not None:
        evo_db = run_root / "evolution_db.sqlite"
        if evo_db.exists():
            _sync_bt_scores_to_shinka_db(run_root, sync_all_scores, branch_prefix, verbose=verbose)

    print(f"Evaluation completed in {_format_elapsed(metrics['runtime'])}")
    print(f"Results saved to {results_dir}")
    if metrics.get("public", {}).get("branch_name"):
        print(f"Branch for checkout (use as parent_branch): {metrics['public']['branch_name']}")

    return metrics


# ── CLI entry point ─────────────────────────────────────────────────


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
    parser.add_argument("--program_path", type=str, default="initial.py",
                        help="Path to the program containing evolved prompt")
    parser.add_argument("--results_dir", type=str, default="results",
                        help="Directory to save evaluation results")
    parser.add_argument("--target_codebase", type=str, default="./example_codebase",
                        help="Path to the codebase to refactor")
    parser.add_argument("--task_spec", type=str, default=DEFAULT_TASK_SPEC,
                        help="Task specification for the coding agent")
    parser.add_argument("--bt_db_path", type=str, default="./bt_scores.db",
                        help="Path to BT-MM scoring database")
    parser.add_argument("--llm_judge_model", type=str, default=DEFAULT_JUDGE_MODEL,
                        help="LLM model for pairwise judging")
    parser.add_argument("--llm_judge_temperature", type=float, default=None,
                        help="Judge LLM temperature (default 0 = deterministic)")
    parser.add_argument("--num_comparisons", type=int, default=DEFAULT_NUM_COMPARISONS,
                        help="Number of pairwise comparisons per evaluation")
    parser.add_argument("--agent_type", type=str, default="pipeline",
                        help="Coding agent type (only 'pipeline' is supported)")
    parser.add_argument("--agent_timeout", type=int, default=None,
                        help="Timeout for coding agent execution in seconds")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to config YAML file (optional)")

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
