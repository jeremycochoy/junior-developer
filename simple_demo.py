"""
Simple Demo: ELO + Pairwise Judge Integration

Demonstrates the complete Milestone 1 system:
1. Create solutions
2. Use LLM to compare them pairwise
3. Update ELO scores
4. Display rankings

Run: python simple_demo.py
"""

from elo_scoring_engine import ELOScoringEngine
from pairwise_judge import PairwiseJudge
import tempfile
from pathlib import Path


def main():
    print("\n" + "="*70)
    print("MILESTONE 1 DEMO: ELO + Pairwise Judge")
    print("="*70)
    
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "demo.db"
        
        # Initialize systems
        print("\n1. Initializing systems...")
        engine = ELOScoringEngine(str(db_path), verbose=False)
        judge = PairwiseJudge(llm_model="mock", verbose=False)  # Use mock for demo
        print("   ✓ ELO Engine ready")
        print("   ✓ Pairwise Judge ready")
        
        # Define task and solutions
        task_spec = """
Task: Implement a function to find the maximum element in a list.
Requirements:
- Handle empty lists
- Handle negative numbers
- Efficient implementation
"""
        
        solutions = {
            "builtin": """
def find_max(nums):
    if not nums:
        return None
    return max(nums)
""",
            "manual_loop": """
def find_max(nums):
    if not nums:
        return None
    max_val = nums[0]
    for num in nums:
        if num > max_val:
            max_val = num
    return max_val
""",
            "reduce": """
def find_max(nums):
    if not nums:
        return None
    from functools import reduce
    return reduce(lambda a, b: a if a > b else b, nums)
""",
            "sorted": """
def find_max(nums):
    if not nums:
        return None
    return sorted(nums)[-1]  # Inefficient but works
""",
        }
        
        print(f"\n2. Tournament with {len(solutions)} solutions:")
        for name in solutions:
            print(f"   - {name}")
        
        # Run tournament
        print("\n3. Running pairwise comparisons...")
        ids = list(solutions.keys())
        comparisons = 0
        
        for i in range(len(ids)):
            for j in range(i+1, len(ids)):
                id_a, id_b = ids[i], ids[j]
                comparisons += 1
                
                print(f"\n   Comparison #{comparisons}: {id_a} vs {id_b}")
                
                # Judge
                winner, reasoning = judge.compare(
                    task_spec=task_spec,
                    candidate_a=solutions[id_a],
                    candidate_b=solutions[id_b],
                )
                
                # Update ELO
                elo_a, elo_b = engine.record_comparison(
                    id_a, id_b, winner, reasoning[:100]
                )
                
                print(f"      Winner: {winner}")
                print(f"      ELOs: {id_a}={elo_a:.1f}, {id_b}={elo_b:.1f}")
        
        # Display final rankings
        print("\n" + "="*70)
        print("4. FINAL RANKINGS")
        print("="*70)
        engine.print_rankings(top_n=10)
        
        # Show statistics
        judge_stats = judge.get_statistics()
        print("Judge Statistics:")
        print(f"  Total comparisons: {judge_stats['total_comparisons']}")
        print(f"  Total cost: ${judge_stats['total_cost']:.4f}")
        
        # Show detailed stats for winner
        rankings = engine.get_rankings()
        if rankings:
            winner_id, winner_elo, winner_stats = rankings[0]
            print(f"\n🏆 Champion: {winner_id}")
            print(f"   ELO: {winner_elo:.1f}")
            print(f"   Record: {winner_stats['wins']}W-{winner_stats['losses']}L-{winner_stats['ties']}T")
            print(f"   Win Rate: {winner_stats['win_rate']:.1%}")
        
        engine.close()
    
    print("\n" + "="*70)
    print("✅ DEMO COMPLETE")
    print("="*70)
    print("\nMilestone 1 components working together:")
    print("  ✓ ELO Scoring Engine")
    print("  ✓ Pairwise Judge")
    print("  ✓ Integration & Rankings")
    print("\nReady for Milestone 2: Git Integration!")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
    