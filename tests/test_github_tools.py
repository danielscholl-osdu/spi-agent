"""Tests for GitHub tools module."""

import copy
from datetime import datetime
from typing import Any
from unittest.mock import Mock

import pytest
from github import GithubException

from spi_agent.config import AgentConfig
from spi_agent.github import GitHubTools


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


# ============ WORKFLOW TESTS ============


def test_list_workflows_success(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_workflows: Mock, mock_workflow: Mock
):
    """Test successful workflow listing."""
    tools = GitHubTools(test_config)

    result = tools.list_workflows(repo="test-repo1")

    assert "Workflows in test-org/test-repo1" in result
    assert "Build and Test" in result
    assert "build.yml" in result
    assert "ID: 12345678" in result
    assert "State: active" in result


def test_list_workflows_no_results(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_workflows: Mock
):
    """Test workflow listing with no results."""
    mock_github_repo_with_workflows.get_workflows.return_value = []

    tools = GitHubTools(test_config)
    result = tools.list_workflows(repo="test-repo1")

    assert "No workflows found" in result


def test_list_workflow_runs_success(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_workflows: Mock, mock_workflow_run: Mock
):
    """Test successful workflow run listing."""
    tools = GitHubTools(test_config)

    result = tools.list_workflow_runs(repo="test-repo1")

    assert "Recent workflow runs in test-org/test-repo1" in result
    assert "Build and Test - Run #987654321" in result
    assert "completed" in result
    assert "success" in result
    assert "main" in result


def test_list_workflow_runs_no_results(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_workflows: Mock
):
    """Test workflow run listing with no results."""
    mock_github_repo_with_workflows.get_workflow_runs.return_value = []

    tools = GitHubTools(test_config)
    result = tools.list_workflow_runs(repo="test-repo1")

    assert "No workflow runs found" in result


def test_list_workflow_runs_with_filters(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_workflows: Mock, mock_workflow_run: Mock
):
    """Test workflow run listing with status and branch filters."""
    tools = GitHubTools(test_config)

    result = tools.list_workflow_runs(repo="test-repo1", status="completed", branch="main")

    assert "Recent workflow runs" in result
    # Verify the filters were applied (run matches both filters)
    assert "Build and Test" in result


def test_get_workflow_run_success(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_workflows: Mock, mock_workflow_run: Mock
):
    """Test successful workflow run retrieval."""
    tools = GitHubTools(test_config)

    result = tools.get_workflow_run(repo="test-repo1", run_id=987654321)

    assert "Workflow Run #987654321" in result
    assert "Build and Test" in result
    assert "Status: ✓ completed" in result
    assert "Conclusion: success" in result
    assert "Branch: main" in result
    assert "Commit: abc123d" in result
    assert "Triggered by: push" in result
    assert "Actor: testuser" in result
    assert "Jobs (2):" in result
    assert "lint" in result
    assert "test" in result


def test_get_workflow_run_not_found(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_workflows: Mock
):
    """Test getting non-existent workflow run."""
    error_data = {"message": "Not Found"}
    mock_github_repo_with_workflows.get_workflow_run.side_effect = GithubException(404, error_data)

    tools = GitHubTools(test_config)
    result = tools.get_workflow_run(repo="test-repo1", run_id=999)

    assert "not found" in result.lower()


def test_trigger_workflow_success(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_workflows: Mock, mock_workflow: Mock
):
    """Test successful workflow trigger."""
    tools = GitHubTools(test_config)

    result = tools.trigger_workflow(
        repo="test-repo1",
        workflow_name_or_id="build.yml",
        ref="main"
    )

    assert "✓ Triggered workflow" in result
    assert "Build and Test" in result
    assert "Branch: main" in result
    mock_workflow.create_dispatch.assert_called_once()


