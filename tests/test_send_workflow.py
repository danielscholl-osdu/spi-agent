"""Tests for send workflow functionality."""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path

from spi_agent.config import AgentConfig
from spi_agent.workflows.send_workflow import (
    extract_pr_data,
    extract_issue_data,
    build_description_with_reference,
    transform_pr_to_mr_data,
    transform_issue_data,
    ensure_upstream_configured,
    get_pr_commits,
    create_mr_branch_from_upstream,
    cherry_pick_commits,
    push_branch_to_gitlab,
    cleanup_mr_branch,
    send_pr_to_gitlab,
    send_issue_to_gitlab,
    send_multiple_items,
)


@pytest.fixture
def mock_config():
    """Create a mock AgentConfig."""
    config = Mock(spec=AgentConfig)
    config.get_repo_full_name.return_value = "test-org/partition"
    config.get_gitlab_project_path.return_value = "osdu/partition"
    config.github_token = "test-github-token"
    config.gitlab_token = "test-gitlab-token"
    return config


@pytest.fixture
def sample_pr_formatted_output():
    """Sample formatted PR output from PullRequestTools."""
    return """Pull Request #5 in test-org/partition

Title: Add new authentication feature
State: open
Author: testuser
Base: main ← Head: feature/auth
Created: 2024-01-15T10:00:00
Updated: 2024-01-16T14:30:00

Changes:
  📝 Files changed: 3
  ➕ Additions: 150 lines
  ➖ Deletions: 20 lines
  💬 Comments: 2
  💬 Review comments: 1

Merge Readiness:
  Mergeable: yes (clean)
  Draft: no

Labels: enhancement, security

Description:
This PR adds a new authentication feature using OAuth 2.0.

It includes:
- New authentication service
- Updated security configuration
- Integration tests

URL: https://github.com/test-org/partition/pull/5
"""


@pytest.fixture
def sample_issue_formatted_output():
    """Sample formatted Issue output from IssueTools."""
    return """Issue #10 in test-org/partition

Title: Fix authentication bug
State: open
Author: testuser
Created: 2024-01-15T10:00:00
Updated: 2024-01-16T14:30:00

Labels: bug, priority-high

Description:
Authentication fails when using special characters in password.

Steps to reproduce:
1. Try to login with password containing @#$
2. Login fails

URL: https://github.com/test-org/partition/issues/10
"""


class TestExtractPRData:
    """Tests for extract_pr_data function."""

    def test_extract_pr_data_success(self, mock_config, sample_pr_formatted_output):
        """Test successful PR data extraction."""
        with patch("spi_agent.workflows.send_workflow.PullRequestTools") as mock_pr_tools:
            mock_instance = Mock()
            mock_instance.get_pull_request.return_value = sample_pr_formatted_output
            mock_pr_tools.return_value = mock_instance

            result = extract_pr_data("partition", 5, mock_config)

            assert result is not None
            assert result["number"] == 5
            assert result["title"] == "Add new authentication feature"
            assert result["state"] == "open"
            assert result["author"] == "testuser"
            assert result["base_ref"] == "main"
            assert result["head_ref"] == "feature/auth"
            assert "OAuth 2.0" in result["body"]
            assert result["html_url"] == "https://github.com/test-org/partition/pull/5"
            assert "enhancement" in result["labels"]
            assert "security" in result["labels"]

    def test_extract_pr_data_not_found(self, mock_config):
        """Test PR not found scenario."""
        with patch("spi_agent.workflows.send_workflow.PullRequestTools") as mock_pr_tools:
            mock_instance = Mock()
            # Use exact error format from GitHub API
            mock_instance.get_pull_request.return_value = "Pull request #999 not found in partition"
            mock_pr_tools.return_value = mock_instance

            result = extract_pr_data("partition", 999, mock_config)

            assert result is None

    def test_extract_pr_data_exception(self, mock_config):
        """Test exception handling."""
        with patch("spi_agent.workflows.send_workflow.PullRequestTools") as mock_pr_tools:
            mock_instance = Mock()
            mock_instance.get_pull_request.side_effect = Exception("API Error")
            mock_pr_tools.return_value = mock_instance

            result = extract_pr_data("partition", 5, mock_config)

            assert result is None


