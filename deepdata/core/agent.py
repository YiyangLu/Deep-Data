"""
Minimal Agent implementation following KISS principle.

Single Agent class focused on lifecycle and query orchestration.
Message handling and streaming are delegated to specialized modules.

Key features:
- Self-registers in global AgentRegistry on start()
- Emits events through public `events` emitter
- Web/CLI/MLE can subscribe to events
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from pathlib import Path

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    Message,
)

from .message_handler import MessageHandler
from .streaming import EventEmitter
from .session_registry import get_session_store
from .session_registry import register_session, unregister_session
from .registry import get_registry
from .agent_context import agent_context


@dataclass
class Agent:
    """
    Self-contained agent that can be created anywhere.

    Features:
    - Self-registers in global registry on start()
    - Emits events through public `events` emitter
    - Web/CLI/tests can subscribe to events
    - Handles its own storage and lifecycle

    Responsibilities:
    - Session lifecycle (start/stop/resume)
    - Query execution and coordination
    - Configuration management
    - Statistics tracking

    Delegated responsibilities:
    - Message handling: MessageHandler
    - Event streaming: EventEmitter

    Example:
        agent = Agent(
            agent_type="chat",
            cwd=workspace,
            enable_storage=True,
            event_sink=my_sink,  # Optional: auto-subscribe to events
        )

        await agent.start()  # Registers globally
        await agent.query("Hello")  # Emits events to sink
        await agent.stop()  # Unregisters
    """

    # Identity
    agent_id: str = "agent"
    agent_type: str = "general"  # "chat", "mle-draft", "analyzer", etc.
    name: str = ""  # Display name (defaults to agent_type)

    # Configuration
    system_prompt: str = ""  # Empty means use Claude Code default
    allowed_tools: list[str] = field(default_factory=list)  # Empty means all tools allowed
    disallowed_tools: list[str] = field(default_factory=list)  # Tools to explicitly disallow
    cwd: str | Path | None = None  # Working directory for Claude Code
    permission_mode: str | None = None  # 'default', 'acceptEdits', 'plan', 'bypassPermissions'
    mcp_servers: dict = field(default_factory=dict)  # MCP server configurations
    output_format: dict | None = None  # Structured output format (JSON schema)
    env: dict = field(default_factory=dict)  # Environment variables for subprocess (e.g., CUDA_VISIBLE_DEVICES)

    # Session (SDK session_id for resume)
    session_id: str | None = None
    model: str | None = None  # Model name from SystemMessage

    # Conversation (managed by MessageHandler)
    messages: list[Message] = field(default_factory=list)  # Raw SDK messages

    # Query statistics (from last ResultMessage)
    duration_ms: int | None = None
    num_turns: int | None = None
    total_cost_usd: float | None = None
    usage: dict | None = None
    api_error: bool = False
    structured_output: dict | None = None  # Structured output from last query (if output_format set)

    # Session Storage (optional persistence)
    enable_storage: bool = False  # Enable session storage to logs/
    logs_root: Path | None = None  # Root directory for logs (default: ./logs)
    debug_raw_messages: bool = False  # Save raw SDK messages to raw_messages.jsonl

    # Parent activity (for sessions created by MLE, deep_plot, etc.)
    parent_activity_type: str | None = None  # 'mle' | 'deep_plot' | None
    parent_activity_id: str | None = None    # run_id | analysis_id | None

    # Public event emitter - subscribe to receive agent events
    events: EventEmitter = field(default_factory=EventEmitter, repr=False)

    # Event sink - if provided, automatically subscribes to events
    # Use this for streaming events to orchestrator/UI
    event_sink: Any = field(default=None, repr=False)

    # Runtime (not persisted)
    _client: ClaudeSDKClient | None = field(default=None, repr=False)
    message_handler: MessageHandler = field(default=None, init=False, repr=False)
    _session_store: any = field(default=None, init=False, repr=False)
    _turn_number: int = field(default=0, init=False, repr=False)  # Track conversation turns

    @property
    def display_name(self) -> str:
        """Display name for UI."""
        return self.name or self.agent_type

    def __post_init__(self):
        """Initialize runtime components."""
        # Resolve cwd to absolute path
        if self.cwd:
            self.cwd = str(Path(self.cwd).resolve())

        self.message_handler = MessageHandler(self.events)

        # Subscribe event sink if provided
        if self.event_sink is not None:
            self.events.subscribe(self.event_sink.emit)

        # Initialize session store if enabled (use singleton)
        if self.enable_storage:
            self._session_store = get_session_store(self.logs_root)

    @property
    def transcript(self) -> str:
        """Access transcript from message handler."""
        return self.message_handler.transcript

    def _save_raw_message(self, msg) -> None:
        """Save raw SDK message to JSONL file for debugging."""
        if not self.debug_raw_messages or not self._session_store or not self.session_id:
            return

        try:
            import json
            from datetime import datetime

            # Get session folder
            session_info = self._session_store.get_session_info(self.session_id)
            raw_file = session_info.folder_path / "raw_messages.jsonl"

            # Convert message to dict
            msg_dict = {
                "timestamp": datetime.now().isoformat(),
                "type": type(msg).__name__,
                "turn": self._turn_number,
            }

            # Try to extract message data
            if hasattr(msg, 'data'):
                msg_dict["data"] = msg.data
            if hasattr(msg, 'content'):
                msg_dict["content"] = msg.content
            if hasattr(msg, '__dict__'):
                # Include all attributes
                for k, v in msg.__dict__.items():
                    if k not in msg_dict:
                        try:
                            json.dumps(v)  # Test if serializable
                            msg_dict[k] = v
                        except (TypeError, ValueError):
                            msg_dict[k] = str(v)

            # Append to file
            with open(raw_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(msg_dict) + "\n")

        except Exception as e:
            logger = __import__('logging').getLogger(__name__)
            logger.warning(f"Failed to save raw message: {e}")

    def _build_options(
        self,
        allowed_tools: list[str] | None = None,
        mcp_servers: dict | None = None,
        resume_session_id: str | None = None
    ) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions from agent configuration.

        Args:
            allowed_tools: Override allowed_tools (default: use self.allowed_tools)
            mcp_servers: Override mcp_servers (default: use self.mcp_servers)
            resume_session_id: Session ID for resume (default: None for new session)

        Returns:
            Configured ClaudeAgentOptions instance
        """
        options_dict = {
            "system_prompt": self.system_prompt,
            "allowed_tools": allowed_tools if allowed_tools is not None else self.allowed_tools,
            "disallowed_tools": self.disallowed_tools,
            "cwd": self.cwd,
            "permission_mode": self.permission_mode,
            "mcp_servers": mcp_servers if mcp_servers is not None else self.mcp_servers,
            "env": self.env,
        }

        # Add model if specified (supports per-agent model configuration)
        # Valid values: "sonnet", "opus", "haiku", or full model names like "claude-opus-4-5"
        if self.model:
            options_dict["model"] = self.model

        # Add structured output format if specified
        if self.output_format:
            options_dict["output_format"] = self.output_format

        if resume_session_id:
            options_dict["resume"] = resume_session_id

        return ClaudeAgentOptions(**options_dict)

    async def start(self):
        """Start new session and register globally."""
        options = self._build_options()
        self._client = ClaudeSDKClient(options)
        await self._client.connect()

        # Register in global registry
        get_registry().register(self)

        # Emit lifecycle event
        await self.events.emit('started', {
            'agent_id': self.agent_id,
            'agent_type': self.agent_type,
            'name': self.display_name,
        })
        # Note: Storage session created on first query when we get SDK session_id

    async def resume(self):
        """Resume from session_id and register globally."""
        if not self.session_id:
            raise ValueError("No session_id to resume")

        options = self._build_options(resume_session_id=self.session_id)
        self._client = ClaudeSDKClient(options)
        await self._client.connect()

        # Register in global registry
        get_registry().register(self)

        # Emit lifecycle event
        await self.events.emit('resumed', {
            'agent_id': self.agent_id,
            'session_id': self.session_id,
        })

    def _block_to_dict(self, block) -> dict:
        """
        Convert SDK block to dict for storage.

        Args:
            block: SDK block (TextBlock, ToolUseBlock, ToolResultBlock)

        Returns:
            Dict representation of block
        """
        block_type = type(block).__name__

        if block_type == 'TextBlock':
            return {
                'type': 'text',
                'text': block.text
            }
        elif block_type == 'ToolUseBlock':
            return {
                'type': 'tool_use',
                'id': block.id,
                'name': block.name,
                'input': block.input
            }
        elif block_type == 'ToolResultBlock':
            return {
                'type': 'tool_result',
                'tool_use_id': block.tool_use_id,
                'content': block.content,
                'is_error': getattr(block, 'is_error', False)
            }
        else:
            # Unknown block type, store what we can
            return {
                'type': 'unknown',
                'raw': str(block)
            }

    def _log_conversation_blocks(self, msg):
        """
        Log conversation blocks to session storage.

        Args:
            msg: AssistantMessage or UserMessage
        """
        if not self.enable_storage or not self._session_store or not self.session_id:
            return

        if not hasattr(msg, 'content'):
            return

        # Determine role based on message type
        msg_type = type(msg).__name__
        role = 'assistant' if msg_type == 'AssistantMessage' else 'user'

        for idx, block in enumerate(msg.content):
            block_data = self._block_to_dict(block)
            self._session_store.log_conversation_block(
                session_id=self.session_id,
                turn_number=self._turn_number,
                block_index=idx,
                block_data=block_data,
                role=role
            )

    async def query(
        self,
        prompt: str,
        display: bool = True,
        on_event: Callable[[str, dict], Awaitable[None]] | None = None,
        hidden: bool = False,
        on_session_start: Callable[[str], None] | None = None
    ) -> list[Message]:
        """Execute query and update transcript with optional event streaming

        Args:
            prompt: User query string
            display: If True, print formatted output to console (for human reading).
                    Displays complete text blocks and tool calls, NOT word-by-word streaming.
                    This is for terminal usage where you want readable formatted output.
                    Set to False for silent execution (benchmarks, scripts).
            on_event: Optional callback for real-time event streaming (for web UI, etc).
                     Receives (event_type, data) as events occur during execution.
                     This enables ChatGPT-like progressive rendering in UIs.
                     Event types: 'text', 'tool_use', 'tool_result', 'complete', 'error'

                     IMPORTANT: display and on_event serve different purposes:
                     - display: Human-readable console output (complete formatted blocks)
                     - on_event: Machine-readable streaming events (incremental chunks)
                     They are independent - you can use both, either, or neither.
            hidden: If True, don't store the user message in conversation_blocks.
                   Use for autonomous agent prompts that shouldn't appear in UI history.
            on_session_start: Optional callback called when session_id is obtained from SDK.
                   Called with session_id string as argument. Use for real-time log tracking.

        Returns:
            List of SDK Message objects

        Examples:
            # Console display (examples/)
            await agent.query("Hello", display=True)

            # Silent execution (benchmarks/)
            await agent.query("Hello", display=False)

            # Web streaming (web/)
            async def callback(event_type, data):
                if event_type == 'text':
                    await websocket.send(data['content'])
            await agent.query("Hello", display=False, on_event=callback)

            # Both console and streaming (debugging web)
            await agent.query("Hello", display=True, on_event=callback)

            # Hidden prompt (autonomous agents)
            await agent.query("System prompt", hidden=True)
        """
        # Set agent context for tools (e.g., plotly)
        with agent_context(self):
            return await self._execute_query(prompt, display, on_event, hidden, on_session_start)

    async def _execute_query(
        self,
        prompt: str,
        display: bool,
        on_event: Callable[[str, dict], Awaitable[None]] | None,
        hidden: bool,
        on_session_start: Callable[[str], None] | None
    ) -> list[Message]:
        """Internal query execution with agent context set."""
        # Reset structured output from previous query
        self.structured_output = None

        # Emit query start event (full prompt - frontend handles display truncation)
        await self.events.emit('query_start', {
            'prompt': prompt,
        }, on_event)

        # Increment turn number for storage
        self._turn_number += 1

        # Record user query
        self.message_handler.record_query(prompt, display=display)

        # Store query for logging after session creation
        current_query = prompt

        if not self._client:
            await self.start()

        # Execute
        await self._client.query(prompt)

        # Collect response messages
        response_messages = []

        try:
            async for msg in self._client.receive_response():
                response_messages.append(msg)
                msg_type = type(msg).__name__

                # Handle different message types
                if msg_type == 'SystemMessage':
                    system_data = self.message_handler.handle_system_message(msg)
                    if 'session_id' in system_data:
                        self.session_id = system_data['session_id']

                        # Create or resume storage session on first SystemMessage
                        if self.enable_storage and self._session_store and self.session_id:
                            cwd = Path(self.cwd) if self.cwd else Path.cwd()

                            # Check if session already exists (resume case)
                            try:
                                session_info = self._session_store.get_session_info(self.session_id)
                                # Session exists - resuming
                                logger = __import__('logging').getLogger(__name__)
                                logger.info(f"Resuming session: {self.session_id}")
                            except ValueError:
                                # Session doesn't exist - create new
                                self._session_store.create_session(
                                    session_id=self.session_id,
                                    cwd=cwd,
                                    agent_id=self.agent_id,
                                    session_name=self.display_name,
                                    parent_activity_type=self.parent_activity_type,
                                    parent_activity_id=self.parent_activity_id,
                                )
                                logger = __import__('logging').getLogger(__name__)
                                logger.info(f"Created new session: {self.session_id}")

                            # Register in global registry for plotly tools
                            register_session(self._session_store, self.session_id)

                            # Emit session_info event so frontend can link pending tab
                            await self.events.emit('session_info', {
                                'session_id': self.session_id,
                                'session_name': self.display_name,
                            }, on_event)

                            # Call on_session_start callback for real-time tracking
                            if on_session_start:
                                on_session_start(self.session_id)

                            # Log the current query to newly created/resumed session
                            self._session_store.update_session_metadata(
                                session_id=self.session_id,
                                latest_query=current_query
                            )
                            self._session_store.update_transcript(
                                session_id=self.session_id,
                                text=f"> {current_query}\n"
                            )

                    if 'model' in system_data:
                        self.model = system_data['model']
                    if 'cwd' in system_data:
                        sdk_cwd = system_data['cwd']
                        # Check if cwd changed (SDK may update cwd mid-session)
                        if self.cwd and sdk_cwd != self.cwd:
                            old_cwd = self.cwd
                            self.cwd = sdk_cwd
                            # Update storage
                            if self.enable_storage and self._session_store and self.session_id:
                                self._session_store.update_current_cwd(self.session_id, sdk_cwd)
                            # Emit cwd_changed event
                            await self.events.emit('cwd_changed', {
                                'old_cwd': old_cwd,
                                'new_cwd': sdk_cwd
                            })
                        elif not self.cwd:
                            # First time seeing cwd
                            self.cwd = sdk_cwd

                    # Log user query now that we have session_id
                    # (SDK doesn't send back user queries in response stream)
                    # Skip if hidden=True (for autonomous agent prompts)
                    if self.enable_storage and self._session_store and self.session_id and not hidden:
                        user_text_block = {
                            'type': 'text',
                            'text': current_query
                        }
                        self._session_store.log_conversation_block(
                            session_id=self.session_id,
                            turn_number=self._turn_number,
                            block_index=0,
                            block_data=user_text_block,
                            role='user'
                        )

                elif msg_type == 'ResultMessage':
                    result_data = self.message_handler.handle_result_message(msg)

                    # Verify session_id if present
                    if 'session_id' in result_data:
                        if self.session_id and result_data['session_id'] != self.session_id:
                            raise ValueError(
                                f"Session ID mismatch: expected {self.session_id}, "
                                f"got {result_data['session_id']}"
                            )

                    # Update statistics
                    if 'duration_ms' in result_data:
                        self.duration_ms = result_data['duration_ms']
                    if 'num_turns' in result_data:
                        self.num_turns = result_data['num_turns']
                    if 'total_cost_usd' in result_data:
                        self.total_cost_usd = result_data['total_cost_usd']
                    if 'usage' in result_data:
                        self.usage = result_data['usage']
                    if 'api_error' in result_data:
                        self.api_error = result_data['api_error']

                    # Capture structured output if present (from output_format)
                    if hasattr(msg, 'structured_output') and msg.structured_output:
                        self.structured_output = msg.structured_output

                    # Emit completion event
                    await self.events.emit(
                        'complete',
                        {
                            'duration_ms': self.duration_ms,
                            'num_turns': self.num_turns,
                            'total_cost_usd': self.total_cost_usd,
                            'usage': self.usage,
                            'structured_output': self.structured_output
                        },
                        on_event
                    )

                elif msg_type == 'AssistantMessage':
                    await self.message_handler.handle_assistant_message(
                        msg, display, self.messages, on_event
                    )
                    # Log conversation blocks to storage
                    self._log_conversation_blocks(msg)

                elif msg_type == 'UserMessage':
                    await self.message_handler.handle_user_message(
                        msg, display, self.messages, on_event
                    )
                    # Log conversation blocks to storage
                    self._log_conversation_blocks(msg)

                # Save raw message for debugging (after session is created)
                self._save_raw_message(msg)

            # Store messages
            self.messages.extend(response_messages)

            # Update storage with final statistics and transcript
            if self.enable_storage and self._session_store and self.session_id:
                # Extract token counts from usage dict
                input_tokens = self.usage.get('input_tokens', 0) if self.usage else 0
                output_tokens = self.usage.get('output_tokens', 0) if self.usage else 0

                self._session_store.update_session_metadata(
                    session_id=self.session_id,
                    total_cost_usd=self.total_cost_usd,
                    duration_ms=self.duration_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens
                )
                # Append assistant response to transcript
                response_text = self.message_handler.get_last_response()
                if response_text:
                    self._session_store.update_transcript(
                        session_id=self.session_id,
                        text=f"{response_text}\n"
                    )

            return response_messages

        except Exception as e:
            # Emit error event
            await self.events.emit('error', {'error': str(e)}, on_event)
            raise

    async def stop(self):
        """Stop session, clear subscribers, and unregister."""
        # Emit lifecycle event before stopping
        await self.events.emit('stopped', {
            'agent_id': self.agent_id,
        })

        # Clear all event subscribers
        self.events.clear()

        if self._client:
            await self._client.disconnect()
            self._client = None

        # Unregister session from global registry
        if self.enable_storage and self.session_id:
            unregister_session()

        # Unregister from agent registry
        get_registry().unregister(self.agent_id)

    def get_last_response(self) -> str:
        """Return the most recent assistant response."""
        return self.message_handler.get_last_response()

    def get_conversation_history(self) -> list[dict]:
        """
        Get conversation history from storage for UI display.

        Returns:
            List of conversation blocks from session storage.
            Empty list if storage is disabled or no session exists.
        """
        if not self.enable_storage or not self._session_store or not self.session_id:
            return []
        try:
            return self._session_store.get_conversation(self.session_id)
        except Exception:
            return []

