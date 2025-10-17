"""Git repository management tools package."""

import logging
from typing import List

from spi_agent.config import AgentConfig
from spi_agent.git.tools import GitRepositoryTools

logger = logging.getLogger(__name__)


def create_git_tools(config: AgentConfig) -> List:
    """
    Create git repository tool functions for the agent.

    Args:
        config: Agent configuration

    Returns:
        List of bound tool methods for git repository operations
    """
    tools = GitRepositoryTools(config)

    return [
        tools.list_local_repositories,
        tools.get_repository_status,
        tools.reset_repository,
        tools.fetch_repository,
        tools.pull_repository,
        tools.pull_all_repositories,
        tools.create_branch,
    ]


__all__ = [
    "GitRepositoryTools",
    "create_git_tools",
]