class TestExtractIssueData:
    """Tests for extract_issue_data function."""

    def test_extract_issue_data_success(self, mock_config, sample_issue_formatted_output):
        """Test successful issue data extraction."""
        with patch("spi_agent.workflows.send_workflow.IssueTools") as mock_issue_tools:
            mock_instance = Mock()
            mock_instance.get_issue.return_value = sample_issue_formatted_output
            mock_issue_tools.return_value = mock_instance

            result = extract_issue_data("partition", 10, mock_config)

            assert result is not None
            assert result["number"] == 10
            assert result["title"] == "Fix authentication bug"
            assert result["state"] == "open"
            assert result["author"] == "testuser"
            assert "special characters" in result["body"]
            assert result["html_url"] == "https://github.com/test-org/partition/issues/10"
            assert "bug" in result["labels"]

    def test_extract_issue_data_not_found(self, mock_config):
        """Test issue not found scenario."""
        with patch("spi_agent.workflows.send_workflow.IssueTools") as mock_issue_tools:
            mock_instance = Mock()
            # Use exact error format from GitHub API
            mock_instance.get_issue.return_value = "Issue #999 not found in partition"
            mock_issue_tools.return_value = mock_instance

            result = extract_issue_data("partition", 999, mock_config)

            assert result is None


class TestBuildDescriptionWithReference:
    """Tests for build_description_with_reference function."""

    def test_build_description_normal(self):
        """Test building description with normal text."""
        original = "This is a test description"
        github_url = "https://github.com/test-org/partition/pull/5"

        result = build_description_with_reference(original, github_url)

        assert "This is a test description" in result
        assert "---" in result
        assert "**Original GitHub Item:**" in result
        assert github_url in result

    def test_build_description_empty(self):
        """Test building description with empty text."""
        github_url = "https://github.com/test-org/partition/pull/5"

        result = build_description_with_reference("", github_url)

        assert "(No description provided)" in result
        assert github_url in result

    def test_build_description_preserves_markdown(self):
        """Test that markdown formatting is preserved."""
        original = "# Header\n\n- List item 1\n- List item 2\n\n**Bold text**"
        github_url = "https://github.com/test-org/partition/pull/5"

        result = build_description_with_reference(original, github_url)

        assert "# Header" in result
        assert "- List item 1" in result
        assert "**Bold text**" in result


class TestTransformPRToMRData:
    """Tests for transform_pr_to_mr_data function."""

    def test_transform_pr_to_mr_data(self):
        """Test PR to MR data transformation."""
        pr_data = {
            "title": "Add authentication",
            "body": "This adds OAuth support",
            "base_ref": "main",
            "head_ref": "feature/auth",
        }
        github_url = "https://github.com/test-org/partition/pull/5"

        result = transform_pr_to_mr_data(pr_data, github_url)

        assert result["title"] == "Add authentication"
        assert "This adds OAuth support" in result["description"]
        assert github_url in result["description"]
        assert result["source_branch"] == "feature/auth"
        assert result["target_branch"] == "main"


class TestTransformIssueData:
    """Tests for transform_issue_data function."""

    def test_transform_issue_data(self):
        """Test issue data transformation."""
        issue_data = {
            "title": "Fix bug",
            "body": "Authentication fails",
        }
        github_url = "https://github.com/test-org/partition/issues/10"

        result = transform_issue_data(issue_data, github_url)

        assert result["title"] == "Fix bug"
        assert "Authentication fails" in result["description"]
        assert github_url in result["description"]


class TestEnsureUpstreamConfigured:
    """Tests for ensure_upstream_configured function."""

    def test_upstream_configured(self, mock_config):
        """Test when upstream is already configured."""
        with patch("spi_agent.workflows.send_workflow.GitRepositoryTools") as mock_git_tools:
            mock_instance = Mock()
            mock_instance._get_repo_path.return_value = Path("/repos/partition")
            mock_instance._validate_repository.return_value = (True, "")
            mock_instance._execute_git_command.return_value = (0, "git@gitlab.com:osdu/partition.git\n", "")
            mock_git_tools.return_value = mock_instance

            success, msg = ensure_upstream_configured("partition", mock_config)

            assert success is True
            assert "git@gitlab.com:osdu/partition.git" in msg

    def test_upstream_not_configured(self, mock_config):
        """Test when upstream is not configured - should auto-configure."""
        with patch("spi_agent.workflows.send_workflow.GitRepositoryTools") as mock_git_tools:
            with patch("subprocess.run") as mock_subprocess:
                mock_instance = Mock()
                mock_instance._get_repo_path.return_value = Path("/repos/partition")
                mock_instance._validate_repository.return_value = (True, "")
                # Call sequence: check if upstream exists (fails), add upstream (succeeds), fetch (succeeds)
                mock_instance._execute_git_command.side_effect = [
                    (1, "", "fatal: No such remote"),  # get-url fails
                    (0, "", ""),  # remote add succeeds
                    (0, "", ""),  # fetch succeeds
                ]
                mock_git_tools.return_value = mock_instance

                # Mock subprocess to return GitLab URL
                mock_subprocess.return_value.returncode = 0
                mock_subprocess.return_value.stdout = "https://community.opengroup.org/osdu/platform/system/partition.git\n"

                mock_config.get_repo_full_name.return_value = "test-org/partition"
                mock_config.gitlab_url = "https://gitlab.com"

                success, msg = ensure_upstream_configured("partition", mock_config)

                assert success is True
                assert "configured" in msg.lower()


