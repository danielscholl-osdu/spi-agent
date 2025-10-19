"""GitLab tools package for SPI Agent."""

from typing import List

from spi_agent.config import AgentConfig

# Will be populated with specialized tool classes
__all__ = [
    "create_gitlab_tools",
    "GitLabToolsBase",
]


def create_gitlab_tools(config: AgentConfig) -> List:
    """
    Create GitLab tools for agent integration.

    Args:
        config: Agent configuration with GitLab settings

    Returns:
        List of all GitLab tool methods (20 total)
    """
    # Import here to avoid circular dependencies
    from spi_agent.gitlab.issues import IssueTools
    from spi_agent.gitlab.merge_requests import MergeRequestTools
    from spi_agent.gitlab.pipelines import PipelineTools

    # Initialize tool classes
    issue_tools = IssueTools(config)
    mr_tools = MergeRequestTools(config)
    pipeline_tools = PipelineTools(config)

    # Return all bound methods preserving type annotations
    return [
        # Issue tools (7)
        issue_tools.list_issues,
        issue_tools.get_issue,
        issue_tools.get_issue_notes,
        issue_tools.create_issue,
        issue_tools.update_issue,
        issue_tools.add_issue_note,
        issue_tools.search_issues,
        # Merge request tools (7)
        mr_tools.list_merge_requests,
        mr_tools.get_merge_request,
        mr_tools.get_mr_notes,
        mr_tools.create_merge_request,
        mr_tools.update_merge_request,
        mr_tools.merge_merge_request,
        mr_tools.add_mr_note,
        # Pipeline tools (6)
        pipeline_tools.list_pipelines,
        pipeline_tools.get_pipeline,
        pipeline_tools.get_pipeline_jobs,
        pipeline_tools.trigger_pipeline,
        pipeline_tools.cancel_pipeline,
        pipeline_tools.retry_pipeline,
    ]
