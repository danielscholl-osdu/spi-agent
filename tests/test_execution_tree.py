"""Tests for execution tree display and phase grouping."""

import pytest
from rich.console import Console

from spi_agent.display.events import LLMRequestEvent, LLMResponseEvent, ToolStartEvent, ToolCompleteEvent
from spi_agent.display.execution_tree import DisplayMode, ExecutionPhase, ExecutionTreeDisplay


def test_execution_phase_creation():
    """Test creating an execution phase."""
    phase = ExecutionPhase(phase_number=1)
    assert phase.phase_number == 1
    assert phase.status == "in_progress"
    assert phase.llm_node is None
    assert len(phase.tool_nodes) == 0
    assert phase.has_nodes is False


def test_execution_phase_with_tools():
    """Test phase with tool nodes."""
    from spi_agent.display.execution_tree import TreeNode

    phase = ExecutionPhase(phase_number=1)

    # Add a tool node
    tool_node = TreeNode("tool-1", "tool", "test_tool")
    phase.add_tool_node(tool_node)

    assert len(phase.tool_nodes) == 1
    assert phase.has_nodes is True
    assert "test_tool" in phase.summary


def test_execution_phase_summary():
    """Test phase summary generation."""
    from spi_agent.display.execution_tree import TreeNode, SYMBOL_TOOL

    phase = ExecutionPhase(phase_number=2)

    # No tools
    assert "Initial thinking" in phase.summary

    # One tool
    tool_node = TreeNode("tool-1", "tool", f"{SYMBOL_TOOL} read_file")
    phase.add_tool_node(tool_node)
    assert "read_file" in phase.summary

    # Multiple tools
    tool_node2 = TreeNode("tool-2", "tool", f"{SYMBOL_TOOL} list_files")
    phase.add_tool_node(tool_node2)
    assert "2 tool calls" in phase.summary


def test_execution_tree_display_mode_minimal():
    """Test display mode MINIMAL initialization."""
    console = Console()
    display = ExecutionTreeDisplay(console=console, display_mode=DisplayMode.MINIMAL)

    assert display.display_mode == DisplayMode.MINIMAL
    assert display._auto_collapse_completed is True
    assert display._show_llm_details is False


def test_execution_tree_display_mode_verbose():
    """Test display mode VERBOSE initialization."""
    console = Console()
    display = ExecutionTreeDisplay(console=console, display_mode=DisplayMode.VERBOSE)

    assert display.display_mode == DisplayMode.VERBOSE
    assert display._auto_collapse_completed is False
    assert display._show_llm_details is True


@pytest.mark.asyncio
async def test_phase_creation_on_llm_event():
    """Test that LLM events create new phases."""
    from spi_agent.display.events import get_event_emitter

    console = Console()
    display = ExecutionTreeDisplay(console=console, display_mode=DisplayMode.VERBOSE)

    # Manually process LLM event
    llm_event = LLMRequestEvent(message_count=2)
    await display._handle_event(llm_event)

    # Should have created one phase
    assert len(display._phases) == 1
    assert display._current_phase is not None
    assert display._current_phase.phase_number == 1


@pytest.mark.asyncio
async def test_tool_added_to_current_phase():
    """Test that tools are added to the current phase."""
    from spi_agent.display.events import get_event_emitter

    console = Console()
    display = ExecutionTreeDisplay(console=console, display_mode=DisplayMode.VERBOSE)

    # Create a phase first
    llm_event = LLMRequestEvent(message_count=2)
    await display._handle_event(llm_event)

    # Add a tool
    tool_event = ToolStartEvent(tool_name="read_file")
    await display._handle_event(tool_event)

    # Tool should be in current phase
    assert len(display._current_phase.tool_nodes) == 1
    assert display._current_phase.has_nodes is True


@pytest.mark.asyncio
async def test_phase_completion():
    """Test phase completion on new LLM event."""
    console = Console()
    display = ExecutionTreeDisplay(console=console, display_mode=DisplayMode.VERBOSE)

    # Create first phase
    llm1 = LLMRequestEvent(message_count=2)
    await display._handle_event(llm1)
    first_phase = display._current_phase

    # Create second phase (should complete first)
    llm2 = LLMRequestEvent(message_count=4)
    await display._handle_event(llm2)

    # First phase should be completed
    assert first_phase.status == "completed"
    assert display._current_phase.phase_number == 2


def test_display_symbols_no_emojis():
    """Verify no emojis in symbol constants."""
    from spi_agent.display.execution_tree import (
        SYMBOL_QUERY, SYMBOL_COMPLETE, SYMBOL_ACTIVE,
        SYMBOL_TOOL, SYMBOL_SUCCESS, SYMBOL_ERROR
    )

    # All symbols should be single unicode characters or short ASCII
    symbols = [SYMBOL_QUERY, SYMBOL_COMPLETE, SYMBOL_ACTIVE,
               SYMBOL_TOOL, SYMBOL_SUCCESS, SYMBOL_ERROR]

    for symbol in symbols:
        assert len(symbol) <= 2, f"Symbol '{symbol}' is too long"
        # Emojis would have ord() > 0x1F300
        for char in symbol:
            assert ord(char) < 0x1F300, f"Symbol '{symbol}' appears to be an emoji"
