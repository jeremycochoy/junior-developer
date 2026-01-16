import time
import tempfile
import json
from pathlib import Path
from elo_scoring_engine import ELOScoringEngine, ELOStats, ComparisonResult


def test_initialization():
    print("\n" + "="*70)
    print("TEST 1: Initialization")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        
        engine = ELOScoringEngine(
            db_path=str(db_path),
            k_factor=32.0,
            initial_elo=1500.0,
            verbose=True
        )
        
        assert engine.k_factor == 32.0
        assert engine.initial_elo == 1500.0
        assert engine.db_path.exists()
        
        engine.close()
        
    print("✓ Initialization test passed\n")


def test_basic_elo_calculations():
    """Test basic ELO score updates."""
    print("\n" + "="*70)
    print("TEST 2: Basic ELO Calculations")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        engine = ELOScoringEngine(db_path=str(db_path), verbose=True)
        
        print("\nInitializing candidates...")
        candidates = ["prog_a", "prog_b", "prog_c"]
        for cand in candidates:
            elo = engine.get_elo(cand)
            print(f"  {cand}: {elo:.1f}")
            assert elo == 1500.0, f"Expected 1500.0, got {elo}"
        
        print("\nTest: A (1500) vs B (1500) -> A wins")
        elo_a, elo_b = engine.record_comparison("prog_a", "prog_b", "a", "A is better")
        print(f"  Result: A={elo_a:.1f}, B={elo_b:.1f}")
        assert elo_a > 1500.0, "Winner should gain points"
        assert elo_b < 1500.0, "Loser should lose points"
        assert abs((elo_a - 1500.0) + (elo_b - 1500.0)) < 0.01, "Points should be conserved"
        
        print("\nTest: C (1500) vs B vs C wins")
        elo_c, elo_b2 = engine.record_comparison("prog_c", "prog_b", "a", "C is better")
        print(f"  Result: C={elo_c:.1f}, B={elo_b2:.1f}")
        assert elo_c > 1500.0
        assert elo_b2 < elo_b  # B loses again
        
        print("\nTest: A vs C -> Tie")
        elo_a2, elo_c2 = engine.record_comparison("prog_a", "prog_c", "tie", "Both equal")
        print(f"  Result: A={elo_a2:.1f}, C={elo_c2:.1f}")
        
        print("\nFinal Rankings:")
        rankings = engine.get_rankings()
        for rank, (cand, elo, stats) in enumerate(rankings, 1):
            print(f"  {rank}. {cand}: {elo:.1f} ({stats['wins']}W-{stats['losses']}L-{stats['ties']}T)")
        
        engine.close()
        
    print("✓ Basic ELO calculations test passed\n")


def test_comparison_caching():
    print("\n" + "="*70)
    print("TEST 3: Comparison Caching")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        engine = ELOScoringEngine(db_path=str(db_path), verbose=True)
        
        print("\nFirst comparison: A vs B")
        elo_a1, elo_b1 = engine.record_comparison("prog_a", "prog_b", "a")
        
        print("\nChecking cache...")
        assert engine.comparison_exists("prog_a", "prog_b"), "Should be cached"
        assert engine.comparison_exists("prog_b", "prog_a"), "Should work in reverse"
        
        cached = engine.get_comparison("prog_a", "prog_b")
        assert cached is not None
        print(f"  Cached result: {cached.winner}, ELO changes: {cached.elo_a_after - cached.elo_a_before:.1f}")
        
        print("\nAttempting duplicate comparison...")
        elo_a2, elo_b2 = engine.record_comparison("prog_a", "prog_b", "b")  # Different winner!
        assert elo_a2 == elo_a1, "ELO should not change on duplicate"
        assert elo_b2 == elo_b1, "ELO should not change on duplicate"
        
        engine.close()
        
    print("✓ Comparison caching test passed\n")


def test_statistics_tracking():
    print("\n" + "="*70)
    print("TEST 4: Statistics Tracking")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        engine = ELOScoringEngine(db_path=str(db_path), verbose=True)
        
        print("\nRunning mini tournament...")
        engine.record_comparison("a", "b", "a")  # A wins
        engine.record_comparison("a", "c", "a")  # A wins
        engine.record_comparison("a", "d", "tie")  # A ties
        engine.record_comparison("b", "c", "b")  # B wins
        
        print("\nChecking stats for 'a':")
        stats = engine.get_stats("a")
        assert stats is not None
        print(f"  ELO: {stats.elo_score:.1f}")
        print(f"  Record: {stats.wins}W-{stats.losses}L-{stats.ties}T")
        print(f"  Win Rate: {stats.win_rate:.1%}")
        print(f"  Comparisons: {stats.num_comparisons}")
        
        assert stats.wins == 2, f"Expected 2 wins, got {stats.wins}"
        assert stats.losses == 0, f"Expected 0 losses, got {stats.losses}"
        assert stats.ties == 1, f"Expected 1 tie, got {stats.ties}"
        assert stats.num_comparisons == 3, f"Expected 3 comparisons, got {stats.num_comparisons}"
        assert 0.8 < stats.win_rate < 0.9, f"Win rate should be ~0.833, got {stats.win_rate}"
        
        engine.close()
        
    print("✓ Statistics tracking test passed\n")


