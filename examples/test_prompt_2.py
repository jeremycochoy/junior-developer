CANDIDATE_ID = "test_002"

TASK_SPEC = "Improve the example.py file by optimizing performance, adding logging, and improving code structure."

INITIAL_PROMPT = """Please improve the example.py file:

1. Add logging functionality (use Python's logging module)
2. Optimize any performance bottlenecks
3. Improve code structure and organization
4. Add unit tests or testable structure
5. Enhance error messages with more context
6. Consider edge cases and boundary conditions

Keep the existing functionality intact while making it more production-ready."""


def get_evolved_prompt() -> str:
    return INITIAL_PROMPT


def get_task_spec() -> str:
    return TASK_SPEC

