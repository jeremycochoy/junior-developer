#!/usr/bin/env python3
"""Re-judge existing pairwise comparisons using the LLM judge.

Reads existing pairs from bt_scores.db, re-runs the LLM judge on the same
candidate diffs, and writes results to a new database (bt_scores_rejudged.db).
After judging, automatically syncs BT scores to a copy of evolution_db.sqlite
so results are viewable in shinka_visualize.

Usage:
    python rejudge.py [OPTIONS]

    # Re-judge all existing pairs with deepseek-reasoner (default)
    python rejudge.py

    # Use a different judge model
    python rejudge.py --judge-model openrouter-qwen/qwen3-coder-30b-a3b-instruct

    # Dry run: list pairs without judging
    python rejudge.py --dry-run

    # Limit to N pairs (for testing)
    python rejudge.py --limit 5

    # Resume from where you left off (skips already-judged pairs)
    python rejudge.py --resume

    # Sync existing BT scores to evolution_db without re-judging
    python rejudge.py --sync-only

    # Sync a specific BT database to evolution_db
    python rejudge.py --sync-only --bt-db path/to/bt_scores.db

    # Skip the evolution_db sync after judging
    python rejudge.py --no-sync
"""

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple, Dict, Any
from dotenv import load_dotenv

load_dotenv()

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from junior_dev.judge import PairwiseJudge
from junior_dev.scoring import BTMMScoringEngine, compute_bt_mm_scipy

# ── Defaults ─────────────────────────────────────────────────────────

DEFAULT_RUN_DIR = "results/rnd/2026.02.16084727_default"
DEFAULT_CODE_DIR = "results/rnd/2026.02.16084727_default/code"
DEFAULT_BASE_BRANCH = "development"
BRANCH_PREFIX = "candidate_"
DEFAULT_TASK_SPEC = "Refactor and improve the code quality"
DEFAULT_JUDGE_MODEL = "deepseek-reasoner"
MAX_DIFF_CHARS = 200_000


def truncate_diff(diff: str, max_chars: int = MAX_DIFF_CHARS) -> str:
    if len(diff) <= max_chars:
        return diff
    keep_each = max_chars // 2
    removed = len(diff) - max_chars
    return (
        diff[:keep_each]
        + f"\n\n... [TRUNCATED {removed:,} characters] ...\n\n"
        + diff[-keep_each:]
    )


def get_diff(code_dir: str, base_branch: str, candidate_branch: str) -> str:
    result = subprocess.run(
        ["git", "diff", f"{base_branch}..{candidate_branch}"],
        cwd=code_dir, capture_output=True, text=True,
    )
    return result.stdout


def branch_exists(code_dir: str, branch_name: str) -> bool:
    result = subprocess.run(
        ["git", "branch", "--list", branch_name],
        cwd=code_dir, capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def load_existing_pairs(db_path: str) -> List[Tuple[str, str]]:
    """Load all (candidate_a, candidate_b) pairs from the original DB."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT candidate_a, candidate_b FROM comparisons ORDER BY id"
    ).fetchall()
    conn.close()
    return [(r[0], r[1]) for r in rows]


def load_existing_candidates(db_path: str) -> List[str]:
    """Load all candidate IDs from the original DB."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT candidate_id FROM bt_scores").fetchall()
    conn.close()
    return [r[0] for r in rows]


