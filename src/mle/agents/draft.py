"""Draft Agent.

Generates a new ML solution from scratch.
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
    read_file,
)

if TYPE_CHECKING:
    from ..node import MCTSNode


DRAFT_PROMPT = """You are solving an ML task.

## Task
{task_description}

## Data
{data_report}
Paths: {data_paths}

## Output Requirements
Output paths: {output_paths}
{output_requirements}

## Goal
{goal}

## Environment
{gpu_instructions}
- Python: ./env/bin/python ({package_list})

## Memory
The memory of previous solutions used to solve this task is provided below:
{sibling_memory}

## Guidelines
- When proposing your design, take the Memory section into account.
- Your proposed solution **must be distinctly different from** the existing designs in the Memory section.
- If a previous approach had bugs, try a different approach to avoid the same issues.
- Use MCP Plotly tools to interactively explore and visualize as needed to support your design.
- Create only one solution that achieves the best validation metric.
"""


def draft_prompt(
    context: Context,
    sibling_memory: str,
    prompt_ctx: PromptContext,
) -> str:
    """Generate draft prompt from context and memory.

    Args:
        context: Environment context (task, data, output requirements)
        sibling_memory: Memory from parent.fetch_child_memory()
        prompt_ctx: Runtime context (time, steps, timeout)

    Returns:
        Formatted prompt string
    """
    # Paths are already relative strings in Context
    # Note: time_remaining/steps_remaining passed but not used in template
    # (reserved for future use if we want to add time pressure to prompts)
    return DRAFT_PROMPT.format(
        time_remaining=format_time(prompt_ctx.time_remaining),
        steps_remaining=prompt_ctx.steps_remaining,
        task_description=context.task_description,
        data_report=read_file(context.data_report_path),
        data_paths=context.data_paths,
        output_paths=context.output_paths,
        output_requirements=context.output_requirements,
        goal=context.goal,
        gpu_instructions=get_gpu_instructions(prompt_ctx.gpu_id),
        package_list=get_package_list(),
        sibling_memory=sibling_memory if sibling_memory else "No previous attempts.",
    )


async def run_draft_agent(
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
    """Generate fresh solution from scratch in isolated worktree.

    The agent explores the data, designs and implements an ML solution,
    then returns a structured result with plan and run command.

    Args:
        worktree: Path to git worktree (already checked out)
        context: Environment context
        parent_node: Virtual root node (for sibling memory)
        prompt_ctx: Runtime context (time, steps)
        event_sink: Optional sink for streaming events
        model: Model to use

    Returns:
        AgentResult with plan and run_command

    Raises:
        ValueError: If agent doesn't produce structured output

    Example:
        result = await run_draft_agent(
            worktree=Path("./worktrees/worker_0"),
            context=context,
            parent_node=virtual_root,
            prompt_ctx=PromptContext(
                time_remaining=3600,
                steps_remaining=10,
                current_step=1,
            ),
        )
    """
    sibling_memory = parent_node.fetch_child_memory()
    prompt = draft_prompt(context, sibling_memory, prompt_ctx)

    # Create plotly MCP server for visualization
    plotly_server, plotly_cleanup = create_plotly_mcp_server(enable_headless=True)

    agent = Agent(
        agent_type="draft",
        name="Draft",
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
            raise ValueError("Draft agent did not produce structured output")

        return AgentResult.model_validate(agent.structured_output)
    finally:
        await agent.stop()
        # Cleanup plotly MCP server
        if plotly_cleanup:
            plotly_cleanup()
