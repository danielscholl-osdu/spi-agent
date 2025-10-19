"""Tests for GitHub repository variables tools."""

from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from spi_agent.config import AgentConfig
from spi_agent.github.variables import RepositoryVariableTools


@pytest.fixture
def mock_config():
    """Create a mock configuration for testing."""
    config = MagicMock(spec=AgentConfig)
    config.github_token = "test_token"
    config.github_org = "test-org"
    config.get_repo_full_name = lambda repo: f"test-org/{repo}"
    return config


@pytest.fixture
def variable_tools(mock_config):
    """Create RepositoryVariableTools instance with mock config."""
    with patch("spi_agent.github.base.Github"):
        tools = RepositoryVariableTools(mock_config)
        tools.github = MagicMock()
        return tools


class TestGetRepositoryVariables:
    """Tests for get_repository_variables method."""

    def test_get_repository_variables_success(self, variable_tools):
        """Test successfully retrieving all variables from a repository."""
        # Mock repository
        mock_repo = MagicMock()

        # Mock variables
        mock_var1 = MagicMock()
        mock_var1.name = "UPSTREAM_REPO_URL"
        mock_var1.value = "https://gitlab.example.com/osdu/partition"

        mock_var2 = MagicMock()
        mock_var2.name = "DEPLOY_ENV"
        mock_var2.value = "production"

        mock_repo.get_variables.return_value = [mock_var1, mock_var2]
        variable_tools.github.get_repo.return_value = mock_repo

        # Execute
        result = variable_tools.get_repository_variables("partition")

        # Verify
        assert "Variables for repository 'test-org/partition':" in result
        assert "UPSTREAM_REPO_URL: https://gitlab.example.com/osdu/partition" in result
        assert "DEPLOY_ENV: production" in result
        variable_tools.github.get_repo.assert_called_once_with("test-org/partition")

    def test_get_repository_variables_no_variables(self, variable_tools):
        """Test retrieving variables when repository has none configured."""
        # Mock repository with no variables
        mock_repo = MagicMock()
        mock_repo.get_variables.return_value = []
        variable_tools.github.get_repo.return_value = mock_repo

        # Execute
        result = variable_tools.get_repository_variables("partition")

        # Verify
        assert "No variables found for repository 'test-org/partition'" in result

    def test_get_repository_variables_repo_not_found(self, variable_tools):
        """Test error handling when repository doesn't exist."""
        # Mock 404 error
        error_data = {"message": "Not Found"}
        variable_tools.github.get_repo.side_effect = GithubException(
            404, error_data, headers={}
        )

        # Execute
        result = variable_tools.get_repository_variables("nonexistent")

        # Verify
        assert "Repository 'nonexistent' not found" in result

    def test_get_repository_variables_access_denied(self, variable_tools):
        """Test error handling when access is denied."""
        # Mock 403 error
        error_data = {"message": "Forbidden"}
        variable_tools.github.get_repo.side_effect = GithubException(
            403, error_data, headers={}
        )

        # Execute
        result = variable_tools.get_repository_variables("partition")

        # Verify
        assert "Error retrieving variables" in result
        assert "Forbidden" in result

    def test_get_repository_variables_unexpected_error(self, variable_tools):
        """Test handling of unexpected errors."""
        # Mock unexpected exception
        variable_tools.github.get_repo.side_effect = Exception("Network error")

        # Execute
        result = variable_tools.get_repository_variables("partition")

        # Verify
        assert "Unexpected error retrieving variables" in result
        assert "Network error" in result


