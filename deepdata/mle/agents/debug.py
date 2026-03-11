"""Debug Agent.

Fixes a buggy ML solution.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from ...core import Agent, EventSink
from ...plotly.mcp_tools import create_plotly_mcp_server
from ..context import Context
from .shared import (
    AgentResult,
    PromptContext,
    format_time,
    get_gpu_instructions,
    get_package_list,
    trim_long_string,
)

if TYPE_CHECKING:
    from ..node import MCTSNode


DEBUG_PROMPT = """Fix this buggy ML solution.

## Task
{task_description}

## Error
{error_info}

## Full Execution Output
```
{execution_output}
```

## Buggy Code Approach
{buggy_plan}

## Environment
{gpu_instructions}
- Python: ./env/bin/python ({package_list})

## Sibling Memory (Previous Fix Attempts)
The memory of previous fix attempts by other branches is provided below:
{sibling_memory}

## Goal
{goal}

## Guidelines
- Analyze the Full Execution Output to understand what went wrong.
- If previous fix attempts failed (see Sibling Memory), try a **different approach** to fix the bug.
- Do NOT change the core algorithm unless the bug is in the algorithm itself.
"""


def debug_prompt(
    context: Context,
    parent_node: "MCTSNode",
    sibling_memory: str,
    prompt_ctx: PromptContext,
) -> str:
    """Generate debug prompt from context, buggy parent node, and memory.

    Args:
        context: Environment context (task, data, output requirements)
        parent_node: Buggy node to fix (for error info and output)
        sibling_memory: Memory from parent.fetch_child_memory()
        prompt_ctx: Runtime context (time, steps, timeout)

    Returns:
        Formatted prompt string
    """
    # Get error info from parent node
    error_info = "Unknown error"
    if hasattr(parent_node, "error_summary") and parent_node.error_summary:
        error_info = parent_node.error_summary

    # Get execution output
    execution_output = "No output captured."
    if hasattr(parent_node, "output") and parent_node.output:
        execution_output = trim_long_string(parent_node.output)

    # Get buggy approach plan
    buggy_plan = getattr(parent_node, "plan", "No plan available.")

    # Note: time_remaining/steps_remaining passed but not used in template
    # (reserved for future use if we want to add time pressure to prompts)
    return DEBUG_PROMPT.format(
        time_remaining=format_time(prompt_ctx.time_remaining),
        steps_remaining=prompt_ctx.steps_remaining,
        task_description=context.task_description,
        error_info=error_info,
        execution_output=execution_output,
        buggy_plan=buggy_plan,
        gpu_instructions=get_gpu_instructions(prompt_ctx.gpu_id),
        package_list=get_package_list(),
        sibling_memory=sibling_memory if sibling_memory else "No previous attempts.",
        goal=context.goal,
    )


async def run_debug_agent(
    worktree: Path,
    context: Context,
    parent_node: "MCTSNode",
    prompt_ctx: PromptContext,
    event_sink: EventSink | None = None,
    model: str = "sonnet",
    run_id: str | None = None,
    on_agent_start: Optional[Callable[[str], None]] = None,
    env: dict | None = None,
) -> AgentResult:
    """Fix buggy solution.

    The agent analyzes the error and execution output, then makes
    minimal fixes to get the solution working.

    Args:
        worktree: Path to git worktree (already checked out to parent's commit)
        context: Environment context
        parent_node: Buggy node to fix
        prompt_ctx: Runtime context (time, steps)
        event_sink: Optional sink for streaming events
        model: Model to use

    Returns:
        AgentResult with plan and run_command

    Raises:
        ValueError: If agent doesn't produce structured output

    Example:
        # Checkout parent's buggy state first
        git_checkout(worktree, parent_node.commit_hash)

        result = await run_debug_agent(
            worktree=worktree,
            context=context,
            parent_node=parent_node,
            prompt_ctx=prompt_ctx,
        )
    """
    sibling_memory = parent_node.fetch_child_memory()
    prompt = debug_prompt(context, parent_node, sibling_memory, prompt_ctx)

    # Create plotly MCP server for visualization
    plotly_server, plotly_cleanup = create_plotly_mcp_server(enable_headless=True)

    agent = Agent(
        agent_type="debug",
        name="Debug",
        cwd=worktree,
        model=model,
        permission_mode="bypassPermissions",
        enable_storage=True,
        event_sink=event_sink,
        mcp_servers={"plotly": plotly_server},
        output_format={
            "type": "json_schema",
            "schema": AgentResult.model_json_schema()
        },
        parent_activity_type="mle" if run_id else None,
        parent_activity_id=run_id,
        env=env or {},
    )

    try:
        await agent.start()

        # Pass on_agent_start to query() so it's called when session_id is obtained
        await agent.query(prompt, display=False, on_session_start=on_agent_start)

        if agent.structured_output is None:
            raise ValueError("Debug agent did not produce structured output")

        return AgentResult.model_validate(agent.structured_output)
    finally:
        await agent.stop()
        # Cleanup plotly MCP server
        if plotly_cleanup:
            plotly_cleanup()