class TestGetPRCommits:
    """Tests for get_pr_commits function."""

    def test_get_pr_commits_success(self, mock_config):
        """Test successful retrieval of PR commits."""
        with patch("spi_agent.workflows.send_workflow.PullRequestTools") as mock_pr_tools:
            # Mock PR object with commits
            mock_commit1 = Mock()
            mock_commit1.sha = "abc123"
            mock_commit2 = Mock()
            mock_commit2.sha = "def456"

            mock_pr = Mock()
            mock_pr.get_commits.return_value = [mock_commit1, mock_commit2]

            mock_repo = Mock()
            mock_repo.get_pull.return_value = mock_pr

            mock_github = Mock()
            mock_github.get_repo.return_value = mock_repo

            mock_instance = Mock()
            mock_instance.github = mock_github
            mock_pr_tools.return_value = mock_instance

            result = get_pr_commits("partition", 5, mock_config)

            assert result == ["abc123", "def456"]


class TestCreateMRBranchFromUpstream:
    """Tests for create_mr_branch_from_upstream function."""

    def test_create_mr_branch_success(self, mock_config):
        """Test successful MR branch creation."""
        with patch("spi_agent.workflows.send_workflow.GitRepositoryTools") as mock_git_tools:
            mock_instance = Mock()
            mock_instance._get_repo_path.return_value = Path("/repos/partition")
            # Mock successful git commands
            mock_instance._execute_git_command.side_effect = [
                (0, "Fetched", ""),  # git fetch upstream
                (0, "Switched to branch", ""),  # git checkout -b
            ]
            mock_git_tools.return_value = mock_instance

            success, branch = create_mr_branch_from_upstream("partition", 5, "main", mock_config)

            assert success is True
            assert branch == "gitlab-mr-5"

    def test_create_mr_branch_already_exists(self, mock_config):
        """Test when branch already exists."""
        with patch("spi_agent.workflows.send_workflow.GitRepositoryTools") as mock_git_tools:
            mock_instance = Mock()
            mock_instance._get_repo_path.return_value = Path("/repos/partition")
            # Mock git commands
            mock_instance._execute_git_command.side_effect = [
                (0, "Fetched", ""),  # git fetch upstream
                (1, "", "fatal: A branch named 'gitlab-mr-5' already exists"),  # git checkout -b (fails)
                (0, "", ""),  # git checkout main
                (0, "", ""),  # git branch -D
                (0, "Switched to branch", ""),  # git checkout -b (retry)
            ]
            mock_git_tools.return_value = mock_instance

            success, branch = create_mr_branch_from_upstream("partition", 5, "main", mock_config)

            assert success is True
            assert branch == "gitlab-mr-5"

    def test_create_mr_branch_with_mapping_and_retry(self, mock_config):
        """Test branch creation with main→master mapping when branch already exists.

        This tests the bug fix where the retry logic was using base_branch instead
        of upstream_branch, causing it to try upstream/main instead of upstream/master.
        """
        with patch("spi_agent.workflows.send_workflow.GitRepositoryTools") as mock_git_tools:
            mock_instance = Mock()
            mock_instance._get_repo_path.return_value = Path("/repos/partition")
            # Mock git commands
            mock_instance._execute_git_command.side_effect = [
                (1, "", "fatal: Needed a single revision"),  # git rev-parse upstream/main (fails)
                (0, "5785ed43ce7aa38a8de760ce82afde8ac01ddda3", ""),  # git rev-parse upstream/master (succeeds)
                (0, "5785ed43ce7aa38a8de760ce82afde8ac01ddda3", ""),  # verify mapped branch exists
                (1, "", "fatal: A branch named 'gitlab-mr-5' already exists"),  # git checkout -b (fails - branch exists)
                (0, "", ""),  # git checkout main
                (0, "", ""),  # git branch -D gitlab-mr-5
                (0, "Switched to branch", ""),  # git checkout -b gitlab-mr-5 upstream/master (retry with MAPPED branch)
            ]
            mock_git_tools.return_value = mock_instance

            success, branch = create_mr_branch_from_upstream("partition", 5, "main", mock_config)

            assert success is True
            assert branch == "gitlab-mr-5"

            # Verify the retry used upstream/master (mapped), not upstream/main
            calls = mock_instance._execute_git_command.call_args_list
            # The last call should be the retry with the mapped branch
            last_call_args = calls[-1][0][1]  # Get the git command list
            assert last_call_args == ["git", "checkout", "-b", "gitlab-mr-5", "upstream/master"]