def test_trigger_workflow_with_inputs(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_workflows: Mock, mock_workflow: Mock
):
    """Test workflow trigger with JSON inputs."""
    tools = GitHubTools(test_config)

    result = tools.trigger_workflow(
        repo="test-repo1",
        workflow_name_or_id="build.yml",
        ref="main",
        inputs='{"environment": "prod", "version": "1.0"}'
    )

    assert "✓ Triggered workflow" in result
    mock_workflow.create_dispatch.assert_called_once()
    call_args = mock_workflow.create_dispatch.call_args
    assert call_args[1]["ref"] == "main"
    assert call_args[1]["inputs"] == {"environment": "prod", "version": "1.0"}


def test_trigger_workflow_invalid_json(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_workflows: Mock
):
    """Test workflow trigger with invalid JSON inputs."""
    tools = GitHubTools(test_config)

    result = tools.trigger_workflow(
        repo="test-repo1",
        workflow_name_or_id="build.yml",
        ref="main",
        inputs='{"bad json'
    )

    assert "Invalid JSON" in result


def test_trigger_workflow_non_string_input(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_workflows: Mock
):
    """Test workflow trigger with non-string input values."""
    tools = GitHubTools(test_config)

    result = tools.trigger_workflow(
        repo="test-repo1",
        workflow_name_or_id="build.yml",
        ref="main",
        inputs='{"count": 5}'
    )

    assert "must be string" in result


def test_trigger_workflow_not_found(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_workflows: Mock
):
    """Test triggering non-existent workflow."""
    mock_github_repo_with_workflows.get_workflow.side_effect = Exception("Not found")

    tools = GitHubTools(test_config)
    result = tools.trigger_workflow(
        repo="test-repo1",
        workflow_name_or_id="nonexistent.yml",
        ref="main"
    )

    assert "not found" in result.lower()


def test_cancel_workflow_run_success(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_workflows: Mock, mock_workflow_run: Mock
):
    """Test successful workflow run cancellation."""
    mock_workflow_run.status = "in_progress"

    tools = GitHubTools(test_config)

    result = tools.cancel_workflow_run(repo="test-repo1", run_id=987654321)

    assert "✓ Cancelled workflow run #987654321" in result
    assert "Build and Test" in result
    assert "Previous status: in_progress" in result
    mock_workflow_run.cancel.assert_called_once()


def test_cancel_workflow_run_already_completed(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_workflows: Mock, mock_workflow_run: Mock
):
    """Test canceling already completed run."""
    mock_workflow_run.status = "completed"

    tools = GitHubTools(test_config)
    result = tools.cancel_workflow_run(repo="test-repo1", run_id=987654321)

    assert "Cannot cancel completed workflow run" in result


def test_cancel_workflow_run_not_found(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_workflows: Mock
):
    """Test canceling non-existent workflow run."""
    error_data = {"message": "Not Found"}
    mock_github_repo_with_workflows.get_workflow_run.side_effect = GithubException(404, error_data)

    tools = GitHubTools(test_config)
    result = tools.cancel_workflow_run(repo="test-repo1", run_id=999)

    assert "not found" in result.lower()


# ============ CODE SCANNING TESTS ============


def test_list_code_scanning_alerts_success(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_code_scanning: Mock
):
    """Test successful code scanning alert listing."""
    tools = GitHubTools(test_config)

    result = tools.list_code_scanning_alerts(repo="test-repo1")

    assert "Found 1 code scanning alert(s)" in result
    assert "Alert #5: SQL Injection" in result
    assert "High" in result or "high" in result
    assert "src/api/query.js" in result
    assert "Open" in result or "open" in result


def test_list_code_scanning_alerts_with_state(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_code_scanning: Mock
):
    """Test listing code scanning alerts with state filter."""
    tools = GitHubTools(test_config)

    result = tools.list_code_scanning_alerts(repo="test-repo1", state="dismissed")

    # Verify API was called with correct parameters
    mock_github_repo_with_code_scanning._requester.requestJsonAndCheck.assert_called_once()
    call_args = mock_github_repo_with_code_scanning._requester.requestJsonAndCheck.call_args

    assert "state" in call_args[1]["parameters"]
    assert call_args[1]["parameters"]["state"] == "dismissed"