def sync_bt_to_evolution_db(
    run_dir: str,
    bt_db_path: str,
    branch_prefix: str = BRANCH_PREFIX,
) -> None:
    """Copy evolution_db.sqlite and update combined_score with BT scores.

    Uses public_metrics.branch_name to map programs to BT candidate IDs
    (same logic as _sync_bt_scores_to_shinka_db in evaluate.py).
    Falls back to generation-number matching for candidates like gen_N_main.
    """
    import re

    run_path = Path(run_dir).resolve()
    evo_db = run_path / "evolution_db.sqlite"
    if not evo_db.exists():
        print(f"No evolution_db.sqlite found in {run_path}, skipping UI sync.")
        return

    evo_bt = run_path / "evolution_db_bt.sqlite"
    shutil.copy2(evo_db, evo_bt)

    bt_conn = sqlite3.connect(bt_db_path)
    bt_rows = bt_conn.execute("SELECT candidate_id, bt_score FROM bt_scores").fetchall()
    score_by_candidate = {cid: score for cid, score in bt_rows}
    bt_conn.close()

    conn = sqlite3.connect(str(evo_bt))
    conn.row_factory = sqlite3.Row

    # Strategy 1: match via public_metrics.branch_name (preferred)
    rows = conn.execute(
        "SELECT id, public_metrics FROM programs "
        "WHERE public_metrics IS NOT NULL AND public_metrics != ''"
    ).fetchall()

    updated = 0
    matched_program_ids = set()
    for row in rows:
        try:
            pm = json.loads(row["public_metrics"]) if row["public_metrics"] else {}
        except (json.JSONDecodeError, TypeError):
            continue

        branch_name = pm.get("branch_name") or pm.get("branch_for_checkout")
        if not branch_name or not isinstance(branch_name, str):
            continue

        candidate_id = (
            branch_name[len(branch_prefix):]
            if branch_name.startswith(branch_prefix)
            else branch_name
        )
        if candidate_id not in score_by_candidate:
            continue

        conn.execute(
            "UPDATE programs SET combined_score = ? WHERE id = ?",
            (score_by_candidate[candidate_id], row["id"]),
        )
        matched_program_ids.add(row["id"])
        updated += 1

    # Strategy 2: fallback for any unmatched — match gen_N_main to generation N
    if updated < len(score_by_candidate):
        for candidate_id, score in score_by_candidate.items():
            m = re.match(r"gen_(\d+)_main", candidate_id)
            if not m:
                continue
            gen = int(m.group(1))
            row = conn.execute(
                "SELECT id FROM programs WHERE generation = ?", (gen,)
            ).fetchone()
            if row and row["id"] not in matched_program_ids:
                conn.execute(
                    "UPDATE programs SET combined_score = ? WHERE id = ?",
                    (score, row["id"]),
                )
                updated += 1

    conn.commit()
    conn.close()

    print(f"\nSynced {updated} BT scores → {evo_bt}")
    print(f"View in UI: shinka_visualize {run_path} --port 8889 --open")


