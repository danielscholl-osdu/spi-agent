"""Unit tests for GitLab tools."""

from unittest.mock import Mock

import pytest
from gitlab.exceptions import GitlabError

from spi_agent.gitlab.issues import IssueTools
from spi_agent.gitlab.merge_requests import MergeRequestTools
from spi_agent.gitlab.pipelines import PipelineTools


class TestGitLabIssueTools:
    """Test GitLab issue management tools."""

    def test_list_issues_success(self, gitlab_config, mock_gitlab, mock_gitlab_issue):
        """Test listing issues successfully."""
        tools = IssueTools(gitlab_config)
        result = tools.list_issues("test-project")

        assert "#42" in result
        assert "Test GitLab Issue" in result
        assert "opened" in result

    def test_list_issues_empty(self, gitlab_config, mock_gitlab):
        """Test listing issues when none found."""
        # Configure empty list
        mock_gitlab.projects.get.return_value.issues.list.return_value = []

        tools = IssueTools(gitlab_config)
        result = tools.list_issues("test-project")

        assert "No opened issues found" in result

    def test_get_issue_success(self, gitlab_config, mock_gitlab, mock_gitlab_issue):
        """Test getting issue details."""
        tools = IssueTools(gitlab_config)
        result = tools.get_issue("test-project", 42)

        assert "Issue #42" in result
        assert "Test GitLab Issue" in result
        assert "issueauthor" in result

    def test_get_issue_not_found(self, gitlab_config, mock_gitlab):
        """Test getting non-existent issue."""
        mock_gitlab.projects.get.return_value.issues.get.side_effect = GitlabError("404 Not Found")

        tools = IssueTools(gitlab_config)
        result = tools.get_issue("test-project", 999)

        assert "not found" in result

    def test_get_issue_notes(self, gitlab_config, mock_gitlab, mock_gitlab_issue, mock_gitlab_note):
        """Test getting issue notes."""
        mock_gitlab_issue.notes = Mock()
        mock_gitlab_issue.notes.list = Mock(return_value=[mock_gitlab_note])

        tools = IssueTools(gitlab_config)
        result = tools.get_issue_notes("test-project", 42)

        assert "noteauthor" in result
        assert "This is a test note" in result

    def test_create_issue_success(self, gitlab_config, mock_gitlab, mock_gitlab_issue):
        """Test creating an issue."""
        tools = IssueTools(gitlab_config)
        result = tools.create_issue("test-project", "New Issue", description="Test description")

        assert "Created issue #42" in result
        assert "Test GitLab Issue" in result  # Mock returns configured title

    def test_update_issue_success(self, gitlab_config, mock_gitlab, mock_gitlab_issue):
        """Test updating an issue."""
        tools = IssueTools(gitlab_config)
        result = tools.update_issue("test-project", 42, title="Updated Title")

        assert "Updated issue #42" in result

    def test_add_issue_note_success(self, gitlab_config, mock_gitlab, mock_gitlab_issue, mock_gitlab_note):
        """Test adding a note to an issue."""
        mock_gitlab_issue.notes = Mock()
        mock_gitlab_issue.notes.create = Mock(return_value=mock_gitlab_note)

        tools = IssueTools(gitlab_config)
        result = tools.add_issue_note("test-project", 42, "Test comment")

        assert "Added note to issue #42" in result

    def test_search_issues_success(self, gitlab_config, mock_gitlab, mock_gitlab_issue):
        """Test searching issues."""
        mock_gitlab.projects.get.return_value.issues.list.return_value = [mock_gitlab_issue]

        tools = IssueTools(gitlab_config)
        result = tools.search_issues("bug", projects="test-project")

        assert "Found" in result
        assert "Test GitLab Issue" in result


