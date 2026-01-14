"""
Initial program for Junior Developer evolution.
This file contains the seed prompt that will be evolved by ShinkaEvolve.
"""

CANDIDATE_ID = "gen_00_initial"

TASK_SPEC = """
Refactor the visualization code outside of the training class 
to an independent visualization instance.
"""

INITIAL_PROMPT = """
Please refactor the codebase to improve code quality and maintainability.

Specifically:
1. Move visualization functions out of the training class
2. Create a separate VisualizationKit class
3. Ensure all existing functionality is preserved
4. Add proper documentation
5. Follow Python best practices
"""


def get_evolved_prompt() -> str:
    """
    Return the evolved prompt text.
    ShinkaEvolve will mutate this function to evolve the prompt.
    """
    return INITIAL_PROMPT


def get_task_spec() -> str:
    """Return the task specification."""
    return TASK_SPEC

