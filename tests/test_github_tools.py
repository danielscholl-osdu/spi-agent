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


def test_get_issue_comments_success(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo: Mock, mock_github_issue: Mock
):
    """Test successful retrieval of issue comments."""
    # Mock comments
    comment1 = Mock()
    comment1.id = 1001
    comment1.body = "First comment on the issue"
    comment1.user = Mock()
    comment1.user.login = "user1"
    comment1.created_at = datetime(2025, 1, 6, 10, 30, 0)
    comment1.updated_at = datetime(2025, 1, 6, 10, 30, 0)
    comment1.html_url = "https://github.com/test-org/test-repo1/issues/42#issuecomment-1001"

    comment2 = Mock()
    comment2.id = 1002
    comment2.body = "Second comment with more details"
    comment2.user = Mock()
    comment2.user.login = "user2"
    comment2.created_at = datetime(2025, 1, 6, 11, 0, 0)
    comment2.updated_at = datetime(2025, 1, 6, 11, 0, 0)
    comment2.html_url = "https://github.com/test-org/test-repo1/issues/42#issuecomment-1002"

    mock_github_issue.get_comments.return_value = [comment1, comment2]

    tools = GitHubTools(test_config)
    result = tools.get_issue_comments(repo="test-repo1", issue_number=42)

    assert "Comments on issue #42" in result
    assert "Comment #1 by user1" in result
    assert "Comment #2 by user2" in result
    assert "First comment on the issue" in result
    assert "Second comment with more details" in result
    assert "Total: 2 comment(s)" in result
    mock_github_issue.get_comments.assert_called_once()


def test_get_issue_comments_no_comments(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo: Mock, mock_github_issue: Mock
):
    """Test getting comments from issue with no comments."""
    mock_github_issue.get_comments.return_value = []

    tools = GitHubTools(test_config)
    result = tools.get_issue_comments(repo="test-repo1", issue_number=42)

    assert "No comments found on issue #42" in result


def test_get_issue_comments_with_limit(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo: Mock, mock_github_issue: Mock
):
    """Test getting comments with limit."""
    # Create 5 mock comments
    comments = []
    for i in range(5):
        comment = Mock()
        comment.id = 1000 + i
        comment.body = f"Comment {i+1}"
        comment.user = Mock()
        comment.user.login = f"user{i+1}"
        comment.created_at = datetime(2025, 1, 6, 10 + i, 0, 0)
        comment.updated_at = datetime(2025, 1, 6, 10 + i, 0, 0)
        comment.html_url = f"https://github.com/test-org/test-repo1/issues/42#issuecomment-{1000+i}"
        comments.append(comment)

    mock_github_issue.get_comments.return_value = comments
    mock_github_issue.comments = 5  # Total comment count

    tools = GitHubTools(test_config)
    result = tools.get_issue_comments(repo="test-repo1", issue_number=42, limit=3)

    # Should only show first 3 comments
    assert "Comment #1 by user1" in result
    assert "Comment #2 by user2" in result
    assert "Comment #3 by user3" in result
    assert "user4" not in result  # 4th and 5th should not be included
    assert "user5" not in result
    assert "Total: 3 comment(s)" in result
    assert "showing first 3 of 5" in result


def test_get_issue_comments_truncation(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo: Mock, mock_github_issue: Mock
):
    """Test that very long comments are truncated."""
    # Create comment with very long body (over 1500 chars)
    long_body = "a" * 2000
    comment = Mock()
    comment.id = 1001
    comment.body = long_body
    comment.user = Mock()
    comment.user.login = "verboseuser"
    comment.created_at = datetime(2025, 1, 6, 10, 30, 0)
    comment.updated_at = datetime(2025, 1, 6, 10, 30, 0)
    comment.html_url = "https://github.com/test-org/test-repo1/issues/42#issuecomment-1001"

    mock_github_issue.get_comments.return_value = [comment]

    tools = GitHubTools(test_config)
    result = tools.get_issue_comments(repo="test-repo1", issue_number=42)

    assert "… (comment truncated)" in result
    # Verify we don't have the full body
    assert len(result) < 2200  # Should be truncated


def test_get_issue_comments_not_found(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo: Mock
):
    """Test getting comments for non-existent issue."""
    error_data = {"message": "Not Found"}
    mock_github_repo.get_issue.side_effect = GithubException(404, error_data)

    tools = GitHubTools(test_config)
    result = tools.get_issue_comments(repo="test-repo1", issue_number=999)

    assert "not found" in result.lower()


