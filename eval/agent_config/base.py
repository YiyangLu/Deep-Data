"""Base config for iPlotBench evaluation agents."""

from typing import List


class BaseConfig:
    """
    Base class for iPlotBench agent configs.

    Subclasses define NAME and TOOLS.
    Use with src.core.agent.Agent:

        from src.core.agent import Agent
        from eval.agent_config import Vision

        agent = Agent(
            agent_type=f"iplotbench-{Vision.NAME}",
            allowed_tools=Vision.TOOLS,
            disallowed_tools=Vision.DISALLOWED_TOOLS,
            ...
        )
    """
    NAME: str = "base"
    TOOLS: List[str] = []

    # Config-specific hint for prompt
    HINT: str = ""

    # Disallow all tools except Read and MCP plotly tools
    # Agent should be read-only with only visualization capabilities
    DISALLOWED_TOOLS: List[str] = [
        # File modification
        # "Read",
        "Write",
        "Edit",
        "NotebookEdit",
        # Command execution
        "Bash",
        "BashOutput",
        "KillBash",
        # Subagents (could bypass restrictions)
        "Task",
        # Search/fetch (not needed for eval)
        "Glob",
        "Grep",
        "WebFetch",
        "WebSearch",
        "LSP",
        # MCP resources
        # "ListMcpResources",
        # "ReadMcpResource",
        # Interactive/planning
        "TodoWrite",
        "AskUserQuestion",
        "EnterPlanMode",
        "ExitPlanMode",
        "Skill",
    ]
