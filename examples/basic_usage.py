import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from junior_dev import BTMMScoringEngine, PairwiseJudge

def main():
    print("="*70)
    print("Junior Developer - Basic Usage Example")
    print("="*70)
    
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("\n⚠️  No API key found. Running in MOCK mode.")
        print("   Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env for real LLM")
        use_real_llm = False
    else:
        print("\n✅ API key found - using real LLM")
        use_real_llm = True
    
    results_dir = Path(__file__).parent.parent / "results"
    results_dir.mkdir(exist_ok=True)
    db_path = results_dir / "example.db"
    
    print("\n1. Initializing BT-MM Scoring Engine...")
    engine = BTMMScoringEngine(
        db_path=str(db_path),
        convergence_tol=1e-6,
        max_iterations=100
    )
    print(f"   ✓ Engine initialized (db: {db_path})")
    
    if use_real_llm:
        model = "gpt-4o-mini" if os.getenv("OPENAI_API_KEY") else "claude-3-5-sonnet-20241022"
        print(f"\n2. Initializing Pairwise Judge (Real LLM: {model})...")
    else:
        model = "mock"
        print("\n2. Initializing Pairwise Judge (Mock Mode)...")
    
    judge = PairwiseJudge(llm_model=model)
    print("   ✓ Judge initialized")
    
    task_spec = "Refactor visualization code to a separate class"
    
    candidates = {
        "prompt_v1": "Move all visualization functions to a new VisualizationKit class",
        "prompt_v2": "Create vis_utils.py module with helper functions",
        "prompt_v3": "Refactor using abstract base class for different visualizations",
        "prompt_v4": "Extract visualization logic into separate package",
    }
    
    print(f"\n3. Task: {task_spec}")
    print(f"   Candidates: {len(candidates)}")
    
    print("\n4. Running Pairwise Comparisons...")
    comparisons = [
        ("prompt_v1", "prompt_v2"),
        ("prompt_v1", "prompt_v3"),
        ("prompt_v2", "prompt_v3"),
        ("prompt_v2", "prompt_v4"),
        ("prompt_v3", "prompt_v4"),
        ("prompt_v1", "prompt_v4"),
    ]
    
    for i, (cand_a, cand_b) in enumerate(comparisons, 1):
        print(f"\n   Comparison {i}: {cand_a} vs {cand_b}")
        
        result = judge.compare_detailed(
            task_spec=task_spec,
            candidate_a=candidates[cand_a],
            candidate_b=candidates[cand_b],
            context=None
        )
        
        print(f"   → Winner: {result.winner}")
        print(f"   → Reasoning: {result.reasoning}")
        
        score_a, score_b = engine.record_comparison(
            candidate_a=cand_a,
            candidate_b=cand_b,
            winner=result.winner,
            reasoning=result.reasoning
        )
        
        print(f"   → Scores: {cand_a}={score_a:.4f}, {cand_b}={score_b:.4f}")
    
    print("\n5. Final Rankings (BT-MM Scores):")
    print("="*70)
    rankings = engine.get_rankings()
    
    for rank, (cand_id, bt_score, stats) in enumerate(rankings, 1):
        print(f"{rank}. {cand_id:15s} "
              f"Score: {bt_score:.4f}  "
              f"W/L/T: {stats['wins']}/{stats['losses']}/{stats['ties']}  "
              f"Win Rate: {stats['win_rate']:.1%}")
    
    print("\n6. Detailed Statistics:")
    print("="*70)
    winner_id, winner_score, winner_stats = rankings[0]
    print(f"Best Candidate: {winner_id}")
    print(f"  BT-MM Score: {winner_score:.4f}")
    print(f"  Comparisons: {winner_stats['comparisons']}")
    print(f"  Wins: {winner_stats['wins']}")
    print(f"  Losses: {winner_stats['losses']}")
    print(f"  Ties: {winner_stats['ties']}")
    print(f"  Win Rate: {winner_stats['win_rate']:.1%}")
    
    print("\n7. Convergence Information:")
    print("="*70)
    print(f"  Total Candidates: {len(rankings)}")
    print(f"  Total Comparisons: {len(comparisons)}")
    print(f"  Algorithm: Bradley-Terry with Minorization-Maximization")
    print(f"  Convergence Tolerance: {engine.convergence_tol}")
    print(f"  Max Iterations: {engine.max_iterations}")
    
    print("\n8. Database Verification:")
    print("="*70)
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM bt_scores")
    num_candidates = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM comparisons")
    num_comparisons = cursor.fetchone()[0]
    
    print(f"  Database: {db_path}")
    print(f"  Candidates in DB: {num_candidates}")
    print(f"  Comparisons in DB: {num_comparisons}")
    
    if num_candidates > 0:
        cursor.execute("SELECT candidate_id, bt_score FROM bt_scores ORDER BY bt_score DESC")
        print("\n  Candidate Scores:")
        for row in cursor.fetchall():
            print(f"    {row[0]:15s} -> {row[1]:.4f}")
    
    conn.close()
    
    engine.close()
    print("\n✓ Example completed successfully!")
    print(f"✓ Database saved to: {db_path}")
    print("="*70)

if __name__ == "__main__":
    main()

