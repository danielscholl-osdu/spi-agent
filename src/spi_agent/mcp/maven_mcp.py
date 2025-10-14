"""Maven MCP Server integration for dependency management."""

import logging
import os
import shutil
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

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
        self._workspace_root = Path(
            os.getenv("SPI_AGENT_REPOS_ROOT", Path.cwd() / "repos")
        )
        self._original_call_tool = None

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
            # Build subprocess environment to suppress MCP server noise
            subprocess_env = os.environ.copy()
            subprocess_env.update({
                "PYTHONLOGGINGLEVEL": "WARNING",  # Allow WARNING+ but suppress INFO
                "MCP_LOG_LEVEL": "WARNING",
                "LOG_LEVEL": "WARNING",
                "FASTMCP_QUIET": "1",  # Suppress FastMCP banner
                "PYTHONWARNINGS": "ignore",  # Suppress Python warnings
            })

            # Initialize MCP stdio tool with controlled environment
            self.mcp_tool = MCPStdioTool(
                name="maven-mcp-server",
                command=self.config.maven_mcp_command,
                args=self.config.maven_mcp_args,
                env=subprocess_env,
            )

            # Enter the MCP tool's context
            await self.mcp_tool.__aenter__()

            # Normalize tool inputs before delegating to MCP server
            self._wrap_workspace_normalization()

            logger.info("Maven MCP server initialized successfully")
            logger.info(
                f"Available tools: {len(self.tools)} "
                f"(Trivy required for security scanning)"
            )

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
                self._restore_original_call_tool()
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

    def _restore_original_call_tool(self) -> None:
        """Restore original MCP call handler if it was wrapped."""
        if self.mcp_tool and self._original_call_tool is not None:
            self.mcp_tool.call_tool = self._original_call_tool
            self._original_call_tool = None

    def _wrap_workspace_normalization(self) -> None:
        """Wrap MCP tool call handling to normalize workspace paths."""
        if not self.mcp_tool or not hasattr(self.mcp_tool, "call_tool"):
            return

        # Avoid double wrapping if re-entered
        if self._original_call_tool is not None:
            return

        original_call_tool = self.mcp_tool.call_tool
        self._original_call_tool = original_call_tool

        async def call_tool_wrapper(tool_self, *call_args: Any, **call_kwargs: Any) -> Any:
            call_args_list = list(call_args)

            # Extract tool name and arguments from args/kwargs
            tool_name = call_args_list[0] if call_args_list else "unknown"
            arguments = call_kwargs.get("arguments")
            argument_source: Optional[str] = "kwargs" if "arguments" in call_kwargs else None

            if arguments is None and len(call_args_list) > 1:
                arguments = call_args_list[1]
                argument_source = "args"
            elif arguments is None and call_args_list:
                # Some tools only pass arguments positionally as the first arg
                arguments = call_args_list[0]
                argument_source = "args0"

            normalized_arguments = self._normalize_tool_arguments(arguments)

            if normalized_arguments is not arguments:
                if argument_source == "kwargs":
                    call_kwargs["arguments"] = normalized_arguments
                elif argument_source == "args":
                    call_args_list[1] = normalized_arguments
                elif argument_source == "args0":
                    call_args_list[0] = normalized_arguments

            # Log clean progress indicator for tool invocation
            workspace = normalized_arguments.get("workspace", "unknown") if isinstance(normalized_arguments, dict) else "unknown"
            workspace_name = Path(workspace).name if workspace != "unknown" else "workspace"
            logger.info(f"🔧 Maven MCP: {tool_name} → {workspace_name}")

            result = await original_call_tool(*call_args_list, **call_kwargs)

            logger.info(f"✓ Maven MCP: {tool_name} completed")
            return result

        self.mcp_tool.call_tool = types.MethodType(call_tool_wrapper, self.mcp_tool)

    def _normalize_tool_arguments(self, arguments: Any) -> Any:
        """Normalize workspace paths in tool arguments."""
        if not isinstance(arguments, dict) or "workspace" not in arguments:
            return arguments

        workspace = arguments.get("workspace")
        if not isinstance(workspace, str) or not workspace.strip():
            return arguments

        normalized_workspace = self._resolve_workspace_path(workspace)
        if normalized_workspace == workspace:
            return arguments

        normalized_arguments: Dict[str, Any] = dict(arguments)
        normalized_arguments["workspace"] = normalized_workspace

        logger.debug(
            "Normalized workspace path from '%s' to '%s'", workspace, normalized_workspace
        )

        return normalized_arguments

    def _resolve_workspace_path(self, workspace: str) -> str:
        """Resolve workspace value to an absolute path under repos/ when appropriate."""
        try:
            workspace_str = workspace.strip()
        except AttributeError:
            return workspace

        if not workspace_str:
            return workspace

        candidate_path = Path(workspace_str)

        # Absolute paths are returned untouched
        if candidate_path.is_absolute():
            return str(candidate_path)

        # Already points to repos/ or explicit relative path - resolve from cwd
        if (
            workspace_str.startswith("./")
            or workspace_str.startswith("../")
            or (candidate_path.parts and candidate_path.parts[0] in {"repos", ".", ".."})
        ):
            resolved = (Path.cwd() / candidate_path).resolve()
            return str(resolved)

        # Handle org/repo notation by using final segment as service name
        if "/" in workspace_str:
            service_name = workspace_str.split("/")[-1]
        else:
            service_name = workspace_str

        resolved = (self._workspace_root / service_name).resolve()

        return str(resolved)
