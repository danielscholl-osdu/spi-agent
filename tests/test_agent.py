"""Tests for agent module."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from spi_agent.agent import SPIAgent
from spi_agent.config import AgentConfig


@pytest.fixture
def test_agent(test_config: AgentConfig) -> SPIAgent:
    """Create a test agent instance with mocked dependencies."""
    with patch("spi_agent.agent.AzureOpenAIResponsesClient"), patch(
        "spi_agent.agent.create_github_tools"
    ) as mock_tools, patch("spi_agent.agent.ChatAgent") as mock_chat_agent:

        # Mock GitHub tools
        mock_tools.return_value = []

        # Mock ChatAgent
        mock_agent_instance = Mock()
        mock_agent_instance.run = AsyncMock(return_value="Mocked agent response")
        mock_chat_agent.return_value = mock_agent_instance

        agent = SPIAgent(config=test_config)
        agent.agent = mock_agent_instance  # Replace with mock

        return agent


def test_agent_initialization():
    """Test agent initialization with default config."""
    with patch("spi_agent.agent.AzureOpenAIResponsesClient"), patch(
        "spi_agent.agent.create_github_tools"
    ), patch("spi_agent.agent.ChatAgent"):
        agent = SPIAgent()

        assert agent.config is not None
        assert agent.github_tools is not None
        assert agent.agent is not None


def test_agent_initialization_with_custom_config(test_config: AgentConfig):
    """Test agent initialization with custom config."""
    with patch("spi_agent.agent.AzureOpenAIResponsesClient"), patch(
        "spi_agent.agent.create_github_tools"
    ), patch("spi_agent.agent.ChatAgent"):
        agent = SPIAgent(config=test_config)

        assert agent.config.organization == "test-org"
        assert "test-repo1" in agent.config.repositories


@pytest.mark.asyncio
async def test_agent_run(test_agent: SPIAgent):
    """Test running agent with a query."""
    response = await test_agent.run("List issues in test-repo1")

    assert response == "Mocked agent response"
    test_agent.agent.run.assert_called_once_with("List issues in test-repo1")


@pytest.mark.asyncio
async def test_agent_run_handles_errors(test_agent: SPIAgent):
    """Test agent run handles exceptions gracefully."""
    test_agent.agent.run.side_effect = Exception("Test error")

    response = await test_agent.run("Test query")

    assert "Error running agent" in response
    assert "Test error" in response


def test_agent_instructions_include_repos(test_config: AgentConfig):
    """Test that agent instructions include repository information."""
    with patch("spi_agent.agent.AzureOpenAIResponsesClient"), patch(
        "spi_agent.agent.create_github_tools"
    ), patch("spi_agent.agent.ChatAgent") as mock_chat_agent:
        agent = SPIAgent(config=test_config)

        # Verify instructions mention the organization and repos
        assert "test-org" in agent.instructions
        assert "test-repo1" in agent.instructions or "test-repo2" in agent.instructions


def test_agent_has_required_tools():
    """Test that agent is initialized with GitHub tools."""
    with patch("spi_agent.agent.AzureOpenAIResponsesClient"), patch(
        "spi_agent.agent.create_github_tools"
    ) as mock_create_tools, patch("spi_agent.agent.ChatAgent") as mock_chat_agent:

        # Mock tools
        mock_tools = [Mock(), Mock(), Mock()]
        mock_create_tools.return_value = mock_tools

        agent = SPIAgent()

        # Verify ChatAgent was called with tools
        mock_chat_agent.assert_called_once()
        call_kwargs = mock_chat_agent.call_args[1]

        assert call_kwargs["tools"] == mock_tools
        assert call_kwargs["name"] == "SPI GitHub Issues Agent"


def test_agent_with_mcp_tools():
    """Test that agent can be initialized with MCP tools."""
    with patch("spi_agent.agent.AzureOpenAIResponsesClient"), patch(
        "spi_agent.agent.create_github_tools"
    ) as mock_create_tools, patch("spi_agent.agent.ChatAgent") as mock_chat_agent:

        # Mock GitHub and MCP tools
        github_tools = [Mock(), Mock()]
        mcp_tools = [Mock()]
        mock_create_tools.return_value = github_tools

        agent = SPIAgent(mcp_tools=mcp_tools)

        # Verify ChatAgent was called with combined tools
        mock_chat_agent.assert_called_once()
        call_kwargs = mock_chat_agent.call_args[1]

        # Should have both GitHub and MCP tools
        assert len(call_kwargs["tools"]) == 3
        assert call_kwargs["tools"] == github_tools + mcp_tools


def test_agent_instructions_include_maven_capabilities(test_config: AgentConfig):
    """Test that agent instructions include Maven MCP capabilities."""
    with patch("spi_agent.agent.AzureOpenAIResponsesClient"), patch(
        "spi_agent.agent.create_github_tools"
    ), patch("spi_agent.agent.ChatAgent"):
        agent = SPIAgent(config=test_config)

        # Verify instructions mention Maven capabilities
        assert "MAVEN DEPENDENCY MANAGEMENT" in agent.instructions
        assert "Check single dependency version" in agent.instructions
        assert "Scan Java projects for security vulnerabilities" in agent.instructions
        assert "triage" in agent.instructions.lower()
        assert "plan" in agent.instructions.lower()
