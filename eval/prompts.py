"""Prompts for iPlotBench evaluation.

Separate queries for Task 1 (recreation) and Task 2 (QA).
"""

# Task 1: Recreation
TASK1_PROMPT = """Read ./input.png and recreate this plot.

Output the Plotly figure as JSON with "data" and "layout" keys:
{{"data": [...], "layout": {{...}}}}"""


# Task 2: QA (single question)
TASK2_PROMPT = """{question}

Reply with ONLY a single digit: 0 or 1"""


def get_task1_prompt(hint: str = "") -> str:
    """Get Task 1 prompt with optional config hint."""
    if hint:
        return f"{TASK1_PROMPT}\n\n{hint}"
    return TASK1_PROMPT


def get_task2_prompt(question: str) -> str:
    """Get Task 2 prompt for a single question."""
    return TASK2_PROMPT.format(question=question)
