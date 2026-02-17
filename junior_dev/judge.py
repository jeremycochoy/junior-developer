import random
import re
import time
import traceback
from typing import Tuple, Dict, Any, Optional
from dataclasses import dataclass, asdict

try:
    from shinka.llm import LLMClient
    SHINKA_AVAILABLE = True
except ImportError:
    SHINKA_AVAILABLE = False

SWAP_PROBABILITY = 0.5
MAX_TIE_RETRIES = 2
MAX_CONTEXT_VALUE_LENGTH = 1000

JUDGE_SYSTEM_PROMPT = """You are an expert software architect and code reviewer. You compare two diffs (patches from a common base branch) and decide which better achieves the stated evolution objective.

What you see: each candidate is a git-style diff (lines starting with +/- showing additions and deletions). Do not treat them as full source files. Judge based on what the resulting code would do and how well it meets the objective.

Evaluation criteria (in order of importance):

1. Faithfulness to the stated objective. The diff should do what was asked — no more, no less. Extra features, refactors, or changes beyond the scope of the objective are negatives, not positives, unless the objective is deliberately broad or abstract, in which case thoughtful interpretation and coverage of implied requirements is a strength.
2. Correctness and completeness. The change should work correctly and handle the cases implied by the objective. A shorter diff that fully satisfies the objective is preferred over a longer one that also satisfies it — conciseness is a tiebreaker, not a primary criterion.
3. Code quality. Readability, idiomatic style, appropriate abstractions, and maintainability.

Key biases to avoid:
- Do NOT prefer a diff because it is longer or touches more files. More code is not inherently better.
- Do NOT reward scope creep. Unrequested features, defensive additions, or speculative generalization that go beyond the objective should count against a candidate.
- Do NOT penalize a diff for being minimal if it fully achieves the objective.
- DO reward a diff that interprets a vague or high-level objective thoughtfully, covering reasonable implied requirements without gold-plating.

You MUST choose one winner — ties are not allowed. Even if both candidates are flawed or nearly equal, pick the one that is closer to the ideal change for the given objective.

Respond in this exact format (plain text, no markdown):

explanation:<your reasoning>
candidate:<candidate>
confidence:<confidence>

Where <candidate> is exactly "first" or "second" (lowercase), <confidence> is a float between 0.0 and 1.0 reflecting how sure you are of your choice, and <your reasoning> explains your decision with reference to the criteria above.
"""


