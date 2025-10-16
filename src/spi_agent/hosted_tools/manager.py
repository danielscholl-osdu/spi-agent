"""Hosted tools manager for lifecycle management and compatibility handling."""

import logging
from typing import Any, Optional

from spi_agent.config import AgentConfig
from spi_agent.hosted_tools.compatibility import (
    detect_available_hosted_tools,
    detect_hosted_tools_support,
    get_client_type_name,
    is_client_compatible,
)

logger = logging.getLogger(__name__)


class HostedToolsManager:
    """
    Manager for Microsoft Agent Framework hosted tools.

    This manager handles the lifecycle of hosted tools, including:
    - Detection of framework support and available tools
    - Validation of client compatibility
    - Graceful fallback when hosted tools unavailable
    - Tool instantiation and configuration

    Usage:
        config = AgentConfig()
        manager = HostedToolsManager(config)

        # Check availability
        if manager.is_available:
            tools = manager.tools
            # Use hosted tools
        else:
            # Fall back to custom tools
    """

    def __init__(self, config: AgentConfig, chat_client: Optional[Any] = None):
        """
        Initialize hosted tools manager.

        Args:
            config: Agent configuration with hosted tools settings
            chat_client: Optional chat client instance for compatibility checking
        """
        self.config = config
        self.chat_client = chat_client
        self._tools: list[Any] = []
        self._available = False
        self._initialized = False
        self._available_tool_types: list[str] = []

        # Perform initial validation
        self._validate_prerequisites()

    def _validate_prerequisites(self) -> None:
        """
        Validate prerequisites for hosted tools.

        Checks:
        1. Framework version supports hosted tools
        2. Client type is compatible (if client provided)
        3. Configuration enables hosted tools
        """
        # Check if hosted tools are enabled in config
        if not self.config.hosted_tools_enabled:
            logger.info("Hosted tools disabled in configuration")
            self._available = False
            return

        # Check framework support
        if not detect_hosted_tools_support():
            logger.warning(
                "Hosted tools requested but not available in current agent_framework version"
            )
            self._available = False
            return

        # Get available tool types
        self._available_tool_types = detect_available_hosted_tools()
        logger.info(f"Available hosted tools: {', '.join(self._available_tool_types)}")

        # Check client compatibility if client provided
        if self.chat_client is not None:
            client_compatible = is_client_compatible(self.chat_client)
            client_type = get_client_type_name(self.chat_client)

            if not client_compatible:
                logger.warning(
                    f"Client type '{client_type}' may have limited hosted tools support. "
                    "For full hosted tools support, consider using AzureAIAgentClient."
                )
                # Note: We don't fail here, just warn. Some hosted tools might still work.

        # If we get here, hosted tools are available
        self._available = True
        logger.info(
            f"Hosted tools available (mode: {self.config.hosted_tools_mode}, client: {get_client_type_name(self.chat_client) if self.chat_client else 'not provided'})"
        )

    def _initialize_tools(self) -> None:
        """Initialize hosted tools based on configuration."""
        if self._initialized:
            return

        if not self._available:
            logger.debug("Skipping hosted tools initialization - not available")
            self._initialized = True
            return

        try:
            from agent_framework import (
                HostedCodeInterpreterTool,
                HostedFileSearchTool,
                HostedWebSearchTool,
            )

            # Initialize hosted tools based on mode and availability
            # Note: These are marker tools that inform the service about capabilities

            # File search tool - for file operations
            # NOTE: File search requires vector store setup in Azure AI Project
            # Disabled for now to test web search and code interpreter
            # if "file_search" in self._available_tool_types:
            #     try:
            #         file_search_tool = HostedFileSearchTool(
            #             description="Search and read files in the workspace. Can list files, read file contents, and search across files."
            #         )
            #         self._tools.append(file_search_tool)
            #         logger.debug("Initialized HostedFileSearchTool")
            #     except Exception as e:
            #         logger.warning(f"Failed to initialize HostedFileSearchTool: {e}")

            # Code interpreter tool - for dynamic analysis
            if "code_interpreter" in self._available_tool_types:
                try:
                    code_interpreter_tool = HostedCodeInterpreterTool(
                        description="Execute generated code for analysis and validation. Can run Java, Python, and other code."
                    )
                    self._tools.append(code_interpreter_tool)
                    logger.debug("Initialized HostedCodeInterpreterTool")
                except Exception as e:
                    logger.warning(f"Failed to initialize HostedCodeInterpreterTool: {e}")

            # Web search tool - for external lookups
            # NOTE: Web search requires Bing connection setup in Azure AI Project
            # Disabled for now to test code interpreter
            # if "web_search" in self._available_tool_types:
            #     try:
            #         web_search_tool = HostedWebSearchTool(
            #             description="Search the web for current information, documentation, and external resources."
            #         )
            #         self._tools.append(web_search_tool)
            #         logger.debug("Initialized HostedWebSearchTool")
            #     except Exception as e:
            #         logger.warning(f"Failed to initialize HostedWebSearchTool: {e}")

            logger.info(f"Initialized {len(self._tools)} hosted tools")

        except ImportError as e:
            logger.error(f"Failed to import hosted tools: {e}")
            self._available = False
        except Exception as e:
            logger.error(f"Unexpected error initializing hosted tools: {e}")
            self._available = False
        finally:
            self._initialized = True

    @property
    def tools(self) -> list[Any]:
        """
        Get list of initialized hosted tools.

        Returns:
            list: List of hosted tool instances, or empty list if unavailable
        """
        if not self._initialized:
            self._initialize_tools()

        return self._tools

    @property
    def is_available(self) -> bool:
        """
        Check if hosted tools are available and ready to use.

        Returns:
            bool: True if hosted tools available, False otherwise
        """
        return self._available

    @property
    def available_tool_types(self) -> list[str]:
        """
        Get list of available hosted tool types.

        Returns:
            list[str]: List of tool type names (e.g., ['file_search', 'code_interpreter'])
        """
        return self._available_tool_types.copy()

    def get_status_summary(self) -> dict[str, Any]:
        """
        Get status summary for debugging and logging.

        Returns:
            dict: Status information including availability, tool count, etc.
        """
        return {
            "enabled": self.config.hosted_tools_enabled,
            "available": self._available,
            "initialized": self._initialized,
            "tool_count": len(self._tools),
            "available_types": self._available_tool_types,
            "mode": self.config.hosted_tools_mode,
            "client_type": get_client_type_name(self.chat_client) if self.chat_client else None,
            "framework_support": detect_hosted_tools_support(),
        }

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"HostedToolsManager(available={self._available}, tools={len(self._tools)}, mode={self.config.hosted_tools_mode})"