class TestCherryPickCommits:
    """Tests for cherry_pick_commits function."""

    def test_cherry_pick_success(self, mock_config):
        """Test successful cherry-pick."""
        with patch("spi_agent.workflows.send_workflow.GitRepositoryTools") as mock_git_tools:
            mock_instance = Mock()
            mock_instance._get_repo_path.return_value = Path("/repos/partition")
            # Mock successful cherry-picks (including git fetch origin first)
            mock_instance._execute_git_command.side_effect = [
                (0, "Fetched", ""),  # git fetch origin
                (0, "Cherry-picked", ""),  # git cherry-pick abc123
                (0, "Cherry-picked", ""),  # git cherry-pick def456
            ]
            mock_git_tools.return_value = mock_instance

            success, msg = cherry_pick_commits("partition", ["abc123", "def456"], mock_config)

            assert success is True
            assert "successfully" in msg.lower()

    def test_cherry_pick_conflict(self, mock_config):
        """Test cherry-pick with conflicts."""
        with patch("spi_agent.workflows.send_workflow.GitRepositoryTools") as mock_git_tools:
            mock_instance = Mock()
            mock_instance._get_repo_path.return_value = Path("/repos/partition")
            # Mock cherry-pick conflict (including git fetch origin first)
            mock_instance._execute_git_command.side_effect = [
                (0, "Fetched", ""),  # git fetch origin
                (1, "", "error: could not apply abc123... CONFLICT"),  # git cherry-pick abc123
                (0, "", ""),  # git cherry-pick --abort
            ]
            mock_git_tools.return_value = mock_instance

            success, msg = cherry_pick_commits("partition", ["abc123"], mock_config)

            assert success is False
            assert "conflict" in msg.lower()
            assert "resolve conflicts manually" in msg.lower()


class TestPushBranchToGitLab:
    """Tests for push_branch_to_gitlab function."""

    def test_push_success(self, mock_config):
        """Test successful push."""
        with patch("spi_agent.workflows.send_workflow.GitRepositoryTools") as mock_git_tools:
            mock_instance = Mock()
            mock_instance._get_repo_path.return_value = Path("/repos/partition")
            mock_instance._execute_git_command.return_value = (0, "Pushed", "")
            mock_git_tools.return_value = mock_instance

            success, msg = push_branch_to_gitlab("partition", "gitlab-mr-5", mock_config)

            assert success is True
            assert "successfully" in msg.lower()

    def test_push_authentication_error(self, mock_config):
        """Test push with authentication error."""
        with patch("spi_agent.workflows.send_workflow.GitRepositoryTools") as mock_git_tools:
            mock_instance = Mock()
            mock_instance._get_repo_path.return_value = Path("/repos/partition")
            mock_instance._execute_git_command.return_value = (1, "", "fatal: Authentication failed")
            mock_git_tools.return_value = mock_instance

            success, msg = push_branch_to_gitlab("partition", "gitlab-mr-5", mock_config)

            assert success is False
            assert "authentication" in msg.lower()
            assert "SSH key" in msg or "token" in msg


