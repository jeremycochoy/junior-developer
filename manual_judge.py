import subprocess
import sys
sys.path.insert(0, "/home/jupyter/JuniorDeveloper")

from junior_dev.git_manager import GitManager
from junior_dev.judge import PairwiseJudge
from junior_dev.shinka.evaluate import truncate_diff
from dotenv import load_dotenv

load_dotenv()

# --- Config ---
REPO = "/home/jupyter/JuniorDeveloper/results/rnd/2026.02.16084727_default/code"
BASE_BRANCH = "development"
BRANCH_A = "origin/feature/refactor_visualization"  
BRANCH_B = "candidate_gen_47_main"
TASK = "Refactor visualization code out of the Trainer class into a dedicated class, improving modularity and maintainability while preserving full backward compatibility. Do not break any feature."

print("Fetching feature/refactor_visualization from origin...")
subprocess.run(
    ["git", "fetch", "origin", "feature/refactor_visualization"],
    cwd=REPO, check=True, capture_output=True,
)
print("Done.\n")

# --- Get diffs ---
git = GitManager(REPO)

diff_a = git.get_diff(BASE_BRANCH, BRANCH_A)
diff_b = git.get_diff(BASE_BRANCH, BRANCH_B)

print(f"Diff A (feature/refactor_visualization): {len(diff_a) // 1024}KB")
print(f"Diff B (shinka best / gen_47):            {len(diff_b) // 1024}KB")

diff_a = truncate_diff(diff_a)
diff_b = truncate_diff(diff_b)
print(f"After truncation: A={len(diff_a) // 1024}KB, B={len(diff_b) // 1024}KB\n")

# --- Run the judge ---
judge = PairwiseJudge()
print(f"Judge model: {judge.llm_model}")
print("=" * 70)
print("Running comparison...")
print("=" * 70)

winner, reasoning = judge.compare(
    task_spec=TASK,
    candidate_a=diff_a,
    candidate_b=diff_b,
    context={"evolution_objective": TASK},
)

# --- Result ---
label_a = "feature/refactor_visualization"
label_b = "candidate_gen_47_main (shinka best)"
winner_label = label_a if winner == "a" else label_b

print("\n" + "=" * 70)
print(f"WINNER: {winner_label}")
print("=" * 70)
print(f"\nFull reasoning:\n{reasoning}")
print("=" * 70)
