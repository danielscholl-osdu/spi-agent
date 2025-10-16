"""File system tools package for local repository operations."""

from typing import List

from spi_agent.config import AgentConfig
from spi_agent.filesystem.tools import FileSystemTools


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


__all__ = [
    "FileSystemTools",
    "create_filesystem_tools",
]
