CANDIDATE_ID = "gen_00_initial"
PARENT_BRANCH = None

# EVOLVE-BLOCK-START
EVOLVED_PROMPT = """Create a simple snake game in this HTML file.

Requirements:
1. Fully contained in a single HTML file
2. Canvas element for rendering
3. Arrow keys for controls
4. Display the score
5. Game over when snake hits wall or itself
6. Simple but appealing visual style
7. Snake grows when eating food

Make the code clean and well-organized."""
# EVOLVE-BLOCK-END


def get_evolved_prompt() -> str:
    """Return the prompt for the coding agent."""
    return EVOLVED_PROMPT


def get_task_spec() -> str:
    """Return the task specification for judging."""
    return "Create a snake game in a self-contained HTML file"
