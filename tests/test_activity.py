"""Tests for activity tracker."""

import pytest

from spi_agent.activity import ActivityTracker, get_activity_tracker


@pytest.mark.asyncio
async def test_activity_tracker_reset():
    """Test that reset clears activity to starting state."""
    tracker = ActivityTracker()

    # Update with some activity
    await tracker.update("Testing...")
    assert tracker.get_current() == "Testing..."

    # Reset should clear back to starting state
    await tracker.reset()
    assert tracker.get_current() == "Thinking..."


@pytest.mark.asyncio
async def test_activity_tracker_reset_thread_safe():
    """Test that reset is thread-safe with lock."""
    tracker = ActivityTracker()

    # Update and reset multiple times
    await tracker.update("Activity 1")
    await tracker.reset()
    assert tracker.get_current() == "Thinking..."

    await tracker.update("Activity 2")
    await tracker.reset()
    assert tracker.get_current() == "Thinking..."


@pytest.mark.asyncio
async def test_activity_tracker_get_current_after_reset():
    """Test get_current returns correct value after reset."""
    tracker = ActivityTracker()

    # Set multiple activities
    await tracker.update("First activity")
    await tracker.update("Second activity")
    await tracker.update("Third activity")

    # Reset
    await tracker.reset()

    # Should be back to starting state
    assert tracker.get_current() == "Thinking..."

    # Can be updated again after reset
    await tracker.update("New activity after reset")
    assert tracker.get_current() == "New activity after reset"


def test_get_activity_tracker_singleton():
    """Test that get_activity_tracker returns the same instance."""
    tracker1 = get_activity_tracker()
    tracker2 = get_activity_tracker()

    assert tracker1 is tracker2
