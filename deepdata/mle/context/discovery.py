"""LLM-based context discovery.

Uses an Agent to explore a workspace and extract Context automatically.
This is the first step in the MLE pipeline.

Example:
    context = await run_discovery_agent(
        workspace=Path("./competition"),
        event_sink=my_sink,
        model="haiku"
    )
"""

from pathlib import Path

from pydantic import BaseModel, Field

from ...core import Agent, EventSink

from .base import Context


class DiscoveryResult(BaseModel):
    """Structured output from discovery agent.

    Schema is enforced by SDK's output_format feature.
    """

    goal: str = Field(
        description="High-level objective, e.g. 'Maximize validation metric.'"
    )
    task_description: str = Field(
        description="Description of the ML task"
    )
    data_paths: dict[str, str] = Field(
        description="Data file paths, e.g. {'train': 'data/train.csv', 'test': 'data/test.csv'}"
    )
    output_paths: dict[str, str] = Field(
        description="Output file paths, e.g. {'prediction': 'output/pred.csv','model': 'output/model.pkl'}"
    )
    output_requirements: str = Field(
        description="Output format requirements"
    )
    gitignore: list[str] = Field(
        description="Patterns to ignore in git (large files, outputs, caches)"
    )
    sync: list[str] = Field(
        description="Paths to symlink across parallel workers"
    )


def discovery_prompt(workspace: Path, partial_context: dict = None) -> str:
    """Generate prompt for discovering Context from a workspace."""
    import json

    prompt = f"""Explore this workspace and extract ML task information.

Workspace: {workspace}

Read README, docs, code to understand the task. Identify data files and output requirements.

## File handling logic
- NOT in gitignore → Tracked by git (synced via checkout)
- IN gitignore AND IN sync → Symlinked (shared across worktrees)
- IN gitignore AND NOT in sync → Per-worktree (separate/fresh)
"""

    if partial_context:
        prompt += f"""
## Partial context (fill missing fields, respect user input)
{json.dumps(partial_context, indent=2)}
"""

    return prompt


async def run_discovery_agent(
    workspace: Path,
    event_sink: EventSink | None = None,
    model: str = "haiku",
    partial_context: dict = None,
) -> Context:
    """Run discovery agent to extract Context from workspace.

    Args:
        workspace: Path to the workspace directory
        event_sink: Optional sink for streaming events (for UI/logging)
        model: Model to use (default: haiku for speed/cost)
        partial_context: User-provided partial context to fill in

    Returns:
        Context object with discovered information
    """
    workspace = Path(workspace).resolve()

    agent = Agent(
        agent_type="discovery",
        name="Discovery",
        cwd=workspace,
        model=model,
        permission_mode="bypassPermissions",
        enable_storage=True,
        event_sink=event_sink,
        allowed_tools=["Read", "Glob", "Grep", "Bash"],
        output_format={
            "type": "json_schema",
            "schema": DiscoveryResult.model_json_schema()
        }
    )

    try:
        await agent.start()
        await agent.query(discovery_prompt(workspace, partial_context), display=False)

        # Check if we got structured output
        if agent.structured_output is None:
            raise ValueError(
                "Discovery agent did not produce structured output. "
                "The agent may have failed to explore the workspace."
            )

        # Validate with Pydantic
        discovery = DiscoveryResult.model_validate(agent.structured_output)

        # Ensure .memory/ is in both gitignore and sync
        # Note: Must add both ".memory/" (directory) and ".memory" (symlink) to gitignore
        gitignore_normalized = {g.rstrip("/") for g in discovery.gitignore}
        if ".memory" not in gitignore_normalized:
            discovery.gitignore.append(".memory/")  # Directory pattern
            discovery.gitignore.append(".memory")   # Symlink pattern

        sync_normalized = {s.rstrip("/") for s in discovery.sync}
        if ".memory" not in sync_normalized:
            discovery.sync.append(".memory/")

        # Ensure .memory directory exists
        memory_dir = workspace / ".memory"
        memory_dir.mkdir(exist_ok=True)

        # Convert paths to relative strings with ./ prefix
        def to_relative(p: str) -> str:
            return p if p.startswith("./") else f"./{p}"

        # Convert to Context
        return Context(
            workspace=workspace,
            goal=discovery.goal,
            task_description=discovery.task_description,
            data_report_path=memory_dir / "data_report.md",
            data_paths={k: to_relative(v) for k, v in discovery.data_paths.items()},
            output_paths={k: to_relative(v) for k, v in discovery.output_paths.items()},
            output_requirements=discovery.output_requirements,
            gitignore=discovery.gitignore,
            sync=discovery.sync,
        )
    finally:
        await agent.stop()
