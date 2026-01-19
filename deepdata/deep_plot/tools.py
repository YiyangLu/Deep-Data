"""
MCP tools for Deep Plot agent.

Provides submit_summary tool for recording evidence plots.
Actual finalization (renumbering, cleanup) happens when the agent finishes.
"""

import json
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server

from ..utils.logging import create_logger

logger = create_logger(__name__)


class DeepPlotReport:
    """
    Tracks the evidence plots selected by the agent.

    Agent can call submit_summary multiple times to update the list.
    Actual finalization happens when DeepPlotAgent.run() completes.
    """

    def __init__(self):
        self._summary: str = ""
        self._evidence_plots: list[int] = []

    def reset(self):
        """Reset for a new run."""
        self._summary = ""
        self._evidence_plots = []

    def submit(self, summary: str, evidence_plots: list[int]):
        """Record the report (can be called multiple times to update)."""
        self._summary = summary
        self._evidence_plots = evidence_plots

    def read(self) -> dict:
        """Read the current report."""
        return {
            "summary": self._summary,
            "evidence_plots": self._evidence_plots.copy()
        }

    @property
    def summary(self) -> str:
        """Get the summary text."""
        return self._summary

    @property
    def evidence_plots(self) -> list[int]:
        """Get the evidence plot IDs."""
        return self._evidence_plots.copy()

    # Backwards compatibility
    @property
    def plot_ids(self) -> list[int]:
        """Alias for evidence_plots (backwards compatibility)."""
        return self._evidence_plots.copy()


def create_deep_plot_mcp_server(report: DeepPlotReport, cwd: Path):
    """
    Create MCP server with Deep Plot tools.

    Args:
        report: DeepPlotReport instance to track the final report
        cwd: Working directory where analysis.md should be written

    Returns:
        McpSdkServerConfig for deep_plot tools
    """

    @tool(
        "submit_summary",
        "Record your analysis. Write analysis.md first, referencing plots as Plot 1, 2, 3... (matching evidence_plots order). Can be called multiple times to update.",
        {
            "evidence_plots": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Plot IDs to keep as evidence, in display order. First becomes Plot 1, second becomes Plot 2, etc."
            }
        }
    )
    async def _mcp_submit_summary(args: dict[str, Any]) -> dict[str, Any]:
        """
        MCP tool for recording the analysis report.

        Just stores the evidence_plots list. Actual finalization
        (renumbering, file cleanup) happens when the agent finishes.

        Args:
            args["evidence_plots"]: List of plot IDs

        Returns:
            Confirmation or error if analysis.md not found
        """
        evidence_plots = args.get("evidence_plots", [])

        # Handle string input for evidence_plots (e.g., "1,2,3" or "[1,2,3]")
        if isinstance(evidence_plots, str):
            cleaned = evidence_plots.strip().strip('[]')
            if cleaned:
                evidence_plots = [x.strip() for x in cleaned.split(',')]
            else:
                evidence_plots = []

        # Convert to integers
        try:
            evidence_plots = [int(pid) for pid in evidence_plots] if evidence_plots else []
        except (ValueError, TypeError) as e:
            return {
                "content": [{
                    "type": "text",
                    "text": json.dumps({
                        "success": False,
                        "error": f"Invalid plot ID: {e}"
                    }, indent=2)
                }],
                "is_error": True
            }

        # Read analysis.md from cwd
        analysis_path = cwd / "analysis.md"
        if not analysis_path.exists():
            return {
                "content": [{
                    "type": "text",
                    "text": json.dumps({
                        "success": False,
                        "error": "analysis.md not found. Please write your analysis to 'analysis.md' first using the Write tool."
                    }, indent=2)
                }],
                "is_error": True
            }

        try:
            summary = analysis_path.read_text(encoding="utf-8")
        except Exception as e:
            return {
                "content": [{
                    "type": "text",
                    "text": json.dumps({
                        "success": False,
                        "error": f"Failed to read analysis.md: {e}"
                    }, indent=2)
                }],
                "is_error": True
            }

        if not summary.strip():
            return {
                "content": [{
                    "type": "text",
                    "text": json.dumps({
                        "success": False,
                        "error": "analysis.md is empty. Please write your findings first."
                    }, indent=2)
                }],
                "is_error": True
            }

        # Just store the report - finalization happens when agent finishes
        report.submit(summary, evidence_plots)

        logger.info(f"Report recorded: {len(summary)} chars, evidence plots: {evidence_plots}")

        message = f"Report recorded ({len(summary)} chars, {len(evidence_plots)} evidence plots). Finalization will occur when analysis completes."

        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "success": True,
                    "message": message,
                    "evidence_plots": evidence_plots
                }, indent=2)
            }]
        }

    return create_sdk_mcp_server(
        name="deep_plot",
        version="1.0.0",
        tools=[
            _mcp_submit_summary
        ]
    )


# Backwards compatibility alias
EvidencePlots = DeepPlotReport

DEEP_PLOT_TOOLS = [
    "mcp__deep_plot__submit_summary"
]
