import tempfile
from pathlib import Path
from junior_dev.shinka.evaluate import evaluate_coding_agent_prompt

with tempfile.TemporaryDirectory() as tmpdir:
    results_dir = Path(tmpdir) / "results"
    results_dir.mkdir()
    
    codebase_dir = Path(tmpdir) / "test_codebase"
    codebase_dir.mkdir()
    
    import subprocess
    subprocess.run(["git", "init"], cwd=codebase_dir, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=codebase_dir)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=codebase_dir)
    
    (codebase_dir / "main.py").write_text("print('Hello World')")
    subprocess.run(["git", "add", "."], cwd=codebase_dir)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=codebase_dir)
    subprocess.run(["git", "branch", "-m", "master"], cwd=codebase_dir)
    
    import junior_dev
    package_dir = Path(junior_dev.__file__).parent
    initial_path = package_dir / "shinka" / "initial.py"
    
    print("Running evaluation test...")
    metrics = evaluate_coding_agent_prompt(
        program_path=str(initial_path),
        results_dir=str(results_dir),
        target_codebase=str(codebase_dir),
        bt_db_path=str(Path(tmpdir) / "test_bt.db"),
        num_comparisons=0,
        verbose=True
    )
    
    print("\n" + "="*70)
    print("TEST RESULTS")
    print("="*70)
    print(f"Combined Score: {metrics['combined_score']}")
    print(f"Runtime: {metrics['runtime']:.2f}s")
    print(f"Public Metrics: {metrics['public']}")
    print("="*70)

