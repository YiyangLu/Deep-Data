"""
Base evaluator for agent testing.

Provides the abstract BaseEvaluator class that combines project management
and result saving for agent testing workflows.
"""

import asyncio
import hashlib
from abc import ABC, abstractmethod
from pathlib import Path

from .project_manager import ProjectManager
from .result_manager import ResultManager


class BaseEvaluator(ABC):
    """Base class for all agent evaluators."""

    def __init__(
        self,
        project_path: str,
        output_dir: str,
        query: str,
        permission_mode: str | None = None,
        min_free_space_multiplier: float = 10.0
    ):
        """
        Initialize the evaluator.

        Args:
            project_path: Path to the project to evaluate
            output_dir: Directory to save evaluation results
            query: Query to send to agent
            permission_mode: Permission mode for agent ('bypassPermissions', etc.)
            min_free_space_multiplier: Minimum free space required as multiple of project size
        """
        self.project_path = Path(project_path)
        self.output_dir = Path(output_dir).resolve()
        self.query = query
        self.permission_mode = permission_mode

        # Initialize managers
        self.project_manager = ProjectManager(
            project_path=self.project_path,
            min_free_space_multiplier=min_free_space_multiplier
        )
        self.result_manager = ResultManager(output_dir=self.output_dir)

    def create_project_copy(self, test_id: str) -> Path:
        """
        Create a fresh copy of the project for testing.

        Args:
            test_id: Unique identifier for this test

        Returns:
            Path to the copied project

        Raises:
            RuntimeError: If insufficient disk space
        """
        return self.project_manager.create_project_copy(test_id)

    def _generate_test_id(self, test_num: int = None) -> str:
        """
        Generate a meaningful test ID from query hash.

        Args:
            test_num: Optional test number (1-indexed). If None, no suffix added.

        Returns:
            Test ID like "visualize_abc123" or "visualize_abc123_test1"
        """
        # Create short hash of query (first 6 chars of SHA256)
        query_hash = hashlib.sha256(self.query.encode()).hexdigest()[:6]

        # Create readable prefix from query (first word, lowercase)
        query_words = self.query.lower().split()
        query_prefix = query_words[0] if query_words else "query"

        if test_num is not None:
            return f"{query_prefix}_{query_hash}_test{test_num}"
        else:
            return f"{query_prefix}_{query_hash}"

    async def save_results(self, agent, messages, test_id: str) -> Path:
        """
        Save evaluation results to disk.

        Args:
            agent: The agent instance (must have .transcript attribute)
            messages: List of message objects from agent.query()
            test_id: Test identifier

        Returns:
            Path to the test results directory
        """
        return await self.result_manager.save_results(agent, messages, test_id)

    @abstractmethod
    async def run_agent(self, project_dir: Path, test_id: str):
        """
        Run the agent on the project and save results.
        Must be implemented by subclasses.

        Args:
            project_dir: Path to the project directory
            test_id: Test identifier
        """
        pass

    async def run_single_test(self, test_id: str):
        """
        Run a single evaluation test.

        Args:
            test_id: Unique identifier for this test
        """
        # Create project copy
        project_copy = self.create_project_copy(test_id)

        # Run agent (saves transcript.txt and raw_messages.json)
        await self.run_agent(project_copy, test_id)

    async def run_evaluation(self, num_tests: int = 1):
        """
        Run evaluation with multiple tests.

        Args:
            num_tests: Number of times to run the test
        """
        print("=" * 70)
        print(f"{self.__class__.__name__} - Evaluation")
        print("=" * 70)
        print(f"Query: {self.query}")
        print(f"Tests: {num_tests}")
        print(f"Output: {self.output_dir}")
        print("=" * 70)

        for i in range(num_tests):
            test_id = self._generate_test_id(i + 1 if num_tests > 1 else None)
            await self.run_single_test(test_id)

            # Brief pause between tests
            if i < num_tests - 1:
                await asyncio.sleep(2)

        print("\n" + "=" * 70)
        print(f"Completed {num_tests} test(s)")
        print(f"Output: {self.output_dir}")
        print("=" * 70)
