import random
import re
import time
from typing import Tuple, Dict, Any, Optional
from dataclasses import dataclass, asdict

try:
    from shinka.llm import LLMClient
    SHINKA_AVAILABLE = True
except ImportError:
    SHINKA_AVAILABLE = False


@dataclass
class JudgmentResult:
    winner: str
    reasoning: str
    confidence: float
    llm_response: str
    cost: float
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['timestamp'] = time.time()
        return data


class PairwiseJudge:
    def __init__(self, llm_model: str = "gpt-4o", system_prompt: Optional[str] = None, 
                 temperature: float = 0.0, max_tokens: int = 2000):
        self.llm_model = llm_model
        self.system_prompt = system_prompt or self._default_system_prompt()
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        self.llm = LLMClient(model_names=[llm_model]) if SHINKA_AVAILABLE else None
        self.total_comparisons = 0
        self.total_cost = 0.0
    
    def _default_system_prompt(self) -> str:
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
    
    def compare(self, task_spec: str, candidate_a: str, candidate_b: str, 
                context: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
        swapped = random.random() < 0.5
        first, second = (candidate_b, candidate_a) if swapped else (candidate_a, candidate_b)
        
        user_prompt = self._build_prompt(task_spec, first, second, context)
        
        if self.llm:
            response = self.llm.query(msg=user_prompt, system_msg=self.system_prompt)
            if response is None:
                llm_response = self._mock_llm_response(first, second)
                cost = 0.0
            else:
                llm_response = response.content
                cost = response.cost if hasattr(response, 'cost') else 0.0
        else:
            llm_response = self._mock_llm_response(first, second)
            cost = 0.0
        
        winner_presented, reasoning, _ = self._parse_response(llm_response)
        
        if swapped:
            winner = {'first': 'b', 'second': 'a', 'tie': 'tie'}[winner_presented]
        else:
            winner = {'first': 'a', 'second': 'b', 'tie': 'tie'}[winner_presented]
        
        self.total_comparisons += 1
        self.total_cost += cost
        
        return winner, reasoning
    
    def compare_detailed(self, task_spec: str, candidate_a: str, candidate_b: str,
                        context: Optional[Dict[str, Any]] = None) -> JudgmentResult:
        winner, reasoning = self.compare(task_spec, candidate_a, candidate_b, context)
        return JudgmentResult(
            winner=winner,
            reasoning=reasoning,
            confidence=0.8,
            llm_response="",
            cost=self.total_cost,
            timestamp=time.time(),
        )
    
    def _build_prompt(self, task_spec: str, first: str, second: str, 
                     context: Optional[Dict[str, Any]] = None) -> str:
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
        winner = "tie"
        winner_match = re.search(r'Winner:\s*(Candidate\s*1|Candidate\s*2|Tie)', response, re.IGNORECASE)
        
        if winner_match:
            winner_text = winner_match.group(1).lower()
            if "1" in winner_text:
                winner = "first"
            elif "2" in winner_text:
                winner = "second"
            else:
                winner = "tie"
        else:
            if re.search(r'\bcandidate\s*1\b.*\bbetter\b', response, re.IGNORECASE):
                winner = "first"
            elif re.search(r'\bcandidate\s*2\b.*\bbetter\b', response, re.IGNORECASE):
                winner = "second"
        
        confidence = 0.5
        confidence_match = re.search(r'Confidence:\s*(High|Medium|Low)', response, re.IGNORECASE)
        if confidence_match:
            conf_text = confidence_match.group(1).lower()
            confidence = {'high': 0.9, 'medium': 0.6, 'low': 0.3}[conf_text]
        
        reasoning = response
        reasoning_match = re.search(r'Reasoning:\s*(.+?)(?=\n\n|\Z)', response, re.IGNORECASE | re.DOTALL)
        if reasoning_match:
            reasoning = reasoning_match.group(1).strip()
        
        return winner, reasoning, confidence
    
    def _mock_llm_response(self, first: str, second: str) -> str:
        if len(first) < len(second):
            winner, reason = "Candidate 1", "more concise implementation"
        elif len(second) < len(first):
            winner, reason = "Candidate 2", "more concise implementation"
        else:
            winner, reason = "Tie", "both solutions are equivalent"
        
        return f"""Winner: {winner}
Confidence: Medium
Reasoning: This is a mock response for testing. {winner} appears to have a {reason}."""
    
    def get_statistics(self) -> Dict[str, Any]:
        return {
            'total_comparisons': self.total_comparisons,
            'total_cost': self.total_cost,
            'average_cost': self.total_cost / max(self.total_comparisons, 1),
            'model': self.llm_model,
        }
    
    def reset_statistics(self):
        self.total_comparisons = 0
        self.total_cost = 0.0
        