"""Tests for Maven MCP integration."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from spi_agent.config import AgentConfig
from spi_agent.mcp import MavenMCPManager


@pytest.fixture
def config():
    """Create config for testing."""
    return AgentConfig()


class TestMavenMCPManager:
    """Test Maven MCP Manager."""

    def test_init(self, config):
        """Test initialization."""
        manager = MavenMCPManager(config)
        assert manager.config == config
        assert manager.mcp_tool is None
        assert manager._validated is False

    @patch("spi_agent.mcp.maven_mcp.shutil.which")
    def test_validate_prerequisites_success(self, mock_which, config):
        """Test successful prerequisite validation."""
        mock_which.return_value = "/usr/local/bin/uvx"
        manager = MavenMCPManager(config)

        result = manager.validate_prerequisites()

        assert result is True
        assert manager._validated is True
        mock_which.assert_called_once_with("uvx")

    @patch("spi_agent.mcp.maven_mcp.shutil.which")
    def test_validate_prerequisites_failure(self, mock_which, config):
        """Test failed prerequisite validation."""
        mock_which.return_value = None
        manager = MavenMCPManager(config)

        result = manager.validate_prerequisites()

        assert result is False
        assert manager._validated is False
        mock_which.assert_called_once_with("uvx")

    @pytest.mark.asyncio
    @patch("spi_agent.mcp.maven_mcp.shutil.which")
    async def test_context_manager_prerequisites_not_met(self, mock_which, config):
        """Test context manager when prerequisites not met."""
        mock_which.return_value = None
        manager = MavenMCPManager(config)

        async with manager as m:
            assert m.mcp_tool is None
            assert m.tools == []
            assert m.is_available is False

    @pytest.mark.asyncio
    @patch("spi_agent.mcp.maven_mcp.shutil.which")
    @patch("spi_agent.mcp.maven_mcp.MCPStdioTool")
    async def test_context_manager_success(
        self, mock_mcp_tool_class, mock_which, config
    ):
        """Test successful context manager initialization."""
        mock_which.return_value = "/usr/local/bin/uvx"
        mock_tool_instance = AsyncMock()
        mock_mcp_tool_class.return_value = mock_tool_instance

        manager = MavenMCPManager(config)

        async with manager as m:
            assert m.mcp_tool == mock_tool_instance
            assert len(m.tools) == 1
            assert m.is_available is True
            mock_tool_instance.__aenter__.assert_called_once()

        mock_tool_instance.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    @patch("spi_agent.mcp.maven_mcp.shutil.which")
    @patch("spi_agent.mcp.maven_mcp.MCPStdioTool")
    async def test_context_manager_file_not_found(
        self, mock_mcp_tool_class, mock_which, config
    ):
        """Test context manager when MCP server not found."""
        mock_which.return_value = "/usr/local/bin/uvx"
        mock_tool_instance = AsyncMock()
        mock_tool_instance.__aenter__.side_effect = FileNotFoundError("mvn-mcp-server not found")
        mock_mcp_tool_class.return_value = mock_tool_instance

        manager = MavenMCPManager(config)

        async with manager as m:
            assert m.mcp_tool is None
            assert m.tools == []
            assert m.is_available is False

    @pytest.mark.asyncio
    @patch("spi_agent.mcp.maven_mcp.shutil.which")
    @patch("spi_agent.mcp.maven_mcp.MCPStdioTool")
    async def test_context_manager_general_error(
        self, mock_mcp_tool_class, mock_which, config
    ):
        """Test context manager with general error."""
        mock_which.return_value = "/usr/local/bin/uvx"
        mock_tool_instance = AsyncMock()
        mock_tool_instance.__aenter__.side_effect = Exception("Connection error")
        mock_mcp_tool_class.return_value = mock_tool_instance

        manager = MavenMCPManager(config)

        async with manager as m:
            assert m.mcp_tool is None
            assert m.tools == []
            assert m.is_available is False

    @pytest.mark.asyncio
    @patch("spi_agent.mcp.maven_mcp.shutil.which")
    @patch("spi_agent.mcp.maven_mcp.MCPStdioTool")
    async def test_context_manager_cleanup_error(
        self, mock_mcp_tool_class, mock_which, config
    ):
        """Test context manager cleanup with error."""
        mock_which.return_value = "/usr/local/bin/uvx"
        mock_tool_instance = AsyncMock()
        mock_tool_instance.__aexit__.side_effect = Exception("Cleanup error")
        mock_mcp_tool_class.return_value = mock_tool_instance

        manager = MavenMCPManager(config)

        # Should not raise exception even if cleanup fails
        async with manager as m:
            pass

    def test_tools_property_no_tool(self, config):
        """Test tools property when no tool initialized."""
        manager = MavenMCPManager(config)
        assert manager.tools == []

    def test_resolve_workspace_path_service(self, config, tmp_path):
        """Service names should resolve under configured repos root."""
        manager = MavenMCPManager(config)
        repos_root = tmp_path / "repos"
        repos_root.mkdir()
        target = repos_root / "partition"
        target.mkdir()

        manager._workspace_root = repos_root

        resolved = manager._resolve_workspace_path("partition")

        assert Path(resolved) == target.resolve()

    def test_resolve_workspace_path_existing_relative(self, config, tmp_path):
        """Relative paths under repos should be normalized to absolute paths."""
        manager = MavenMCPManager(config)
        repos_root = tmp_path / "repos"
        repos_root.mkdir()
        target = repos_root / "legal"
        target.mkdir()

        manager._workspace_root = repos_root

        resolved = manager._resolve_workspace_path("./repos/legal")

        assert Path(resolved) == target.resolve()

    @pytest.mark.asyncio
    async def test_call_tool_normalizes_workspace(self, config, tmp_path):
        """call_tool wrapper should rewrite workspace argument before delegation."""
        manager = MavenMCPManager(config)
        repos_root = tmp_path / "repos"
        repos_root.mkdir()
        (repos_root / "storage").mkdir()

        manager._workspace_root = repos_root

        mock_tool_instance = AsyncMock()

        async def original_call(name, arguments=None, **kwargs):
            return name, arguments, kwargs

        async_mock = AsyncMock(side_effect=original_call)
        mock_tool_instance.call_tool = async_mock
        manager.mcp_tool = mock_tool_instance
        manager._wrap_workspace_normalization()

        await manager.mcp_tool.call_tool("scan_java_project", {"workspace": "storage"})

        expected_path = (repos_root / "storage").resolve()

        async_mock.assert_awaited_once()
        await_args = async_mock.await_args
        assert await_args.args[0] == "scan_java_project"
        assert await_args.args[1]["workspace"] == str(expected_path)

    @pytest.mark.asyncio
    @patch("spi_agent.mcp.maven_mcp.shutil.which")
    @patch("spi_agent.mcp.maven_mcp.MCPStdioTool")
    async def test_tools_property_with_tool(
        self, mock_mcp_tool_class, mock_which, config
    ):
        """Test tools property when tool is initialized."""
        mock_which.return_value = "/usr/local/bin/uvx"
        mock_tool_instance = AsyncMock()
        mock_mcp_tool_class.return_value = mock_tool_instance

        manager = MavenMCPManager(config)

        async with manager:
            assert len(manager.tools) == 1
            assert manager.tools[0] == mock_tool_instance

    def test_is_available_false(self, config):
        """Test is_available property when not available."""
        manager = MavenMCPManager(config)
        assert manager.is_available is False

    @pytest.mark.asyncio
    @patch("spi_agent.mcp.maven_mcp.shutil.which")
    @patch("spi_agent.mcp.maven_mcp.MCPStdioTool")
    async def test_is_available_true(
        self, mock_mcp_tool_class, mock_which, config
    ):
        """Test is_available property when available."""
        mock_which.return_value = "/usr/local/bin/uvx"
        mock_tool_instance = AsyncMock()
        mock_mcp_tool_class.return_value = mock_tool_instance

        manager = MavenMCPManager(config)

        async with manager:
            assert manager.is_available is True
