import subprocess
import os
from pathlib import Path
from typing import Optional, List, Tuple


class GitManager:
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        if not self.repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")
        
        if not self._is_git_repo():
            raise ValueError(f"Not a git repository: {repo_path}")
    
    def _is_git_repo(self) -> bool:
        git_dir = self.repo_path / ".git"
        return git_dir.exists() or git_dir.is_file()
    
    def _run_git(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                check=check,
                timeout=30
            )
            return result
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Git command timed out: {' '.join(args)}")
        except subprocess.CalledProcessError as e:
            if check:
                raise RuntimeError(f"Git command failed: {' '.join(args)}\n{e.stderr}")
            return e
    
    def get_current_branch(self) -> str:
        result = self._run_git(["branch", "--show-current"])
        return result.stdout.strip()
    
    def branch_exists(self, branch_name: str) -> bool:
        result = self._run_git(["branch", "--list", branch_name], check=False)
        return bool(result.stdout.strip())
    
    def create_branch(self, branch_name: str, from_branch: str = "master") -> bool:
        if self.branch_exists(branch_name):
            return False
        
        self.checkout_branch(from_branch)
        result = self._run_git(["checkout", "-b", branch_name], check=False)
        return result.returncode == 0
    
    def checkout_branch(self, branch_name: str) -> bool:
        result = self._run_git(["checkout", branch_name], check=False)
        return result.returncode == 0
    
    def delete_branch(self, branch_name: str, force: bool = False) -> bool:
        if branch_name == "master" or branch_name == "main":
            return False
        
        args = ["branch", "-D" if force else "-d", branch_name]
        result = self._run_git(args, check=False)
        return result.returncode == 0
    
    def get_diff(self, base_branch: str, compare_branch: str) -> str:
        result = self._run_git(["diff", f"{base_branch}..{compare_branch}"], check=False)
        return result.stdout
    
    def get_diff_stats(self, base_branch: str, compare_branch: str) -> dict:
        result = self._run_git(
            ["diff", "--stat", f"{base_branch}..{compare_branch}"],
            check=False
        )
        return {"stats": result.stdout, "has_changes": bool(result.stdout.strip())}
    
    def stage_all(self) -> bool:
        result = self._run_git(["add", "."], check=False)
        return result.returncode == 0
    
    def stage_files(self, files: List[str]) -> bool:
        result = self._run_git(["add"] + files, check=False)
        return result.returncode == 0
    
    def commit(self, message: str, allow_empty: bool = False) -> bool:
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")
        
        result = self._run_git(args, check=False)
        return result.returncode == 0
    
    def has_uncommitted_changes(self) -> bool:
        result = self._run_git(["status", "--porcelain"], check=False)
        return bool(result.stdout.strip())
    
    def get_commit_hash(self, branch: Optional[str] = None) -> Optional[str]:
        ref = branch if branch else "HEAD"
        result = self._run_git(["rev-parse", ref], check=False)
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    
    def list_branches(self, pattern: Optional[str] = None) -> List[str]:
        args = ["branch", "--list"]
        if pattern:
            args.append(pattern)
        
        result = self._run_git(args, check=False)
        branches = [b.strip().replace("*", "").strip() for b in result.stdout.split("\n") if b.strip()]
        return branches
    
    def reset_hard(self, branch: str = "HEAD") -> bool:
        result = self._run_git(["reset", "--hard", branch], check=False)
        return result.returncode == 0
    
    def clean_untracked(self, force: bool = False) -> bool:
        args = ["clean", "-fd" if force else "-fd"]
        result = self._run_git(args, check=False)
        return result.returncode == 0

