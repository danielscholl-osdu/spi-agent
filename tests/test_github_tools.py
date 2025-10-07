"""Tests for GitHub tools module."""

from datetime import datetime
from typing import Any
from unittest.mock import Mock

import pytest
from github import GithubException

from spi_agent.config import AgentConfig
from spi_agent.github_tools import GitHubTools


def test_list_issues_success(test_config: AgentConfig, mock_github: Mock, mock_github_issue: Mock):
    """Test successful issue listing."""
    tools = GitHubTools(test_config)

    result = tools.list_issues(repo="test-repo1")

    assert "Found 1 issue(s)" in result
    assert "#42: Test Issue" in result
    assert "bug" in result
    assert "priority:high" in result


def test_list_issues_with_filters(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo: Mock
):
    """Test issue listing with filters."""
    tools = GitHubTools(test_config)

    result = tools.list_issues(
        repo="test-repo1", state="closed", labels="bug,enhancement", assignee="testuser", limit=10
    )

    # Verify get_issues was called with correct parameters
    mock_github_repo.get_issues.assert_called_once()
    call_kwargs = mock_github_repo.get_issues.call_args[1]

    assert call_kwargs["state"] == "closed"
    assert call_kwargs["labels"] == ["bug", "enhancement"]
    assert call_kwargs["assignee"] == "testuser"


def test_list_issues_no_results(test_config: AgentConfig, mock_github: Mock, mock_github_repo: Mock):
    """Test issue listing with no results."""
    # Mock empty results
    mock_github_repo.get_issues.return_value = []

    tools = GitHubTools(test_config)
    result = tools.list_issues(repo="test-repo1")

    assert "No open issues found" in result


def test_get_issue_success(test_config: AgentConfig, mock_github: Mock, mock_github_issue: Mock):
    """Test successful issue retrieval."""
    tools = GitHubTools(test_config)

    result = tools.get_issue(repo="test-repo1", issue_number=42)

    assert "Issue #42" in result
    assert "Test Issue" in result
    assert "This is a test issue body" in result
    assert "open" in result


def test_get_issue_not_found(test_config: AgentConfig, mock_github: Mock, mock_github_repo: Mock):
    """Test getting non-existent issue."""
    # Mock 404 error
    error_data = {"message": "Not Found"}
    mock_github_repo.get_issue.side_effect = GithubException(404, error_data)

    tools = GitHubTools(test_config)
    result = tools.get_issue(repo="test-repo1", issue_number=999)

    assert "not found" in result.lower()


def test_get_issue_is_pull_request(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo: Mock
):
    """Test getting issue that is actually a PR."""
    pr_issue = Mock()
    pr_issue.number = 42
    pr_issue.pull_request = Mock()  # Has pull_request attribute

    mock_github_repo.get_issue.return_value = pr_issue

    tools = GitHubTools(test_config)
    result = tools.get_issue(repo="test-repo1", issue_number=42)

    assert "pull request" in result.lower()


def test_create_issue_success(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo: Mock, mock_github_issue: Mock
):
    """Test successful issue creation."""
    tools = GitHubTools(test_config)

    result = tools.create_issue(
        repo="test-repo1",
        title="New Test Issue",
        body="Issue description",
        labels="bug,enhancement",
        assignees="user1,user2",
    )

    assert "✓ Created issue" in result
    assert "#42" in result

    # Verify create_issue was called correctly
    mock_github_repo.create_issue.assert_called_once()
    call_kwargs = mock_github_repo.create_issue.call_args[1]

    assert call_kwargs["title"] == "New Test Issue"
    assert call_kwargs["body"] == "Issue description"
    assert call_kwargs["labels"] == ["bug", "enhancement"]
    assert call_kwargs["assignees"] == ["user1", "user2"]


def test_create_issue_minimal(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo: Mock
):
    """Test issue creation with minimal parameters."""
    tools = GitHubTools(test_config)

    result = tools.create_issue(repo="test-repo1", title="Simple Issue")

    assert "✓ Created issue" in result

    # Verify only title and empty body were passed
    call_kwargs = mock_github_repo.create_issue.call_args[1]
    assert call_kwargs["title"] == "Simple Issue"
    assert call_kwargs["body"] == ""


def test_update_issue_success(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo: Mock, mock_github_issue: Mock
):
    """Test successful issue update."""
    tools = GitHubTools(test_config)

    result = tools.update_issue(
        repo="test-repo1", issue_number=42, title="Updated Title", state="closed"
    )

    assert "✓ Updated issue" in result
    assert "#42" in result

    # Verify edit was called
    mock_github_issue.edit.assert_called_once()
    call_kwargs = mock_github_issue.edit.call_args[1]

    assert call_kwargs["title"] == "Updated Title"
    assert call_kwargs["state"] == "closed"


def test_update_issue_invalid_state(
    test_config: AgentConfig, mock_github: Mock, mock_github_issue: Mock
):
    """Test update with invalid state."""
    tools = GitHubTools(test_config)

    result = tools.update_issue(repo="test-repo1", issue_number=42, state="invalid")

    assert "Invalid state" in result


def test_add_comment_success(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo: Mock, mock_github_issue: Mock
):
    """Test successful comment addition."""
    # Mock comment creation
    mock_comment = Mock()
    mock_comment.id = 12345
    mock_comment.html_url = "https://github.com/test-org/test-repo1/issues/42#issuecomment-12345"
    mock_github_issue.create_comment.return_value = mock_comment

    tools = GitHubTools(test_config)

    result = tools.add_issue_comment(
        repo="test-repo1", issue_number=42, comment="This is a test comment"
    )

    assert "✓ Added comment" in result
    assert "Comment ID: 12345" in result

    mock_github_issue.create_comment.assert_called_once_with("This is a test comment")


def test_search_issues_success(test_config: AgentConfig, mock_github: Mock, mock_github_issue: Mock):
    """Test successful issue search."""
    # Mock search results
    mock_github.search_issues.return_value = [mock_github_issue]

    tools = GitHubTools(test_config)

    result = tools.search_issues(query="authentication", repos="test-repo1")

    assert "Found 1 issue(s)" in result
    assert "#42: Test Issue" in result


def test_search_issues_no_results(test_config: AgentConfig, mock_github: Mock):
    """Test search with no results."""
    mock_github.search_issues.return_value = []

    tools = GitHubTools(test_config)

    result = tools.search_issues(query="nonexistent")

    assert "No issues found" in result


def test_search_issues_all_repos(test_config: AgentConfig, mock_github: Mock):
    """Test searching across all configured repos."""
    mock_github.search_issues.return_value = []

    tools = GitHubTools(test_config)

    result = tools.search_issues(query="bug")

    # Verify search query includes all repos
    mock_github.search_issues.assert_called_once()
    query_arg = mock_github.search_issues.call_args[0][0]

    assert "repo:test-org/test-repo1" in query_arg
    assert "repo:test-org/test-repo2" in query_arg
    assert "is:issue" in query_arg


def test_github_tools_authentication_with_token(test_config: AgentConfig):
    """Test GitHub client initialization with token."""
    tools = GitHubTools(test_config)
    assert tools.github is not None


def test_github_tools_authentication_without_token():
    """Test GitHub client initialization without token."""
    config = AgentConfig(organization="test-org", repositories=["repo1"], github_token=None)

    tools = GitHubTools(config)
    assert tools.github is not None