def test_list_code_scanning_alerts_with_severity_filter(
    test_config: AgentConfig,
    mock_github: Mock,
    mock_github_repo_with_code_scanning: Mock,
    mock_code_scanning_alert: dict[str, Any],
):
    """Test listing code scanning alerts with severity filter."""
    # Mock multiple alerts with different severities
    high_alert = copy.deepcopy(mock_code_scanning_alert)
    high_alert["rule"]["security_severity_level"] = "high"

    low_alert = copy.deepcopy(mock_code_scanning_alert)
    low_alert["number"] = 6
    low_alert["rule"]["security_severity_level"] = "low"

    mock_github_repo_with_code_scanning._requester.requestJsonAndCheck.return_value = (
        {},
        [high_alert, low_alert],
    )

    tools = GitHubTools(test_config)
    result = tools.list_code_scanning_alerts(repo="test-repo1", severity="high")

    # Should only show high severity alert
    assert "Alert #5" in result
    assert "Alert #6" not in result


def test_list_code_scanning_alerts_no_results(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_code_scanning: Mock
):
    """Test listing code scanning alerts with no results."""
    mock_github_repo_with_code_scanning._requester.requestJsonAndCheck.return_value = ({}, [])

    tools = GitHubTools(test_config)
    result = tools.list_code_scanning_alerts(repo="test-repo1")

    assert "No open code scanning alerts found" in result


def test_list_code_scanning_alerts_access_denied(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_code_scanning: Mock
):
    """Test listing code scanning alerts with access denied."""
    error_data = {"message": "Resource not accessible"}
    mock_github_repo_with_code_scanning._requester.requestJsonAndCheck.side_effect = (
        GithubException(403, error_data)
    )

    tools = GitHubTools(test_config)
    result = tools.list_code_scanning_alerts(repo="test-repo1")

    assert "Access denied" in result
    assert "security_events" in result


def test_get_code_scanning_alert_success(
    test_config: AgentConfig,
    mock_github: Mock,
    mock_github_repo_with_code_scanning: Mock,
    mock_code_scanning_alert: dict[str, Any],
):
    """Test successfully getting a code scanning alert."""
    mock_github_repo_with_code_scanning._requester.requestJsonAndCheck.return_value = (
        {},
        mock_code_scanning_alert,
    )

    tools = GitHubTools(test_config)
    result = tools.get_code_scanning_alert(repo="test-repo1", alert_number=5)

    assert "Code Scanning Alert #5" in result
    assert "SQL Injection" in result
    assert "src/api/query.js" in result
    assert "Lines: 42-45" in result
    assert "High" in result or "high" in result
    assert "CodeQL" in result
    assert "Open" in result or "open" in result


def test_get_code_scanning_alert_dismissed(
    test_config: AgentConfig,
    mock_github: Mock,
    mock_github_repo_with_code_scanning: Mock,
    mock_code_scanning_alert_dismissed: dict[str, Any],
):
    """Test getting a dismissed code scanning alert."""
    mock_github_repo_with_code_scanning._requester.requestJsonAndCheck.return_value = (
        {},
        mock_code_scanning_alert_dismissed,
    )

    tools = GitHubTools(test_config)
    result = tools.get_code_scanning_alert(repo="test-repo1", alert_number=10)

    assert "Code Scanning Alert #10" in result
    assert "Path Injection" in result
    assert "Dismissed" in result or "dismissed" in result
    assert "false positive" in result
    assert "securityteam" in result
    assert "This is actually safe due to input validation" in result


def test_get_code_scanning_alert_not_found(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_code_scanning: Mock
):
    """Test getting non-existent code scanning alert."""
    error_data = {"message": "Not Found"}
    mock_github_repo_with_code_scanning._requester.requestJsonAndCheck.side_effect = (
        GithubException(404, error_data)
    )

    tools = GitHubTools(test_config)
    result = tools.get_code_scanning_alert(repo="test-repo1", alert_number=999)

    assert "not found" in result.lower()