class TestGitLabMergeRequestTools:
    """Test GitLab merge request management tools."""

    def test_list_merge_requests_success(self, gitlab_config, mock_gitlab, mock_gitlab_mr):
        """Test listing merge requests successfully."""
        tools = MergeRequestTools(gitlab_config)
        result = tools.list_merge_requests("test-project")

        assert "!123" in result
        assert "Test Merge Request" in result
        assert "feature/test" in result
        assert "main" in result

    def test_list_merge_requests_empty(self, gitlab_config, mock_gitlab):
        """Test listing MRs when none found."""
        mock_gitlab.projects.get.return_value.mergerequests.list.return_value = []

        tools = MergeRequestTools(gitlab_config)
        result = tools.list_merge_requests("test-project")

        assert "No opened merge requests found" in result

    def test_get_merge_request_success(self, gitlab_config, mock_gitlab, mock_gitlab_mr):
        """Test getting MR details."""
        tools = MergeRequestTools(gitlab_config)
        result = tools.get_merge_request("test-project", 123)

        assert "Merge Request !123" in result
        assert "Test Merge Request" in result
        assert "can_be_merged" in result

    def test_get_merge_request_not_found(self, gitlab_config, mock_gitlab):
        """Test getting non-existent MR."""
        mock_gitlab.projects.get.return_value.mergerequests.get.side_effect = GitlabError("404 Not Found")

        tools = MergeRequestTools(gitlab_config)
        result = tools.get_merge_request("test-project", 999)

        assert "not found" in result

    def test_get_mr_notes(self, gitlab_config, mock_gitlab, mock_gitlab_mr, mock_gitlab_note):
        """Test getting MR notes."""
        mock_gitlab_mr.notes = Mock()
        mock_gitlab_mr.notes.list = Mock(return_value=[mock_gitlab_note])

        tools = MergeRequestTools(gitlab_config)
        result = tools.get_mr_notes("test-project", 123)

        assert "noteauthor" in result
        assert "This is a test note" in result

    def test_create_merge_request_success(self, gitlab_config, mock_gitlab, mock_gitlab_mr):
        """Test creating a merge request."""
        tools = MergeRequestTools(gitlab_config)
        result = tools.create_merge_request(
            "test-project",
            "feature/test",
            "main",
            "New MR"
        )

        assert "Created merge request !123" in result
        assert "feature/test" in result
        assert "main" in result

    def test_update_merge_request_success(self, gitlab_config, mock_gitlab, mock_gitlab_mr):
        """Test updating a merge request."""
        tools = MergeRequestTools(gitlab_config)
        result = tools.update_merge_request("test-project", 123, title="Updated MR")

        assert "Updated merge request !123" in result

    def test_merge_merge_request_success(self, gitlab_config, mock_gitlab, mock_gitlab_mr):
        """Test merging a merge request."""
        mock_gitlab_mr.merge = Mock()

        tools = MergeRequestTools(gitlab_config)
        result = tools.merge_merge_request("test-project", 123)

        assert "Successfully merged !123" in result
        mock_gitlab_mr.merge.assert_called_once()

    def test_merge_merge_request_with_conflicts(self, gitlab_config, mock_gitlab, mock_gitlab_mr):
        """Test merging MR with conflicts."""
        mock_gitlab_mr.has_conflicts = True

        tools = MergeRequestTools(gitlab_config)
        result = tools.merge_merge_request("test-project", 123)

        assert "Cannot merge" in result
        assert "conflicts" in result

    def test_add_mr_note_success(self, gitlab_config, mock_gitlab, mock_gitlab_mr, mock_gitlab_note):
        """Test adding a note to MR."""
        mock_gitlab_mr.notes = Mock()
        mock_gitlab_mr.notes.create = Mock(return_value=mock_gitlab_note)

        tools = MergeRequestTools(gitlab_config)
        result = tools.add_mr_note("test-project", 123, "Test comment")

        assert "Added note to merge request !123" in result


