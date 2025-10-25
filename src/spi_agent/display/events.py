"""Event types and emission system for execution transparency."""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class ExecutionEvent:
    """Base class for execution events.

    Attributes:
        event_id: Unique identifier for this event
        timestamp: When the event occurred
        parent_id: ID of parent event (for hierarchical display)
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    parent_id: Optional[str] = None


@dataclass
class ToolStartEvent(ExecutionEvent):
    """Event emitted when a tool execution starts.

    Attributes:
        tool_name: Name of the tool being executed
        arguments: Tool arguments (sanitized, no secrets)
    """

    tool_name: str = ""
    arguments: Optional[Dict[str, Any]] = None


@dataclass
class ToolCompleteEvent(ExecutionEvent):
    """Event emitted when a tool execution completes successfully.

    Attributes:
        tool_name: Name of the tool that completed
        result_summary: Human-readable summary of results
        duration: Execution duration in seconds
    """

    tool_name: str = ""
    result_summary: str = ""
    duration: float = 0.0


@dataclass
class ToolErrorEvent(ExecutionEvent):
    """Event emitted when a tool execution fails.

    Attributes:
        tool_name: Name of the tool that failed
        error_message: Error message
        duration: Execution duration before failure in seconds
    """

    tool_name: str = ""
    error_message: str = ""
    duration: float = 0.0


@dataclass
class WorkflowStepEvent(ExecutionEvent):
    """Event emitted for workflow progress steps.

    Attributes:
        step_name: Name of the workflow step
        status: Step status (started, completed, failed)
        metadata: Additional step metadata
    """

    step_name: str = ""
    status: str = "started"  # started, completed, failed
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SubprocessOutputEvent(ExecutionEvent):
    """Event emitted for subprocess output lines.

    Attributes:
        command: Command being executed
        output_line: Single line of output
    """

    command: str = ""
    output_line: str = ""


@dataclass
class LLMRequestEvent(ExecutionEvent):
    """Event emitted when making an LLM request.

    Attributes:
        message_count: Number of messages in the request
    """

    message_count: int = 0


@dataclass
class LLMResponseEvent(ExecutionEvent):
    """Event emitted when LLM response is received.

    Attributes:
        duration: Request duration in seconds
    """

    duration: float = 0.0


class EventEmitter:
    """Thread-safe event emitter using asyncio queue.

    This emitter provides a thread-safe way to emit execution events
    that can be consumed by the execution tree display.
    """

    def __init__(self) -> None:
        """Initialize event emitter with asyncio queue."""
        self._queue: asyncio.Queue[ExecutionEvent] = asyncio.Queue()
        self._enabled = True
        # Store execution mode flags (avoids ContextVar propagation issues)
        self._is_interactive = False
        self._show_visualization = False

    def emit(self, event: ExecutionEvent) -> None:
        """Emit an event to the queue.

        Args:
            event: Event to emit

        Note:
            This is safe to call from async contexts. The queue is thread-safe.
        """
        if not self._enabled:
            return

        try:
            # Use put_nowait since we don't want to block
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            # If queue is full, drop the event (prevents memory issues)
            pass

    async def get_event(self) -> ExecutionEvent:
        """Get next event from queue.

        Returns:
            Next event from queue

        Note:
            This will block until an event is available.
        """
        return await self._queue.get()

    async def get_event_nowait(self) -> Optional[ExecutionEvent]:
        """Get next event without blocking.

        Returns:
            Next event or None if queue is empty
        """
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def disable(self) -> None:
        """Disable event emission (for CLI mode)."""
        self._enabled = False

    def enable(self) -> None:
        """Enable event emission (for interactive mode)."""
        self._enabled = True

    @property
    def is_enabled(self) -> bool:
        """Check if emitter is enabled."""
        return self._enabled

    def clear(self) -> None:
        """Clear all pending events from queue."""
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def set_interactive_mode(self, is_interactive: bool, show_visualization: bool) -> None:
        """Set the interactive mode flags.

        Args:
            is_interactive: Whether running in interactive mode
            show_visualization: Whether to show visualization
        """
        self._is_interactive = is_interactive
        self._show_visualization = show_visualization

    def is_interactive_mode(self) -> bool:
        """Check if in interactive mode with visualization.

        Returns:
            True if interactive mode with visualization enabled
        """
        return self._is_interactive and self._show_visualization


# Global singleton instance
_event_emitter: Optional[EventEmitter] = None


def get_event_emitter() -> EventEmitter:
    """Get the global event emitter instance.

    Returns:
        EventEmitter singleton instance
    """
    global _event_emitter
    if _event_emitter is None:
        _event_emitter = EventEmitter()
    return _event_emitter
