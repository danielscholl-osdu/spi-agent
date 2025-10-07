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
