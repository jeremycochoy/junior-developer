import time
from junior_dev.judge import PairwiseJudge, JudgmentResult


def test_initialization():
    print("\n" + "="*70)
    print("TEST 1: Judge Initialization")
    print("="*70)
    
    judge = PairwiseJudge(llm_model="gpt-4")
    assert judge.llm_model == "gpt-4"
    assert judge.temperature == 0.0
    assert judge.total_comparisons == 0
    print("✓ Initialization test passed\n")


def test_randomized_ordering():
    print("\n" + "="*70)
    print("TEST 2: Randomized Ordering (Position Bias Check)")
    print("="*70)
    
    judge = PairwiseJudge(llm_model="mock")
    
    a_wins = 0
    iterations = 200
    
    for i in range(iterations):
        winner, _ = judge.compare("Test task", "candidate_a_text", "candidate_b_text")
        if winner == "a":
            a_wins += 1
    
    # Mock randomly picks Candidate 1 or 2, and swap is 50/50,
    # so A wins should be roughly 50%. Allow 30-70% range.
    a_rate = a_wins / iterations
    print(f"After {iterations} comparisons: A wins = {a_wins} ({a_rate:.0%})")
    assert 0.30 < a_rate < 0.70, f"Expected ~50% A wins, got {a_rate:.0%}"
    print("✓ Randomized ordering test passed\n")


def test_basic_comparison():
    print("\n" + "="*70)
    print("TEST 3: Basic Comparison")
    print("="*70)
    
    judge = PairwiseJudge(llm_model="mock")
    
    candidate_a = "def sort_numbers(nums): return sorted(nums)"
    candidate_b = "def sort_numbers(nums): # bubble sort... long implementation"
    
    winner, reasoning = judge.compare("Sort numbers efficiently", candidate_a, candidate_b)
    
    print(f"Winner: {winner}")
    print(f"Reasoning: {reasoning[:100]}...")
    
    assert winner in ("a", "b"), "Ties are not allowed; mock always picks a winner"
    assert len(reasoning) > 0
    print("✓ Basic comparison test passed\n")


def test_no_ties():
    print("\n" + "="*70)
    print("TEST 4: No Ties Allowed")
    print("="*70)
    
    judge = PairwiseJudge(llm_model="mock")
    candidate = "def hello(): return 'Hello World'"
    winner, reasoning = judge.compare("Greet the world", candidate, candidate)
    
    print(f"Winner: {winner}")
    assert winner in ("a", "b"), "Ties are forbidden; judge must always pick a/b"
    print("✓ No-ties test passed\n")


def test_with_context():
    print("\n" + "="*70)
    print("TEST 5: Comparison with Context")
    print("="*70)
    
    judge = PairwiseJudge(llm_model="mock")
    context = {
        "test_results_a": "All tests passed",
        "test_results_b": "2 tests failed",
        "performance_a": "10ms",
        "performance_b": "50ms",
    }
    
    winner, reasoning = judge.compare("Implement fast function", "fast", "slow", context)
    print(f"Winner: {winner}")
    assert winner in ("a", "b"), "Must pick a winner"
    print("✓ Context test passed\n")


def test_response_parsing():
    print("\n" + "="*70)
    print("TEST 6: Response Parsing")
    print("="*70)
    
    judge = PairwiseJudge(llm_model="mock")
    test_cases = [
        ("explanation:First is better\ncandidate:first\nconfidence:0.9", "first", 0.9),
        ("explanation:Second wins clearly\ncandidate:second\nconfidence:0.3", "second", 0.3),
        ("Some random text with no structure", "tie", 0.5),  # Unparseable → tie
        ("explanation:Reasoning here.\ncandidate:first\nconfidence:0.75", "first", 0.75),
    ]
    for response_text, expected_winner, expected_conf in test_cases:
        winner, reasoning, confidence = judge._parse_response(response_text)
        print(f"  Parsed: winner={winner} (expected: {expected_winner}), confidence={confidence:.2f} (expected: {expected_conf:.2f})")
        assert winner == expected_winner, f"Expected {expected_winner}, got {winner} for: {response_text}"
        assert abs(confidence - expected_conf) < 0.01, f"Expected confidence {expected_conf}, got {confidence}"
    
    print("✓ Response parsing test passed\n")


