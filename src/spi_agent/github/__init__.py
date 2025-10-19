"""GitHub tools package - modular organization of GitHub operations.

This package provides a unified interface to GitHub operations through specialized
tool classes organized by domain: issues, pull requests, workflows, and code scanning.

For backward compatibility, all tools are also available through a unified GitHubTools
class and create_github_tools() function.
"""

from typing import List

from spi_agent.config import AgentConfig
from spi_agent.github.base import GitHubToolsBase
from spi_agent.github.code_scanning import CodeScanningTools
from spi_agent.github.issues import IssueTools
from spi_agent.github.pull_requests import PullRequestTools
from spi_agent.github.variables import RepositoryVariableTools
from spi_agent.github.workflows import WorkflowTools


class GitHubTools:
    """
    Unified GitHub tools interface providing all GitHub operations.

    This class combines specialized tool classes (IssueTools, PullRequestTools,
    WorkflowTools, CodeScanningTools) into a single unified interface for
    backward compatibility with existing code.

    Example:
        >>> tools = GitHubTools(config)
        >>> tools.list_issues("partition", state="open")
        >>> tools.list_pull_requests("legal", limit=10)
    """

    def __init__(self, config: AgentConfig):
        """Initialize GitHub tools with configuration.

        Args:
            config: Agent configuration containing GitHub token and org info
        """
        self.config = config

        # Initialize specialized tool instances
        self._issues = IssueTools(config)
        self._pull_requests = PullRequestTools(config)
        self._workflows = WorkflowTools(config)
        self._code_scanning = CodeScanningTools(config)
        self._variables = RepositoryVariableTools(config)

    @property
    def github(self):
        """Access to GitHub client for backward compatibility.

        Returns the GitHub client instance from the issues tool.
        All specialized tools share the same GitHub client configuration.
        """
        return self._issues.github

    def _format_code_scanning_alert(self, *args, **kwargs):
        """Format code scanning alert for backward compatibility with tests."""
        return self._code_scanning._format_code_scanning_alert(*args, **kwargs)

    # ============ ISSUES ============

    def list_issues(self, *args, **kwargs):
        """List issues from a repository."""
        return self._issues.list_issues(*args, **kwargs)

    def get_issue(self, *args, **kwargs):
        """Get detailed information about a specific issue."""
        return self._issues.get_issue(*args, **kwargs)

    def get_issue_comments(self, *args, **kwargs):
        """Get comments from an issue."""
        return self._issues.get_issue_comments(*args, **kwargs)

    def create_issue(self, *args, **kwargs):
        """Create a new issue in a repository."""
        return self._issues.create_issue(*args, **kwargs)

    def update_issue(self, *args, **kwargs):
        """Update an existing issue."""
        return self._issues.update_issue(*args, **kwargs)

    def add_issue_comment(self, *args, **kwargs):
        """Add a comment to an existing issue."""
        return self._issues.add_issue_comment(*args, **kwargs)

    def search_issues(self, *args, **kwargs):
        """Search issues across repositories."""
        return self._issues.search_issues(*args, **kwargs)

    def assign_issue_to_copilot(self, *args, **kwargs):
        """Assign an issue to GitHub Copilot coding agent."""
        return self._issues.assign_issue_to_copilot(*args, **kwargs)

    # ============ PULL REQUESTS ============

    def list_pull_requests(self, *args, **kwargs):
        """List pull requests in a repository."""
        return self._pull_requests.list_pull_requests(*args, **kwargs)

    def get_pull_request(self, *args, **kwargs):
        """Get detailed information about a specific pull request."""
        return self._pull_requests.get_pull_request(*args, **kwargs)

    def get_pr_comments(self, *args, **kwargs):
        """Get discussion comments from a pull request."""
        return self._pull_requests.get_pr_comments(*args, **kwargs)

    def create_pull_request(self, *args, **kwargs):
        """Create a new pull request."""
        return self._pull_requests.create_pull_request(*args, **kwargs)

    def update_pull_request(self, *args, **kwargs):
        """Update pull request metadata."""
        return self._pull_requests.update_pull_request(*args, **kwargs)

    def merge_pull_request(self, *args, **kwargs):
        """Merge a pull request."""
        return self._pull_requests.merge_pull_request(*args, **kwargs)

    def add_pr_comment(self, *args, **kwargs):
        """Add a comment to a pull request discussion."""
        return self._pull_requests.add_pr_comment(*args, **kwargs)

    # ============ WORKFLOWS/ACTIONS ============

    def list_workflows(self, *args, **kwargs):
        """List available workflows in a repository."""
        return self._workflows.list_workflows(*args, **kwargs)

    def list_workflow_runs(self, *args, **kwargs):
        """List recent workflow runs."""
        return self._workflows.list_workflow_runs(*args, **kwargs)

    def get_workflow_run(self, *args, **kwargs):
        """Get detailed information about a specific workflow run."""
        return self._workflows.get_workflow_run(*args, **kwargs)

    def trigger_workflow(self, *args, **kwargs):
        """Manually trigger a workflow (workflow_dispatch)."""
        return self._workflows.trigger_workflow(*args, **kwargs)

    def cancel_workflow_run(self, *args, **kwargs):
        """Cancel a running workflow."""
        return self._workflows.cancel_workflow_run(*args, **kwargs)

    def check_pr_workflow_approvals(self, *args, **kwargs):
        """Check if a PR has workflows waiting for approval."""
        return self._workflows.check_pr_workflow_approvals(*args, **kwargs)

    # ============ CODE SCANNING ============

    def list_code_scanning_alerts(self, *args, **kwargs):
        """List code scanning alerts in a repository."""
        return self._code_scanning.list_code_scanning_alerts(*args, **kwargs)

    def get_code_scanning_alert(self, *args, **kwargs):
        """Get detailed information about a specific code scanning alert."""
        return self._code_scanning.get_code_scanning_alert(*args, **kwargs)

    # ============ REPOSITORY VARIABLES ============

    def get_repository_variables(self, *args, **kwargs):
        """List all GitHub Actions variables for a repository."""
        return self._variables.get_repository_variables(*args, **kwargs)

    def get_repository_variable(self, *args, **kwargs):
        """Get a specific GitHub Actions variable value from a repository."""
        return self._variables.get_repository_variable(*args, **kwargs)

    def close(self) -> None:
        """Close GitHub connections for all tool instances."""
        for tools in [self._issues, self._pull_requests, self._workflows, self._code_scanning, self._variables]:
            if hasattr(tools, 'github') and tools.github:
                tools.github.close()


