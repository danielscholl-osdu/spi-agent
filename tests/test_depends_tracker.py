"""Tests for DependsTracker."""

import pytest
from spi_agent.copilot.trackers.depends_tracker import DependsTracker


def test_depends_tracker_initialization():
    """Test DependsTracker initializes with services."""
    services = ["partition", "legal"]
    tracker = DependsTracker(services)

    assert len(tracker.services) == 2
    assert "partition" in tracker.services
    assert "legal" in tracker.services

    # Check initial state
    for service in services:
        assert tracker.services[service]["status"] == "pending"
        assert tracker.services[service]["major_updates"] == 0
        assert tracker.services[service]["minor_updates"] == 0
        assert tracker.services[service]["patch_updates"] == 0
        assert tracker.services[service]["total_dependencies"] == 0
        assert tracker.services[service]["outdated_dependencies"] == 0


def test_depends_tracker_update():
    """Test DependsTracker update method."""
    tracker = DependsTracker(["partition"])

    tracker.update(
        "partition",
        "complete",
        "Analysis complete",
        major_updates=2,
        minor_updates=5,
        patch_updates=10,
        total_dependencies=50,
        outdated_dependencies=17,
    )

    assert tracker.services["partition"]["status"] == "complete"
    assert tracker.services["partition"]["details"] == "Analysis complete"
    assert tracker.services["partition"]["major_updates"] == 2
    assert tracker.services["partition"]["minor_updates"] == 5
    assert tracker.services["partition"]["patch_updates"] == 10
    assert tracker.services["partition"]["total_dependencies"] == 50
    assert tracker.services["partition"]["outdated_dependencies"] == 17


def test_depends_tracker_get_summary():
    """Test DependsTracker get_summary method."""
    tracker = DependsTracker(["partition", "legal", "file"])

    tracker.update(
        "partition",
        "complete",
        "Done",
        major_updates=2,
        minor_updates=5,
        patch_updates=10,
        total_dependencies=50,
        outdated_dependencies=17,
    )

    tracker.update(
        "legal",
        "complete",
        "Done",
        major_updates=0,
        minor_updates=3,
        patch_updates=8,
        total_dependencies=40,
        outdated_dependencies=11,
    )

    tracker.update(
        "file",
        "error",
        "Failed",
    )

    summary = tracker.get_summary()

    assert summary["major_updates"] == 2
    assert summary["minor_updates"] == 8
    assert summary["patch_updates"] == 18
    assert summary["total_dependencies"] == 90
    assert summary["outdated_dependencies"] == 28
    assert summary["total_services"] == 3
    assert summary["completed_services"] == 2
    assert summary["error_services"] == 1


def test_depends_tracker_get_table():
    """Test DependsTracker get_table method generates Rich table."""
    tracker = DependsTracker(["partition"])

    tracker.update(
        "partition",
        "complete",
        "Analysis complete",
        major_updates=2,
        minor_updates=5,
        patch_updates=10,
    )

    table = tracker.get_table()

    # Check table has correct title
    assert "Service Status" in table.title

    # Check table has correct columns
    assert len(table.columns) == 5  # Service, Status, Major, Minor, Patch


def test_depends_tracker_table_title():
    """Test DependsTracker has correct table title."""
    tracker = DependsTracker(["partition"])
    assert tracker.table_title == "[italic]Service Status[/italic]"


def test_depends_tracker_with_modules():
    """Test DependsTracker with module-level breakdown."""
    tracker = DependsTracker(["partition"])

    # Simulate module breakdown
    tracker.services["partition"]["modules"] = {
        "core": {"major": 1, "minor": 2, "patch": 3},
        "azure": {"major": 1, "minor": 3, "patch": 7},
    }

    assert "core" in tracker.services["partition"]["modules"]
    assert "azure" in tracker.services["partition"]["modules"]
    assert tracker.services["partition"]["modules"]["core"]["major"] == 1
    assert tracker.services["partition"]["modules"]["azure"]["minor"] == 3
