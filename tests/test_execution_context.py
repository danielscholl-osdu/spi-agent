"""Tests for execution context and mode detection."""

from spi_agent.display.execution_context import (
    ExecutionContext,
    get_execution_context,
    is_interactive_mode,
    set_execution_context,
)


def test_execution_context_creation():
    """Test creating an execution context."""
    context = ExecutionContext(is_interactive=True, show_visualization=True)

    assert context.is_interactive is True
    assert context.show_visualization is True


def test_execution_context_defaults():
    """Test execution context defaults."""
    context = ExecutionContext()

    assert context.is_interactive is False
    assert context.show_visualization is False


def test_set_and_get_execution_context():
    """Test setting and getting execution context."""
    context = ExecutionContext(is_interactive=True, show_visualization=True)

    set_execution_context(context)

    retrieved_context = get_execution_context()
    assert retrieved_context is not None
    assert retrieved_context.is_interactive is True
    assert retrieved_context.show_visualization is True


def test_get_execution_context_when_not_set():
    """Test getting execution context when not set."""
    # Clear any existing context
    set_execution_context(None)

    context = get_execution_context()
    assert context is None


def test_is_interactive_mode_true():
    """Test is_interactive_mode returns True when context is interactive."""
    context = ExecutionContext(is_interactive=True, show_visualization=True)
    set_execution_context(context)

    assert is_interactive_mode() is True


def test_is_interactive_mode_false_when_no_visualization():
    """Test is_interactive_mode returns False when visualization disabled."""
    context = ExecutionContext(is_interactive=True, show_visualization=False)
    set_execution_context(context)

    assert is_interactive_mode() is False


def test_is_interactive_mode_false_when_not_interactive():
    """Test is_interactive_mode returns False when not interactive."""
    context = ExecutionContext(is_interactive=False, show_visualization=True)
    set_execution_context(context)

    assert is_interactive_mode() is False


def test_is_interactive_mode_false_when_no_context():
    """Test is_interactive_mode returns False when no context set."""
    set_execution_context(None)

    assert is_interactive_mode() is False
