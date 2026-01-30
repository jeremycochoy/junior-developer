import argparse
import os
import subprocess
import time
from pathlib import Path

from junior_dev.git_manager import GitManager
from junior_dev.coding_agent import CodingAgent


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True, capture_output=True, text=True)


def _init_repo(repo: Path, base_branch: str) -> None:
    _run(["git", "init"], repo)
    _run(["git", "config", "user.email", "test@example.local"], repo)
    _run(["git", "config", "user.name", "Example Test"], repo)

    (repo / "README.md").write_text("# Example Test Repository\n\nThis repository is used for testing coding agents.\n")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-m", "Initial commit"], repo)
    _run(["git", "branch", "-M", base_branch], repo)


def run_once(
    repo: Path,
    base_branch: str,
    agent_type: str,
    timeout: int,
    candidate_id: str,
    prompt: str,
    allow_dirty: bool,
    cleanup_branch: bool,
    agent_args: list[str],
) -> int:
    print("="*60)
    print("EXAMPLE TEST")
    print("="*60)
    print(f"Repository: {repo}")
    print(f"Base branch: {base_branch}")
    print(f"Agent type: {agent_type}")
    print(f"Timeout: {timeout}s")
    print(f"Candidate ID: {candidate_id}")
    print()
    
    gm = GitManager(str(repo))
    if not allow_dirty and gm.has_uncommitted_changes():
        raise SystemExit("Repo has uncommitted changes (use --allow-dirty to override).")

    candidate_branch = f"candidate_{candidate_id}"

    print(f"[INFO] Checking out base branch: {base_branch}")
    if not gm.checkout_branch(base_branch):
        raise SystemExit(f"Base branch not found: {base_branch}")

    print(f"[INFO] Creating candidate branch: {candidate_branch}")
    if not gm.create_branch(candidate_branch, from_branch=base_branch):
        print(f"[INFO] Branch already exists, checking out...")
        gm.checkout_branch(candidate_branch)

    print(f"[INFO] Initializing {agent_type} agent...")
    agent = CodingAgent(agent_type=agent_type, timeout=timeout, working_dir=str(repo), agent_args=agent_args)
    if not agent.check_agent_available():
        print(f"AGENT NOT AVAILABLE: {agent_type}")
        print("Install the agent binary and ensure it is in PATH.")
        return 4

    print(f"[INFO] Agent prompt: {prompt}")
    
    target_file = repo / "example.py"
    if not target_file.exists():
        target_file.write_text('"""Example Python script for testing coding agents."""\n\n\ndef greet(name: str = "World") -> str:\n    """Return a greeting message."""\n    return f"Hello, {name}!"\n\n\nif __name__ == "__main__":\n    print(greet())\n')

    print(f"[INFO] Executing agent (timeout: {timeout}s)...")
    result = agent.execute(prompt, files=[str(target_file)])
    
    print(f"[INFO] Agent execution completed in {result.execution_time:.2f}s")
    if result.output:
        print("[AGENT OUTPUT]")
        print(result.output)
    if result.error:
        print("[AGENT ERROR]")
        print(result.error)
    
    if not result.success:
        print("AGENT FAILED")
        print(f"Exit code: {result.exit_code}")
        return 2

    if result.changes_made:
        print("[INFO] Staging changes...")
        gm.stage_all()
        print("[INFO] Committing changes...")
        committed = gm.commit(f"Example test: {candidate_id}", allow_empty=False)
        if not committed:
            print("COMMIT FAILED (no changes staged?)")
            return 3
        print("[INFO] Commit successful")
    else:
        print("[WARN] Agent reported no changes made")

    print("[INFO] Computing diff stats...")
    stats = gm.get_diff_stats(base_branch, candidate_branch)
    print("\n" + "="*60)
    print("TEST RESULT: OK")
    print("="*60)
    print(f"repo: {repo}")
    print(f"base: {base_branch}")
    print(f"candidate: {candidate_branch}")
    print(f"agent: {agent_type}")
    print(f"execution_time: {result.execution_time:.2f}s")
    print(f"diff_has_changes: {stats['has_changes']}")
    if stats["stats"].strip():
        print("\nDiff stats:")
        print(stats["stats"].rstrip())
    print("="*60)

    if cleanup_branch:
        gm.checkout_branch(base_branch)
        gm.delete_branch(candidate_branch, force=True)

    return 0


def main() -> int:
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()
    
    project_root = Path(__file__).parent.parent
    default_repo = project_root / "results" / "test_repos" / "example_test_repo"
    
    p = argparse.ArgumentParser(description="Example test for coding agents (Git + CodingAgent)")
    p.add_argument("--repo", type=str, default="", help=f"Path to a git repo (if empty, uses {default_repo})")
    p.add_argument("--base-branch", type=str, default="master")
    p.add_argument("--agent-type", type=str, default="pipeline", help="pipeline (only supported type)")
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--candidate-id", type=str, default="")
    p.add_argument("--prompt", type=str, default="Update the greet() function in example.py to return 'Hello, {name}! How are you?' instead of 'Hello, {name}!'.")
    p.add_argument("--agent-arg", action="append", default=[], help="Pass-through arg to the agent CLI (repeatable)")
    p.add_argument("--allow-dirty", action="store_true", help="Allow running with uncommitted changes")
    p.add_argument("--cleanup-branch", action="store_true", help="Delete the candidate branch at the end")
    p.add_argument("--reinit", action="store_true", help="Reinitialize the repo (deletes existing repo)")
    args = p.parse_args()

    candidate_id = args.candidate_id or str(int(time.time()))
    
    if args.repo:
        repo = Path(args.repo).resolve()
    else:
        repo = default_repo.resolve()
    
    if args.reinit and repo.exists():
        print(f"[INFO] Removing existing repo at {repo}")
        import shutil
        shutil.rmtree(repo)
    
    if not repo.exists() or not (repo / ".git").exists():
        print(f"[INFO] Initializing new repo at {repo}")
        repo.mkdir(parents=True, exist_ok=True)
        _init_repo(repo, args.base_branch)
    
    return run_once(
        repo=repo,
        base_branch=args.base_branch,
        agent_type=args.agent_type,
        timeout=args.timeout,
        candidate_id=candidate_id,
        prompt=args.prompt,
        allow_dirty=args.allow_dirty if args.repo else True,
        cleanup_branch=args.cleanup_branch,
        agent_args=args.agent_arg,
    )


if __name__ == "__main__":
    raise SystemExit(main())
