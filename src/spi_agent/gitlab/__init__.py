"""GitLab tools package for SPI Agent."""

from typing import List

from spi_agent.config import AgentConfig

# Will be populated with specialized tool classes
__all__ = [
    "create_gitlab_tools",
    "GitLabToolsBase",
]


def _prefix_tool_name(tool, prefix: str = "glab_"):
    """
    Wrap a tool method with a prefixed name for clarity.

    This makes it explicit which platform each tool belongs to and prevents
    naming conflicts with GitHub tools.

    Args:
        tool: Bound method to wrap
        prefix: Prefix to add to tool name (default: "glab_")

    Returns:
        Wrapped tool with prefixed __name__
    """
    import functools

    # Create a wrapper that preserves the original functionality
    @functools.wraps(tool)
    def wrapper(*args, **kwargs):
        return tool(*args, **kwargs)

    # Override __name__ with prefix while preserving other attributes via functools.wraps
    wrapper.__name__ = f"{prefix}{tool.__name__}"

    # Preserve __qualname__ if it exists (for better introspection)
    if hasattr(tool, '__qualname__'):
        wrapper.__qualname__ = f"{prefix}{tool.__qualname__}"

    return wrapper


def create_gitlab_tools(config: AgentConfig) -> List:
    """
    Create GitLab tools for agent integration.

    Args:
        config: Agent configuration with GitLab settings

    Returns:
        List of all GitLab tool methods (20 total) with 'glab_' prefix
        for clarity and to avoid naming conflicts with GitHub tools
    """
    # Import here to avoid circular dependencies
    from spi_agent.gitlab.issues import IssueTools
    from spi_agent.gitlab.merge_requests import MergeRequestTools
    from spi_agent.gitlab.pipelines import PipelineTools

    # Initialize tool classes
    issue_tools = IssueTools(config)
    mr_tools = MergeRequestTools(config)
    pipeline_tools = PipelineTools(config)

    # Return all bound methods with glab_ prefix for clarity
    # This makes it explicit which platform each tool belongs to
    return [
        # Issue tools (7)
        _prefix_tool_name(issue_tools.list_issues),
        _prefix_tool_name(issue_tools.get_issue),
        _prefix_tool_name(issue_tools.get_issue_notes),
        _prefix_tool_name(issue_tools.create_issue),
        _prefix_tool_name(issue_tools.update_issue),
        _prefix_tool_name(issue_tools.add_issue_note),
        _prefix_tool_name(issue_tools.search_issues),
        # Merge request tools (7)
        _prefix_tool_name(mr_tools.list_merge_requests),
        _prefix_tool_name(mr_tools.get_merge_request),
        _prefix_tool_name(mr_tools.get_mr_notes),
        _prefix_tool_name(mr_tools.create_merge_request),
        _prefix_tool_name(mr_tools.update_merge_request),
        _prefix_tool_name(mr_tools.merge_merge_request),
        _prefix_tool_name(mr_tools.add_mr_note),
        # Pipeline tools (6)
        _prefix_tool_name(pipeline_tools.list_pipelines),
        _prefix_tool_name(pipeline_tools.get_pipeline),
        _prefix_tool_name(pipeline_tools.get_pipeline_jobs),
        _prefix_tool_name(pipeline_tools.trigger_pipeline),
        _prefix_tool_name(pipeline_tools.cancel_pipeline),
        _prefix_tool_name(pipeline_tools.retry_pipeline),
    ]
