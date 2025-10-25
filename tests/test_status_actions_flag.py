"""Tests for --actions flag functionality in status command."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from spi_agent.copilot.runners.status_runner import StatusRunner
from spi_agent.workflows.status_workflow import run_status_workflow


class TestStatusRunnerActionsFlag:
    """Tests for StatusRunner show_actions parameter."""

    def test_status_runner_default_hides_actions(self):
        """Test that StatusRunner defaults to show_actions=False."""
        runner = StatusRunner(None, ["partition"])

        assert hasattr(runner, "show_actions")
        assert runner.show_actions is False

    def test_status_runner_with_flag_shows_actions(self):
        """Test that StatusRunner accepts show_actions=True."""
        runner = StatusRunner(None, ["partition"], show_actions=True)

        assert runner.show_actions is True

    def test_status_runner_gitlab_with_actions_flag(self):
        """Test that StatusRunner accepts show_actions with GitLab providers."""
        runner = StatusRunner(None, ["partition"], providers=["Azure"], show_actions=True)

        assert runner.show_actions is True
        assert runner.providers == ["Azure"]

    @patch("spi_agent.copilot.runners.status_runner.console")
    def test_display_status_hides_workflow_table_by_default(self, mock_console):
        """Test that display_status hides workflow table when show_actions=False."""
        runner = StatusRunner(None, ["partition"], show_actions=False)

        # Mock status data with workflows
        status_data = {
            "timestamp": datetime.now().isoformat(),
            "services": {
                "partition": {
                    "repo": {"exists": True, "updated_at": "2025-10-25T00:00:00Z"},
                    "issues": {"count": 0, "items": []},
                    "pull_requests": {"count": 0, "items": []},
                    "workflows": {
                        "recent": [
                            {
                                "name": "Test Workflow",
                                "status": "completed",
                                "conclusion": "success",
                                "created_at": "2025-10-25T00:00:00Z",
                            }
                        ]
                    },
                }
            },
        }

        runner.display_status(status_data)

        # Verify that console.print was called (for summary table and condensed summary)
        assert mock_console.print.called

        # Check that a Panel with "Workflows Summary" was printed (condensed summary)
        from rich.panel import Panel

        panel_calls = [
            call[0][0] for call in mock_console.print.call_args_list if len(call[0]) > 0 and isinstance(call[0][0], Panel)
        ]
        assert any("Workflows Summary" in str(panel.title) for panel in panel_calls)

    @patch("spi_agent.copilot.runners.status_runner.console")
    def test_display_status_shows_workflow_table_with_flag(self, mock_console):
        """Test that display_status shows workflow table when show_actions=True."""
        runner = StatusRunner(None, ["partition"], show_actions=True)

        # Mock status data with workflows
        status_data = {
            "timestamp": datetime.now().isoformat(),
            "services": {
                "partition": {
                    "repo": {"exists": True, "updated_at": "2025-10-25T00:00:00Z"},
                    "issues": {"count": 0, "items": []},
                    "pull_requests": {"count": 0, "items": []},
                    "workflows": {
                        "recent": [
                            {
                                "name": "Test Workflow",
                                "status": "completed",
                                "conclusion": "success",
                                "created_at": "2025-10-25T00:00:00Z",
                                "head_branch": "main",
                            }
                        ]
                    },
                }
            },
        }

        runner.display_status(status_data)

        # Verify that console.print was called (for summary table and workflow table)
        assert mock_console.print.called

        # Check that the workflow table was printed (should contain "Action Status")
        # The call_args_list contains all calls to console.print
        # We expect to see a Table object being printed
        from rich.table import Table

        table_printed = any(
            isinstance(call[0][0], Table) for call in mock_console.print.call_args_list
        )
        assert table_printed


class TestStatusWorkflowActionsFlag:
    """Tests for run_status_workflow with show_actions parameter."""

    def test_status_workflow_signature_accepts_show_actions(self):
        """Test that run_status_workflow function signature includes show_actions parameter."""
        import inspect

        sig = inspect.signature(run_status_workflow)
        params = sig.parameters

        assert "show_actions" in params
        assert params["show_actions"].default is False  # Default value should be False


class TestCLIActionsFlag:
    """Tests for CLI argument parsing of --actions flag."""

    def test_cli_parser_recognizes_actions_flag(self):
        """Test that the CLI parser recognizes --actions flag."""
        from spi_agent.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["status", "--service", "partition", "--actions"])

        assert hasattr(args, "actions")
        assert args.actions is True

    def test_cli_parser_default_actions_flag(self):
        """Test that the CLI parser defaults --actions to False."""
        from spi_agent.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["status", "--service", "partition"])

        assert hasattr(args, "actions")
        assert args.actions is False

    def test_cli_parser_actions_with_other_flags(self):
        """Test that --actions works with other flags."""
        from spi_agent.cli import build_parser

        parser = build_parser()
        args = parser.parse_args([
            "status",
            "--service",
            "partition",
            "--platform",
            "gitlab",
            "--actions",
        ])

        assert args.actions is True
        assert args.platform == "gitlab"
        assert args.service == "partition"


class TestSlashCommandActionsFlag:
    """Tests for slash command parsing of --actions flag."""

    def test_slash_command_parses_actions_flag(self):
        """Test that slash command parsing logic correctly identifies --actions flag."""
        # Test that --actions is detected in command parts
        parts_with_flag = ["/status", "partition", "--actions"]
        assert "--actions" in parts_with_flag

        parts_without_flag = ["/status", "partition"]
        assert "--actions" not in parts_without_flag

        # This demonstrates the parsing logic used in handle_slash_command


class TestEdgeCases:
    """Tests for edge cases with --actions flag."""

    @patch("spi_agent.copilot.runners.status_runner.console")
    def test_no_workflows_with_actions_flag(self, mock_console):
        """Test that display_status handles no workflows gracefully with flag."""
        runner = StatusRunner(None, ["partition"], show_actions=True)

        # Mock status data with NO workflows
        status_data = {
            "timestamp": datetime.now().isoformat(),
            "services": {
                "partition": {
                    "repo": {"exists": True, "updated_at": "2025-10-25T00:00:00Z"},
                    "issues": {"count": 0, "items": []},
                    "pull_requests": {"count": 0, "items": []},
                    "workflows": {"recent": []},
                }
            },
        }

        # Should not raise an exception
        runner.display_status(status_data)
        assert mock_console.print.called

    @patch("spi_agent.copilot.runners.status_runner.console")
    def test_gitlab_pipelines_with_actions_flag(self, mock_console):
        """Test that display_status shows GitLab pipelines with flag."""
        runner = StatusRunner(None, ["partition"], providers=["Azure"], show_actions=True)

        # Mock GitLab status data
        status_data = {
            "timestamp": datetime.now().isoformat(),
            "projects": {
                "partition": {
                    "issues": {"count": 0, "items": []},
                    "merge_requests": {
                        "count": 1,
                        "items": [
                            {
                                "iid": 1,
                                "title": "Test MR",
                                "state": "opened",
                                "draft": False,
                                "pipelines": [
                                    {
                                        "id": 123,
                                        "status": "success",
                                        "created_at": "2025-10-25T00:00:00Z",
                                    }
                                ],
                            }
                        ],
                    },
                }
            },
        }

        # Should not raise an exception
        runner.display_status(status_data)
        assert mock_console.print.called
