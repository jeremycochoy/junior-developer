"""
Pairwise LLM Judge for Junior Developer Project

Uses a single LLM to compare two candidates (Git branches, code solutions, etc.)
and determine which one better fulfills a task specification.

Key Features:
- Randomized ordering to avoid position bias
- Clean prompt templates
- Robust response parsing
- Integration with ELO scoring
- Cost tracking for LLM calls
"""

import random
import re
import time
from typing import Tuple, Dict, Any, Optional, List
from dataclasses import dataclass

# Import Shinka's LLM client
try:
    from shinka.llm import LLMClient
    SHINKA_AVAILABLE = True
except ImportError:
    SHINKA_AVAILABLE = False
    print("Warning: Shinka not available. Using mock LLM for testing.")


@dataclass
class JudgmentResult:
    """Result of a pairwise comparison."""
    winner: str  # "a", "b", or "tie"
    reasoning: str
    confidence: float  # 0.0 to 1.0
    llm_response: str
    cost: float
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'winner': self.winner,
            'reasoning': self.reasoning,
            'confidence': self.confidence,
            'llm_response': self.llm_response,
            'cost': self.cost,
            'timestamp': time.time(),
        }


class PairwiseJudge:
    """
    LLM-based judge for comparing two candidates.
    
    This judge compares two candidates (e.g., Git branch diffs, code solutions)
    and determines which one better accomplishes a given task.
    
    Key feature: RANDOMIZES presentation order to avoid position bias.
    (LLMs sometimes favor the first or second option systematically)
    
    Example:
        >>> judge = PairwiseJudge(llm_model="gpt-4")
        >>> winner, reasoning = judge.compare(
        ...     task_spec="Sort numbers efficiently",
        ...     candidate_a="def sort(x): return sorted(x)",
        ...     candidate_b="def sort(x): # bubble sort implementation",
        ... )
        >>> print(winner)  # "a", "b", or "tie"
    """
    
    def __init__(
        self,
        llm_model: str = "gpt-4",
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 2000,
        verbose: bool = False,
    ):
        """
        Initialize pairwise judge.
        
        Args:
            llm_model: Model name (e.g., "gpt-4", "claude-sonnet-4")
            system_prompt: Custom system prompt (uses default if None)
            temperature: LLM temperature (0.0 = deterministic)
            max_tokens: Max tokens for response
            verbose: Print debug information
        """
        self.llm_model = llm_model
        self.system_prompt = system_prompt or self._default_system_prompt()
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.verbose = verbose
        
        # Initialize LLM client
        if SHINKA_AVAILABLE:
            self.llm = LLMClient(
                model_names=[llm_model],
                verbose=verbose,
            )
        else:
            self.llm = None  # Will use mock for testing
        
        # Statistics
        self.total_comparisons = 0
        self.total_cost = 0.0
        
        if self.verbose:
            print(f"PairwiseJudge initialized:")
            print(f"  Model: {llm_model}")
            print(f"  Temperature: {temperature}")
    
    def _default_system_prompt(self) -> str:
        """Default system prompt for judging."""
        return """You are an expert software architect and code reviewer.

Your task is to compare two solutions to a programming task and determine which one is better.

Evaluation criteria (in order of importance):
1. **Correctness**: Does it achieve the stated goal?
2. **Code Quality**: Is it clean, readable, and maintainable?
3. **Completeness**: Are edge cases and error handling addressed?
4. **Efficiency**: Is the approach reasonably efficient?
5. **Best Practices**: Does it follow language conventions?

Important rules:
- Be objective and specific in your reasoning
- If both solutions are equally good, say "Tie"
- Focus on substantial differences, not minor style preferences
- Consider the task requirements carefully

Response format:
Winner: [Candidate 1 / Candidate 2 / Tie]
Confidence: [High / Medium / Low]
Reasoning: [Your detailed explanation]"""
    
    def compare(
        self,
        task_spec: str,
        candidate_a: str,
        candidate_b: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        """
        Compare two candidates and return winner.
        
        Args:
            task_spec: Description of what the candidates should accomplish
            candidate_a: First candidate (code, diff, output, etc.)
            candidate_b: Second candidate
            context: Optional additional context (e.g., file contents, test results)
            
        Returns:
            (winner, reasoning) where winner is "a", "b", or "tie"
        """
        # Randomize presentation order to avoid position bias
        if random.random() < 0.5:
            first, second = candidate_a, candidate_b
            first_label, second_label = "a", "b"
            swapped = False
        else:
            first, second = candidate_b, candidate_a
            first_label, second_label = "b", "a"
            swapped = True
        
        if self.verbose:
            swap_msg = "(SWAPPED)" if swapped else "(NOT SWAPPED)"
            print(f"\nComparing candidates {swap_msg}")
        
        # Build prompt
        user_prompt = self._build_prompt(
            task_spec, first, second, context
        )
        
        # Query LLM
        start_time = time.time()
        
        if self.llm:
            response = self.llm.query(
                msg=user_prompt,
                system_msg=self.system_prompt,
                llm_kwargs={
                    'temperature': self.temperature,
                    'max_tokens': self.max_tokens,
                }
            )
            llm_response = response.content
            cost = response.cost if hasattr(response, 'cost') else 0.0
        else:
            # Mock response for testing without LLM
            llm_response = self._mock_llm_response(first, second)
            cost = 0.0
        
        elapsed = time.time() - start_time
        
        # Parse response
        winner_presented, reasoning, confidence = self._parse_response(llm_response)
        
        # Un-swap if needed
        if swapped:
            if winner_presented == "first":
                winner = "b"
            elif winner_presented == "second":
                winner = "a"
            else:
                winner = "tie"
        else:
            if winner_presented == "first":
                winner = "a"
            elif winner_presented == "second":
                winner = "b"
            else:
                winner = "tie"
        
        # Update statistics
        self.total_comparisons += 1
        self.total_cost += cost
        
        if self.verbose:
            print(f"  Decision: {winner} (confidence: {confidence})")
            print(f"  Time: {elapsed:.2f}s, Cost: ${cost:.4f}")
            print(f"  Reasoning preview: {reasoning[:100]}...")
        
        return winner, reasoning
    
    def compare_detailed(
        self,
        task_spec: str,
        candidate_a: str,
        candidate_b: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> JudgmentResult:
        """
        Compare two candidates and return detailed judgment.
        
        Returns:
            JudgmentResult with winner, reasoning, confidence, cost, etc.
        """
        # Use compare method but capture more details
        winner, reasoning = self.compare(task_spec, candidate_a, candidate_b, context)
        
        # Extract confidence from last comparison
        # (This is a simplified version - in production, parse from response)
        confidence = 0.8  # Default confidence
        
        return JudgmentResult(
            winner=winner,
            reasoning=reasoning,
            confidence=confidence,
            llm_response="",  # Full response
            cost=self.total_cost,
            timestamp=time.time(),
        )
    
    def _build_prompt(
        self,
        task_spec: str,
        first: str,
        second: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build the comparison prompt for the LLM."""
        prompt = f"""# Task Specification

{task_spec}

# Candidate 1

{first}

# Candidate 2

{second}
"""
        
        if context:
            prompt += "\n# Additional Context\n\n"
            for key, value in context.items():
                if isinstance(value, str) and len(value) < 1000:
                    prompt += f"**{key}**:\n{value}\n\n"
                elif isinstance(value, (int, float, bool)):
                    prompt += f"**{key}**: {value}\n"
        
        prompt += """
# Your Task

Compare the two candidates and determine which one better fulfills the task specification.
Provide your judgment in the following format:

Winner: [Candidate 1 / Candidate 2 / Tie]
Confidence: [High / Medium / Low]
Reasoning: [Your detailed explanation of why this candidate is better]
"""
        
        return prompt
    
    def _parse_response(self, response: str) -> Tuple[str, str, float]:
        """
        Parse LLM response to extract winner, reasoning, and confidence.
        
        Returns:
            (winner, reasoning, confidence) where:
            - winner: "first", "second", or "tie"
            - reasoning: extracted explanation
            - confidence: 0.0 to 1.0
        """
        # Extract winner
        winner = "tie"  # Default
        
        # Look for "Winner:" line
        winner_match = re.search(
            r'Winner:\s*(Candidate\s*1|Candidate\s*2|Tie)',
            response,
            re.IGNORECASE
        )
        if winner_match:
            winner_text = winner_match.group(1).lower()
            if "1" in winner_text:
                winner = "first"
            elif "2" in winner_text:
                winner = "second"
            else:
                winner = "tie"
        else:
            # Fallback: look for keywords in response
            if re.search(r'\bcandidate\s*1\b.*\bbetter\b', response, re.IGNORECASE):
                winner = "first"
            elif re.search(r'\bcandidate\s*2\b.*\bbetter\b', response, re.IGNORECASE):
                winner = "second"
        
        # Extract confidence
        confidence = 0.5  # Default
        confidence_match = re.search(
            r'Confidence:\s*(High|Medium|Low)',
            response,
            re.IGNORECASE
        )
        if confidence_match:
            conf_text = confidence_match.group(1).lower()
            if "high" in conf_text:
                confidence = 0.9
            elif "medium" in conf_text:
                confidence = 0.6
            else:
                confidence = 0.3
        
        # Extract reasoning
        reasoning = response  # Default to full response
        reasoning_match = re.search(
            r'Reasoning:\s*(.+?)(?=\n\n|\Z)',
            response,
            re.IGNORECASE | re.DOTALL
        )
        if reasoning_match:
            reasoning = reasoning_match.group(1).strip()
        
        return winner, reasoning, confidence
    
    def _mock_llm_response(self, first: str, second: str) -> str:
        """Generate mock LLM response for testing without API calls."""
        # Simple heuristic: prefer shorter, cleaner code
        if len(first) < len(second):
            winner = "Candidate 1"
            reason = "more concise implementation"
        elif len(second) < len(first):
            winner = "Candidate 2"
            reason = "more concise implementation"
        else:
            winner = "Tie"
            reason = "both solutions are equivalent"
        
        return f"""Winner: {winner}
Confidence: Medium
Reasoning: This is a mock response for testing. {winner} appears to have a {reason}."""
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get judge statistics."""
        return {
            'total_comparisons': self.total_comparisons,
            'total_cost': self.total_cost,
            'average_cost': self.total_cost / max(self.total_comparisons, 1),
            'model': self.llm_model,
        }
    
    def reset_statistics(self):
        """Reset comparison statistics."""
        self.total_comparisons = 0
        self.total_cost = 0.0
