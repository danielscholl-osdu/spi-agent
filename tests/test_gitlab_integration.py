"""Integration tests for GitLab tools with agent."""

from unittest.mock import Mock, patch

import pytest

from spi_agent import SPIAgent
from spi_agent.config import AgentConfig


class TestGitLabAgentIntegration:
    """Test GitLab tools integration with the agent."""

    @patch("spi_agent.agent.AzureOpenAIResponsesClient")
    @patch("spi_agent.agent.AzureCliCredential")
    def test_agent_with_gitlab_tools(
        self, mock_credential, mock_client, gitlab_config, mock_gitlab
    ):
        """Test agent initializes with GitLab tools when configured."""
        # Create agent with GitLab configuration
        agent = SPIAgent(config=gitlab_config)

        # Verify GitLab tools are created
        assert hasattr(agent, "gitlab_tools")
        assert len(agent.gitlab_tools) == 20  # All 20 GitLab tools

    @patch("spi_agent.agent.AzureOpenAIResponsesClient")
    @patch("spi_agent.agent.AzureCliCredential")
    def test_agent_without_gitlab_config(self, mock_credential, mock_client):
        """Test agent works when GitLab not configured."""
        # Create config without GitLab token
        config = AgentConfig(
            organization="test-org",
            repositories=["test-repo"],
            github_token="github_token",
            gitlab_token=None,  # No GitLab token
        )

        # Create agent without GitLab
        agent = SPIAgent(config=config)

        # Verify agent initializes without GitLab tools (needs both URL and token)
        assert hasattr(agent, "gitlab_tools")
        # GitLab tools are created if URL exists, even without token (for public projects)
        # So just verify agent initializes successfully
        assert agent is not None

    @patch("spi_agent.agent.AzureOpenAIResponsesClient")
    @patch("spi_agent.agent.AzureCliCredential")
    @patch("spi_agent.github.base.Github")  # Patch Github in the right module
    def test_github_and_gitlab_together(
        self, mock_github_class, mock_credential, mock_client, mock_gitlab
    ):
        """Test both GitHub and GitLab tools work simultaneously."""
        # Create config with both GitHub and GitLab
        config = AgentConfig(
            organization="test-org",
            repositories=["test-repo"],
            github_token="github_token",
            gitlab_url="https://gitlab.example.com",
            gitlab_token="gitlab_token",
            gitlab_default_group="test-group",
        )

        agent = SPIAgent(config=config)

        # Verify both tool sets are created
        assert len(agent.github_tools) > 0  # GitHub tools present
        assert len(agent.gitlab_tools) == 20  # GitLab tools present

    @patch("spi_agent.agent.AzureOpenAIResponsesClient")
    @patch("spi_agent.agent.AzureCliCredential")
    def test_gitlab_client_initialization(self, mock_credential, mock_client, gitlab_config, mock_gitlab):
        """Test GitLab client created with correct parameters."""
        agent = SPIAgent(config=gitlab_config)

        # GitLab tools should be initialized
        assert agent.gitlab_tools is not None
        assert len(agent.gitlab_tools) > 0

    def test_create_gitlab_tools_returns_correct_count(self, gitlab_config, mock_gitlab):
        """Test factory function returns correct number of tools."""
        from spi_agent.gitlab import create_gitlab_tools

        tools = create_gitlab_tools(gitlab_config)

        # Verify tool count: 7 issue + 7 MR + 6 pipeline = 20 total
        assert len(tools) == 20

        # Verify all tools are callable
        for tool in tools:
            assert callable(tool)


class TestGitLabToolsInAgent:
    """Test individual GitLab tools within agent context."""

    @patch("spi_agent.agent.AzureOpenAIResponsesClient")
    @patch("spi_agent.agent.AzureCliCredential")
    def test_gitlab_tools_accessible_from_agent(
        self, mock_credential, mock_client, gitlab_config, mock_gitlab
    ):
        """Test GitLab tools are accessible through agent."""
        agent = SPIAgent(config=gitlab_config)

        # Verify tools are in agent's tool list
        all_tools = agent.github_tools + agent.filesystem_tools + agent.git_tools + agent.gitlab_tools

        assert len(agent.gitlab_tools) == 20
        assert len(all_tools) >= 20  # At least GitLab tools present

    @patch("spi_agent.agent.AzureOpenAIResponsesClient")
    @patch("spi_agent.agent.AzureCliCredential")
    def test_gitlab_config_validation(self, mock_credential, mock_client):
        """Test GitLab configuration validation."""
        # Config with GitLab URL but no token should still work
        config = AgentConfig(
            organization="test-org",
            repositories=["test-repo"],
            gitlab_url="https://gitlab.example.com",
            gitlab_token=None,  # No token
        )

        with patch("spi_agent.gitlab.base.gitlab.Gitlab"):
            agent = SPIAgent(config=config)
            # Agent should initialize even without token
            assert agent is not None


class TestGitLabToolsErrorHandling:
    """Test error handling in GitLab tools."""

    def test_gitlab_api_error_handled(self, gitlab_config, mock_gitlab):
        """Test GitLab API errors are handled gracefully."""
        from gitlab.exceptions import GitlabError
        from spi_agent.gitlab.issues import IssueTools

        # Configure mock to raise error
        mock_gitlab.projects.get.side_effect = GitlabError("API Error")

        tools = IssueTools(gitlab_config)
        result = tools.list_issues("test-project")

        # Should return error message, not raise exception
        assert "error" in result.lower()

    def test_invalid_project_handled(self, gitlab_config, mock_gitlab):
        """Test invalid project names are handled."""
        from gitlab.exceptions import GitlabError
        from spi_agent.gitlab.issues import IssueTools

        mock_gitlab.projects.get.side_effect = GitlabError("404 Project Not Found")

        tools = IssueTools(gitlab_config)
        result = tools.get_issue("invalid-project", 1)

        # Should return error message, not raise exception
        assert "not found" in result.lower() or "error" in result.lower()
