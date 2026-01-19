"""
Result management utilities for testing.

Handles saving test results including transcripts and messages.
"""

import json
from pathlib import Path


class ResultManager:
    """Manages saving of test results."""

    def __init__(self, output_dir: Path):
        """
        Initialize the result manager.

        Args:
            output_dir: Directory to save results to
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

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
        # Create test directory
        test_dir = self.output_dir / f"test_{test_id}"
        test_dir.mkdir(parents=True, exist_ok=True)

        # Save transcript.txt
        transcript_path = test_dir / "transcript.txt"
        with open(transcript_path, "w") as f:
            f.write(agent.transcript)

        # Save raw_messages.json
        messages_path = test_dir / "raw_messages.json"
        serializable_messages = []
        for msg in messages:
            msg_dict = {
                "type": type(msg).__name__,
                "repr": repr(msg),
            }
            # Extract all attributes
            if hasattr(msg, '__dict__'):
                msg_dict["attributes"] = {}
                for key, value in msg.__dict__.items():
                    try:
                        json.dumps(value)
                        msg_dict["attributes"][key] = value
                    except (TypeError, ValueError):
                        msg_dict["attributes"][key] = repr(value)
            serializable_messages.append(msg_dict)

        with open(messages_path, "w") as f:
            json.dump(serializable_messages, f, indent=2)

        return test_dir
