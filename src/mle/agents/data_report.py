"""Data Report Agent.

Generates minimal data structure overview before MCTS starts.
The report is stored at `.memory/data_report.md` and provides
baseline context for all draft agents.
"""

from pathlib import Path

from pydantic import BaseModel, Field

from ...core import Agent, EventSink
from ..context import Context


class DataReportResult(BaseModel):
    """Data structure overview for ML task."""

    data_type: str = Field(
        description="Describe the ML task type, e.g., 'binary image classification', 'tabular regression', 'multi-label text classification'"
    )

    files: dict[str, str] = Field(
        description="File/folder patterns and their purpose. Group similar files (e.g., '*.jpg' not individual images). 10 entries max. Prioritize data files (train/test/input/output). If more files exist, summarize remainder as 'other'."
    )


DATA_REPORT_PROMPT = """Explore: {data_paths}

Return structured output describing the data layout.
"""


def data_report_prompt(context: Context) -> str:
    """Generate data report prompt from context."""
    data_paths_str = ", ".join(
        f"{name}: {path}" for name, path in context.data_paths.items()
    )
    return DATA_REPORT_PROMPT.format(data_paths=data_paths_str)


def write_report(result: DataReportResult, path: Path) -> None:
    """Format structured data into markdown report."""
    lines = [
        "# Data Report",
        "",
        f"**Type:** {result.data_type}",
        "",
        "## Files",
        "",
    ]
    for pattern, purpose in result.files.items():
        lines.append(f"- `{pattern}`: {purpose}")

    path.write_text("\n".join(lines) + "\n")


async def run_data_report_agent(
    workspace: Path,
    context: Context,
    event_sink: EventSink | None = None,
    model: str = "haiku",
    run_id: str | None = None,
) -> Path:
    """Generate minimal data structure overview before MCTS starts.

    Uses structured output to extract data layout, then formats
    into a concise markdown report at `.memory/data_report.md`.

    Args:
        workspace: Workspace directory
        context: Environment context with data paths
        event_sink: Optional sink for streaming events
        model: Model to use (default: haiku for speed)

    Returns:
        Path to the generated data report

    Example:
        report_path = await run_data_report_agent(
            workspace=Path("./competition"),
            context=context,
        )
    """
    # Skip if already exists
    if context.data_report_path.exists():
        return context.data_report_path

    prompt = data_report_prompt(context)

    agent = Agent(
        agent_type="data_report",
        name="DataReport",
        cwd=workspace,
        model=model,
        permission_mode="bypassPermissions",
        enable_storage=True,
        event_sink=event_sink,
        allowed_tools=["Read", "Glob", "Grep", "Bash"],
        output_format={
            "type": "json_schema",
            "schema": DataReportResult.model_json_schema(),
        },
        parent_activity_type="mle" if run_id else None,
        parent_activity_id=run_id,
    )

    try:
        await agent.start()
        await agent.query(prompt, display=False)

        if agent.structured_output is None:
            raise ValueError("DataReport agent did not produce structured output")

        result = DataReportResult.model_validate(agent.structured_output)
        write_report(result, context.data_report_path)

        return context.data_report_path
    finally:
        await agent.stop()
