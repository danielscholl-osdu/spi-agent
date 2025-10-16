"""Hosted tools management for Microsoft Agent Framework integration."""

from spi_agent.hosted_tools.compatibility import (
    detect_available_hosted_tools,
    detect_hosted_tools_support,
    is_client_compatible,
)
from spi_agent.hosted_tools.manager import HostedToolsManager

__all__ = [
    "HostedToolsManager",
    "detect_hosted_tools_support",
    "detect_available_hosted_tools",
    "is_client_compatible",
]
