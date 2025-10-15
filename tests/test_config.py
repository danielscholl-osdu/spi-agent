"""Tests for configuration module."""

import os
from unittest.mock import patch

import pytest

from spi_agent.config import AgentConfig


def test_config_defaults():
    """Test default configuration values."""
    with patch.dict(
        os.environ,
        {
            "SPI_AGENT_ORGANIZATION": "test-org",
            "SPI_AGENT_REPOSITORIES": "repo1,repo2",
        },
        clear=True,
    ):
        config = AgentConfig()
        assert config.organization == "test-org"
        assert config.repositories == ["repo1", "repo2"]


def test_config_custom_values():
    """Test configuration with custom values."""
    config = AgentConfig(organization="custom-org", repositories=["custom-repo"])

    assert config.organization == "custom-org"
    assert config.repositories == ["custom-repo"]


def test_config_validation_empty_org():
    """Test configuration validation fails with empty organization."""
    with pytest.raises(ValueError, match="organization is required"):
        config = AgentConfig(organization="", repositories=["repo1"])


def test_config_validation_empty_repos():
    """Test configuration validation fails with empty repositories."""
    with pytest.raises(ValueError, match="repositories list cannot be empty"):
        config = AgentConfig(organization="test-org", repositories=[])


def test_get_repo_full_name():
    """Test getting full repository name."""
    config = AgentConfig(organization="test-org", repositories=["test-repo"])

    assert config.get_repo_full_name("test-repo") == "test-org/test-repo"
    assert config.get_repo_full_name("another-repo") == "test-org/another-repo"


def test_config_strips_whitespace():
    """Test that repository names are stripped of whitespace."""
    config = AgentConfig(
        organization="test-org", repositories=["repo1 ", " repo2", "  repo3  "]
    )

    assert config.repositories == ["repo1", "repo2", "repo3"]


def test_config_from_env_var_parsing():
    """Test parsing repositories from environment variable."""
    with patch.dict(
        os.environ,
        {"SPI_AGENT_REPOSITORIES": "partition, legal , entitlements"},
        clear=True,
    ):
        config = AgentConfig()
        assert config.repositories == ["partition", "legal", "entitlements"]


def test_config_maven_mcp_defaults():
    """Test Maven MCP default configuration values."""
    with patch.dict(os.environ, {}, clear=True):
        config = AgentConfig()
        assert config.maven_mcp_command == "uvx"
        assert config.maven_mcp_args == ["--quiet", "mvn-mcp-server==2.2.1"]


def test_config_maven_mcp_version_override():
    """Test Maven MCP version can be overridden via environment variable."""
    with patch.dict(os.environ, {"MAVEN_MCP_VERSION": "mvn-mcp-server==2.3.0"}, clear=True):
        config = AgentConfig()
        assert config.maven_mcp_args == ["--quiet", "mvn-mcp-server==2.3.0"]

    # Test unpinned version
    with patch.dict(os.environ, {"MAVEN_MCP_VERSION": "mvn-mcp-server"}, clear=True):
        config = AgentConfig()
        assert config.maven_mcp_args == ["--quiet", "mvn-mcp-server"]
