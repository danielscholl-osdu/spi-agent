"""Activity tracking for real-time agent feedback.

This module provides a thread-safe activity tracker that enables real-time
visibility into what the agent is doing during query execution.
"""

import asyncio
from typing import Optional


class ActivityTracker:
    """Thread-safe activity tracker for console status updates.

    This tracker maintains the current activity state and provides
    formatted display strings for tool calls and LLM operations.
    """

    def __init__(self):
        """Initialize activity tracker."""
        self._current_activity = "Thinking..."
        self._lock = asyncio.Lock()

    async def update(self, activity: str) -> None:
        """Update current activity.

        Args:
            activity: Activity description to display
        """
        async with self._lock:
            self._current_activity = activity

    def get_current(self) -> str:
        """Get current activity (thread-safe read).

        Returns:
            Current activity string
        """
        return self._current_activity

    async def reset(self) -> None:
        """Reset activity tracker to initial state.

        This clears the current activity and returns it to the starting state.
        Useful when clearing chat context to provide a clean slate.
        """
        async with self._lock:
            self._current_activity = "Thinking..."

    def format_tool_name(self, tool: str) -> str:
        """Format tool name for user-friendly display.

        Args:
            tool: Raw tool name (e.g., 'gh_list_issues')

        Returns:
            Human-readable tool description
        """
        # GitHub tools
        gh_mapping = {
            "gh_list_issues": "Listing GitHub issues",
            "gh_get_issue": "Reading GitHub issue",
            "gh_get_issue_comments": "Reading issue comments",
            "gh_create_issue": "Creating GitHub issue",
            "gh_update_issue": "Updating GitHub issue",
            "gh_add_issue_comment": "Adding issue comment",
            "gh_search_issues": "Searching GitHub issues",
            "gh_assign_issue_to_copilot": "Assigning issue to Copilot",
            "gh_list_pull_requests": "Listing pull requests",
            "gh_get_pull_request": "Reading pull request",
            "gh_get_pr_comments": "Reading PR comments",
            "gh_create_pull_request": "Creating pull request",
            "gh_update_pull_request": "Updating pull request",
            "gh_merge_pull_request": "Merging pull request",
            "gh_add_pr_comment": "Adding PR comment",
            "gh_list_workflows": "Listing workflows",
            "gh_list_workflow_runs": "Listing workflow runs",
            "gh_get_workflow_run": "Reading workflow run",
            "gh_trigger_workflow": "Triggering workflow",
            "gh_cancel_workflow_run": "Cancelling workflow",
            "gh_check_pr_workflow_approvals": "Checking PR approvals",
            "gh_list_code_scanning_alerts": "Listing security alerts",
            "gh_get_code_scanning_alert": "Reading security alert",
            "gh_get_repository_variables": "Reading repository variables",
            "gh_get_repository_variable": "Reading repository variable",
        }

        # GitLab tools
        glab_mapping = {
            "glab_list_issues": "Listing GitLab issues",
            "glab_get_issue": "Reading GitLab issue",
            "glab_get_issue_notes": "Reading issue notes",
            "glab_create_issue": "Creating GitLab issue",
            "glab_update_issue": "Updating GitLab issue",
            "glab_add_issue_note": "Adding issue note",
            "glab_search_issues": "Searching GitLab issues",
            "glab_list_merge_requests": "Listing merge requests",
            "glab_get_merge_request": "Reading merge request",
            "glab_get_mr_notes": "Reading MR notes",
            "glab_create_merge_request": "Creating merge request",
            "glab_update_merge_request": "Updating merge request",
            "glab_merge_merge_request": "Merging merge request",
            "glab_add_mr_note": "Adding MR note",
            "glab_list_pipelines": "Listing pipelines",
            "glab_get_pipeline": "Reading pipeline",
            "glab_get_pipeline_jobs": "Reading pipeline jobs",
            "glab_trigger_pipeline": "Triggering pipeline",
            "glab_cancel_pipeline": "Cancelling pipeline",
            "glab_retry_pipeline": "Retrying pipeline",
        }

        # Maven MCP tools
        maven_mapping = {
            "check_version_tool": "Checking Maven version",
            "check_version_batch_tool": "Checking Maven versions (batch)",
            "list_available_versions_tool": "Listing available versions",
            "scan_java_project_tool": "Scanning Java project",
            "analyze_pom_file_tool": "Analyzing POM file",
        }

        # Filesystem tools
        fs_mapping = {
            "list_directory": "Listing directory",
            "read_file": "Reading file",
            "search_files": "Searching files",
            "find_in_directory": "Finding in directory",
            "parse_pom_file": "Parsing POM file",
            "find_dependency_version": "Finding dependency version",
        }

        # Git tools
        git_mapping = {
            "get_git_status": "Checking git status",
            "get_git_diff": "Reading git diff",
            "list_git_branches": "Listing git branches",
        }

        # Check all mappings
        for mapping in [gh_mapping, glab_mapping, maven_mapping, fs_mapping, git_mapping]:
            if tool in mapping:
                return mapping[tool]

        # Handle MCP tools with server prefix
        if tool.startswith("mcp__mvn-mcp-server__"):
            tool_name = tool.replace("mcp__mvn-mcp-server__", "")
            if tool_name in maven_mapping:
                return maven_mapping[tool_name]
            return f"Running Maven {tool_name.replace('_', ' ')}"

        # Fallback: format the tool name nicely
        return f"Running {tool.replace('_', ' ').replace('gh ', 'GitHub ').replace('glab ', 'GitLab ')}"


# Global singleton instance
_activity_tracker: Optional[ActivityTracker] = None


def get_activity_tracker() -> ActivityTracker:
    """Get the global activity tracker instance.

    Returns:
        ActivityTracker singleton instance
    """
    global _activity_tracker
    if _activity_tracker is None:
        _activity_tracker = ActivityTracker()
    return _activity_tracker
