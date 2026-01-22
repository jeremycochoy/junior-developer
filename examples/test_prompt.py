CANDIDATE_ID = "test_001"

TASK_SPEC = "Improve the example.py file by adding better documentation, error handling, and type hints."

INITIAL_PROMPT = """Please improve the example.py file:

1. Add comprehensive docstrings to all functions
2. Add proper error handling (try/except blocks where appropriate)
3. Improve type hints
4. Add input validation
5. Make the code more robust and maintainable

Keep the existing functionality intact."""


def get_evolved_prompt() -> str:
    return INITIAL_PROMPT


def get_task_spec() -> str:
    return TASK_SPEC