def test_get_issue_comments_is_pull_request(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo: Mock
):
    """Test getting comments when issue is actually a PR."""
    pr_issue = Mock()
    pr_issue.number = 42
    pr_issue.pull_request = Mock()  # Has pull_request attribute

    mock_github_repo.get_issue.return_value = pr_issue

    tools = GitHubTools(test_config)
    result = tools.get_issue_comments(repo="test-repo1", issue_number=42)

    assert "pull request" in result.lower()


# ============ PULL REQUEST TESTS ============


def test_list_pull_requests_success(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_pr: Mock, mock_github_pr: Mock
):
    """Test successful PR listing."""
    tools = GitHubTools(test_config)

    result = tools.list_pull_requests(repo="test-repo1")

    assert "Found 1 pull request(s)" in result
    assert "#123: Test Pull Request" in result
    assert "[open]" in result
    assert "prauthor" in result


def test_list_pull_requests_no_results(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_pr: Mock
):
    """Test PR listing with no results."""
    mock_github_repo_with_pr.get_pulls.return_value = []

    tools = GitHubTools(test_config)
    result = tools.list_pull_requests(repo="test-repo1")

    assert "No open pull requests found" in result


def test_get_pull_request_success(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_pr: Mock, mock_github_pr: Mock
):
    """Test successful PR retrieval."""
    tools = GitHubTools(test_config)

    result = tools.get_pull_request(repo="test-repo1", pr_number=123)

    assert "Pull Request #123" in result
    assert "Test Pull Request" in result
    assert "prauthor" in result
    assert "Base: main ← Head: feature/test" in result
    assert "Merge Readiness" in result
    assert "Mergeable: yes" in result


def test_get_pull_request_not_found(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_pr: Mock
):
    """Test getting non-existent PR."""
    error_data = {"message": "Not Found"}
    mock_github_repo_with_pr.get_pull.side_effect = GithubException(404, error_data)

    tools = GitHubTools(test_config)
    result = tools.get_pull_request(repo="test-repo1", pr_number=999)

    assert "not found" in result.lower()


def test_get_pr_comments_success(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_pr: Mock, mock_github_pr: Mock
):
    """Test getting PR comments."""
    # Mock PR comments
    comment1 = Mock()
    comment1.id = 2001
    comment1.body = "First comment on PR"
    comment1.user = Mock()
    comment1.user.login = "reviewer1"
    comment1.created_at = datetime(2025, 1, 6, 10, 30, 0)
    comment1.updated_at = datetime(2025, 1, 6, 10, 30, 0)
    comment1.html_url = "https://github.com/test-org/test-repo1/pull/123#issuecomment-2001"

    mock_issue = Mock()
    mock_issue.get_comments.return_value = [comment1]
    mock_github_pr.as_issue.return_value = mock_issue

    tools = GitHubTools(test_config)
    result = tools.get_pr_comments(repo="test-repo1", pr_number=123)

    assert "Comments on PR #123" in result
    assert "reviewer1" in result
    assert "First comment on PR" in result


def test_get_pr_comments_no_comments(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_pr: Mock, mock_github_pr: Mock
):
    """Test getting PR with no comments."""
    mock_issue = Mock()
    mock_issue.get_comments.return_value = []
    mock_github_pr.as_issue.return_value = mock_issue

    tools = GitHubTools(test_config)
    result = tools.get_pr_comments(repo="test-repo1", pr_number=123)

    assert "No comments found on PR #123" in result


def test_create_pull_request_success(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_pr: Mock, mock_github_pr: Mock
):
    """Test successful PR creation."""
    tools = GitHubTools(test_config)

    result = tools.create_pull_request(
        repo="test-repo1",
        title="New Feature PR",
        head_branch="feature/new",
        base_branch="main",
        body="PR description",
        draft=False,
    )

    assert "✓ Created pull request #123" in result
    assert "Title:" in result

    # Verify create_pull was called correctly
    mock_github_repo_with_pr.create_pull.assert_called_once()
    call_kwargs = mock_github_repo_with_pr.create_pull.call_args[1]
    assert call_kwargs["title"] == "New Feature PR"
    assert call_kwargs["head"] == "feature/new"
    assert call_kwargs["base"] == "main"
    assert call_kwargs["draft"] is False