class TestGetRepositoryVariable:
    """Tests for get_repository_variable method."""

    def test_get_repository_variable_success(self, variable_tools):
        """Test successfully retrieving a specific variable."""
        # Mock repository and variable
        mock_repo = MagicMock()
        mock_variable = MagicMock()
        mock_variable.name = "UPSTREAM_REPO_URL"
        mock_variable.value = "https://gitlab.example.com/osdu/partition"

        mock_repo.get_variable.return_value = mock_variable
        variable_tools.github.get_repo.return_value = mock_repo

        # Execute
        result = variable_tools.get_repository_variable("partition", "UPSTREAM_REPO_URL")

        # Verify
        assert result == "UPSTREAM_REPO_URL: https://gitlab.example.com/osdu/partition"
        mock_repo.get_variable.assert_called_once_with("UPSTREAM_REPO_URL")

    def test_get_repository_variable_not_found(self, variable_tools):
        """Test error handling when variable doesn't exist."""
        # Mock repository that exists but variable doesn't
        mock_repo = MagicMock()
        error_data = {"message": "Not Found"}
        mock_repo.get_variable.side_effect = GithubException(404, error_data, headers={})

        variable_tools.github.get_repo.return_value = mock_repo

        # Execute
        result = variable_tools.get_repository_variable("partition", "NONEXISTENT_VAR")

        # Verify
        assert "Variable 'NONEXISTENT_VAR' not found in repository 'test-org/partition'" in result

    def test_get_repository_variable_repo_not_found(self, variable_tools):
        """Test error handling when repository doesn't exist."""
        # Mock repository not found on both calls
        error_data = {"message": "Not Found"}
        variable_tools.github.get_repo.side_effect = GithubException(
            404, error_data, headers={}
        )

        # Execute
        result = variable_tools.get_repository_variable("nonexistent", "UPSTREAM_REPO_URL")

        # Verify
        assert "Repository 'nonexistent' not found" in result

    def test_get_repository_variable_api_error(self, variable_tools):
        """Test error handling for GitHub API errors."""
        # Mock API error
        mock_repo = MagicMock()
        error_data = {"message": "API rate limit exceeded"}
        mock_repo.get_variable.side_effect = GithubException(429, error_data, headers={})

        variable_tools.github.get_repo.return_value = mock_repo

        # Execute
        result = variable_tools.get_repository_variable("partition", "UPSTREAM_REPO_URL")

        # Verify
        assert "Error retrieving variable" in result
        assert "API rate limit exceeded" in result

    def test_get_repository_variable_unexpected_error(self, variable_tools):
        """Test handling of unexpected errors."""
        # Mock unexpected exception
        mock_repo = MagicMock()
        mock_repo.get_variable.side_effect = Exception("Connection timeout")

        variable_tools.github.get_repo.return_value = mock_repo

        # Execute
        result = variable_tools.get_repository_variable("partition", "UPSTREAM_REPO_URL")

        # Verify
        assert "Unexpected error retrieving variable" in result
        assert "Connection timeout" in result

    def test_get_repository_variable_empty_value(self, variable_tools):
        """Test retrieving a variable with an empty value."""
        # Mock repository and variable with empty value
        mock_repo = MagicMock()
        mock_variable = MagicMock()
        mock_variable.name = "EMPTY_VAR"
        mock_variable.value = ""

        mock_repo.get_variable.return_value = mock_variable
        variable_tools.github.get_repo.return_value = mock_repo

        # Execute
        result = variable_tools.get_repository_variable("partition", "EMPTY_VAR")

        # Verify
        assert result == "EMPTY_VAR: "

    def test_get_repository_variable_special_characters(self, variable_tools):
        """Test retrieving a variable with special characters in value."""
        # Mock repository and variable with special characters
        mock_repo = MagicMock()
        mock_variable = MagicMock()
        mock_variable.name = "COMPLEX_URL"
        mock_variable.value = "https://user:pass@gitlab.com/org/repo?foo=bar&baz=qux"

        mock_repo.get_variable.return_value = mock_variable
        variable_tools.github.get_repo.return_value = mock_repo

        # Execute
        result = variable_tools.get_repository_variable("partition", "COMPLEX_URL")

        # Verify
        assert "COMPLEX_URL: https://user:pass@gitlab.com/org/repo?foo=bar&baz=qux" in result
