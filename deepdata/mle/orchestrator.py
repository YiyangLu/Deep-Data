"""MCTS Orchestrator.

Main orchestrator managing the MCTS search for ML solutions.
Aligned with ML-Master's algorithm as documented in algorithm.md.
"""

import asyncio
import logging
import math
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from claude_agent_sdk import ProcessError

from ..core import Agent
from ..plotly.mcp_tools import create_plotly_mcp_server
from .agents import (
    run_data_report_agent,
    run_debug_agent,
    run_draft_agent,
    run_improve_agent,
    AgentResult,
    PromptContext,
)
from .config import MCTSConfig
from .context import Context
from .journal import Journal
from .node import MCTSNode, MetricValue, WorstMetricValue
from .storage import get_mle_store, MLEStore
from .utils import GitWorkspace


class MCTSOrchestrator:
    """Main orchestrator for MCTS-based ML solution search.

    Implements ML-Master's MCTS algorithm with:
    - Conditional backpropagation based on check_improvement
    - Parallel workers with current_node tracking
    - Debug success and continue_improve flag propagation

    Usage:
        orchestrator = MCTSOrchestrator(workspace, context, config)
        results = await orchestrator.run()
    """

    def __init__(
        self,
        workspace: Path,
        context: Context,
        config: MCTSConfig,
        run_id: str | None = None,
    ):
        """Initialize orchestrator.

        Args:
            workspace: Root workspace directory
            context: Environment context (task, data, outputs)
            config: MCTS configuration
            run_id: Unique run identifier (for session tagging)
        """
        self.workspace = Path(workspace)
        self.context = context
        self.config = config
        self.run_id = run_id or str(uuid.uuid4())

        # Storage in logs/mle/{run_id}/
        self.store = get_mle_store()
        self.store.create_run(self.run_id, context, self.workspace)

        # Journal for persistence (stored in logs/, not .memory/)
        journal_path = self.store.get_journal_path(self.run_id)
        self.journal = Journal(journal_path)

        # Git workspace for worktrees
        self.git = GitWorkspace(
            workspace=self.workspace,
            gitignore=context.gitignore,
            sync=context.sync,
            base_conda_env=config.base_conda_env if config.base_conda_env else None,
        )

        # Virtual root node (ML-Master pattern)
        self.virtual_root = MCTSNode(
            id="root",
            stage="root",
            parent=None,
            plan="Virtual root - starting point for all drafts",
            metric=WorstMetricValue(),
            is_buggy=None,  # Root is never evaluated
        )
        self.journal.append(self.virtual_root)

        # Time tracking
        self.start_time: float = 0.0
        self.search_start_time: float = 0.0  # After init, for search-only timing
        self.current_step: int = 0
        self.accumulated_time: float = 0.0  # Total time from previous sessions

        # Best solution tracking (ML-Master pattern)
        self.best_node: Optional[MCTSNode] = None

        # Current node tracking for workers (ML-Master's current_node_list concept)
        self.current_node_list: list[MCTSNode] = []

        # Worktrees storage
        self.worktrees: list[Path] = []

        # In-progress nodes tracking (for UI visibility)
        # Maps worker_id -> (node, status) where status is "expanding"|"executing"|"evaluating"
        self.in_progress_nodes: dict[int, tuple[MCTSNode, str]] = {}

        # Failed expansions tracking (for debugging and potential reborn)
        self.failed_expansions: list[dict] = []

        # Logger
        self.logger = logging.getLogger(__name__)

    @classmethod
    def from_journal(
        cls,
        run_id: str,
        config: MCTSConfig,
    ) -> "MCTSOrchestrator":
        """Restore orchestrator from existing journal for resume after server restart.

        Args:
            run_id: Run identifier (must exist in logs/mle/)
            config: MCTS configuration (will use new time/step limits)

        Returns:
            Restored MCTSOrchestrator with tree loaded from journal

        Raises:
            FileNotFoundError: If journal.db doesn't exist
            ValueError: If run not found
        """
        store = get_mle_store()

        # Load context and run state from storage
        context = store.load_context(run_id)
        run_state = store.load_run_state(run_id)
        workspace = Path(run_state["workspace"])

        journal_path = store.get_journal_path(run_id)
        if not journal_path.exists():
            raise FileNotFoundError(f"Journal not found: {journal_path}")

        # Create instance without creating a new root
        orchestrator = object.__new__(cls)

        # Initialize basic attributes
        orchestrator.workspace = workspace
        orchestrator.context = context
        orchestrator.config = config
        orchestrator.run_id = run_id
        orchestrator.store = store

        # Open existing journal
        orchestrator.journal = Journal(journal_path)

        # Git workspace
        orchestrator.git = GitWorkspace(
            workspace=orchestrator.workspace,
            gitignore=context.gitignore,
            sync=context.sync,
        )

        # Load tree from journal
        root = orchestrator.journal.load_tree()
        if root is None:
            raise ValueError("Journal is empty - cannot restore")
        orchestrator.virtual_root = root

        # Restore current_step from journal
        step_str = orchestrator.journal.get_state("current_step")
        orchestrator.current_step = int(step_str) if step_str else len(orchestrator.journal)

        # Restore best_node from journal
        best_id = orchestrator.journal.get_state("best_node_id")
        orchestrator.best_node = None
        if best_id:
            # Find node by ID in the tree
            def find_node(node: MCTSNode, target_id: str) -> Optional[MCTSNode]:
                if node.id == target_id:
                    return node
                for child in node.children:
                    found = find_node(child, target_id)
                    if found:
                        return found
                return None
            orchestrator.best_node = find_node(root, best_id)

        # Initialize other attributes
        orchestrator.start_time = 0.0
        orchestrator.search_start_time = 0.0
        orchestrator.current_node_list = []
        orchestrator.worktrees = []
        orchestrator.in_progress_nodes = {}
        orchestrator.failed_expansions = []
        orchestrator.logger = logging.getLogger(__name__)

        # Restore accumulated time from journal
        time_str = orchestrator.journal.get_state("time_elapsed")
        orchestrator.accumulated_time = float(time_str) if time_str else 0.0

        return orchestrator

    def time_remaining(self) -> float:
        """Calculate remaining time budget in seconds."""
        if self.start_time == 0:
            return float(self.config.time_limit)
        elapsed = time.time() - self.start_time
        return max(0, self.config.time_limit - elapsed)

    def time_fraction(self) -> float:
        """Calculate fraction of time elapsed (0.0 to 1.0)."""
        if self.start_time == 0:
            return 0.0
        elapsed = time.time() - self.start_time
        return min(1.0, elapsed / self.config.time_limit)

    def get_exploration_constant(self) -> float:
        """Calculate exploration constant C with decay.

        Uses piecewise decay as default (ML-Master style).
        Returns higher C early (more exploration), lower C later (more exploitation).
        """
        frac = self.time_fraction()

        if self.config.decay_type == "none":
            return self.config.initial_C

        elif self.config.decay_type == "linear":
            # Linear decay from initial_C to final_C
            return self.config.initial_C + (self.config.final_C - self.config.initial_C) * frac

        else:  # piecewise (default)
            if frac < self.config.decay_start:
                return self.config.initial_C
            elif frac > self.config.decay_end:
                return self.config.final_C
            else:
                # Linear interpolation in decay region
                decay_frac = (frac - self.config.decay_start) / (self.config.decay_end - self.config.decay_start)
                return self.config.initial_C + (self.config.final_C - self.config.initial_C) * decay_frac

    def _get_prompt_context(self, gpu_id: int | None = None) -> PromptContext:
        """Build PromptContext for agent prompts.

        Args:
            gpu_id: Assigned GPU ID for this worker (None if no GPU)
        """
        return PromptContext(
            time_remaining=int(self.time_remaining()),
            steps_remaining=self.config.max_steps - self.current_step,
            current_step=self.current_step,
            gpu_id=gpu_id,
        )

    # === Selection (ML-Master aligned) ===

    def _uct_value(self, node: MCTSNode, C: float) -> float:
        """Calculate UCT value for a node.

        UCT = Q/N + C * sqrt(ln(N_parent) / N)

        Args:
            node: Node to evaluate
            C: Exploration constant

        Returns:
            UCT value (infinity for unvisited nodes)
        """
        if node.visits == 0:
            return float('inf')
        if node.parent is None or node.parent.visits == 0:
            return float('inf')

        exploitation = node.total_reward / node.visits
        exploration = C * math.sqrt(math.log(node.parent.visits) / node.visits)
        return exploitation + exploration

    def _uct_select_child(self, node: MCTSNode, C: float) -> Optional[MCTSNode]:
        """Select best child using UCT.

        Note: Does NOT filter terminal nodes (matches ML-Master).
        If terminal node selected, loop exits on next iteration.

        Args:
            node: Parent node
            C: Exploration constant

        Returns:
            Best child by UCT, or None if no children
        """
        if not node.children:
            return None

        return max(node.children, key=lambda n: self._uct_value(n, C))

    def is_fully_expanded(self, node: MCTSNode) -> bool:
        """Check if node has reached expansion limit.

        Args:
            node: Node to check

        Returns:
            True if no more children should be added
        """
        actual = len(node.children)
        pending = node.expected_child_count

        if node.stage == "root":
            return (actual + pending) >= self.config.num_drafts

        elif node.is_buggy:
            # For buggy/invalid nodes, stop after first successful debug child
            if any(c.is_debug_success for c in node.children):
                return True
            return (actual + pending) >= self.config.max_debug_children

        elif node.stage == "draft":
            return (actual + pending) >= self.config.max_draft_children

        else:  # improve
            return (actual + pending) >= self.config.max_improve_children

    def _is_expandable(self, node: MCTSNode) -> bool:
        """Check if node can be expanded.

        A node is expandable if:
        1. Not fully expanded
        2. Not terminal
        3. For debug: not exceeded max depth
        4. For improve: still has continue_improve flag or not exceeded failure depth
        """
        if node.is_terminal:
            return False
        if self.is_fully_expanded(node):
            return False

        # Check debug depth limit
        if node.stage == "debug" and node.debug_depth >= self.config.max_debug_depth:
            return False

        # Check improve failure limit
        if node.stage == "improve" and not node.continue_improve:
            if node.improve_failure_depth >= self.config.max_improve_failure:
                return False

        return True

    def select(self) -> MCTSNode:
        """Select node to expand using UCT.

        Matches ML-Master's selection logic exactly.
        Respects continue_improve and is_debug_success flags.

        Returns:
            Selected node for expansion
        """
        node = self.virtual_root
        C = self.get_exploration_constant()

        while node is not None and not node.is_terminal:
            if not self.is_fully_expanded(node):
                # Case 1: Buggy node with debug success - explore debug children
                if node.is_buggy and node.is_debug_success:
                    child = self._uct_select_child(node, C)
                    if child:
                        node = child
                        continue
                    return node

                # Case 2: Should continue improving - go deeper
                elif node.continue_improve and len(node.children) > 0:
                    child = self._uct_select_child(node, C)
                    if child:
                        node = child
                        continue
                    return node

                # Case 3: Node needs expansion
                else:
                    return node

            else:
                # Fully expanded - select best child via UCT
                child = self._uct_select_child(node, C)
                if child is None:
                    return node
                node = child

        return node

    # === Expansion ===

    def _get_child_stage(self, parent: MCTSNode) -> str:
        """Determine what stage a new child should be.

        Args:
            parent: Parent node

        Returns:
            Stage for child node ("draft", "improve", or "debug")
        """
        if parent.stage == "root":
            return "draft"
        elif parent.is_buggy:
            return "debug"
        else:
            return "improve"

    async def expand(
        self, parent: MCTSNode, worktree: Path, placeholder: MCTSNode | None = None,
        worker_id: int = 0
    ) -> MCTSNode:
        """Generate a child node by running appropriate agent.

        The agent modifies files in the worktree, then we commit and create node.

        NOTE: Does NOT add to tree - caller adds after evaluation (ML-Master pattern).

        Args:
            parent: Parent node to expand from
            worktree: Git worktree path to work in
            placeholder: Optional placeholder node to update with session_id
            worker_id: Worker index (for GPU assignment)

        Returns:
            New child node (not yet evaluated)
        """
        stage = self._get_child_stage(parent)

        # Compute GPU assignment
        gpu_id = None
        if self.config.num_gpus > 0:
            gpu_id = worker_id % self.config.num_gpus

        prompt_ctx = self._get_prompt_context(gpu_id=gpu_id)

        # Build environment: conda env vars for isolated env
        # GPU assignment is via prompt (agent sets os.environ['CUDA_VISIBLE_DEVICES'])
        env = self.git.get_env_vars(worktree)  # PATH, CONDA_PREFIX

        # Callback to set session_id on placeholder for real-time tracking
        def on_agent_start(session_id: str):
            if placeholder:
                placeholder.session_id = session_id

        # Checkout parent's state (or clean for draft)
        if parent.stage == "root":
            self.git.checkout(worktree, self.git.default_branch)
        else:
            self.git.checkout(worktree, parent.commit_hash)

        # Run appropriate agent
        if stage == "draft":
            result = await run_draft_agent(
                worktree=worktree,
                context=self.context,
                parent_node=parent,
                prompt_ctx=prompt_ctx,
                model=self.config.model,
                run_id=self.run_id,
                on_agent_start=on_agent_start,
                env=env,
            )
            local_best = parent  # Draft uses virtual_root as baseline

        elif stage == "debug":
            result = await run_debug_agent(
                worktree=worktree,
                context=self.context,
                parent_node=parent,
                prompt_ctx=prompt_ctx,
                model=self.config.model,
                run_id=self.run_id,
                on_agent_start=on_agent_start,
                env=env,
            )
            local_best = parent.local_best_node

        else:  # improve
            result = await run_improve_agent(
                worktree=worktree,
                context=self.context,
                parent_node=parent,
                prompt_ctx=prompt_ctx,
                model=self.config.model,
                run_id=self.run_id,
                on_agent_start=on_agent_start,
                env=env,
            )
            local_best = parent.local_best_node

        # Commit changes
        commit_msg = f"{stage}: {result.plan[:50]}"
        commit_hash = self.git.commit(worktree, commit_msg)

        # Create node with all fields from agent result
        node = MCTSNode(
            id=str(uuid.uuid4()),
            stage=stage,
            parent=parent,
            plan=result.plan,
            run_command=result.run_command,
            commit_hash=commit_hash,
            local_best_node=local_best,
        )

        # Fill evaluation fields from agent result
        node.absorb_agent_result(result)

        return node

    # === Reward Calculation (ML-Master aligned) ===

    def calculate_reward(self, child: MCTSNode, parent: MCTSNode) -> float:
        """Calculate reward for backpropagation.

        Reward components (from ML-Master):
        - -1 for buggy/invalid solutions
        - +1 for debug success OR +1 base reward (mutually exclusive)
        - +1 additional for beating global best

        Args:
            child: Evaluated child node
            parent: Parent node

        Returns:
            Reward value
        """
        if child.is_buggy is True or child.is_buggy is None:
            return -1.0

        if child.metric is None or child.metric.value is None:
            return -1.0

        reward = 0.0

        # Check for global best improvement
        is_new_best = self._update_best_node(child)
        if is_new_best:
            reward += 1.0

        # Debug success OR base reward (mutually exclusive)
        if parent.is_buggy is True:
            child.is_debug_success = True
            reward += 1.0
        else:
            reward += 1.0

        return reward

    # === Backpropagation (ML-Master aligned) ===

    def backpropagate(self, node: MCTSNode, reward: float, add_to_tree: bool = True) -> None:
        """Update statistics from node to root, propagating flags.

        Propagates:
        - is_debug_success up the tree
        - continue_improve flag up (except to root)
        - Resets improve_failure_depth on successful backprop

        Args:
            node: Starting node
            reward: Reward to propagate
            add_to_tree: Whether to update visits/reward (False for error rollback)
        """
        node.finish_time = datetime.now().isoformat()
        current = node

        while current is not None:
            # 1. Propagate debug success
            if current.parent is not None:
                if current.is_buggy is False and current.parent.is_buggy is True:
                    current.parent.is_debug_success = True
                elif current.is_buggy is True and current.is_debug_success is True and current.parent.is_buggy is True:
                    current.parent.is_debug_success = True

            # 2. Propagate continue_improve (except to root)
            if current.parent is not None and current.parent.stage != "root":
                current.parent.continue_improve = current.continue_improve

            # 3. Reset improve_failure_depth on backprop
            if add_to_tree and current.improve_failure_depth > 0:
                current.improve_failure_depth = 0

            # 4. Update MCTS statistics
            if add_to_tree:
                current.visits += 1
                current.total_reward += reward

            self.journal.update_node(current)
            current = current.parent

    # === Improvement Tracking (ML-Master aligned) ===

    def check_improvement(self, child: MCTSNode, parent: MCTSNode) -> bool:
        """Check if child improved over parent. Update tracking state.

        Matches ML-Master exactly:
        - Calls backpropagate() INSIDE this function when should_backprop
        - Returns True if backpropagated (caller should return to root)
        - Returns False if did NOT backpropagate (caller should continue from child)

        Args:
            child: New child node (already evaluated)
            parent: Parent node

        Returns:
            True: backpropagated (caller should restart from root)
            False: did NOT backpropagate (caller should continue from child)
        """
        should_backpropagate = False
        local_best = child.local_best_node  # Inherited from parent during node creation

        if child.is_buggy is False:
            new_metric = child.metric.value if child.metric else None

            # Debug success case - always backprop to reward the fix
            if parent.is_buggy:
                should_backpropagate = True

            if new_metric is not None and local_best is not None and local_best.metric is not None and local_best.metric.value is not None:
                # Calculate improvement
                improvement = child.metric.improvement_over(local_best.metric)

                if improvement < self.config.metric_improvement_threshold:
                    if local_best.improve_failure_depth < self.config.max_improve_failure:
                        # Below threshold but can still try - DON'T backprop
                        local_best.improve_failure_depth += 1
                        child.continue_improve = True
                    else:
                        # Max failures reached - terminate this path
                        child.continue_improve = False
                        child.is_terminal = True
                        should_backpropagate = True
                else:
                    # Good improvement - update local best, DON'T backprop
                    child.local_best_node = child
                    child.continue_improve = True

            elif new_metric is not None:
                # No local best yet - this node becomes local best, DON'T backprop
                child.local_best_node = child
                child.continue_improve = True
            else:
                # No metric value - backprop
                should_backpropagate = True

        elif child.is_buggy is None:
            should_backpropagate = True

        else:  # child.is_buggy is True
            # Debug depth termination (from ML-Master)
            if child.debug_depth >= self.config.back_debug_depth:
                should_backpropagate = True
                if child.debug_depth >= self.config.max_debug_depth:
                    child.is_terminal = True

        # ML-Master style: handle backprop INSIDE this function
        if should_backpropagate:
            reward = self.calculate_reward(child, parent)
            self.backpropagate(child, reward)
        else:
            self.current_node_list.append(child)  # Track for debugging/logging

        return should_backpropagate

    def _update_best_node(self, candidate: MCTSNode) -> bool:
        """Update global best node if candidate is better.

        Args:
            candidate: Candidate node

        Returns:
            True if candidate became new best
        """
        if candidate.is_buggy or candidate.metric is None:
            return False

        if self.best_node is None:
            self.best_node = candidate
            self.journal.set_state("best_node_id", candidate.id)
            return True

        if candidate.metric > self.best_node.metric:
            self.best_node = candidate
            self.journal.set_state("best_node_id", candidate.id)
            return True

        return False

    # === Main Loop (ML-Master aligned) ===

    async def _reborn_agent(
        self,
        session_id: str,
        stderr: str | None,
        worktree: Path,
        worker_id: int,
    ) -> AgentResult:
        """Reborn a dead agent by resuming its session with a recovery prompt.

        Args:
            session_id: Session ID of the dead agent
            stderr: Error output from ProcessError (may be None)
            worktree: Path to the worktree
            worker_id: Worker index (for GPU assignment)

        Returns:
            AgentResult from the resumed agent

        Raises:
            ValueError: If agent doesn't produce structured output
        """
        # Build recovery prompt
        if stderr:
            recovery_prompt = f"""Your previous session crashed with error:
{stderr}

Please continue from where you left off."""
        else:
            recovery_prompt = """Your previous session crashed unexpectedly.
Please continue from where you left off."""

        # Build environment (same as expand)
        env = self.git.get_env_vars(worktree)
        gpu_id = worker_id % self.config.num_gpus if self.config.num_gpus > 0 else None
        if gpu_id is not None:
            env["CUDA_VISIBLE_DEVICES"] = str(gpu_id)

        # Create plotly MCP server for visualization
        plotly_server, plotly_cleanup = create_plotly_mcp_server(enable_headless=True)

        # Create agent with same config as original
        agent = Agent(
            agent_type="reborn",
            name="Reborn",
            cwd=worktree,
            model=self.config.model,
            permission_mode="bypassPermissions",
            enable_storage=True,
            mcp_servers={"plotly": plotly_server},
            output_format={
                "type": "json_schema",
                "schema": AgentResult.model_json_schema()
            },
            env=env,
        )

        # Set session_id for resume
        agent.session_id = session_id

        try:
            # Resume the session (creates new subprocess with old context)
            await agent.resume()

            # Send recovery prompt
            await agent.query(recovery_prompt, display=False)

            if agent.structured_output is None:
                raise ValueError("Reborn agent did not produce structured output")

            return AgentResult.model_validate(agent.structured_output)
        finally:
            await agent.stop()
            # Cleanup plotly MCP server
            if plotly_cleanup:
                plotly_cleanup()

    async def step(self, current_node: Optional[MCTSNode], worker_id: int) -> MCTSNode:
        """Single MCTS iteration.

        Args:
            current_node: Node to continue from (if check_improvement returned False).
                          If None or root, starts fresh selection from virtual root.
            worker_id: Worker index (for worktree isolation).

        Returns:
            - virtual_root: if should restart selection (backpropagated or terminal)
            - child: if should continue from this node (no backprop, keep improving)
        """
        worktree = self.worktrees[worker_id]

        # 1. SELECT: Use current_node or select from root
        if current_node is None or current_node.stage == "root":
            node = self.select()
        else:
            node = current_node

        # Check if we can expand
        if not self._is_expandable(node):
            return self.virtual_root

        node.expected_child_count += 1  # Reserve slot

        # Create placeholder for in-progress tracking
        stage = self._get_child_stage(node)
        placeholder = MCTSNode(
            id=str(uuid.uuid4()),
            stage=stage,
            parent=node,
            plan=f"Running {stage} agent...",
        )
        self.in_progress_nodes[worker_id] = (placeholder, "expanding")

        try:
            # 2. EXPAND: Agent writes code, runs it, reports results
            #    expand() calls absorb_agent_result() to fill is_buggy, metric, etc.
            child = await self.expand(node, worktree, placeholder=placeholder, worker_id=worker_id)

            # 3. ADD TO PARENT'S CHILDREN (for tree structure)
            node.children.append(child)

            # 4. CHECK IMPROVEMENT: Conditionally backpropagate (ML-Master style)
            #    NOTE: check_improvement calls backprop inside (matches ML-Master exactly)
            should_backprop = self.check_improvement(child, node)

            # 5. ADD TO JOURNAL: Only after check_improvement (ML-Master order)
            self.journal.append(child)

            if should_backprop:
                return self.virtual_root  # Return to root for next selection
            else:
                return child  # Caller continues from this node

        except ProcessError as e:
            # Agent process died - try to reborn
            session_id = placeholder.session_id
            self.logger.warning(
                f"Worker {worker_id} agent died with ProcessError: {e.stderr or str(e)}"
            )

            # Track the failure
            self.failed_expansions.append({
                "worker_id": worker_id,
                "node_id": placeholder.id,
                "session_id": session_id,
                "exit_code": e.exit_code,
                "stderr": e.stderr,
                "timestamp": time.time(),
            })

            if session_id:
                try:
                    self.logger.info(f"Attempting to reborn agent with session {session_id}")
                    result = await self._reborn_agent(
                        session_id=session_id,
                        stderr=e.stderr,
                        worktree=worktree,
                        worker_id=worker_id,
                    )

                    # Reborn succeeded - create child node from result
                    commit_msg = f"{stage}: {result.plan[:50]} (reborn)"
                    commit_hash = self.git.commit(worktree, commit_msg)

                    child = MCTSNode(
                        id=str(uuid.uuid4()),
                        stage=stage,
                        parent=node,
                        plan=result.plan,
                        run_command=result.run_command,
                        commit_hash=commit_hash,
                        local_best_node=node.local_best_node if stage != "draft" else node,
                    )
                    child.absorb_agent_result(result)

                    # Continue normal flow
                    node.children.append(child)
                    should_backprop = self.check_improvement(child, node)
                    self.journal.append(child)

                    self.logger.info(f"Agent reborn succeeded for worker {worker_id}")

                    if should_backprop:
                        return self.virtual_root
                    else:
                        return child

                except Exception as reborn_error:
                    self.logger.error(f"Reborn failed for worker {worker_id}: {reborn_error}")
                    # Fall through to normal error handling

            # Rollback on error (ML-Master style)
            self.backpropagate(node, reward=0, add_to_tree=False)
            raise e

        except Exception as e:
            # Rollback on error (ML-Master style)
            self.backpropagate(node, reward=0, add_to_tree=False)
            raise e

        finally:
            node.expected_child_count -= 1  # Release slot
            # Clear in-progress tracking
            self.in_progress_nodes.pop(worker_id, None)

    async def run(self) -> dict:
        """Main MCTS search loop with conditional backpropagation (ML-Master style).

        Returns:
            Results dictionary with best_node, metrics, stats
        """
        # 1. Initialize timing and generate data report
        self.start_time = time.time()
        await run_data_report_agent(
            workspace=self.workspace,
            context=self.context,
            model=self.config.model,
            run_id=self.run_id,
        )
        self.search_start_time = time.time()  # After init, for search-only timing

        # 2. Virtual root already created in __init__ (ML-Master pattern)

        # 3. Track current node per worker (ML-Master's current_node_list concept)
        current_nodes: dict[int, Optional[MCTSNode]] = {
            i: None for i in range(self.config.parallel_workers)
        }

        # Initialize worktrees
        self.git.init()

        # Save initial commit to storage for reset capability
        initial_commit = self.git.head_commit
        self.store.update_run_state(self.run_id, initial_commit=initial_commit)

        # Save initial config for resume tracking
        self.store.save_initial_config(
            self.run_id,
            time_limit=self.config.time_limit,
            max_steps=self.config.max_steps,
            workers=self.config.parallel_workers,
            model=self.config.model,
        )

        self.worktrees = []
        for i in range(self.config.parallel_workers):
            wt = self.git.create_worktree(i)
            self.worktrees.append(wt)

        try:
            # 4. MCTS loop with parallel workers
            # max_steps <= 0 means infinite (time limit is the only constraint)
            unlimited_steps = self.config.max_steps <= 0
            while self.time_remaining() > 0 and (unlimited_steps or self.current_step < self.config.max_steps):
                tasks = []
                for worker_id in range(self.config.parallel_workers):
                    if self.time_remaining() > 0 and (unlimited_steps or self.current_step + len(tasks) < self.config.max_steps):
                        # Pass current node and worker_id for this worker
                        tasks.append(self.step(current_nodes[worker_id], worker_id))

                if not tasks:
                    break

                # Hard timeout: cancel all workers when time runs out
                try:
                    results = await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True),
                        timeout=self.time_remaining()
                    )
                except asyncio.TimeoutError:
                    logging.getLogger(__name__).info(
                        "Time limit reached - stopping all workers"
                    )
                    break  # Exit loop cleanly, finally block will save state

                for worker_id, result in enumerate(results):
                    if isinstance(result, Exception):
                        # Error - restart from root
                        current_nodes[worker_id] = None
                    elif isinstance(result, MCTSNode):
                        # Update current node for this worker based on return value
                        if result.stage == "root":
                            current_nodes[worker_id] = None  # Backpropagated → restart
                        else:
                            current_nodes[worker_id] = result  # Continue from here
                        self.current_step += 1
                        self.save_progress()

        finally:
            # Always save final state for pause/resume capability
            self.save_progress()
            # Save best solution to main workspace before cleanup
            if self.best_node and self.best_node.commit_hash:
                # Find a worktree that still exists to copy output files from
                for i in range(self.config.parallel_workers):
                    worktree = self.git.get_worktree_path(i)
                    if worktree.exists():
                        self.git.save_best_to_main(
                            self.best_node.commit_hash,
                            worktree
                        )
                        break

            # Cleanup worktrees
            for i in range(self.config.parallel_workers):
                self.git.remove_worktree(i)

        # 5. Return best solution
        return self.get_results()

    def save_progress(self) -> None:
        """Persist current state to journal for crash recovery."""
        if self.best_node:
            self.journal.set_state("best_node_id", self.best_node.id)
        self.journal.set_state("current_step", str(self.current_step))
        # Save total elapsed time (accumulated + current session)
        total_elapsed = self.get_total_elapsed()
        self.journal.set_state("time_elapsed", str(total_elapsed))

    def get_total_elapsed(self) -> float:
        """Get total elapsed time including all sessions.

        Returns:
            Total seconds elapsed (accumulated + current session)
        """
        if self.start_time == 0:
            return self.accumulated_time
        current_session = time.time() - self.start_time
        return self.accumulated_time + current_session

    async def continue_search(self) -> dict:
        """Continue MCTS search after pause (for resume functionality).

        Unlike run(), this skips initialization and continues the main loop
        with existing state. Call after updating config.time_limit and config.max_steps.

        Returns:
            Results dictionary with best_node, metrics, stats
        """
        # Calculate additional amounts by comparing with stored effective limits
        effective = self.store.get_effective_limits(self.run_id)
        additional_time = self.config.time_limit - effective.get("time_limit", 0)
        additional_steps = self.config.max_steps - effective.get("max_steps", 0)

        # Record resume event if there are additional resources
        if additional_time > 0 or additional_steps > 0:
            self.store.add_resume_event(
                self.run_id,
                additional_time=max(0, additional_time),
                additional_steps=max(0, additional_steps),
            )

        # Reset timing for new budget (caller should have set config.time_limit)
        self.start_time = time.time()

        # Track current node per worker (restart from root after pause)
        current_nodes: dict[int, Optional[MCTSNode]] = {
            i: None for i in range(self.config.parallel_workers)
        }

        # Ensure git workspace is initialized
        # (needed after server restart when restored from journal)
        if self.git.repo is None:
            self.git.init()

        if not self.worktrees:
            self.worktrees = []
            for i in range(self.config.parallel_workers):
                wt = self.git.get_worktree_path(i)
                if wt.exists():
                    self.worktrees.append(wt)
                else:
                    # Recreate if missing
                    wt = self.git.create_worktree(i)
                    self.worktrees.append(wt)

        try:
            # Continue MCTS loop
            # max_steps <= 0 means infinite (time limit is the only constraint)
            unlimited_steps = self.config.max_steps <= 0
            while self.time_remaining() > 0 and (unlimited_steps or self.current_step < self.config.max_steps):
                tasks = []
                for worker_id in range(self.config.parallel_workers):
                    if self.time_remaining() > 0 and (unlimited_steps or self.current_step + len(tasks) < self.config.max_steps):
                        tasks.append(self.step(current_nodes[worker_id], worker_id))

                if not tasks:
                    break

                # Hard timeout: cancel all workers when time runs out
                try:
                    results = await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True),
                        timeout=self.time_remaining()
                    )
                except asyncio.TimeoutError:
                    logging.getLogger(__name__).info(
                        "Time limit reached - stopping all workers"
                    )
                    break

                for worker_id, result in enumerate(results):
                    if isinstance(result, Exception):
                        current_nodes[worker_id] = None
                    elif isinstance(result, MCTSNode):
                        if result.stage == "root":
                            current_nodes[worker_id] = None
                        else:
                            current_nodes[worker_id] = result
                        self.current_step += 1
                        self.save_progress()

        finally:
            self.save_progress()

        return self.get_results()

    def get_results(self) -> dict:
        """Return final results after search completes.

        Returns:
            Results dictionary
        """
        return {
            "best_node_id": self.best_node.id if self.best_node else None,
            "best_metric": self.best_node.metric.value if self.best_node and self.best_node.metric else None,
            "best_plan": self.best_node.plan if self.best_node else None,
            "total_steps": self.current_step,
            "time_elapsed": self.get_total_elapsed(),
            "nodes_evaluated": len(self.journal),
        }

    def get_in_progress_nodes(self) -> list[dict]:
        """Get list of in-progress nodes for UI display.

        Returns:
            List of node info dicts with id, parent_id, stage, status, session_id
        """
        result = []
        for worker_id, (node, status) in self.in_progress_nodes.items():
            result.append({
                "id": node.id,
                "parent_id": node.parent.id if node.parent else None,
                "stage": node.stage,
                "status": status,  # "expanding" | "executing" | "evaluating"
                "plan": node.plan,
                "worker_id": worker_id,
                "session_id": node.session_id,  # For real-time log streaming
            })
        return result