def test_create_pull_request_branch_not_found(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_pr: Mock
):
    """Test PR creation with non-existent branch."""
    error_data = {"message": "Branch does not exist"}
    mock_github_repo_with_pr.create_pull.side_effect = GithubException(422, error_data)

    tools = GitHubTools(test_config)
    result = tools.create_pull_request(
        repo="test-repo1", title="Test PR", head_branch="nonexistent", base_branch="main"
    )

    assert "Branch not found" in result
    assert "For same-repo PR use 'branch-name'" in result


def test_update_pull_request_success(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_pr: Mock, mock_github_pr: Mock
):
    """Test successful PR update."""
    tools = GitHubTools(test_config)

    result = tools.update_pull_request(
        repo="test-repo1", pr_number=123, title="Updated PR Title", draft=True
    )

    assert "✓ Updated pull request #123" in result
    assert "Updated fields: title, draft" in result

    # Verify edit was called
    mock_github_pr.edit.assert_called_once()
    call_kwargs = mock_github_pr.edit.call_args[1]
    assert call_kwargs["title"] == "Updated PR Title"
    assert call_kwargs["draft"] is True


def test_update_pull_request_invalid_state(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_pr: Mock
):
    """Test PR update with invalid state."""
    tools = GitHubTools(test_config)

    result = tools.update_pull_request(repo="test-repo1", pr_number=123, state="invalid")

    assert "Invalid state" in result


def test_update_pull_request_merged(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_pr: Mock, mock_github_pr: Mock
):
    """Test updating merged PR."""
    mock_github_pr.merged = True

    tools = GitHubTools(test_config)
    result = tools.update_pull_request(repo="test-repo1", pr_number=123, state="closed")

    assert "Cannot change state of merged PR" in result


def test_merge_pull_request_success(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_pr: Mock, mock_github_pr: Mock
):
    """Test successful PR merge."""
    merge_result = Mock()
    merge_result.merged = True
    merge_result.sha = "abc123def456"
    mock_github_pr.merge.return_value = merge_result

    tools = GitHubTools(test_config)

    result = tools.merge_pull_request(
        repo="test-repo1", pr_number=123, merge_method="squash"
    )

    assert "✓ Merged pull request #123" in result
    assert "Method: squash" in result
    assert "Commit SHA: abc123def456" in result

    mock_github_pr.merge.assert_called_once()


def test_merge_pull_request_already_merged(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_pr: Mock, mock_github_pr: Mock
):
    """Test merging already merged PR."""
    mock_github_pr.merged = True

    tools = GitHubTools(test_config)
    result = tools.merge_pull_request(repo="test-repo1", pr_number=123)

    assert "already merged" in result


def test_merge_pull_request_not_mergeable(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_pr: Mock, mock_github_pr: Mock
):
    """Test merging unmergeable PR."""
    mock_github_pr.mergeable = False
    mock_github_pr.mergeable_state = "dirty"

    tools = GitHubTools(test_config)
    result = tools.merge_pull_request(repo="test-repo1", pr_number=123)

    assert "cannot be merged" in result
    assert "dirty" in result


def test_merge_pull_request_invalid_method(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_pr: Mock, mock_github_pr: Mock
):
    """Test merge with invalid method."""
    tools = GitHubTools(test_config)
    result = tools.merge_pull_request(repo="test-repo1", pr_number=123, merge_method="invalid")

    assert "Invalid merge method" in result


def test_add_pr_comment_success(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_pr: Mock, mock_github_pr: Mock
):
    """Test adding comment to PR."""
    mock_comment = Mock()
    mock_comment.id = 3001
    mock_comment.html_url = "https://github.com/test-org/test-repo1/pull/123#issuecomment-3001"
    mock_github_pr.create_issue_comment.return_value = mock_comment

    tools = GitHubTools(test_config)

    result = tools.add_pr_comment(
        repo="test-repo1", pr_number=123, comment="This looks good to me!"
    )

    assert "✓ Added comment to PR #123" in result
    assert "Comment ID: 3001" in result

    mock_github_pr.create_issue_comment.assert_called_once_with("This looks good to me!")


def test_add_pr_comment_empty(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_pr: Mock
):
    """Test adding empty comment."""
    tools = GitHubTools(test_config)
    result = tools.add_pr_comment(repo="test-repo1", pr_number=123, comment="   ")

    assert "Cannot add empty comment" in result