def test_get_code_scanning_alert_access_denied(
    test_config: AgentConfig, mock_github: Mock, mock_github_repo_with_code_scanning: Mock
):
    """Test getting code scanning alert with access denied."""
    error_data = {"message": "Resource not accessible"}
    mock_github_repo_with_code_scanning._requester.requestJsonAndCheck.side_effect = (
        GithubException(403, error_data)
    )

    tools = GitHubTools(test_config)
    result = tools.get_code_scanning_alert(repo="test-repo1", alert_number=5)

    assert "Access denied" in result
    assert "security_events" in result


def test_format_code_scanning_alert(test_config: AgentConfig, mock_code_scanning_alert: dict[str, Any]):
    """Test formatting code scanning alert data."""
    tools = GitHubTools(test_config)
    formatted = tools._format_code_scanning_alert(mock_code_scanning_alert)

    assert formatted["number"] == 5
    assert formatted["state"] == "open"
    assert formatted["rule_id"] == "js/sql-injection"
    assert formatted["rule_name"] == "SQL Injection"
    assert formatted["rule_security_severity_level"] == "high"
    assert formatted["tool_name"] == "CodeQL"
    assert formatted["tool_version"] == "2.15.0"
    assert formatted["file_path"] == "src/api/query.js"
    assert formatted["start_line"] == 42
    assert formatted["end_line"] == 45
    assert formatted["message"] == "This SQL query depends on a user-provided value."


def test_format_code_scanning_alert_with_nulls(
    test_config: AgentConfig, mock_code_scanning_alert_with_nulls: dict[str, Any]
):
    """Test formatting code scanning alert with None values (edge case)."""
    tools = GitHubTools(test_config)
    formatted = tools._format_code_scanning_alert(mock_code_scanning_alert_with_nulls)

    # Should handle None values gracefully
    assert formatted["number"] == 15
    assert formatted["state"] == "fixed"
    assert formatted["rule_id"] == "js/unused-variable"
    assert formatted["rule_name"] == "Unused Variable"
    assert formatted["rule_security_severity_level"] == "unknown"  # None → "unknown"
    assert formatted["rule_description"] == ""  # None → ""
    assert formatted["rule_tags"] == []  # None → []
    assert formatted["tool_name"] == "ESLint"
    assert formatted["tool_version"] == "unknown"  # None → "unknown"
    assert formatted["file_path"] == "unknown"  # No instance → "unknown"
    assert formatted["start_line"] is None  # No instance → None
    assert formatted["message"] == ""  # No instance → ""
    assert formatted["ref"] == "unknown"  # No instance → "unknown"


def test_list_code_scanning_alerts_with_null_severity(
    test_config: AgentConfig,
    mock_github: Mock,
    mock_github_repo_with_code_scanning: Mock,
    mock_code_scanning_alert_with_nulls: dict[str, Any],
):
    """Test listing alerts when security_severity_level is None."""
    mock_github_repo_with_code_scanning._requester.requestJsonAndCheck.return_value = (
        {},
        [mock_code_scanning_alert_with_nulls],
    )

    tools = GitHubTools(test_config)
    result = tools.list_code_scanning_alerts(repo="test-repo1")

    # Should not crash and should display "Unknown" for severity
    assert "Alert #15: Unused Variable" in result
    assert "Unknown" in result or "unknown" in result


def test_get_code_scanning_alert_with_null_severity(
    test_config: AgentConfig,
    mock_github: Mock,
    mock_github_repo_with_code_scanning: Mock,
    mock_code_scanning_alert_with_nulls: dict[str, Any],
):
    """Test getting alert details when security_severity_level is None."""
    mock_github_repo_with_code_scanning._requester.requestJsonAndCheck.return_value = (
        {},
        mock_code_scanning_alert_with_nulls,
    )

    tools = GitHubTools(test_config)
    result = tools.get_code_scanning_alert(repo="test-repo1", alert_number=15)

    # Should not crash and should display "Unknown" for severity
    assert "Code Scanning Alert #15" in result
    assert "Unused Variable" in result
    assert "Unknown" in result or "unknown" in result
