"""Maven MCP Server integration for dependency management."""

import logging
import os
import shutil
from typing import List, Optional

from agent_framework import MCPStdioTool

from spi_agent.config import AgentConfig

logger = logging.getLogger(__name__)


class MavenMCPManager:
    """
    Manages Maven MCP server lifecycle and integration.

    Provides Maven dependency management capabilities including:
    - Version checking and update discovery
    - Security vulnerability scanning with Trivy
    - Dependency triage and analysis
    - Actionable remediation planning
    """

    def __init__(self, config: AgentConfig):
        """
        Initialize Maven MCP Manager.

        Args:
            config: Agent configuration with Maven MCP settings
        """
        self.config = config
        self.mcp_tool: Optional[MCPStdioTool] = None
        self._validated = False

    def validate_prerequisites(self) -> bool:
        """
        Validate that required commands are available.

        Returns:
            True if prerequisites met, False otherwise
        """
        # Check if command exists
        command_path = shutil.which(self.config.maven_mcp_command)
        if not command_path:
            logger.warning(
                f"Maven MCP disabled: '{self.config.maven_mcp_command}' command not found. "
                f"Install with: pip install uv"
            )
            return False

        self._validated = True
        return True

    async def __aenter__(self) -> "MavenMCPManager":
        """
        Async context manager entry.

        Returns:
            Self with initialized MCP tool
        """
        if not self.validate_prerequisites():
            logger.warning("Maven MCP prerequisites not met, continuing without Maven tools")
            return self

        try:
            # Suppress MCP server logs by setting environment variables
            # Save original env vars
            original_env = {}
            env_keys = ["PYTHONLOGGINGLEVEL", "MCP_LOG_LEVEL", "LOG_LEVEL", "FASTMCP_QUIET", "PYTHONWARNINGS"]

            for key in env_keys:
                original_env[key] = os.environ.get(key)

            # Set logging to ERROR to suppress INFO logs from MCP server
            os.environ["PYTHONLOGGINGLEVEL"] = "ERROR"
            os.environ["MCP_LOG_LEVEL"] = "ERROR"
            os.environ["LOG_LEVEL"] = "ERROR"
            os.environ["FASTMCP_QUIET"] = "1"  # Suppress FastMCP banner
            os.environ["PYTHONWARNINGS"] = "ignore"  # Suppress Python warnings

            # Temporarily suppress logging from mcp.server modules
            mcp_logger = logging.getLogger("mcp")
            original_mcp_level = mcp_logger.level
            mcp_logger.setLevel(logging.ERROR)

            fastmcp_logger = logging.getLogger("fastmcp")
            original_fastmcp_level = fastmcp_logger.level
            fastmcp_logger.setLevel(logging.ERROR)

            mvn_logger = logging.getLogger("mvn_mcp_server")
            original_mvn_level = mvn_logger.level
            mvn_logger.setLevel(logging.ERROR)

            try:
                # Initialize MCP stdio tool
                self.mcp_tool = MCPStdioTool(
                    name="maven-mcp-server",
                    command=self.config.maven_mcp_command,
                    args=self.config.maven_mcp_args,
                )

                # Enter the MCP tool's context
                await self.mcp_tool.__aenter__()

                logger.info("Maven MCP server initialized successfully")
                logger.info(
                    f"Available tools: {len(self.tools)} "
                    f"(Trivy required for security scanning)"
                )
            finally:
                # Restore original environment and logging levels
                for key, value in original_env.items():
                    if value is not None:
                        os.environ[key] = value
                    else:
                        os.environ.pop(key, None)

                mcp_logger.setLevel(original_mcp_level)
                fastmcp_logger.setLevel(original_fastmcp_level)
                mvn_logger.setLevel(original_mvn_level)

        except FileNotFoundError as e:
            logger.error(
                f"Maven MCP server not found: {e}. "
                f"Install with: uvx mvn-mcp-server"
            )
            self.mcp_tool = None
        except Exception as e:
            logger.error(f"Failed to initialize Maven MCP server: {e}")
            self.mcp_tool = None

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Async context manager exit.

        Args:
            exc_type: Exception type if any
            exc_val: Exception value if any
            exc_tb: Exception traceback if any
        """
        if self.mcp_tool:
            try:
                await self.mcp_tool.__aexit__(exc_type, exc_val, exc_tb)
                logger.info("Maven MCP server cleaned up successfully")
            except Exception as e:
                logger.error(f"Error cleaning up Maven MCP server: {e}")

    @property
    def tools(self) -> List:
        """
        Get Maven MCP tools for agent integration.

        Returns:
            List containing MCP tool if available, empty list otherwise
        """
        if self.mcp_tool:
            return [self.mcp_tool]
        return []

    @property
    def is_available(self) -> bool:
        """
        Check if Maven MCP is available.

        Returns:
            True if Maven MCP tools are available
        """
        return self.mcp_tool is not None
