import tempfile
import subprocess
from pathlib import Path
from junior_dev.git_manager import GitManager


def test_initialization():
    print("\n" + "="*70)
    print("TEST 1: GitManager Initialization")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "test_repo"
        repo_path.mkdir()
        
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path)
        
        (repo_path / "README.md").write_text("# Test Repo")
        subprocess.run(["git", "add", "."], cwd=repo_path)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path)
        subprocess.run(["git", "branch", "-m", "master"], cwd=repo_path)
        
        manager = GitManager(str(repo_path))
        assert manager.repo_path == repo_path.resolve()
        
        current_branch = manager.get_current_branch()
        assert current_branch == "master"
        
    print("✓ Initialization test passed\n")


def test_branch_operations():
    print("\n" + "="*70)
    print("TEST 2: Branch Operations")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "test_repo"
        repo_path.mkdir()
        
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path)
        
        (repo_path / "README.md").write_text("# Test Repo")
        subprocess.run(["git", "add", "."], cwd=repo_path)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path)
        subprocess.run(["git", "branch", "-m", "master"], cwd=repo_path)
        
        manager = GitManager(str(repo_path))
        
        assert manager.create_branch("feature/test") == True
        assert manager.branch_exists("feature/test") == True
        
        assert manager.checkout_branch("feature/test") == True
        assert manager.get_current_branch() == "feature/test"
        
        assert manager.checkout_branch("master") == True
        assert manager.get_current_branch() == "master"
        
    print("✓ Branch operations test passed\n")


def test_diff_operations():
    print("\n" + "="*70)
    print("TEST 3: Diff Operations")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "test_repo"
        repo_path.mkdir()
        
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path)
        
        (repo_path / "README.md").write_text("# Test Repo")
        subprocess.run(["git", "add", "."], cwd=repo_path)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path)
        subprocess.run(["git", "branch", "-m", "master"], cwd=repo_path)
        
        manager = GitManager(str(repo_path))
        
        manager.create_branch("feature/test")
        manager.checkout_branch("feature/test")
        
        (repo_path / "new_file.py").write_text("print('hello')")
        manager.stage_all()
        manager.commit("Add new file")
        
        diff = manager.get_diff("master", "feature/test")
        assert "new_file.py" in diff or "hello" in diff
        
        stats = manager.get_diff_stats("master", "feature/test")
        assert stats["has_changes"] == True
        
    print("✓ Diff operations test passed\n")


def test_commit_operations():
    print("\n" + "="*70)
    print("TEST 4: Commit Operations")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "test_repo"
        repo_path.mkdir()
        
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path)
        
        (repo_path / "README.md").write_text("# Test Repo")
        subprocess.run(["git", "add", "."], cwd=repo_path)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path)
        subprocess.run(["git", "branch", "-m", "master"], cwd=repo_path)
        
        manager = GitManager(str(repo_path))
        
        assert manager.has_uncommitted_changes() == False
        
        (repo_path / "test.txt").write_text("test content")
        assert manager.has_uncommitted_changes() == True
        
        manager.stage_all()
        assert manager.commit("Add test file") == True
        assert manager.has_uncommitted_changes() == False
        
        commit_hash = manager.get_commit_hash()
        assert commit_hash is not None
        assert len(commit_hash) == 40
        
    print("✓ Commit operations test passed\n")


def test_list_branches():
    print("\n" + "="*70)
    print("TEST 5: List Branches")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "test_repo"
        repo_path.mkdir()
        
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path)
        
        (repo_path / "README.md").write_text("# Test Repo")
        subprocess.run(["git", "add", "."], cwd=repo_path)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path)
        subprocess.run(["git", "branch", "-m", "master"], cwd=repo_path)
        
        manager = GitManager(str(repo_path))
        
        manager.create_branch("feature/branch1")
        manager.create_branch("feature/branch2")
        
        branches = manager.list_branches()
        assert "master" in branches
        assert "feature/branch1" in branches
        assert "feature/branch2" in branches
        
        feature_branches = manager.list_branches("feature/*")
        assert len(feature_branches) >= 2
        
    print("✓ List branches test passed\n")


if __name__ == "__main__":
    test_initialization()
    test_branch_operations()
    test_diff_operations()
    test_commit_operations()
    test_list_branches()
    print("\n" + "="*70)
    print("ALL GIT MANAGER TESTS PASSED")
    print("="*70 + "\n")