def rejudge(
    run_dir: str,
    code_dir: str,
    output_db: str,
    judge_model: str,
    judge_temperature: float,
    task_spec: str,
    base_branch: str,
    dry_run: bool,
    limit: int,
    resume: bool,
    no_sync: bool = False,
):
    run_path = Path(run_dir).resolve()
    code_path = Path(code_dir).resolve()
    orig_db = str(run_path / "bt_scores.db")

    pairs = load_existing_pairs(orig_db)
    candidates = load_existing_candidates(orig_db)

    print(f"Original DB: {orig_db}")
    print(f"  {len(candidates)} candidates, {len(pairs)} pairs")
    print(f"Code repo: {code_path}")
    print(f"Base branch: {base_branch}")
    print(f"Judge model: {judge_model}")
    print(f"Output DB: {output_db}")
    print()

    if dry_run:
        print("DRY RUN — listing pairs:")
        for i, (a, b) in enumerate(pairs):
            branch_a = f"{BRANCH_PREFIX}{a}"
            branch_b = f"{BRANCH_PREFIX}{b}"
            exists_a = branch_exists(str(code_path), branch_a)
            exists_b = branch_exists(str(code_path), branch_b)
            status = "OK" if (exists_a and exists_b) else f"MISSING({'A' if not exists_a else ''}{'B' if not exists_b else ''})"
            print(f"  [{i+1:3d}] {a} vs {b}  [{status}]")
        return

    if limit > 0:
        pairs = pairs[:limit]

    # Initialize output DB (fresh or resume)
    engine = BTMMScoringEngine(db_path=output_db)

    # Register all candidates
    for cid in candidates:
        engine.get_score(cid)

    # If resuming, skip pairs that already exist in the output DB
    if resume:
        original_count = len(pairs)
        pairs = [(a, b) for a, b in pairs if not engine.comparison_exists(a, b)]
        print(f"Resuming: {original_count - len(pairs)} pairs already judged, {len(pairs)} remaining")

    if not pairs:
        print("No pairs to judge.")
        engine.print_rankings(top_n=20)
        engine.close()
        return

    # Initialize judge
    judge = PairwiseJudge(
        llm_model=judge_model,
        temperature=judge_temperature,
    )

    log_path = Path(output_db).with_suffix(".judge_log.txt")
    log_file = open(log_path, "a" if resume else "w")
    judge.log_file = log_file

    print(f"Judge log: {log_path}")
    print(f"\nStarting re-judging of {len(pairs)} pairs...\n")

    wins_total = 0
    losses_total = 0
    skipped = 0
    start_time = time.time()

    for i, (cand_a, cand_b) in enumerate(pairs):
        branch_a = f"{BRANCH_PREFIX}{cand_a}"
        branch_b = f"{BRANCH_PREFIX}{cand_b}"

        # Check branches exist
        if not branch_exists(str(code_path), branch_a):
            print(f"  [{i+1}/{len(pairs)}] SKIP {cand_a} vs {cand_b}: branch {branch_a} missing")
            skipped += 1
            continue
        if not branch_exists(str(code_path), branch_b):
            print(f"  [{i+1}/{len(pairs)}] SKIP {cand_a} vs {cand_b}: branch {branch_b} missing")
            skipped += 1
            continue

        # Get diffs
        diff_a = truncate_diff(get_diff(str(code_path), base_branch, branch_a))
        diff_b = truncate_diff(get_diff(str(code_path), base_branch, branch_b))

        context = {
            "evolution_objective": task_spec,
            "branch_a": branch_a,
            "branch_b": branch_b,
        }

        # Judge
        winner, reasoning = judge.compare(
            task_spec=task_spec,
            candidate_a=diff_a,
            candidate_b=diff_b,
            context=context,
        )

        # Record
        score_a, score_b = engine.record_comparison(cand_a, cand_b, winner, reasoning)

        if winner == "a":
            wins_total += 1
        else:
            losses_total += 1

        elapsed = time.time() - start_time
        rate = (i + 1 - skipped) / elapsed if elapsed > 0 else 0
        remaining = (len(pairs) - i - 1) / rate if rate > 0 else 0

        print(
            f"  [{i+1:3d}/{len(pairs)}] {cand_a} vs {cand_b}: "
            f"winner={winner} (scores: {score_a:.2f} vs {score_b:.2f})  "
            f"[{elapsed:.0f}s elapsed, ~{remaining:.0f}s remaining]"
        )

    log_file.close()

    elapsed = time.time() - start_time
    judge_stats = judge.get_statistics()

    print(f"\n{'='*70}")
    print(f"Re-judging complete!")
    print(f"  Judged: {len(pairs) - skipped} pairs")
    print(f"  Skipped: {skipped} (missing branches)")
    print(f"  Time: {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print(f"  LLM cost: ${judge_stats['total_cost']:.4f}")
    print(f"{'='*70}\n")

    engine.print_rankings(top_n=20)

    if not no_sync:
        sync_bt_to_evolution_db(run_dir, output_db)

    engine.close()


def main():
    parser = argparse.ArgumentParser(description="Re-judge existing pairwise comparisons")
    parser.add_argument("--run-dir", default=DEFAULT_RUN_DIR,
                        help="Path to the experiment run directory")
    parser.add_argument("--code-dir", default=DEFAULT_CODE_DIR,
                        help="Path to the target codebase with candidate branches")
    parser.add_argument("--output-db", default=None,
                        help="Output DB path (default: <run-dir>/bt_scores_rejudged.db)")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL,
                        help=f"LLM model for judging (default: {DEFAULT_JUDGE_MODEL})")
    parser.add_argument("--judge-temperature", type=float, default=0.0,
                        help="Judge temperature (default: 0.0)")
    parser.add_argument("--task-spec", default=DEFAULT_TASK_SPEC,
                        help="Task specification / evolution objective")
    parser.add_argument("--base-branch", default=DEFAULT_BASE_BRANCH,
                        help=f"Base branch for diffs (default: {DEFAULT_BASE_BRANCH})")
    parser.add_argument("--dry-run", action="store_true",
                        help="List pairs without judging")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit to first N pairs (0 = all)")
    parser.add_argument("--resume", action="store_true",
                        help="Skip pairs already in the output DB")
    parser.add_argument("--sync-only", action="store_true",
                        help="Skip judging, just sync existing BT scores to evolution_db_bt.sqlite")
    parser.add_argument("--bt-db", default=None,
                        help="BT scores DB to sync from (default: <run-dir>/bt_scores.db, or --output-db if set)")
    parser.add_argument("--no-sync", action="store_true",
                        help="Skip the evolution_db sync after judging")

    args = parser.parse_args()

    output_db = args.output_db or str(Path(args.run_dir) / "bt_scores_rejudged.db")

    if args.sync_only:
        bt_db = args.bt_db or output_db
        if not Path(bt_db).exists():
            bt_db = str(Path(args.run_dir) / "bt_scores.db")
        if not Path(bt_db).exists():
            print(f"Error: BT database not found. Tried: {bt_db}")
            sys.exit(1)
        print(f"Sync-only mode: syncing {bt_db} → evolution_db_bt.sqlite")
        sync_bt_to_evolution_db(args.run_dir, bt_db)
        return

    rejudge(
        run_dir=args.run_dir,
        code_dir=args.code_dir,
        output_db=output_db,
        judge_model=args.judge_model,
        judge_temperature=args.judge_temperature,
        task_spec=args.task_spec,
        base_branch=args.base_branch,
        dry_run=args.dry_run,
        limit=args.limit,
        resume=args.resume,
        no_sync=args.no_sync,
    )


if __name__ == "__main__":
    main()
