"""File system tools package for local repository operations."""

import logging
from typing import Any, List, Optional

from spi_agent.config import AgentConfig
from spi_agent.filesystem.tools import FileSystemTools

logger = logging.getLogger(__name__)


def create_filesystem_tools(config: AgentConfig) -> List:
    """
    Create file system tool functions for the agent.

    Args:
        config: Agent configuration

    Returns:
        List of bound tool methods for file system operations
    """
    tools = FileSystemTools(config)

    return [
        tools.list_files,
        tools.read_file,
        tools.search_in_files,
        tools.parse_pom_dependencies,
        tools.find_dependency_versions,
    ]


def create_hybrid_filesystem_tools(
    config: AgentConfig, hosted_tools_manager: Optional[Any] = None
) -> List:
    """
    Create hybrid file system tools combining hosted and custom tools.

    This function implements intelligent tool selection based on:
    - Hosted tools availability
    - Configuration mode (complement, replace, fallback)
    - Tool capabilities (specialized vs. general)

    Tool Selection Strategy:
    - "complement": Use both hosted and custom tools together
    - "replace": Prefer hosted tools for general operations, keep specialized custom tools
    - "fallback": Use custom tools primarily, hosted tools as backup

    Specialized tools (always included):
    - parse_pom_dependencies: OSDU-specific POM parsing
    - find_dependency_versions: Cross-repository dependency tracking

    Args:
        config: Agent configuration with hosted tools settings
        hosted_tools_manager: Optional hosted tools manager instance

    Returns:
        List of tools (mix of hosted and custom based on configuration)
    """
    custom_tools = FileSystemTools(config)
    result_tools: List[Any] = []

    # Always include specialized OSDU tools (these provide unique value)
    specialized_tools = [
        custom_tools.parse_pom_dependencies,
        custom_tools.find_dependency_versions,
    ]

    # General filesystem tools (may be replaced by hosted tools)
    general_custom_tools = [
        custom_tools.list_files,
        custom_tools.read_file,
        custom_tools.search_in_files,
    ]

    # Check if hosted tools are available
    has_hosted_tools = (
        hosted_tools_manager is not None
        and hasattr(hosted_tools_manager, "is_available")
        and hosted_tools_manager.is_available
    )

    if not has_hosted_tools:
        # No hosted tools available - use all custom tools
        logger.info("Using custom filesystem tools (hosted tools not available)")
        return general_custom_tools + specialized_tools

    # Hosted tools available - apply strategy based on mode
    mode = config.hosted_tools_mode
    hosted_tools = hosted_tools_manager.tools if hasattr(hosted_tools_manager, "tools") else []

    if mode == "replace":
        # Replace general tools with hosted, keep specialized
        if hosted_tools:
            logger.info(
                f"Using hosted tools for general operations ({len(hosted_tools)} hosted tools) + {len(specialized_tools)} specialized custom tools"
            )
            result_tools = hosted_tools + specialized_tools
        else:
            logger.warning("Replace mode requested but no hosted tools available, using custom tools")
            result_tools = general_custom_tools + specialized_tools

    elif mode == "complement":
        # Use both hosted and custom tools
        logger.info(
            f"Using hybrid tools: {len(hosted_tools)} hosted + {len(general_custom_tools)} general custom + {len(specialized_tools)} specialized custom"
        )
        result_tools = hosted_tools + general_custom_tools + specialized_tools

    elif mode == "fallback":
        # Custom tools primarily, hosted as backup
        logger.info(
            f"Using custom tools primarily with {len(hosted_tools)} hosted tools as fallback"
        )
        result_tools = general_custom_tools + specialized_tools + hosted_tools

    else:
        # Unknown mode - default to all custom tools
        logger.warning(f"Unknown hosted_tools_mode '{mode}', defaulting to custom tools only")
        result_tools = general_custom_tools + specialized_tools

    logger.debug(f"Created {len(result_tools)} total filesystem tools (mode: {mode})")
    return result_tools


__all__ = [
    "FileSystemTools",
    "create_filesystem_tools",
    "create_hybrid_filesystem_tools",
]
