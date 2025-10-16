"""Compatibility detection utilities for hosted tools."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def detect_hosted_tools_support() -> bool:
    """
    Detect if the current agent_framework version supports hosted tools.

    Returns:
        bool: True if hosted tools are available, False otherwise
    """
    try:
        import agent_framework

        # Check if hosted tools are available in the module
        required_tools = [
            "HostedFileSearchTool",
            "HostedCodeInterpreterTool",
            "HostedWebSearchTool",
        ]

        available = all(hasattr(agent_framework, tool) for tool in required_tools)

        if available:
            logger.debug(
                f"Hosted tools support detected in agent_framework {getattr(agent_framework, '__version__', 'unknown')}"
            )
        else:
            logger.debug(
                "Hosted tools not available in current agent_framework version"
            )

        return available

    except ImportError as e:
        logger.warning(f"Failed to import agent_framework: {e}")
        return False
    except Exception as e:
        logger.warning(f"Unexpected error detecting hosted tools support: {e}")
        return False


def detect_available_hosted_tools() -> list[str]:
    """
    Detect which specific hosted tools are available.

    Returns:
        list[str]: List of available hosted tool names
            Possible values: 'file_search', 'code_interpreter', 'web_search', 'mcp'
    """
    available_tools = []

    try:
        import agent_framework

        # Check each hosted tool individually
        tool_mapping = {
            "file_search": "HostedFileSearchTool",
            "code_interpreter": "HostedCodeInterpreterTool",
            "web_search": "HostedWebSearchTool",
            "mcp": "HostedMCPTool",
        }

        for tool_name, class_name in tool_mapping.items():
            if hasattr(agent_framework, class_name):
                available_tools.append(tool_name)
                logger.debug(f"Detected available hosted tool: {tool_name}")

    except ImportError:
        logger.debug("agent_framework not available")
    except Exception as e:
        logger.warning(f"Error detecting available hosted tools: {e}")

    return available_tools


def is_client_compatible(client: Any) -> bool:
    """
    Check if the given client type is compatible with hosted tools.

    Hosted tools are designed to work with AzureAIAgentClient which provides
    the Azure AI Agents service integration. AzureOpenAIResponsesClient may
    have limited or no support for hosted tools.

    Args:
        client: Chat client instance to check

    Returns:
        bool: True if client is compatible with hosted tools, False otherwise
    """
    try:
        from agent_framework.azure import AzureAIAgentClient

        # Check if client is instance of AzureAIAgentClient
        is_compatible = isinstance(client, AzureAIAgentClient)

        if is_compatible:
            logger.debug(f"Client {type(client).__name__} is compatible with hosted tools")
        else:
            logger.debug(
                f"Client {type(client).__name__} may have limited hosted tools support"
            )

        return is_compatible

    except ImportError:
        logger.debug("AzureAIAgentClient not available")
        return False
    except Exception as e:
        logger.warning(f"Error checking client compatibility: {e}")
        return False


def get_client_type_name(client: Any) -> str:
    """
    Get the friendly name of the client type.

    Args:
        client: Chat client instance

    Returns:
        str: Client type name (e.g., 'AzureOpenAIResponses', 'AzureAIAgent', 'Unknown')
    """
    try:
        class_name = type(client).__name__

        # Simplify common client names
        if "AzureOpenAIResponses" in class_name:
            return "AzureOpenAIResponses"
        elif "AzureAIAgent" in class_name:
            return "AzureAIAgent"
        else:
            return class_name

    except Exception:
        return "Unknown"
