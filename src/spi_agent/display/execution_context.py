"""Execution context for mode detection and visualization control."""

import contextvars
from dataclasses import dataclass
from typing import Optional

# Thread-local context variable for execution mode
_execution_context: contextvars.ContextVar[Optional["ExecutionContext"]] = (
    contextvars.ContextVar("execution_context", default=None)
)


@dataclass
class ExecutionContext:
    """Context information about the current execution mode.

    Attributes:
        is_interactive: True if running in interactive chat mode
        show_visualization: True if visualization should be displayed
    """

    is_interactive: bool = False
    show_visualization: bool = False


def set_execution_context(context: Optional[ExecutionContext]) -> None:
    """Set the execution context for the current async context.

    Args:
        context: Execution context to set (or None to clear)

    Note:
        This also sets the mode on the EventEmitter singleton to ensure
        it's accessible across asyncio task boundaries.
    """
    # Import here to avoid circular dependency
    from spi_agent.display.events import get_event_emitter

    # Set ContextVar (for potential future use)
    _execution_context.set(context)

    # Also set on EventEmitter singleton (works across task boundaries)
    emitter = get_event_emitter()
    if context is None:
        emitter.set_interactive_mode(False, False)
    else:
        emitter.set_interactive_mode(context.is_interactive, context.show_visualization)


def get_execution_context() -> Optional[ExecutionContext]:
    """Get the current execution context.

    Returns:
        Current execution context or None if not set
    """
    return _execution_context.get()


def is_interactive_mode() -> bool:
    """Check if currently in interactive mode with visualization enabled.

    Returns:
        True if in interactive mode with visualization enabled

    Note:
        This now reads from the EventEmitter singleton to avoid ContextVar
        propagation issues across asyncio task boundaries.
    """
    # Import here to avoid circular dependency
    from spi_agent.display.events import get_event_emitter

    # Use EventEmitter as the source of truth (works across task boundaries)
    emitter = get_event_emitter()
    return emitter.is_interactive_mode()
