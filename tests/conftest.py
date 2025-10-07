"""Pytest configuration and fixtures."""

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest

from spi_agent.config import AgentConfig


@pytest.fixture
def test_config() -> AgentConfig:
    """Provide test configuration."""
    return AgentConfig(
        organization="test-org",
        repositories=["test-repo1", "test-repo2"],
        github_token="test_token_123",
    )


@pytest.fixture
def mock_github_issue() -> Mock:
    """Create a mock GitHub issue object."""
    issue = Mock()
    issue.number = 42
    issue.title = "Test Issue"
    issue.body = "This is a test issue body"
    issue.state = "open"

    # Create proper label mocks
    label1 = Mock()
    label1.name = "bug"
    label2 = Mock()
    label2.name = "priority:high"
    issue.labels = [label1, label2]

    # Create proper assignee mocks
    assignee1 = Mock()
    assignee1.login = "testuser"
    issue.assignees = [assignee1]

    issue.created_at = datetime(2025, 1, 6, 10, 0, 0)
    issue.updated_at = datetime(2025, 1, 6, 12, 0, 0)
    issue.html_url = "https://github.com/test-org/test-repo1/issues/42"
    issue.comments = 3

    # Create proper user mock
    user = Mock()
    user.login = "issueauthor"
    issue.user = user

    issue.pull_request = None  # Not a PR
    return issue


@pytest.fixture
def mock_github_repo(mock_github_issue: Mock) -> Mock:
    """Create a mock GitHub repository object."""
    repo = Mock()
    repo.full_name = "test-org/test-repo1"
    repo.name = "test-repo1"

    # Mock get_issues to return our mock issue
    repo.get_issues.return_value = [mock_github_issue]

    # Mock get_issue to return specific issue
    repo.get_issue.return_value = mock_github_issue

    # Mock create_issue
    repo.create_issue.return_value = mock_github_issue

    return repo


@pytest.fixture
def mock_github_client(mock_github_repo: Mock) -> Mock:
    """Create a mock GitHub client."""
    client = Mock()
    client.get_repo.return_value = mock_github_repo

    # Mock search
    client.search_issues.return_value = []

    return client


@pytest.fixture
def mock_github(monkeypatch: Any, mock_github_client: Mock) -> Mock:
    """Mock the Github class constructor."""

    def mock_github_constructor(*args: Any, **kwargs: Any) -> Mock:
        return mock_github_client

    monkeypatch.setattr("spi_agent.github_tools.Github", mock_github_constructor)
    return mock_github_client


@pytest.fixture
def mock_github_pr() -> Mock:
    """Create a mock GitHub pull request object."""
    pr = Mock()
    pr.number = 123
    pr.title = "Test Pull Request"
    pr.body = "This is a test PR body"
    pr.state = "open"
    pr.draft = False
    pr.merged = False
    pr.mergeable = True
    pr.mergeable_state = "clean"

    # Base and head refs
    base = Mock()
    base.ref = "main"
    pr.base = base

    head = Mock()
    head.ref = "feature/test"
    pr.head = head

    # Labels and assignees
    label1 = Mock()
    label1.name = "enhancement"
    pr.labels = [label1]

    assignee1 = Mock()
    assignee1.login = "testuser"
    pr.assignees = [assignee1]

    # Timestamps
    pr.created_at = datetime(2025, 1, 6, 10, 0, 0)
    pr.updated_at = datetime(2025, 1, 6, 12, 0, 0)
    pr.merged_at = None

    # URLs and counts
    pr.html_url = "https://github.com/test-org/test-repo1/pull/123"
    pr.comments = 2
    pr.review_comments = 1
    pr.commits = 3
    pr.changed_files = 5
    pr.additions = 150
    pr.deletions = 50

    # User
    user = Mock()
    user.login = "prauthor"
    pr.user = user

    # Mock methods
    pr.as_issue = Mock()
    pr.create_issue_comment = Mock()
    pr.edit = Mock()
    pr.merge = Mock()

    return pr


@pytest.fixture
def mock_github_repo_with_pr(mock_github_repo: Mock, mock_github_pr: Mock) -> Mock:
    """Enhance mock repository with PR support."""
    mock_github_repo.get_pulls.return_value = [mock_github_pr]
    mock_github_repo.get_pull.return_value = mock_github_pr
    mock_github_repo.create_pull.return_value = mock_github_pr
    return mock_github_repo


@pytest.fixture
def mock_workflow() -> Mock:
    """Create a mock GitHub workflow object."""
    workflow = Mock()
    workflow.id = 12345678
    workflow.name = "Build and Test"
    workflow.path = ".github/workflows/build.yml"
    workflow.state = "active"
    workflow.created_at = datetime(2025, 1, 1, 10, 0, 0)
    workflow.updated_at = datetime(2025, 1, 6, 10, 0, 0)
    workflow.html_url = "https://github.com/test-org/test-repo1/actions/workflows/build.yml"
    workflow.create_dispatch = Mock(return_value=True)
    workflow.get_runs = Mock()
    return workflow


@pytest.fixture
def mock_workflow_run() -> Mock:
    """Create a mock GitHub workflow run object."""
    run = Mock()
    run.id = 987654321
    run.name = "Build and Test"
    run.workflow_id = 12345678
    run.status = "completed"
    run.conclusion = "success"
    run.head_branch = "main"
    run.head_sha = "abc123def456"
    run.event = "push"
    run.created_at = datetime(2025, 1, 6, 10, 0, 0)
    run.updated_at = datetime(2025, 1, 6, 10, 5, 0)
    run.run_started_at = datetime(2025, 1, 6, 10, 0, 15)
    run.html_url = "https://github.com/test-org/test-repo1/actions/runs/987654321"

    # Actor
    actor = Mock()
    actor.login = "testuser"
    run.actor = actor

    # Mock jobs
    job1 = Mock()
    job1.name = "lint"
    job1.status = "completed"
    job1.conclusion = "success"

    job2 = Mock()
    job2.name = "test"
    job2.status = "completed"
    job2.conclusion = "success"

    jobs_paginated = Mock()
    jobs_paginated.__iter__ = Mock(return_value=iter([job1, job2]))
    jobs_paginated.totalCount = 2

    run.get_jobs = Mock(return_value=jobs_paginated)
    run.cancel = Mock(return_value=True)

    return run


@pytest.fixture
def mock_github_repo_with_workflows(mock_github_repo: Mock, mock_workflow: Mock, mock_workflow_run: Mock) -> Mock:
    """Enhance mock repository with workflow support."""
    mock_github_repo.get_workflows.return_value = [mock_workflow]
    mock_github_repo.get_workflow.return_value = mock_workflow
    mock_github_repo.get_workflow_runs.return_value = [mock_workflow_run]
    mock_github_repo.get_workflow_run.return_value = mock_workflow_run
    return mock_github_repo