def test_statistics_tracking():
    print("\n" + "="*70)
    print("TEST 7: Statistics Tracking")
    print("="*70)
    
    judge = PairwiseJudge(llm_model="mock")
    assert judge.total_comparisons == 0
    
    for i in range(5):
        judge.compare(f"Task {i}", f"Solution A{i}", f"Solution B{i}")
    
    stats = judge.get_statistics()
    print(f"Total comparisons: {stats['total_comparisons']}")
    assert stats['total_comparisons'] == 5
    
    judge.reset_statistics()
    assert judge.total_comparisons == 0
    print("✓ Statistics tracking test passed\n")


def test_integration_with_bt():
    print("\n" + "="*70)
    print("TEST 8: Integration with BT-MM Engine")
    print("="*70)
    
    from junior_dev.scoring import BTMMScoringEngine
    import tempfile
    from pathlib import Path
    
    with tempfile.TemporaryDirectory() as tmpdir:
        judge = PairwiseJudge(llm_model="mock")
        engine = BTMMScoringEngine(db_path=str(Path(tmpdir) / "test.db"))
        
        solutions = {
            "bubble_sort": "def sort(x): # bubble sort...",
            "quick_sort": "def sort(x): # quicksort...",
            "merge_sort": "def sort(x): # mergesort...",
        }
        
        print("\nRunning tournament...")
        ids = list(solutions.keys())
        for i in range(len(ids)):
            for j in range(i+1, len(ids)):
                id_a, id_b = ids[i], ids[j]
                winner, reasoning = judge.compare("Sort efficiently", solutions[id_a], solutions[id_b])
                score_a, score_b = engine.record_comparison(id_a, id_b, winner, reasoning)
                print(f"  {id_a} vs {id_b}: {winner} wins (scores: {score_a:.1f}, {score_b:.1f})")
        
        print("\nFinal Rankings:")
        for rank, (id, score, stats) in enumerate(engine.get_rankings(), 1):
            print(f"  {rank}. {id}: {score:.2f}")
        
        engine.close()
    
    print("✓ Integration test passed\n")


def test_edge_cases():
    print("\n" + "="*70)
    print("TEST 9: Edge Cases")
    print("="*70)
    
    judge = PairwiseJudge(llm_model="mock")
    
    print("Test: Empty candidates")
    winner, _ = judge.compare("Test", "", "")
    assert winner in ("a", "b"), "Must pick a winner even for empty candidates"
    print("  ✓ Empty candidates handled")
    
    print("Test: Very long candidates")
    long_text = "x" * 10000
    winner, _ = judge.compare("Test", long_text, "short")
    assert winner in ("a", "b")
    print("  ✓ Long candidates handled")
    
    print("Test: Special characters")
    winner, _ = judge.compare("Test", "def func(): return '\\n\\t\"quotes\"'", "def func(): return 'normal'")
    assert winner in ("a", "b")
    print("  ✓ Special characters handled")
    
    print("✓ Edge cases test passed\n")


def test_detailed_judgment():
    print("\n" + "="*70)
    print("TEST 10: Detailed Judgment")
    print("="*70)
    
    judge = PairwiseJudge(llm_model="mock")
    result = judge.compare_detailed("Test task", "Solution A", "Solution B")
    
    print(f"Winner: {result.winner}")
    print(f"Confidence: {result.confidence}")
    
    assert isinstance(result, JudgmentResult)
    assert result.winner in ("a", "b"), "Ties are not allowed"
    assert 0.0 <= result.confidence <= 1.0
    
    result_dict = result.to_dict()
    assert 'winner' in result_dict
    print("✓ Detailed judgment test passed\n")


def run_all_tests():
    print("\n" + "="*70)
    print("PAIRWISE JUDGE - COMPREHENSIVE TEST SUITE")
    print("="*70)
    
    tests = [
        test_initialization,
        test_randomized_ordering,
        test_basic_comparison,
        test_no_ties,
        test_with_context,
        test_response_parsing,
        test_statistics_tracking,
        test_integration_with_bt,
        test_edge_cases,
        test_detailed_judgment,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"\n❌ {test.__name__} FAILED: {e}")
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