def create_github_tools(config: AgentConfig) -> List:
    """
    Create GitHub tool functions for the agent.

    This function creates specialized tool class instances and returns their
    bound methods, which preserve type annotations for proper agent framework integration.

    Args:
        config: Agent configuration containing GitHub token and org info

    Returns:
        List of 25 bound tool methods organized by domain:
        - Issues (8 tools): list, get, get_comments, create, update, add_comment, search, assign_to_copilot
        - Pull Requests (7 tools): list, get, get_comments, create, update, merge, add_comment
        - Workflows/Actions (6 tools): list, list_runs, get_run, trigger, cancel_run, check_pr_approvals
        - Code Scanning (2 tools): list_alerts, get_alert
        - Repository Variables (2 tools): get_repository_variables, get_repository_variable
    """
    # Create specialized tool instances
    # Using separate instances (not via GitHubTools wrapper) preserves method signatures
    issues = IssueTools(config)
    pull_requests = PullRequestTools(config)
    workflows = WorkflowTools(config)
    code_scanning = CodeScanningTools(config)
    variables = RepositoryVariableTools(config)

    # Return bound methods directly from specialized tool classes
    # This preserves type annotations that were lost when accessing via GitHubTools wrapper
    return [
        # Issues (8 tools)
        issues.list_issues,
        issues.get_issue_comments,
        issues.get_issue,
        issues.create_issue,
        issues.update_issue,
        issues.add_issue_comment,
        issues.search_issues,
        issues.assign_issue_to_copilot,
        # Pull Requests (7 tools)
        pull_requests.list_pull_requests,
        pull_requests.get_pull_request,
        pull_requests.get_pr_comments,
        pull_requests.create_pull_request,
        pull_requests.update_pull_request,
        pull_requests.merge_pull_request,
        pull_requests.add_pr_comment,
        # Workflows/Actions (6 tools)
        workflows.list_workflows,
        workflows.list_workflow_runs,
        workflows.get_workflow_run,
        workflows.trigger_workflow,
        workflows.cancel_workflow_run,
        workflows.check_pr_workflow_approvals,
        # Code Scanning (2 tools)
        code_scanning.list_code_scanning_alerts,
        code_scanning.get_code_scanning_alert,
        # Repository Variables (2 tools)
        variables.get_repository_variables,
        variables.get_repository_variable,
    ]


__all__ = [
    # Main interfaces (backward compatibility)
    "GitHubTools",
    "create_github_tools",
    # Base class
    "GitHubToolsBase",
    # Specialized tool classes
    "IssueTools",
    "PullRequestTools",
    "WorkflowTools",
    "CodeScanningTools",
    "RepositoryVariableTools",
]
