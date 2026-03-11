"""
Deep Plot Agent - Autonomous data analysis agent.

Runs in a continuous loop for a configurable duration, conducting
iterative analysis to understand the dataset. Uses statistical methods,
ML techniques, and visualizations to discover patterns and insights.
Produces a final summary report before timeout.

Design:
- Creates Agent directly (no WebConnection/AgentManager dependency)
- Takes optional on_event callback for event forwarding
- Agent self-registers in global registry on start()
- Caller decides how to handle events (WebSocket, logging, etc.)
"""

import asyncio
import time
from pathlib import Path
from typing import Callable, Awaitable

from .tools import create_deep_plot_mcp_server, DeepPlotReport, DEEP_PLOT_TOOLS
from ..core.agent import Agent
from ..core.session.store import SessionStore
from ..utils.logging import create_logger
from ..utils.paths import get_logs_root
from ..plotly.mcp_tools import create_plotly_mcp_server, PLOTLY_TOOLS
from ..plotly.server.services.plot_service import get_plot_store

logger = create_logger(__name__)

# Type alias for event callback
EventCallback = Callable[[str, dict], Awaitable[None]]


class DeepPlotAgent:
    """
    Autonomous agent that conducts deep data analysis.

    Creates Agent directly - no dependency on web layer.
    Caller can provide on_event callback for event forwarding.

    Usage:
        # Simple usage (no streaming)
        agent = DeepPlotAgent(
            cwd=Path("/path/to/dir"),
            data_files=["sales.csv"],
            timeout_seconds=300
        )
        result = await agent.run()

        # With event streaming
        async def handle_event(event_type: str, data: dict):
            print(f"{event_type}: {data}")

        agent = DeepPlotAgent(
            cwd=Path("/path/to/dir"),
            data_files=["sales.csv"],
            on_event=handle_event
        )
        result = await agent.run()
    """

    INITIAL_PROMPT = """Explore the working directory and find data files to analyze. You have {timeout_seconds} seconds.

**Research process:**
1. **Look** - List files in the directory. Load any data files you find (csv, json, parquet, etc.).
2. **Ask** - What is this dataset about? What questions are worth investigating?
3. **Investigate** - Answer your questions. Support each finding with evidence (numbers or plotly visualizations).
4. **Synthesize** - What did you learn?
{filenames}{user_prompt}"""

    IMPROVEMENT_PROMPT = """You have {time_remaining:.0f} seconds remaining.

**Reflect:**
- Does your evidence support your findings?
- Dig deeper. Check specific values. Use `get_plot_image` to view plots, and `relayout`/`legendclick`/`selected` to interact.
- What new questions emerge?

Continue investigating."""

    FINAL_REPORT_PROMPT = """Write your **Final Report**.

**Structure:**
1. **Data** - Describe the dataset
2. **Findings** - List each finding with evidence (numbers, tables, or plot references)

**To finish:**
1. Redraw any unclear plots (fix overlapping, ensure readable).
2. Decide which plots are evidence and their display order (e.g., plots 4, 7, 2).
3. Write `analysis.md` referencing plots as Plot 1, Plot 2, Plot 3... (matching the order you chose).
4. Call `submit_summary(evidence_plots=[4, 7, 2])` with original IDs in that order.
"""

    def __init__(
        self,
        cwd: Path | str,
        data_files: list[str] | str | None = None,
        timeout_seconds: int = 120,
        user_prompt: str = "",
        on_event: EventCallback | None = None,
        model: str | None = None,
        session_name: str = "Deep Plot"
    ):
        """
        Initialize Deep Plot Agent.

        Args:
            cwd: Working directory containing data files
            data_files: Name(s) of data file(s) to analyze. If None/empty, agent explores cwd.
            timeout_seconds: Maximum time to run (default: 120 seconds)
            user_prompt: Optional additional instructions from user
            on_event: Optional callback for event streaming.
                      Signature: async def callback(event_type: str, data: dict)
            model: Model to use (e.g., "sonnet", "opus")
            session_name: Display name for the session
        """
        self.cwd = Path(cwd).resolve()
        if data_files is None:
            self.data_files = []
        elif isinstance(data_files, str):
            self.data_files = [data_files]
        else:
            self.data_files = list(data_files)
        self.timeout_seconds = timeout_seconds
        self.user_prompt = user_prompt
        self.on_event = on_event
        self.model = model
        self.session_name = session_name

        # Runtime state
        self.agent: Agent | None = None
        self.iteration_count = 0
        self.start_time: float | None = None
        self.report = DeepPlotReport()

        # Cleanup function for plotly event subscription
        self._plotly_cleanup: Callable | None = None

    def _time_remaining(self) -> float:
        """Get remaining time in seconds."""
        if self.start_time is None:
            return self.timeout_seconds
        elapsed = time.time() - self.start_time
        return max(0, self.timeout_seconds - elapsed)

    def _is_time_up(self) -> bool:
        """Check if timeout has been reached."""
        return self._time_remaining() <= 0

    async def run(self) -> dict:
        """
        Run the deep plot agent.

        The agent runs continuously until timeout, then produces a final report.
        Events are streamed via on_event callback if provided.

        Returns:
            Dict with final statistics:
            - iteration_count: Number of iterations completed
            - evidence_plots: List of plot IDs from final report
            - summary: Summary text from final report
            - total_cost_usd: Total cost
            - duration_ms: Total duration
            - session_id: Session ID for accessing plots
        """
        self.start_time = time.time()
        self.report.reset()

        try:

            # Create MCP servers
            # Pass on_event to plotly server - it handles EventBus subscription
            plotly_server, self._plotly_cleanup = create_plotly_mcp_server(
                enable_headless=True,
                on_event=self.on_event
            )
            deep_plot_server = create_deep_plot_mcp_server(self.report, self.cwd)

            # Build tools list
            allowed_tools = list(PLOTLY_TOOLS) + list(DEEP_PLOT_TOOLS)

            # Create Agent directly
            self.agent = Agent(
                agent_type="deep-plot",
                name=self.session_name,
                cwd=self.cwd,
                permission_mode="bypassPermissions",
                allowed_tools=allowed_tools,
                mcp_servers={
                    "plotly": plotly_server,
                    "deep_plot": deep_plot_server
                },
                enable_storage=True,
                logs_root=get_logs_root(),
                model=self.model
            )

            # Subscribe to agent events if callback provided
            if self.on_event:
                self.agent.events.subscribe(self.on_event)

            # Start agent (self-registers in global registry)
            await self.agent.start()

            # Emit session_info event immediately after agent starts
            # This allows frontend to update pending tab with real session_id
            if self.on_event and self.agent.session_id:
                await self.on_event('session_info', {
                    'session_id': self.agent.session_id,
                    'session_name': self.session_name
                })

            logger.info(f"Deep Plot Agent started (session: {self.agent.session_id}, timeout: {self.timeout_seconds}s, files: {self.data_files})")

            # Initial query
            self.iteration_count = 1
            if self.data_files:
                filenames = ', '.join(f'`{f}`' for f in self.data_files)
                filenames_section = f"\n\n**User uploaded:** {filenames}"
            else:
                filenames_section = ""
            user_prompt_section = f"\n\n{self.user_prompt}" if self.user_prompt else ""
            initial_prompt = self.INITIAL_PROMPT.format(
                filenames=filenames_section,
                user_prompt=user_prompt_section,
                timeout_seconds=self.timeout_seconds
            )

            await self.agent.query(initial_prompt, display=False, hidden=True)

            # Continuous analysis loop - runs until timeout
            while not self._is_time_up():
                self.iteration_count += 1
                time_remaining = self._time_remaining()

                prompt = self.IMPROVEMENT_PROMPT.format(
                    time_remaining=time_remaining
                )

                await self.agent.query(prompt, display=False, hidden=True)

                # Small delay between iterations
                await asyncio.sleep(1)

            # Analysis phase complete, now request final report
            logger.info(f"Analysis phase complete after {self.iteration_count} iterations, requesting final report")
            self.iteration_count += 1
            await self.agent.query(self.FINAL_REPORT_PROMPT, display=False, hidden=True)

            logger.info(f"Final report complete, evidence plots: {self.report.evidence_plots}")

        except Exception as e:
            logger.error(f"Deep Plot Agent error: {e}")
            raise

        finally:
            # Cleanup plotly event subscription
            if self._plotly_cleanup:
                self._plotly_cleanup()
                self._plotly_cleanup = None

            # Read final report
            final_report = self.report.read()
            evidence_plots = final_report['evidence_plots']
            session_id = self.agent.session_id if self.agent else None

            # Finalize plots: renumber evidence plots, delete non-evidence plots
            id_mapping = {}
            if session_id and evidence_plots:
                try:
                    session_store = SessionStore(get_logs_root())
                    id_mapping = session_store.finalize_plots(session_id, evidence_plots)
                    logger.info(f"Finalized plots: {id_mapping}")

                    # Clear PlotStore cache for this session (so frontend refetches)
                    get_plot_store().clear_session(session_id)

                    # Emit plots_renumbered event for frontend to update tabs
                    if self.on_event:
                        await self.on_event('plots_renumbered', {
                            'session_id': session_id,
                            'id_mapping': id_mapping,
                            'final_plot_ids': list(id_mapping.values())
                        })
                except Exception as e:
                    logger.error(f"Failed to finalize plots: {e}")

            # Collect final stats
            stats = {
                'iteration_count': self.iteration_count,
                'evidence_plots': evidence_plots,
                'summary': final_report['summary'],
                'total_cost_usd': self.agent.total_cost_usd if self.agent else 0,
                'duration_ms': int((time.time() - self.start_time) * 1000) if self.start_time else 0,
                'session_id': session_id,
                'id_mapping': id_mapping
            }

            # Stop agent (clears event subscribers, unregisters from registry)
            if self.agent:
                await self.agent.stop()
                self.agent = None

            return stats
