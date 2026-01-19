"""Event sink protocol and implementations.

EventSink is the interface for receiving streaming events from agents.
Different sinks support different use cases:
- FileSink: Log to JSONL for debugging/replay
- DatabaseSink: Persist for analysis
- WebSocketSink: Stream to UI (implemented in web module)
- NullSink: Discard events (silent mode)
- MultiSink: Forward to multiple sinks

All agents always stream events - the sink determines where they go.
"""

import json
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class EventSink(Protocol):
    """Interface for receiving events from agents.

    All event sinks must implement this protocol.
    The emit method is async to support non-blocking I/O.

    Example:
        class MySink:
            async def emit(self, event_type: str, data: dict) -> None:
                print(f"{event_type}: {data}")

        agent.events.subscribe(my_sink.emit)
    """

    async def emit(self, event_type: str, data: dict) -> None:
        """Receive an event.

        Args:
            event_type: Type of event (e.g., 'text', 'tool_use', 'complete')
            data: Event payload
        """
        ...


class NullSink:
    """Discard all events (silent mode).

    Use when you don't need event streaming but want to maintain
    the same code path.

    Example:
        orchestrator = MCTSOrchestrator(
            workspace=workspace,
            event_sink=NullSink()
        )
    """

    async def emit(self, event_type: str, data: dict) -> None:
        """Discard the event."""
        pass


class FileSink:
    """Log events to JSONL file.

    Each event is written as a single JSON line with timestamp.
    Useful for debugging and replay.

    Example:
        sink = FileSink(Path("events.jsonl"))
        agent.events.subscribe(sink.emit)
        # ... run agent ...
        sink.close()

        # Later: replay events
        for event in FileSink.read(Path("events.jsonl")):
            print(event)
    """

    def __init__(self, path: Path):
        """Initialize file sink.

        Args:
            path: Path to JSONL file (will be created/appended)
        """
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.path, "a", encoding="utf-8")

    async def emit(self, event_type: str, data: dict) -> None:
        """Write event as JSON line."""
        import time
        event = {
            "type": event_type,
            "timestamp": time.time(),
            **data
        }
        self._file.write(json.dumps(event) + "\n")
        self._file.flush()

    def close(self) -> None:
        """Close the file."""
        self._file.close()

    @staticmethod
    def read(path: Path):
        """Read events from JSONL file.

        Yields:
            dict: Each event from the file
        """
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class MultiSink:
    """Forward events to multiple sinks.

    Use when you need both logging and UI streaming.

    Example:
        sink = MultiSink([
            FileSink(Path("events.jsonl")),
            websocket_sink
        ])
        agent.events.subscribe(sink.emit)
    """

    def __init__(self, sinks: list[EventSink]):
        """Initialize with list of sinks.

        Args:
            sinks: List of sinks to forward events to
        """
        self.sinks = sinks

    async def emit(self, event_type: str, data: dict) -> None:
        """Forward event to all sinks."""
        for sink in self.sinks:
            await sink.emit(event_type, data)

    def add(self, sink: EventSink) -> None:
        """Add a sink dynamically.

        Useful for late-connecting UI.
        """
        self.sinks.append(sink)

    def remove(self, sink: EventSink) -> None:
        """Remove a sink.

        Useful when UI disconnects.
        """
        if sink in self.sinks:
            self.sinks.remove(sink)


class CallbackSink:
    """Wrap a callback function as EventSink.

    Bridges the old on_event callback pattern to EventSink.

    Example:
        async def my_handler(event_type, data):
            print(f"{event_type}: {data}")

        sink = CallbackSink(my_handler)
    """

    def __init__(self, callback):
        """Initialize with callback.

        Args:
            callback: Async function(event_type, data) -> None
        """
        self.callback = callback

    async def emit(self, event_type: str, data: dict) -> None:
        """Forward to callback."""
        await self.callback(event_type, data)
