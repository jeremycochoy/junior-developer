import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

GIT_COMMAND_TIMEOUT_SECONDS = 30
PROTECTED_BRANCHES = {"master", "main"}


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
            return subprocess.run(
                ["git"] + args,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                check=check,
                timeout=GIT_COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Git command timed out after {GIT_COMMAND_TIMEOUT_SECONDS}s: {' '.join(args)}")
        except subprocess.CalledProcessError as e:
            if check:
                raise RuntimeError(f"Git command failed: {' '.join(args)}\n{e.stderr}")
            return subprocess.CompletedProcess(
                args=e.cmd, returncode=e.returncode,
                stdout=e.stdout or "", stderr=e.stderr or "",
            )

    # ── Branch operations ───────────────────────────────────────────

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
        if branch_name in PROTECTED_BRANCHES:
            return False
        flag = "-D" if force else "-d"
        result = self._run_git(["branch", flag, branch_name], check=False)
        return result.returncode == 0

    def list_branches(self, pattern: Optional[str] = None) -> List[str]:
        args = ["branch", "--list"]
        if pattern:
            args.append(pattern)
        result = self._run_git(args, check=False)
        return [b.strip().lstrip("* ").strip() for b in result.stdout.split("\n") if b.strip()]

    # ── Diff operations ─────────────────────────────────────────────

    def get_diff(self, base_branch: str, compare_branch: str) -> str:
        result = self._run_git(["diff", f"{base_branch}..{compare_branch}"], check=False)
        return result.stdout

    def get_diff_stats(self, base_branch: str, compare_branch: str) -> Dict[str, Any]:
        result = self._run_git(
            ["diff", "--stat", f"{base_branch}..{compare_branch}"],
            check=False,
        )
        return {"stats": result.stdout, "has_changes": bool(result.stdout.strip())}

    # ── Staging & commit ────────────────────────────────────────────

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

    # ── Status & info ───────────────────────────────────────────────

    def has_uncommitted_changes(self) -> bool:
        result = self._run_git(["status", "--porcelain"], check=False)
        return bool(result.stdout.strip())

    def get_commit_hash(self, branch: Optional[str] = None) -> Optional[str]:
        ref = branch or "HEAD"
        result = self._run_git(["rev-parse", ref], check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    # ── Reset & clean ───────────────────────────────────────────────

    def reset_hard(self, branch: str = "HEAD") -> bool:
        result = self._run_git(["reset", "--hard", branch], check=False)
        return result.returncode == 0

    def clean_untracked(self) -> bool:
        result = self._run_git(["clean", "-fd"], check=False)
        return result.returncode == 0