@dataclass
class JudgmentResult:
    winner: str
    reasoning: str
    confidence: float
    llm_response: str
    cost: float
    timestamp: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PairwiseJudge:

    def __init__(self, llm_model: str = "deepseek-reasoner", system_prompt: Optional[str] = None,
                 temperature: float = 0.0, max_tokens: int = 2000):
        self.llm_model = llm_model
        self.system_prompt = system_prompt or JUDGE_SYSTEM_PROMPT
        self.temperature = temperature
        self.max_tokens = max_tokens

        if SHINKA_AVAILABLE and llm_model != "mock":
            self.llm = LLMClient(model_names=[llm_model], temperatures=temperature)
        else:
            self.llm = None
        self.total_comparisons = 0
        self.total_cost = 0.0
        self.log_file = None  # set externally to write verbose output to a file

    def compare(self, task_spec: str, candidate_a: str, candidate_b: str,
                context: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
        swapped = random.random() < SWAP_PROBABILITY
        first, second = (candidate_b, candidate_a) if swapped else (candidate_a, candidate_b)

        user_prompt = self._build_prompt(task_spec, first, second, context)

        cost = 0.0
        winner_presented = "tie"
        reasoning = ""

        for attempt in range(MAX_TIE_RETRIES):
            llm_response, cost = self._query_llm(user_prompt)
            winner_presented, reasoning, confidence = self._parse_response(llm_response)

            self._log(f"\n--- Judge LLM Response (attempt {attempt + 1}) ---")
            self._log(llm_response)
            self._log(f"--- Parsed: winner={winner_presented}, confidence={confidence:.2f}, swapped={swapped} ---\n")

            if winner_presented == "tie":
                print(f"  [judge] Parse failed on attempt {attempt + 1}, retrying...")
            if winner_presented != "tie":
                break

        if winner_presented == "tie":
            winner_presented = random.choice(["first", "second"])
            reasoning = f"{reasoning}\n\n[Note: Judge failed to parse after {MAX_TIE_RETRIES} attempts; randomly selected winner]"
            print(f"  [judge] WARNING: Could not parse winner after {MAX_TIE_RETRIES} attempts, picked randomly")

        if swapped:
            winner = {"first": "b", "second": "a"}[winner_presented]
        else:
            winner = {"first": "a", "second": "b"}[winner_presented]

        self.total_comparisons += 1
        self.total_cost += cost

        return winner, reasoning

    def compare_detailed(self, task_spec: str, candidate_a: str, candidate_b: str,
                         context: Optional[Dict[str, Any]] = None) -> JudgmentResult:
        cost_before = self.total_cost
        winner, reasoning = self.compare(task_spec, candidate_a, candidate_b, context)
        cost_for_this_comparison = self.total_cost - cost_before

        return JudgmentResult(
            winner=winner,
            reasoning=reasoning,
            confidence=0.6,
            llm_response="",
            cost=cost_for_this_comparison,
            timestamp=time.time(),
        )

    def _log(self, msg: str):
        if self.log_file:
            self.log_file.write(msg + "\n")
            self.log_file.flush()

    def _query_llm(self, user_prompt: str) -> Tuple[str, float]:
        if self.llm:
            response = self.llm.query(msg=user_prompt, system_msg=self.system_prompt)
            if response is None:
                return self._mock_llm_response(), 0.0
            cost = response.cost if hasattr(response, "cost") else 0.0
            return response.content, cost
        return self._mock_llm_response(), 0.0

    def _build_prompt(self, task_spec: str, first: str, second: str,
                      context: Optional[Dict[str, Any]] = None) -> str:
        objective = task_spec
        if context and "evolution_objective" in context:
            objective = context["evolution_objective"]

        prompt = f"""Evolution objective:
{objective}

First candidate (diff from base):
{first}

Second candidate (diff from base):
{second}
"""
        if context:
            for key, value in context.items():
                if key == "evolution_objective":
                    continue
                if isinstance(value, str) and len(value) < MAX_CONTEXT_VALUE_LENGTH:
                    prompt += f"\n{key}: {value}\n"
                elif isinstance(value, (int, float, bool)):
                    prompt += f"\n{key}: {value}\n"

        prompt += """
Which diff, when applied to the base, would better achieve the evolution objective? Judge the outcome, not diff size.

Formulate your judgment following this exact format:

explanation:<your reasoning>
candidate:<candidate>
confidence:<confidence>

Where <candidate> is replaced by exactly the word "first" or "second" (lowercase, no quotes), where <confidence> is a float between 0.0 and 1.0, and where <your reasoning> is a textual explanation of your decision. Respect the formatting (spaces, case, no markdown)."""
        return prompt

    def _parse_response(self, response: str) -> Tuple[str, str, float]:
        # Parse candidate: first|second
        winner = "tie"
        candidate_match = re.search(r'^candidate:\s*(first|second)\s*$', response, re.IGNORECASE | re.MULTILINE)
        if candidate_match:
            winner = candidate_match.group(1).lower()

        # Parse confidence: float
        confidence = 0.5
        confidence_match = re.search(r'^confidence:\s*([0-9]*\.?[0-9]+)\s*$', response, re.IGNORECASE | re.MULTILINE)
        if confidence_match:
            confidence = max(0.0, min(1.0, float(confidence_match.group(1))))

        # Parse explanation: text (everything after "explanation:" until "candidate:" or end)
        reasoning = response
        explanation_match = re.search(r'^explanation:\s*(.+?)(?=^candidate:|\Z)', response, re.IGNORECASE | re.DOTALL | re.MULTILINE)
        if explanation_match:
            reasoning = explanation_match.group(1).strip()

        return winner, reasoning, confidence

    def _mock_llm_response(self) -> str:
        winner = random.choice(["first", "second"])
        return f"explanation:Mock response for testing. Randomly selected winner.\ncandidate:{winner}\nconfidence:0.5"

    def get_statistics(self) -> Dict[str, Any]:
        return {
            "total_comparisons": self.total_comparisons,
            "total_cost": self.total_cost,
            "average_cost": self.total_cost / max(self.total_comparisons, 1),
            "model": self.llm_model,
        }

    def reset_statistics(self):
        self.total_comparisons = 0
        self.total_cost = 0.0
