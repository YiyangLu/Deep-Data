"""MCTS Node and related types.

Core data structures for the MCTS search tree.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:
    from .agents.shared import AgentResult


@dataclass
class MetricValue:
    """Wraps metric with optimization direction for correct comparison.

    Examples:
        # Accuracy (higher is better)
        m1 = MetricValue(0.95, maximize=True)
        m2 = MetricValue(0.90, maximize=True)
        assert m1 > m2

        # RMSE (lower is better)
        m3 = MetricValue(0.5, maximize=False)
        m4 = MetricValue(0.8, maximize=False)
        assert m3 > m4  # 0.5 is better than 0.8 for RMSE
    """

    value: Optional[float]
    maximize: bool = True  # True for accuracy/AUC, False for RMSE/loss

    def __lt__(self, other: "MetricValue") -> bool:
        """Less than = worse performance."""
        if self.value is None:
            return True  # None is always worst
        if other.value is None:
            return False
        if self.maximize:
            return self.value < other.value
        else:
            return self.value > other.value  # Lower is better

    def __gt__(self, other: "MetricValue") -> bool:
        """Greater than = better performance."""
        if self.value is None:
            return False
        if other.value is None:
            return True
        if self.maximize:
            return self.value > other.value
        else:
            return self.value < other.value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MetricValue):
            return NotImplemented
        return self.value == other.value

    def __le__(self, other: "MetricValue") -> bool:
        return self < other or self == other

    def __ge__(self, other: "MetricValue") -> bool:
        return self > other or self == other

    def improvement_over(self, other: "MetricValue") -> float:
        """Calculate improvement (positive = better).

        Args:
            other: Baseline metric to compare against

        Returns:
            Positive value if self is better, negative if worse, 0 if equal or None
        """
        if self.value is None or other.value is None:
            return 0.0
        diff = self.value - other.value
        return diff if self.maximize else -diff


class WorstMetricValue(MetricValue):
    """Special case for buggy solutions - always compares as worst."""

    def __init__(self):
        super().__init__(value=None, maximize=True)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, MetricValue):
            return NotImplemented
        return True  # Always worst

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, MetricValue):
            return NotImplemented
        return False  # Never better


@dataclass
class MCTSNode:
    """Represents a single solution in the MCTS search tree.

    Key design: No `code` field - Git stores the code via commit_hash.
    Fields are filled gradually through the node lifecycle.

    Lifecycle:
        1. Creation: id, stage, parent
        2. Agent run: plan, run_command, commit_hash, is_buggy, metric, analysis, error_summary
        3. Backprop: visits, total_reward
    """

    # === Required at creation ===
    id: str
    stage: Literal["root", "draft", "improve", "debug"]
    parent: Optional["MCTSNode"] = None
    children: list["MCTSNode"] = field(default_factory=list)

    # === Filled by agent (code gen + execution + evaluation) ===
    plan: Optional[str] = None
    run_command: Optional[str] = None
    commit_hash: Optional[str] = None
    metric: Optional[MetricValue] = None
    is_buggy: Optional[bool] = None
    analysis: Optional[str] = None
    error_summary: Optional[str] = None

    # === Legacy fields (for debug prompts showing parent's output) ===
    output: Optional[str] = None

    # === Assigned by journal.append() ===
    step: Optional[int] = None

    # === MCTS statistics ===
    visits: int = 0
    total_reward: float = 0.0
    is_terminal: bool = False

    # === Improvement tracking ===
    local_best_node: Optional["MCTSNode"] = None
    improve_failure_depth: int = 0
    continue_improve: bool = False

    # === Debug tracking ===
    is_debug_success: bool = False

    # === Parallel expansion tracking ===
    expected_child_count: int = 0

    # === Timestamps ===
    finish_time: Optional[str] = None

    # === Running agent tracking ===
    session_id: Optional[str] = None  # Session ID of agent currently working on this node

    # === Absorb Methods ===

    def absorb_agent_result(self, result: "AgentResult") -> None:
        """Fill node fields from agent result.

        Agent runs code and reports is_success, metric, analysis, etc.
        This replaces the old absorb_exec_result + absorb_eval_result flow.

        Args:
            result: AgentResult with is_success, metric_value, etc.
        """
        self.is_buggy = not result.is_success
        self.analysis = result.analysis
        self.error_summary = result.error_summary
        self.output = result.output

        if result.metric_value is not None:
            self.metric = MetricValue(
                value=result.metric_value,
                maximize=not (result.lower_is_better or False),
            )
        else:
            self.metric = WorstMetricValue()

    # === Memory Functions ===

    def fetch_child_memory(self) -> str:
        """Build context from child nodes (siblings of potential new child).

        Helps agent avoid repeating failed approaches by showing what
        sibling nodes have already tried.

        Returns:
            Formatted string describing children's approaches and results
        """
        summaries = []
        for child in self.children:
            if child.is_buggy is None:
                continue  # Skip unevaluated nodes

            summary = f"Design: {child.plan}\n"

            if child.is_buggy is True:
                summary += "Results: The implementation of this design has bugs.\n"
                summary += "Insight: Using a different approach may avoid the same bugs.\n"
            else:
                if child.analysis:
                    summary += f"Results: {child.analysis}\n"
                if child.metric and child.metric.value is not None:
                    summary += f"Validation Metric: {child.metric.value}\n"

            summaries.append(summary)

        if not summaries:
            return "There is no previous memory"
        return "\n-------------------------------\n".join(summaries)

    def fetch_parent_memory(self) -> str:
        """Build context from parent's successful approach.

        Used for improve prompts to understand what the current
        solution looks like before improving it.

        Returns:
            Formatted string describing parent's approach and results
        """
        if self.parent is None:
            return ""
        if self.parent.is_buggy is None or self.parent.is_buggy is True:
            return ""

        summary = f"Design: {self.parent.plan}\n"

        if self.parent.analysis:
            summary += f"Results: {self.parent.analysis}\n"
        if self.parent.metric and self.parent.metric.value is not None:
            summary += f"Validation Metric: {self.parent.metric.value}\n"

        return summary

    # === Computed Properties ===

    @property
    def debug_depth(self) -> int:
        """Depth in debug chain (computed from parent).

        Returns:
            0 if not a debug node
            1 if parent is buggy but grandparent isn't
            n if n consecutive debug steps
        """
        if self.stage != "debug":
            return 0
        if self.parent is None:
            return 0
        return self.parent.debug_depth + 1

    def has_successful_debug_child(self) -> bool:
        """Check if any child successfully fixed this node's bug."""
        return any(c.is_debug_success for c in self.children)
