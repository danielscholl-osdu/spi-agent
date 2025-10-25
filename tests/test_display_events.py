"""Tests for display event system."""

import asyncio

import pytest

from spi_agent.display.events import (
    EventEmitter,
    LLMRequestEvent,
    LLMResponseEvent,
    ToolCompleteEvent,
    ToolErrorEvent,
    ToolStartEvent,
    WorkflowStepEvent,
    get_event_emitter,
)


def test_tool_start_event_creation():
    """Test creating a tool start event."""
    event = ToolStartEvent(tool_name="gh_list_issues", arguments={"repo": "partition"})

    assert event.tool_name == "gh_list_issues"
    assert event.arguments == {"repo": "partition"}
    assert event.event_id is not None
    assert event.timestamp is not None


def test_tool_complete_event_creation():
    """Test creating a tool complete event."""
    event = ToolCompleteEvent(
        tool_name="gh_list_issues", result_summary="Found 3 issues", duration=0.5
    )

    assert event.tool_name == "gh_list_issues"
    assert event.result_summary == "Found 3 issues"
    assert event.duration == 0.5


def test_tool_error_event_creation():
    """Test creating a tool error event."""
    event = ToolErrorEvent(
        tool_name="gh_list_issues", error_message="Connection failed", duration=0.3
    )

    assert event.tool_name == "gh_list_issues"
    assert event.error_message == "Connection failed"
    assert event.duration == 0.3


def test_workflow_step_event_creation():
    """Test creating a workflow step event."""
    event = WorkflowStepEvent(
        step_name="Scanning dependencies", status="started", metadata={"service": "partition"}
    )

    assert event.step_name == "Scanning dependencies"
    assert event.status == "started"
    assert event.metadata == {"service": "partition"}


def test_llm_request_event_creation():
    """Test creating an LLM request event."""
    event = LLMRequestEvent(message_count=5)

    assert event.message_count == 5


def test_llm_response_event_creation():
    """Test creating an LLM response event."""
    event = LLMResponseEvent(duration=2.5)

    assert event.duration == 2.5


@pytest.mark.asyncio
async def test_event_emitter_emit_and_get():
    """Test emitting and getting events."""
    emitter = EventEmitter()

    event = ToolStartEvent(tool_name="test_tool")
    emitter.emit(event)

    # Get the event
    retrieved_event = await asyncio.wait_for(emitter.get_event(), timeout=1.0)

    assert retrieved_event.event_id == event.event_id
    assert retrieved_event.tool_name == "test_tool"


@pytest.mark.asyncio
async def test_event_emitter_get_nowait():
    """Test getting event without waiting."""
    emitter = EventEmitter()

    # Queue is empty
    result = await emitter.get_event_nowait()
    assert result is None

    # Add event
    event = ToolStartEvent(tool_name="test_tool")
    emitter.emit(event)

    # Get event immediately
    retrieved_event = await emitter.get_event_nowait()
    assert retrieved_event is not None
    assert retrieved_event.event_id == event.event_id


def test_event_emitter_enable_disable():
    """Test enabling and disabling event emitter."""
    emitter = EventEmitter()

    assert emitter.is_enabled is True

    emitter.disable()
    assert emitter.is_enabled is False

    # Emitting while disabled should not add to queue
    event = ToolStartEvent(tool_name="test_tool")
    emitter.emit(event)

    # Queue should be empty
    result = asyncio.run(emitter.get_event_nowait())
    assert result is None

    # Re-enable
    emitter.enable()
    assert emitter.is_enabled is True


def test_event_emitter_clear():
    """Test clearing event queue."""
    emitter = EventEmitter()

    # Add multiple events
    for i in range(5):
        event = ToolStartEvent(tool_name=f"tool_{i}")
        emitter.emit(event)

    # Clear queue
    emitter.clear()

    # Queue should be empty
    result = asyncio.run(emitter.get_event_nowait())
    assert result is None


def test_get_event_emitter_singleton():
    """Test that get_event_emitter returns singleton."""
    emitter1 = get_event_emitter()
    emitter2 = get_event_emitter()

    assert emitter1 is emitter2
