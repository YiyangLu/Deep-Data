"""MCTS Configuration.

Configuration dataclass for the MCTS search.
"""

from dataclasses import dataclass


@dataclass
class MCTSConfig:
    """Configuration for MCTS search.

    Attributes:
        max_steps: Maximum MCTS iterations
        time_limit: Total time budget in seconds
        parallel_workers: Number of parallel worktrees/workers

        model: Claude model to use (sonnet, opus, haiku)

        num_drafts: Max drafts from root node
        max_draft_children: Max children per draft node
        max_debug_children: Max debug attempts per buggy node
        max_improve_children: Max improvements per working node

        decay_type: Exploration decay type (piecewise, linear, none)
        initial_C: Initial exploration constant
        final_C: Final exploration constant after decay
        decay_start: Fraction of time when decay starts
        decay_end: Fraction of time when decay ends

        metric_improvement_threshold: Min improvement to count as success
        max_improve_failure: Max consecutive failed improvements
        max_debug_depth: Max chained debug attempts
        back_debug_depth: How far back to try debugging
    """

    # Defaults (single source of truth)
    DEFAULT_WORKERS: int = 2

    # Search parameters
    max_steps: int = 0  # 0 = infinite (time limit is primary constraint)
    time_limit: int = 21600  # 6 hours
    parallel_workers: int = DEFAULT_WORKERS

    # GPU assignment (workers are distributed across GPUs round-robin)
    num_gpus: int = 2  # Set to 0 to disable GPU assignment

    # Conda environment isolation (each worker gets its own cloned env)
    base_conda_env: str = "agent"  # Name of base env to clone, empty to disable

    # Model
    model: str = "opus"

    # Expansion limits
    num_drafts: int = 5
    max_draft_children: int = 5
    max_debug_children: int = 3
    max_improve_children: int = 3

    # Exploration decay
    decay_type: str = "piecewise"
    initial_C: float = 1.414
    final_C: float = 0.7
    decay_start: float = 0.3
    decay_end: float = 0.7

    # Improvement tracking
    metric_improvement_threshold: float = 0.0001
    max_improve_failure: int = 3
    max_debug_depth: int = 20
    back_debug_depth: int = 3