class TestSendPRToGitLab:
    """Tests for send_pr_to_gitlab function."""

    @patch("spi_agent.workflows.send_workflow.cleanup_mr_branch")
    @patch("spi_agent.workflows.send_workflow.MergeRequestTools")
    @patch("spi_agent.workflows.send_workflow.push_branch_to_gitlab")
    @patch("spi_agent.workflows.send_workflow.cherry_pick_commits")
    @patch("spi_agent.workflows.send_workflow.create_mr_branch_from_upstream")
    @patch("spi_agent.workflows.send_workflow.get_pr_commits")
    @patch("spi_agent.workflows.send_workflow.ensure_upstream_configured")
    @patch("spi_agent.workflows.send_workflow.extract_pr_data")
    def test_send_pr_to_gitlab_success(
        self,
        mock_extract,
        mock_ensure_upstream,
        mock_get_commits,
        mock_create_branch,
        mock_cherry_pick,
        mock_push,
        mock_mr_tools,
        mock_cleanup,
        mock_config,
    ):
        """Test successful PR to GitLab workflow."""
        # Setup mocks
        mock_extract.return_value = {
            "number": 5,
            "title": "Test PR",
            "body": "Test description",
            "base_ref": "main",
            "head_ref": "feature/test",
            "html_url": "https://github.com/test-org/partition/pull/5",
        }
        mock_ensure_upstream.return_value = (True, "Configured")
        mock_get_commits.return_value = ["abc123", "def456"]
        mock_create_branch.return_value = (True, "gitlab-mr-5")
        mock_cherry_pick.return_value = (True, "Success")
        mock_push.return_value = (True, "Success")

        mock_mr_instance = Mock()
        mock_mr_instance.create_merge_request.return_value = "Created merge request !42: Test PR\nURL: https://gitlab.com/osdu/partition/-/merge_requests/42"
        mock_mr_tools.return_value = mock_mr_instance

        result = send_pr_to_gitlab("partition", 5, mock_config)

        assert "✓" in result
        assert "PR #5" in result
        assert "https://github.com/test-org/partition/pull/5" in result
        assert "https://gitlab.com/osdu/partition/-/merge_requests/42" in result
        mock_cleanup.assert_called_once_with("partition", "gitlab-mr-5", mock_config)

    @patch("spi_agent.workflows.send_workflow.extract_pr_data")
    def test_send_pr_to_gitlab_pr_not_found(self, mock_extract, mock_config):
        """Test when PR is not found."""
        mock_extract.return_value = None

        result = send_pr_to_gitlab("partition", 999, mock_config)

        assert "Error" in result
        assert "not found" in result


class TestSendIssueToGitLab:
    """Tests for send_issue_to_gitlab function."""

    @patch("spi_agent.workflows.send_workflow.GitLabIssueTools")
    @patch("spi_agent.workflows.send_workflow.extract_issue_data")
    def test_send_issue_to_gitlab_success(self, mock_extract, mock_issue_tools, mock_config):
        """Test successful issue to GitLab workflow."""
        # Setup mocks
        mock_extract.return_value = {
            "number": 10,
            "title": "Test Issue",
            "body": "Test description",
            "html_url": "https://github.com/test-org/partition/issues/10",
        }

        mock_issue_instance = Mock()
        mock_issue_instance.create_issue.return_value = "Created issue #25: Test Issue\nURL: https://gitlab.com/osdu/partition/-/issues/25"
        mock_issue_tools.return_value = mock_issue_instance

        result = send_issue_to_gitlab("partition", 10, mock_config)

        assert "✓" in result
        assert "Issue #10" in result
        assert "https://github.com/test-org/partition/issues/10" in result
        assert "https://gitlab.com/osdu/partition/-/issues/25" in result

    @patch("spi_agent.workflows.send_workflow.extract_issue_data")
    def test_send_issue_to_gitlab_issue_not_found(self, mock_extract, mock_config):
        """Test when issue is not found."""
        mock_extract.return_value = None

        result = send_issue_to_gitlab("partition", 999, mock_config)

        assert "Error" in result
        assert "not found" in result


class TestSendMultipleItems:
    """Tests for send_multiple_items function."""

    @patch("spi_agent.workflows.send_workflow.send_issue_to_gitlab")
    @patch("spi_agent.workflows.send_workflow.send_pr_to_gitlab")
    def test_send_multiple_items_all_success(self, mock_send_pr, mock_send_issue, mock_config):
        """Test sending multiple items with all successes."""
        mock_send_pr.return_value = "✓ Sent PR #5"
        mock_send_issue.return_value = "✓ Sent Issue #10"

        items = [("pr", 5), ("issue", 10)]
        result = send_multiple_items("partition", items, mock_config)

        assert "2 succeeded, 0 failed" in result
        assert "PR #5" in result
        assert "Issue #10" in result

    @patch("spi_agent.workflows.send_workflow.send_issue_to_gitlab")
    @patch("spi_agent.workflows.send_workflow.send_pr_to_gitlab")
    def test_send_multiple_items_partial_failure(self, mock_send_pr, mock_send_issue, mock_config):
        """Test sending multiple items with partial failure."""
        mock_send_pr.return_value = "✓ Sent PR #5"
        mock_send_issue.return_value = "Error: Issue #999 not found"

        items = [("pr", 5), ("issue", 999)]
        result = send_multiple_items("partition", items, mock_config)

        assert "1 succeeded, 1 failed" in result
        assert "PR #5" in result
        assert "Issue #999" in result