class TestGitLabPipelineTools:
    """Test GitLab CI/CD pipeline management tools."""

    def test_list_pipelines_success(self, gitlab_config, mock_gitlab, mock_gitlab_pipeline):
        """Test listing pipelines successfully."""
        tools = PipelineTools(gitlab_config)
        result = tools.list_pipelines("test-project")

        assert "Pipeline #987654" in result
        assert "success" in result
        assert "main" in result

    def test_list_pipelines_empty(self, gitlab_config, mock_gitlab):
        """Test listing pipelines when none found."""
        mock_gitlab.projects.get.return_value.pipelines.list.return_value = []

        tools = PipelineTools(gitlab_config)
        result = tools.list_pipelines("test-project")

        assert "No pipelines found" in result

    def test_list_pipelines_with_filters(self, gitlab_config, mock_gitlab, mock_gitlab_pipeline):
        """Test listing pipelines with status filter."""
        tools = PipelineTools(gitlab_config)
        result = tools.list_pipelines("test-project", status="failed", ref="develop")

        assert "Pipeline #987654" in result or "No pipelines found" in result

    def test_get_pipeline_success(self, gitlab_config, mock_gitlab, mock_gitlab_pipeline):
        """Test getting pipeline details."""
        tools = PipelineTools(gitlab_config)
        result = tools.get_pipeline("test-project", 987654)

        assert "Pipeline #987654" in result
        assert "success" in result
        assert "285s" in result

    def test_get_pipeline_not_found(self, gitlab_config, mock_gitlab):
        """Test getting non-existent pipeline."""
        mock_gitlab.projects.get.return_value.pipelines.get.side_effect = GitlabError("404 Not Found")

        tools = PipelineTools(gitlab_config)
        result = tools.get_pipeline("test-project", 999)

        assert "not found" in result

    def test_get_pipeline_jobs(self, gitlab_config, mock_gitlab, mock_gitlab_pipeline, mock_gitlab_job):
        """Test getting pipeline jobs."""
        mock_gitlab_pipeline.jobs = Mock()
        mock_gitlab_pipeline.jobs.list = Mock(return_value=[mock_gitlab_job])

        tools = PipelineTools(gitlab_config)
        result = tools.get_pipeline_jobs("test-project", 987654)

        assert "test-job" in result
        assert "success" in result

    def test_trigger_pipeline_success(self, gitlab_config, mock_gitlab, mock_gitlab_pipeline):
        """Test triggering a pipeline."""
        tools = PipelineTools(gitlab_config)
        result = tools.trigger_pipeline("test-project", "main")

        assert "Triggered pipeline" in result
        assert "main" in result

    def test_trigger_pipeline_with_variables(self, gitlab_config, mock_gitlab, mock_gitlab_pipeline):
        """Test triggering pipeline with variables."""
        tools = PipelineTools(gitlab_config)
        result = tools.trigger_pipeline("test-project", "main", variables="ENV=prod,DEBUG=true")

        assert "Triggered pipeline" in result

    def test_cancel_pipeline_success(self, gitlab_config, mock_gitlab, mock_gitlab_pipeline):
        """Test canceling a running pipeline."""
        mock_gitlab_pipeline.status = "running"
        mock_gitlab_pipeline.cancel = Mock()

        tools = PipelineTools(gitlab_config)
        result = tools.cancel_pipeline("test-project", 987654)

        assert "Canceled pipeline" in result
        mock_gitlab_pipeline.cancel.assert_called_once()

    def test_cancel_pipeline_not_running(self, gitlab_config, mock_gitlab, mock_gitlab_pipeline):
        """Test canceling completed pipeline."""
        mock_gitlab_pipeline.status = "success"

        tools = PipelineTools(gitlab_config)
        result = tools.cancel_pipeline("test-project", 987654)

        assert "Cannot cancel" in result
        assert "not running" in result

    def test_retry_pipeline_success(self, gitlab_config, mock_gitlab, mock_gitlab_pipeline):
        """Test retrying a failed pipeline."""
        mock_gitlab_pipeline.status = "failed"
        mock_gitlab_pipeline.retry = Mock()

        tools = PipelineTools(gitlab_config)
        result = tools.retry_pipeline("test-project", 987654)

        assert "Retrying pipeline" in result
        mock_gitlab_pipeline.retry.assert_called_once()


class TestGitLabToolsFactory:
    """Test GitLab tools factory function."""

    def test_create_gitlab_tools_returns_all_tools(self, gitlab_config, mock_gitlab):
        """Test that factory returns all 20 tools."""
        from spi_agent.gitlab import create_gitlab_tools

        tools = create_gitlab_tools(gitlab_config)

        assert len(tools) == 20

    def test_tools_are_callable(self, gitlab_config, mock_gitlab):
        """Test that all tools are callable methods."""
        from spi_agent.gitlab import create_gitlab_tools

        tools = create_gitlab_tools(gitlab_config)

        for tool in tools:
            assert callable(tool)


class TestGitLabConfig:
    """Test GitLab configuration."""

    def test_gitlab_config_from_env(self, gitlab_config):
        """Test GitLab config loaded from environment."""
        assert gitlab_config.gitlab_url == "https://gitlab.example.com"
        assert gitlab_config.gitlab_token == "test_gitlab_token"
        assert gitlab_config.gitlab_default_group == "test-group"

    def test_get_gitlab_project_path_with_group(self, gitlab_config):
        """Test project path generation with default group."""
        path = gitlab_config.get_gitlab_project_path("test-project")
        assert path == "test-group/test-project"

    def test_get_gitlab_project_path_full_path(self, gitlab_config):
        """Test project path with full path provided."""
        path = gitlab_config.get_gitlab_project_path("osdu/partition")
        assert path == "osdu/partition"

    def test_get_gitlab_project_path_no_group(self):
        """Test project path without default group."""
        from spi_agent.config import AgentConfig

        config = AgentConfig(
            organization="test-org",
            repositories=["test-repo"],
            gitlab_url="https://gitlab.example.com",
            gitlab_token="token",
            gitlab_default_group=None,
        )

        path = config.get_gitlab_project_path("test-project")
        assert path == "test-project"
