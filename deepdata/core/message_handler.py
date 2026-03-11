"""
Message processing and display handling.

Handles different SDK message types and coordinates display/transcript recording.
"""

from typing import Callable, Awaitable, TYPE_CHECKING
from claude_agent_sdk import Message

from .display import (
    display_query,
    display_text_block,
    display_tool_block,
    display_tool_result_block
)
from .message_utils import save_messages
from ..utils.logging import create_logger

if TYPE_CHECKING:
    from .streaming import EventEmitter

logger = create_logger(__name__)


class MessageHandler:
    """
    Handles message processing, display, and transcript recording.

    Responsibilities:
    - Process different SDK message types (SystemMessage, AssistantMessage, etc.)
    - Coordinate display output
    - Build transcript string
    - Buffer tool calls for result pairing
    """

    def __init__(self, event_emitter: 'EventEmitter'):
        """
        Initialize message handler.

        Args:
            event_emitter: EventEmitter for streaming events
        """
        self.event_emitter = event_emitter
        self.transcript: str = ""
        self._last_response: str = ""
        self._tool_use_buffer: dict = {}  # tool_use_id -> ToolUseBlock

    def record_query(self, query_text: str, display: bool = True):
        """
        Record user query to transcript.

        Args:
            query_text: User's query text
            display: Whether to display to console
        """
        text = display_query(query_text, display=display)
        self.transcript += f"> {text}\n"
        self._last_response = ""

    def _record_block(self, msg, display: bool, messages: list[Message]):
        """
        Record a message block to transcript and display.

        Args:
            msg: Message block (TextBlock, ToolUseBlock, ToolResultBlock)
            display: Whether to display to console
            messages: All messages (for error debugging)
        """
        block_type = type(msg).__name__
        try:
            if block_type == 'TextBlock':
                text = display_text_block(msg, display=display)
                self.transcript += f"\n{text}\n"
                self._last_response += f"{text}"
            elif block_type == 'ToolUseBlock':
                tool_text = display_tool_block(msg, display=display)
                self.transcript += f"{tool_text}\n"
                self._last_response += f"\n{tool_text}"
            elif block_type == 'ToolResultBlock':
                result_text = display_tool_result_block(msg, display=False)
                self.transcript += f"{result_text}\n"
                self._last_response += f"\n{result_text}"
        except Exception:
            # Save messages on error for debugging
            if messages:
                error_file = save_messages(messages, prefix="error_messages")
                logger.warning(f"Error in message handling - messages saved to: {error_file}")
            raise

    def handle_system_message(self, msg) -> dict:
        """
        Handle SystemMessage - extract session_id, model, cwd.

        Args:
            msg: SystemMessage from SDK

        Returns:
            dict with extracted fields: session_id, model, cwd
        """
        result = {}
        if not hasattr(msg, 'data'):
            return result

        data = msg.data
        if 'session_id' in data:
            result['session_id'] = data['session_id']
        if 'model' in data:
            result['model'] = data['model']
        if 'cwd' in data:
            result['cwd'] = str(data['cwd'])

        return result

    def handle_result_message(self, msg) -> dict:
        """
        Handle ResultMessage - extract statistics.

        Args:
            msg: ResultMessage from SDK

        Returns:
            dict with extracted statistics
        """
        result = {}
        if hasattr(msg, 'session_id'):
            result['session_id'] = msg.session_id
        if hasattr(msg, 'duration_ms'):
            result['duration_ms'] = msg.duration_ms
        if hasattr(msg, 'num_turns'):
            result['num_turns'] = msg.num_turns
        if hasattr(msg, 'total_cost_usd'):
            result['total_cost_usd'] = msg.total_cost_usd
        if hasattr(msg, 'usage'):
            result['usage'] = msg.usage
        if hasattr(msg, 'is_error'):
            result['api_error'] = msg.is_error

        return result

    async def handle_assistant_message(
        self,
        msg,
        display: bool,
        messages: list[Message],
        on_event: Callable | None
    ):
        """
        Handle AssistantMessage - display text immediately, buffer tool calls.

        Args:
            msg: AssistantMessage from SDK
            display: Whether to display to console
            messages: All messages (for error debugging)
            on_event: Optional event callback
        """
        if hasattr(msg, 'content'):
            for block in msg.content:
                block_type = type(block).__name__
                if block_type == 'TextBlock':
                    # Emit text event
                    await self.event_emitter.emit(
                        'text',
                        {'content': block.text},
                        on_event
                    )
                    # Display and record
                    self._record_block(block, display, messages)
                elif block_type == 'ToolUseBlock':
                    # Emit tool use event
                    await self.event_emitter.emit(
                        'tool_use',
                        {'name': block.name, 'input': block.input},
                        on_event
                    )
                    # Buffer for later pairing with result
                    self._tool_use_buffer[block.id] = block

    async def handle_user_message(
        self,
        msg,
        display: bool,
        messages: list[Message],
        on_event: Callable | None
    ):
        """
        Handle UserMessage - pair tool results with buffered calls.

        Args:
            msg: UserMessage from SDK
            display: Whether to display to console
            messages: All messages (for error debugging)
            on_event: Optional event callback
        """
        if hasattr(msg, 'content'):
            for block in msg.content:
                block_type = type(block).__name__
                if block_type == 'ToolResultBlock':
                    # Display buffered tool call first
                    tool_use_id = block.tool_use_id
                    tool_name = "unknown"
                    if tool_use_id in self._tool_use_buffer:
                        tool_block = self._tool_use_buffer.pop(tool_use_id)
                        tool_name = tool_block.name
                        self._record_block(tool_block, display, messages)

                    # Emit tool result event (full content - frontend handles display truncation)
                    result_text = str(block.content) if block.content else ""
                    await self.event_emitter.emit(
                        'tool_result',
                        {'name': tool_name, 'result': result_text},
                        on_event
                    )

                    # Display result
                    self._record_block(block, display, messages)

    def get_last_response(self) -> str:
        """
        Return the most recent assistant response.

        `_last_response` is built incrementally during live runs. When the agent
        is reloaded from disk, that cache starts empty, so we recompute from the
        transcript on the first call.
        """
        if self._last_response == "":
            self._last_response = self._compute_last_response_from_transcript()
        return self._last_response

    def _compute_last_response_from_transcript(self) -> str:
        """Derive last assistant response by scanning the transcript."""
        # Split by user prompts (lines starting with ">")
        parts = self.transcript.split("\n> ")
        if len(parts) > 1:
            # Check last exchange for response
            last_exchange = parts[-1]
            lines = last_exchange.split("\n", 1)
            if len(lines) > 1 and lines[1].strip():
                # Last exchange has a non-empty response
                return lines[1].strip()
            elif len(parts) >= 2:
                # Last exchange has no response yet, get previous exchange
                prev_exchange = parts[-2]
                lines = prev_exchange.split("\n", 1)
                if len(lines) > 1:
                    return lines[1].strip()
        return ""