def test_rankings_and_filtering():
    print("\n" + "="*70)
    print("TEST 5: Rankings and Filtering")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        engine = ELOScoringEngine(db_path=str(db_path), verbose=True)

        print("\nCreating tournament...")
        engine.record_comparison("champion", "player1", "a")
        engine.record_comparison("champion", "player2", "a")
        engine.record_comparison("champion", "player3", "a")
        
        engine.record_comparison("strong", "player1", "a")
        engine.record_comparison("strong", "player2", "a")
        engine.record_comparison("strong", "champion", "b")
        
        engine.record_comparison("average", "player1", "a")
        engine.record_comparison("average", "player2", "b")
        
        engine.record_comparison("weak", "player1", "b")
        engine.record_comparison("weak", "player2", "b")
        
        print("\nTop 3 rankings:")
        top_3 = engine.get_rankings(top_n=3)
        for rank, (cand, elo, stats) in enumerate(top_3, 1):
            print(f"  {rank}. {cand}: {elo:.1f}")
        assert len(top_3) == 3
        assert top_3[0][0] == "champion", "Champion should be #1"
        
        print("\nCandidates with at least 2 comparisons:")
        filtered = engine.get_rankings(min_comparisons=2)
        print(f"  Found {len(filtered)} candidates")
        for cand, elo, stats in filtered:
            print(f"    {cand}: {stats['comparisons']} comparisons")
            assert stats['comparisons'] >= 2
        
        engine.close()
        
    print("✓ Rankings and filtering test passed\n")


def test_random_sampling():
    print("\n" + "="*70)
    print("TEST 6: Random Candidate Sampling")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        engine = ELOScoringEngine(db_path=str(db_path), verbose=True)
        
        print("\nCreating 10 candidates...")
        for i in range(10):
            engine.get_elo(f"prog_{i}")
        
        print("\nSampling 5 random candidates:")
        sample = engine.get_random_candidates(n=5)
        print(f"  {sample}")
        assert len(sample) == 5
        assert len(set(sample)) == 5, "Should be unique"
        
        print("\nSampling 3, excluding first 5:")
        sample = engine.get_random_candidates(n=3, exclude=[f"prog_{i}" for i in range(5)])
        print(f"  {sample}")
        assert len(sample) == 3
        for cand in sample:
            assert not cand.startswith("prog_0") and not cand.startswith("prog_1")
        
        engine.close()
        
    print("✓ Random sampling test passed\n")


def test_comparison_history():
    print("\n" + "="*70)
    print("TEST 7: Comparison History")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        engine = ELOScoringEngine(db_path=str(db_path), verbose=True)
        
        print("\nCreating comparison history for 'prog_a'...")
        engine.record_comparison("prog_a", "prog_b", "a", "A wins round 1")
        time.sleep(0.01)  # Small delay for timestamp difference
        engine.record_comparison("prog_a", "prog_c", "tie", "Tie round 2")
        time.sleep(0.01)
        engine.record_comparison("prog_a", "prog_d", "b", "A loses round 3")
        
        history = engine.get_comparison_history("prog_a")
        print(f"\nFound {len(history)} comparisons:")
        for comp in history:
            print(f"  {comp.candidate_a} vs {comp.candidate_b}: {comp.winner}")
            print(f"    Reasoning: {comp.judge_reasoning}")
        
        assert len(history) == 3
        assert "round 3" in history[0].judge_reasoning
        
        engine.close()
        
    print("✓ Comparison history test passed\n")


