"""Maven MCP Server integration for dependency management."""

import asyncio
import logging
import os
import shutil
import subprocess
import types
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_framework import MCPStdioTool

from spi_agent.config import AgentConfig
from spi_agent.mcp.tool_arg_normalizer import normalize_maven_tool_arguments

logger = logging.getLogger(__name__)


class QuietMCPStdioTool(MCPStdioTool):
    """MCP stdio tool that redirects server stderr to a log file.

    This prevents MCP server output (banners, startup messages, etc.) from
    interfering with Rich Live display updates while preserving logs for debugging.

    The implementation uses OS-level file descriptor manipulation (os.dup/dup2)
    to redirect stderr before the subprocess is created, ensuring the MCP server
    inherits the redirected stderr.
    """

    def __init__(self, *args, stderr_log_path: Optional[Path] = None, **kwargs):
        """Initialize quiet MCP tool.

        Args:
            *args: Positional arguments for MCPStdioTool
            stderr_log_path: Path to redirect stderr output (default: logs/maven_mcp_TIMESTAMP.log)
            **kwargs: Keyword arguments for MCPStdioTool
        """
        super().__init__(*args, **kwargs)

        # Generate timestamped log path following convention
        if stderr_log_path is None:
            logs_dir = Path("logs")
            logs_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            stderr_log_path = logs_dir / f"maven_mcp_{timestamp}.log"

        self._stderr_log_path = stderr_log_path
        self._stderr_file = None

    async def __aenter__(self):
        """Enter async context - start server with stderr redirected."""
        # Open stderr log file before starting server
        try:
            self._stderr_file = open(self._stderr_log_path, "w", buffering=1)
            self._stderr_file.write(f"Maven MCP Server Log - {datetime.now().isoformat()}\n")
            self._stderr_file.write("=" * 70 + "\n\n")
        except Exception as e:
            logger.warning(f"Could not open stderr log file: {e}")
            self._stderr_file = None

        # Redirect stderr at the file descriptor level
        # This will affect subprocess created during connect()
        import sys
        self._original_stderr_fd = None

        try:
            if self._stderr_file:
                # Save original stderr file descriptor
                self._original_stderr_fd = os.dup(sys.stderr.fileno())

                # Redirect stderr to our log file
                os.dup2(self._stderr_file.fileno(), sys.stderr.fileno())

            # Call parent __aenter__ which will start the subprocess
            # Subprocess will inherit the redirected stderr
            result = await super().__aenter__()
            return result
        finally:
            # Restore original stderr file descriptor
            if self._original_stderr_fd is not None:
                os.dup2(self._original_stderr_fd, sys.stderr.fileno())
                os.close(self._original_stderr_fd)
                self._original_stderr_fd = None

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context - cleanup stderr redirection."""
        # Call parent cleanup first
        result = await super().__aexit__(exc_type, exc_val, exc_tb)

        # Close stderr log file
        if self._stderr_file and not self._stderr_file.closed:
            self._stderr_file.write(f"\n\nServer shutdown - {datetime.now().isoformat()}\n")
            self._stderr_file.close()

        return result


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
            # Build subprocess environment
            subprocess_env = os.environ.copy()

            # Initialize QuietMCPStdioTool with stderr redirection
            # This prevents MCP server output from interfering with Rich Live display
            self.mcp_tool = QuietMCPStdioTool(
                name="maven-mcp-server",
                command=self.config.maven_mcp_command,
                args=self.config.maven_mcp_args,
                env=subprocess_env,
                # stderr_log_path defaults to logs/maven_mcp_TIMESTAMP.log
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

            # First normalize workspace paths
            normalized_arguments = self._normalize_tool_arguments(arguments)

            # Then normalize array parameters (e.g., profiles) that LLM might return as strings
            normalized_arguments = normalize_maven_tool_arguments(normalized_arguments)

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

            # Debug: Log the exact arguments being sent to MCP server
            logger.debug(f"MCP Tool Call - Name: {tool_name}")
            logger.debug(f"MCP Tool Call - Arguments: {normalized_arguments}")
            logger.debug(f"MCP Tool Call - Argument Types: {type(normalized_arguments)}")
            if isinstance(normalized_arguments, dict):
                for key, value in normalized_arguments.items():
                    logger.debug(f"  {key}: {value} (type: {type(value).__name__})")

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