def test_export_import():
    print("\n" + "="*70)
    print("TEST 8: Data Export")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        engine = ELOScoringEngine(db_path=str(db_path), verbose=True)
        
        print("\nCreating test data...")
        engine.record_comparison("a", "b", "a")
        engine.record_comparison("a", "c", "a")
        engine.record_comparison("b", "c", "tie")
        
        print("\nExporting data...")
        data = engine.export_data()
        
        print(f"\nExport summary:")
        print(f"  Total candidates: {data['metadata']['total_candidates']}")
        print(f"  Total comparisons: {data['metadata']['total_comparisons']}")
        print(f"  K-factor: {data['metadata']['k_factor']}")
        
        export_file = Path(tmpdir) / "export.json"
        with open(export_file, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"\nExported to: {export_file}")
        print(f"  File size: {export_file.stat().st_size} bytes")
        
        assert 'scores' in data
        assert 'comparisons' in data
        assert 'metadata' in data
        assert len(data['scores']) == 3
        assert len(data['comparisons']) == 3
        
        engine.close()
        
    print("✓ Export test passed\n")


def test_edge_cases():
    print("\n" + "="*70)
    print("TEST 9: Edge Cases and Error Handling")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        engine = ELOScoringEngine(db_path=str(db_path), verbose=True)
        
        print("\nTest: Invalid winner value")
        try:
            engine.record_comparison("a", "b", "invalid")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            print(f"  ✓ Correctly raised ValueError: {e}")
        
        print("\nTest: Self-comparison")
        elo_before = engine.get_elo("self")
        elo_a, elo_b = engine.record_comparison("self", "self", "tie")
        print(f"  Self vs Self: {elo_before:.1f} → {elo_a:.1f}")
        assert abs(elo_a - elo_before) < 1.0
        
        print("\nTest: Empty candidate ID")
        elo = engine.get_elo("")
        print(f"  Empty string ELO: {elo:.1f}")
        assert elo == 1500.0
        
        print("\nTest: Very long candidate ID")
        long_id = "x" * 1000
        elo = engine.get_elo(long_id)
        print(f"  Long ID ELO: {elo:.1f}")
        assert elo == 1500.0

        print("\nTest: Non-existent candidate stats")
        stats = engine.get_stats("does_not_exist")
        assert stats is None
        print("  ✓ Correctly returned None")
        
        engine_empty = ELOScoringEngine(db_path=str(Path(tmpdir) / "empty.db"))
        rankings = engine_empty.get_rankings()
        assert len(rankings) == 0
        print("  ✓ Empty rankings work correctly")
        engine_empty.close()
        
        engine.close()
        
    print("✓ Edge cases test passed\n")


def test_performance():
    print("\n" + "="*70)
    print("TEST 10: Performance Benchmark")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        engine = ELOScoringEngine(db_path=str(db_path), verbose=False)
        
        n_candidates = 100
        print(f"\nCreating {n_candidates} candidates...")
        start = time.time()
        for i in range(n_candidates):
            engine.get_elo(f"prog_{i:03d}")
        elapsed = time.time() - start
        print(f"  Time: {elapsed:.3f}s ({n_candidates/elapsed:.0f} candidates/s)")
        
        n_comparisons = 500
        print(f"\nRunning {n_comparisons} comparisons...")
        start = time.time()
        import random
        for _ in range(n_comparisons):
            a = f"prog_{random.randint(0, n_candidates-1):03d}"
            b = f"prog_{random.randint(0, n_candidates-1):03d}"
            if a != b and not engine.comparison_exists(a, b):
                winner = random.choice(["a", "b", "tie"])
                engine.record_comparison(a, b, winner)
        elapsed = time.time() - start
        print(f"  Time: {elapsed:.3f}s ({n_comparisons/elapsed:.0f} comparisons/s)")
        
        print(f"\nQuerying rankings...")
        start = time.time()
        rankings = engine.get_rankings(top_n=10)
        elapsed = time.time() - start
        print(f"  Time: {elapsed:.6f}s")
        
        print(f"\nRandom sampling...")
        start = time.time()
        for _ in range(100):
            engine.get_random_candidates(n=5)
        elapsed = time.time() - start
        print(f"  Time: {elapsed:.3f}s (100 samples)")
        
        engine.close()
        
    print("✓ Performance test passed\n")


def run_all_tests():
    print("\n" + "="*70)
    print("ELO SCORING ENGINE - COMPREHENSIVE TEST SUITE")
    print("="*70)
    
    tests = [
        test_initialization,
        test_basic_elo_calculations,
        test_comparison_caching,
        test_statistics_tracking,
        test_rankings_and_filtering,
        test_random_sampling,
        test_comparison_history,
        test_export_import,
        test_edge_cases,
        test_performance,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"\n❌ {test.__name__} FAILED:")
            print(f"   {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"  Passed: {passed}/{len(tests)}")
    print(f"  Failed: {failed}/{len(tests)}")
    
    if failed == 0:
        print("\n✅ ALL TESTS PASSED!")
    else:
        print(f"\n❌ {failed} TEST(S) FAILED")
    print("="*70 + "\n")


if __name__ == "__main__":
    run_all_tests()
