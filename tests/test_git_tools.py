"""Tests for git repository management tools."""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spi_agent.config import AgentConfig
from spi_agent.git import GitRepositoryTools
from spi_agent.git.tools import SecurityError


@pytest.fixture
def git_tools():
    """Create GitRepositoryTools instance for testing."""
    config = AgentConfig()
    return GitRepositoryTools(config)


@pytest.fixture
def mock_repos_dir(tmp_path, monkeypatch):
    """Create a mock repos directory with git repositories."""
    repos_dir = tmp_path / "repos"
    repos_dir.mkdir()

    # Create test repositories
    for repo_name in ["partition", "legal", "storage"]:
        repo_path = repos_dir / repo_name
        repo_path.mkdir()
        # Create .git directory to make it look like a git repo
        (repo_path / ".git").mkdir()

    # Monkeypatch the repos_dir to use our temp directory
    monkeypatch.setattr("spi_agent.git.tools.Path", lambda x: tmp_path if x == "./repos" else Path(x))

    return repos_dir


class TestSecuritySandboxing:
    """Test security sandboxing features to prevent path traversal."""

    def test_sanitize_service_name_rejects_parent_directory(self, git_tools):
        """Test that service names with parent directory references are rejected."""
        with pytest.raises(ValueError, match="path separators"):
            git_tools._sanitize_service_name("../evil")

    def test_sanitize_service_name_rejects_absolute_paths(self, git_tools):
        """Test that absolute paths are rejected."""
        with pytest.raises(ValueError, match="path separators"):
            git_tools._sanitize_service_name("/etc/passwd")

    def test_sanitize_service_name_rejects_forward_slash(self, git_tools):
        """Test that service names with forward slashes are rejected."""
        with pytest.raises(ValueError, match="path separators"):
            git_tools._sanitize_service_name("foo/bar")

    def test_sanitize_service_name_rejects_backslash(self, git_tools):
        """Test that service names with backslashes are rejected."""
        with pytest.raises(ValueError, match="path separators"):
            git_tools._sanitize_service_name("foo\\bar")

    def test_sanitize_service_name_rejects_special_characters(self, git_tools):
        """Test that service names with special characters are rejected."""
        with pytest.raises(ValueError, match="only alphanumeric"):
            git_tools._sanitize_service_name("foo@bar")

        with pytest.raises(ValueError, match="only alphanumeric"):
            git_tools._sanitize_service_name("foo bar")

    def test_sanitize_service_name_accepts_valid_names(self, git_tools):
        """Test that valid service names are accepted."""
        assert git_tools._sanitize_service_name("partition") == "partition"
        assert git_tools._sanitize_service_name("legal-service") == "legal-service"
        assert git_tools._sanitize_service_name("storage_v2") == "storage_v2"
        assert git_tools._sanitize_service_name("Service123") == "Service123"

    def test_sanitize_service_name_empty_rejected(self, git_tools):
        """Test that empty service names are rejected."""
        with pytest.raises(ValueError, match="cannot be empty"):
            git_tools._sanitize_service_name("")

        with pytest.raises(ValueError, match="cannot be empty"):
            git_tools._sanitize_service_name("   ")

    def test_validate_repo_path_is_sandboxed_rejects_outside_paths(self, git_tools):
        """Test that paths outside repos/ are rejected."""
        # Try to access parent directory
        with pytest.raises(SecurityError, match="outside the repos/ directory"):
            git_tools._validate_repo_path_is_sandboxed(git_tools.repos_dir.parent)

        # Try to access root
        with pytest.raises(SecurityError, match="outside the repos/ directory"):
            git_tools._validate_repo_path_is_sandboxed(Path("/etc"))

    def test_validate_repo_path_is_sandboxed_accepts_inside_paths(self, git_tools):
        """Test that paths inside repos/ are accepted."""
        test_path = git_tools.repos_dir / "partition"
        assert git_tools._validate_repo_path_is_sandboxed(test_path) is True

    def test_get_repo_path_prevents_traversal(self, git_tools):
        """Test that _get_repo_path prevents path traversal via service name."""
        # These should all be rejected by _sanitize_service_name
        with pytest.raises(ValueError):
            git_tools._get_repo_path("../../../etc/passwd")

        with pytest.raises(ValueError):
            git_tools._get_repo_path("../../spi-agent")


class TestListLocalRepositories:
    """Test list_local_repositories tool."""

    @patch("spi_agent.git.tools.subprocess.run")
    def test_list_repositories_success(self, mock_run, git_tools, tmp_path, monkeypatch):
        """Test listing repositories successfully."""
        # Setup
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()

        # Create test repos
        for name in ["partition", "legal"]:
            repo = repos_dir / name
            repo.mkdir()
            (repo / ".git").mkdir()

        # Patch repos_dir
        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Mock git commands
        def mock_subprocess(cmd, **kwargs):
            mock_result = MagicMock()
            if "branch" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = "main\n"
                mock_result.stderr = ""
            elif "status" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = ""
                mock_result.stderr = ""
            return mock_result

        mock_run.side_effect = mock_subprocess

        # Execute
        result = git_tools.list_local_repositories()

        # Verify
        assert "Found 2 local repository(ies)" in result
        assert "partition" in result
        assert "legal" in result
        assert "main" in result
        assert "clean" in result

    def test_list_repositories_no_repos_dir(self, git_tools, tmp_path, monkeypatch):
        """Test listing when repos/ directory doesn't exist."""
        # Patch to non-existent directory
        monkeypatch.setattr(git_tools, "repos_dir", tmp_path / "nonexistent")

        result = git_tools.list_local_repositories()

        assert "No repositories found" in result
        assert "does not exist" in result

    def test_list_repositories_empty_dir(self, git_tools, tmp_path, monkeypatch):
        """Test listing when repos/ is empty."""
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        result = git_tools.list_local_repositories()

        assert "No repositories found" in result

    @patch("spi_agent.git.tools.subprocess.run")
    def test_list_repositories_invalid_git_repo(self, mock_run, git_tools, tmp_path, monkeypatch):
        """Test listing when directory exists but is not a git repo."""
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()

        # Create directory without .git
        invalid_repo = repos_dir / "not-a-repo"
        invalid_repo.mkdir()

        # Create valid repo
        valid_repo = repos_dir / "partition"
        valid_repo.mkdir()
        (valid_repo / ".git").mkdir()

        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Mock git commands for valid repo
        mock_run.return_value = MagicMock(returncode=0, stdout="main\n", stderr="")

        result = git_tools.list_local_repositories()

        # Should only list the valid repo
        assert "partition" in result
        assert "not-a-repo" not in result


class TestGetRepositoryStatus:
    """Test get_repository_status tool."""

    @patch("spi_agent.git.tools.subprocess.run")
    def test_get_status_clean_repo(self, mock_run, git_tools, tmp_path, monkeypatch):
        """Test getting status of a clean repository."""
        # Setup
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        partition = repos_dir / "partition"
        partition.mkdir()
        (partition / ".git").mkdir()

        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Mock _validate_repository to always return True
        monkeypatch.setattr(git_tools, "_validate_repository", lambda path: (True, ""))

        # Mock git commands
        def mock_subprocess(cmd, **kwargs):
            mock_result = MagicMock()
            if "branch" in cmd and "--show-current" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = "main\n"
            elif "rev-parse" in cmd and "--abbrev-ref" in cmd:
                # Upstream tracking branch
                mock_result.returncode = 0
                mock_result.stdout = "origin/main\n"
            elif "rev-list" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = "0\t0\n"
            elif "status" in cmd and "--porcelain" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = ""
            else:
                mock_result.returncode = 0
                mock_result.stdout = ""
            mock_result.stderr = ""
            return mock_result

        mock_run.side_effect = mock_subprocess

        # Execute
        result = git_tools.get_repository_status("partition")

        # Verify
        assert "Git status for partition" in result
        assert "Branch: main" in result
        assert "Tracking: origin/main" in result
        assert "Working tree clean" in result

    @patch("spi_agent.git.tools.subprocess.run")
    def test_get_status_dirty_repo(self, mock_run, git_tools, tmp_path, monkeypatch):
        """Test getting status with uncommitted changes."""
        # Setup
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        partition = repos_dir / "partition"
        partition.mkdir()
        (partition / ".git").mkdir()

        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Mock _validate_repository to always return True
        monkeypatch.setattr(git_tools, "_validate_repository", lambda path: (True, ""))

        # Mock git commands
        def mock_subprocess(cmd, **kwargs):
            mock_result = MagicMock()
            if "branch" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = "main\n"
            elif "status" in cmd and "--porcelain" in cmd:
                mock_result.returncode = 0
                # Porcelain format: " M" means unstaged, "??" means untracked
                mock_result.stdout = " M file1.txt\n?? file2.txt\n"
            else:
                mock_result.returncode = 0
                mock_result.stdout = ""
            mock_result.stderr = ""
            return mock_result

        mock_run.side_effect = mock_subprocess

        # Execute
        result = git_tools.get_repository_status("partition")

        # Verify
        assert "Unstaged changes" in result or "Untracked files" in result

    def test_get_status_invalid_service_name(self, git_tools):
        """Test getting status with invalid service name."""
        result = git_tools.get_repository_status("../etc")

        assert "Error" in result
        assert "path separators" in result

    def test_get_status_nonexistent_repo(self, git_tools, tmp_path, monkeypatch):
        """Test getting status of non-existent repository."""
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        result = git_tools.get_repository_status("nonexistent")

        assert "Error" in result
        assert "does not exist" in result


class TestResetRepository:
    """Test reset_repository tool."""

    @patch("spi_agent.git.tools.subprocess.run")
    def test_reset_repository_with_files(self, mock_run, git_tools, tmp_path, monkeypatch):
        """Test resetting repository with untracked files."""
        # Setup
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        partition = repos_dir / "partition"
        partition.mkdir()
        (partition / ".git").mkdir()

        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Mock git commands
        def mock_subprocess(cmd, **kwargs):
            mock_result = MagicMock()
            if "--dry-run" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = "Would remove file1.txt\nWould remove file2.txt\n"
            elif "clean" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = "Removing file1.txt\nRemoving file2.txt\n"
            mock_result.stderr = ""
            return mock_result

        mock_run.side_effect = mock_subprocess

        # Execute
        result = git_tools.reset_repository("partition")

        # Verify
        assert "Resetting repository: partition" in result
        assert "file1.txt" in result
        assert "file2.txt" in result
        assert "Successfully cleaned" in result

    @patch("spi_agent.git.tools.subprocess.run")
    def test_reset_repository_already_clean(self, mock_run, git_tools, tmp_path, monkeypatch):
        """Test resetting repository that is already clean."""
        # Setup
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        partition = repos_dir / "partition"
        partition.mkdir()
        (partition / ".git").mkdir()

        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Mock git clean --dry-run returning nothing
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # Execute
        result = git_tools.reset_repository("partition")

        # Verify
        assert "already clean" in result

    def test_reset_repository_path_traversal_attempt(self, git_tools):
        """Test that reset rejects path traversal attempts."""
        result = git_tools.reset_repository("../../spi-agent")

        assert "Error" in result
        assert "path separators" in result


class TestFetchRepository:
    """Test fetch_repository tool."""

    @patch("spi_agent.git.tools.subprocess.run")
    def test_fetch_repository_success(self, mock_run, git_tools, tmp_path, monkeypatch):
        """Test fetching repository successfully."""
        # Setup
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        partition = repos_dir / "partition"
        partition.mkdir()
        (partition / ".git").mkdir()

        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Mock git fetch
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="From https://github.com/org/repo\n   abc123..def456  main -> origin/main\n"
        )

        # Execute
        result = git_tools.fetch_repository("partition")

        # Verify
        assert "Fetching updates for partition" in result
        assert "Fetch completed" in result

    @patch("spi_agent.git.tools.subprocess.run")
    def test_fetch_repository_network_error(self, mock_run, git_tools, tmp_path, monkeypatch):
        """Test fetch with network error."""
        # Setup
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        partition = repos_dir / "partition"
        partition.mkdir()
        (partition / ".git").mkdir()

        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Mock network error
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="fatal: unable to access 'https://github.com/': Could not resolve host\n"
        )

        # Execute
        result = git_tools.fetch_repository("partition")

        # Verify
        assert "Network error" in result

    @patch("spi_agent.git.tools.subprocess.run")
    def test_fetch_repository_with_prune(self, mock_run, git_tools, tmp_path, monkeypatch):
        """Test fetch with prune option."""
        # Setup
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        partition = repos_dir / "partition"
        partition.mkdir()
        (partition / ".git").mkdir()

        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # Execute with prune
        result = git_tools.fetch_repository("partition", prune=True)

        # Verify --prune was in the command
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "--prune" in call_args


class TestPullRepository:
    """Test pull_repository tool."""

    @patch("spi_agent.git.tools.subprocess.run")
    def test_pull_repository_success(self, mock_run, git_tools, tmp_path, monkeypatch):
        """Test pulling repository successfully."""
        # Setup
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        partition = repos_dir / "partition"
        partition.mkdir()
        (partition / ".git").mkdir()

        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Mock git commands
        def mock_subprocess(cmd, **kwargs):
            mock_result = MagicMock()
            if "branch" in cmd and "--show-current" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = "main\n"
            elif "pull" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = "Updating abc123..def456\nFast-forward\n 1 file changed\n"
            mock_result.stderr = ""
            return mock_result

        mock_run.side_effect = mock_subprocess

        # Execute
        result = git_tools.pull_repository("partition")

        # Verify
        assert "Pulling partition" in result
        assert "Fast-forward" in result

    @patch("spi_agent.git.tools.subprocess.run")
    def test_pull_repository_already_up_to_date(self, mock_run, git_tools, tmp_path, monkeypatch):
        """Test pull when already up to date."""
        # Setup
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        partition = repos_dir / "partition"
        partition.mkdir()
        (partition / ".git").mkdir()

        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Mock git commands
        def mock_subprocess(cmd, **kwargs):
            mock_result = MagicMock()
            if "branch" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = "main\n"
            elif "pull" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = "Already up to date.\n"
            mock_result.stderr = ""
            return mock_result

        mock_run.side_effect = mock_subprocess

        # Execute
        result = git_tools.pull_repository("partition")

        # Verify
        assert "Already up to date" in result

    @patch("spi_agent.git.tools.subprocess.run")
    def test_pull_repository_with_conflicts(self, mock_run, git_tools, tmp_path, monkeypatch):
        """Test pull with merge conflicts."""
        # Setup
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        partition = repos_dir / "partition"
        partition.mkdir()
        (partition / ".git").mkdir()

        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Mock git commands
        def mock_subprocess(cmd, **kwargs):
            mock_result = MagicMock()
            if "branch" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = "main\n"
            elif "pull" in cmd:
                mock_result.returncode = 1
                mock_result.stdout = "CONFLICT (content): Merge conflict in file.txt\n"
            mock_result.stderr = ""
            return mock_result

        mock_run.side_effect = mock_subprocess

        # Execute
        result = git_tools.pull_repository("partition")

        # Verify
        assert "Merge conflicts detected" in result


class TestPullAllRepositories:
    """Test pull_all_repositories tool."""

    @patch("spi_agent.git.tools.subprocess.run")
    def test_pull_all_repositories_success(self, mock_run, git_tools, tmp_path, monkeypatch):
        """Test pulling all repositories successfully."""
        # Setup
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()

        for name in ["partition", "legal"]:
            repo = repos_dir / name
            repo.mkdir()
            (repo / ".git").mkdir()

        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Mock git commands
        def mock_subprocess(cmd, **kwargs):
            mock_result = MagicMock()
            if "branch" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = "main\n"
            elif "pull" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = "Already up to date.\n"
            mock_result.stderr = ""
            return mock_result

        mock_run.side_effect = mock_subprocess

        # Execute
        result = git_tools.pull_all_repositories()

        # Verify
        assert "Pulling latest changes for 2 repository(ies)" in result
        assert "partition" in result
        assert "legal" in result
        assert "Summary: 2 succeeded, 0 failed" in result

    @patch("spi_agent.git.tools.subprocess.run")
    def test_pull_all_repositories_some_fail(self, mock_run, git_tools, tmp_path, monkeypatch):
        """Test pull all when some repositories fail with meaningful error messages."""
        # Setup
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()

        for name in ["partition", "legal"]:
            repo = repos_dir / name
            repo.mkdir()
            (repo / ".git").mkdir()

        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Mock git commands - legal fails with network error, partition succeeds
        def mock_subprocess(cmd, **kwargs):
            mock_result = MagicMock()
            cwd = kwargs.get("cwd")

            if "branch" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = "main\n"
            elif "pull" in cmd:
                if "legal" in str(cwd):
                    mock_result.returncode = 1
                    mock_result.stderr = "fatal: unable to access 'https://github.com/': Could not resolve host\n"
                else:
                    mock_result.returncode = 0
                    mock_result.stdout = "Already up to date.\n"
            mock_result.stderr = mock_result.stderr if hasattr(mock_result, 'stderr') else ""
            return mock_result

        mock_run.side_effect = mock_subprocess

        # Execute
        result = git_tools.pull_all_repositories()

        # Verify summary counts
        assert "Summary: 1 succeeded, 1 failed" in result
        assert "Failed repositories:" in result

        # Verify the error message is meaningful (not just "Pulling legal...")
        assert "Network error" in result or "unable to access" in result
        # Should NOT just say "Pulling legal from origin/main..."
        assert result.count("Pulling legal") == 1  # Should appear once in processing, not in error summary


class TestCreateBranch:
    """Test create_branch tool."""

    @patch("spi_agent.git.tools.subprocess.run")
    def test_create_branch_success(self, mock_run, git_tools, tmp_path, monkeypatch):
        """Test creating a new branch successfully."""
        # Setup
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        partition = repos_dir / "partition"
        partition.mkdir()
        (partition / ".git").mkdir()

        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Mock git commands
        def mock_subprocess(cmd, **kwargs):
            mock_result = MagicMock()
            if "check-ref-format" in cmd:
                mock_result.returncode = 0
            elif "rev-parse" in cmd and "verify" in cmd:
                # Branch doesn't exist yet
                mock_result.returncode = 1
            elif "checkout" in cmd:
                mock_result.returncode = 0
                mock_result.stdout = "Switched to a new branch 'feature-test'\n"
            mock_result.stdout = getattr(mock_result, 'stdout', "")
            mock_result.stderr = ""
            return mock_result

        mock_run.side_effect = mock_subprocess

        # Execute
        result = git_tools.create_branch("partition", "feature-test")

        # Verify
        assert "Creating branch 'feature-test'" in result
        assert "Successfully created" in result

    @patch("spi_agent.git.tools.subprocess.run")
    def test_create_branch_already_exists(self, mock_run, git_tools, tmp_path, monkeypatch):
        """Test creating a branch that already exists."""
        # Setup
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        partition = repos_dir / "partition"
        partition.mkdir()
        (partition / ".git").mkdir()

        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Mock _validate_repository to always return True
        monkeypatch.setattr(git_tools, "_validate_repository", lambda path: (True, ""))

        # Mock git commands
        def mock_subprocess(cmd, **kwargs):
            mock_result = MagicMock()
            mock_result.stdout = ""
            mock_result.stderr = ""
            if "check-ref-format" in cmd:
                mock_result.returncode = 0
            elif "rev-parse" in cmd and "verify" in cmd:
                # Branch already exists
                mock_result.returncode = 0
            else:
                mock_result.returncode = 0
            return mock_result

        mock_run.side_effect = mock_subprocess

        # Execute
        result = git_tools.create_branch("partition", "existing-branch")

        # Verify
        assert "already exists" in result

    @patch("spi_agent.git.tools.subprocess.run")
    def test_create_branch_without_checkout(self, mock_run, git_tools, tmp_path, monkeypatch):
        """Test creating a branch without checking it out."""
        # Setup
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        partition = repos_dir / "partition"
        partition.mkdir()
        (partition / ".git").mkdir()

        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Mock git commands
        def mock_subprocess(cmd, **kwargs):
            mock_result = MagicMock()
            if "check-ref-format" in cmd:
                mock_result.returncode = 0
            elif "rev-parse" in cmd and "verify" in cmd:
                mock_result.returncode = 1
            elif "branch" in cmd and "checkout" not in cmd:
                mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
            return mock_result

        mock_run.side_effect = mock_subprocess

        # Execute
        result = git_tools.create_branch("partition", "feature-test", checkout=False)

        # Verify
        assert "Successfully created" in result
        assert "not checked out" in result

    def test_create_branch_invalid_name(self, git_tools, tmp_path, monkeypatch):
        """Test creating a branch with invalid name."""
        # Setup
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        partition = repos_dir / "partition"
        partition.mkdir()
        (partition / ".git").mkdir()

        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Execute with invalid branch name
        result = git_tools.create_branch("partition", "")

        # Verify
        assert "Error" in result
        assert "cannot be empty" in result


class TestGitCommandExecution:
    """Test git command execution and error handling."""

    @patch("spi_agent.git.tools.subprocess.run")
    def test_execute_git_command_timeout(self, mock_run, git_tools, tmp_path, monkeypatch):
        """Test git command with timeout."""
        # Setup
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        partition = repos_dir / "partition"
        partition.mkdir()
        (partition / ".git").mkdir()

        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Mock timeout
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["git", "status"], timeout=30)

        # Execute
        returncode, stdout, stderr = git_tools._execute_git_command(
            partition, ["git", "status"], timeout=30
        )

        # Verify
        assert returncode == 1
        assert "timed out" in stderr

    def test_execute_git_command_security_check(self, git_tools, tmp_path):
        """Test that execute_git_command validates path sandboxing."""
        # Try to execute git command outside repos/
        with pytest.raises(SecurityError):
            git_tools._execute_git_command(Path("/etc"), ["git", "status"])


class TestRepositoryValidation:
    """Test repository validation logic."""

    def test_validate_repository_not_exists(self, git_tools, tmp_path, monkeypatch):
        """Test validation of non-existent repository."""
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        nonexistent = repos_dir / "nonexistent"
        is_valid, error = git_tools._validate_repository(nonexistent)

        assert is_valid is False
        assert "does not exist" in error

    def test_validate_repository_not_a_directory(self, git_tools, tmp_path, monkeypatch):
        """Test validation of a file (not directory)."""
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Create a file
        file_path = repos_dir / "somefile.txt"
        file_path.write_text("test")

        is_valid, error = git_tools._validate_repository(file_path)

        assert is_valid is False
        assert "not a directory" in error

    def test_validate_repository_no_git_dir(self, git_tools, tmp_path, monkeypatch):
        """Test validation of directory without .git."""
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Create directory without .git
        not_git = repos_dir / "not-git"
        not_git.mkdir()

        is_valid, error = git_tools._validate_repository(not_git)

        assert is_valid is False
        assert "Not a git repository" in error

    def test_validate_repository_valid(self, git_tools, tmp_path, monkeypatch):
        """Test validation of valid git repository."""
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        monkeypatch.setattr(git_tools, "repos_dir", repos_dir)

        # Create valid git repo
        valid_repo = repos_dir / "partition"
        valid_repo.mkdir()
        (valid_repo / ".git").mkdir()

        is_valid, error = git_tools._validate_repository(valid_repo)

        assert is_valid is True
        assert error == ""


class TestToolsIntegration:
    """Integration tests for git tools."""

    def test_create_git_tools_returns_correct_count(self):
        """Test that create_git_tools returns all 12 tools."""
        from spi_agent.git import create_git_tools

        config = AgentConfig()
        tools = create_git_tools(config)

        # Should have 12 tools (7 repo management + 3 remote management + 2 upstream config)
        assert len(tools) == 12

        # Verify tool names
        tool_names = [tool.__name__ for tool in tools]
        expected_tools = [
            # Repository Management (7 tools)
            "list_local_repositories",
            "get_repository_status",
            "reset_repository",
            "fetch_repository",
            "pull_repository",
            "pull_all_repositories",
            "create_branch",
            # Remote Management (3 tools)
            "list_remotes",
            "add_remote",
            "remove_remote",
            # Upstream Configuration (2 tools)
            "configure_upstream_remote",
            "configure_all_upstream_remotes",
        ]

        for expected in expected_tools:
            assert expected in tool_names

    def test_tools_have_annotations(self):
        """Test that tools have proper type annotations."""
        from spi_agent.git import create_git_tools

        config = AgentConfig()
        tools = create_git_tools(config)

        # Check that tools have annotations (required for agent framework)
        for tool in tools:
            assert hasattr(tool, "__annotations__") or hasattr(tool.__func__, "__annotations__")


class TestRemoteManagement:
    """Test git remote management operations."""

    @patch.object(GitRepositoryTools, "_execute_git_command")
    @patch.object(GitRepositoryTools, "_validate_repository")
    def test_list_remotes_single_remote(self, mock_validate, mock_execute, git_tools):
        """Test listing remotes when repository has one remote."""
        mock_validate.return_value = (True, "")
        mock_execute.return_value = (
            0,
            "origin\thttps://github.com/org/partition.git (fetch)\n"
            "origin\thttps://github.com/org/partition.git (push)\n",
            "",
        )

        result = git_tools.list_remotes("partition")

        assert "Remotes for repository 'partition'" in result
        assert "origin:" in result
        assert "https://github.com/org/partition.git" in result

    @patch.object(GitRepositoryTools, "_execute_git_command")
    @patch.object(GitRepositoryTools, "_validate_repository")
    def test_list_remotes_multiple_remotes(self, mock_validate, mock_execute, git_tools):
        """Test listing remotes when repository has multiple remotes."""
        mock_validate.return_value = (True, "")
        mock_execute.return_value = (
            0,
            "origin\thttps://github.com/org/partition.git (fetch)\n"
            "origin\thttps://github.com/org/partition.git (push)\n"
            "upstream\thttps://gitlab.com/osdu/partition.git (fetch)\n"
            "upstream\thttps://gitlab.com/osdu/partition.git (push)\n",
            "",
        )

        result = git_tools.list_remotes("partition")

        assert "origin:" in result
        assert "upstream:" in result
        assert "github.com" in result
        assert "gitlab.com" in result

    @patch.object(GitRepositoryTools, "_execute_git_command")
    @patch.object(GitRepositoryTools, "_validate_repository")
    def test_list_remotes_no_remotes(self, mock_validate, mock_execute, git_tools):
        """Test listing remotes when repository has no remotes configured."""
        mock_validate.return_value = (True, "")
        mock_execute.return_value = (0, "", "")

        result = git_tools.list_remotes("partition")

        assert "No remotes configured" in result

    @patch.object(GitRepositoryTools, "_execute_git_command")
    @patch.object(GitRepositoryTools, "_validate_repository")
    def test_add_remote_success(self, mock_validate, mock_execute, git_tools):
        """Test successfully adding a new remote."""
        mock_validate.return_value = (True, "")
        # First call: check if remote exists (should fail)
        # Second call: add remote (should succeed)
        mock_execute.side_effect = [
            (1, "", ""),  # get-url fails (remote doesn't exist)
            (0, "", ""),  # add succeeds
        ]

        result = git_tools.add_remote(
            "partition", "upstream", "https://gitlab.com/osdu/partition.git"
        )

        assert "Successfully added remote 'upstream'" in result
        assert "gitlab.com" in result

    @patch.object(GitRepositoryTools, "_execute_git_command")
    @patch.object(GitRepositoryTools, "_validate_repository")
    def test_add_remote_already_exists(self, mock_validate, mock_execute, git_tools):
        """Test adding a remote that already exists."""
        mock_validate.return_value = (True, "")
        mock_execute.return_value = (0, "https://github.com/org/partition.git\n", "")

        result = git_tools.add_remote(
            "partition", "origin", "https://gitlab.com/osdu/partition.git"
        )

        assert "Error" in result
        assert "already exists" in result

    def test_add_remote_invalid_url(self, git_tools):
        """Test adding a remote with invalid URL."""
        with patch.object(GitRepositoryTools, "_validate_repository", return_value=(True, "")):
            result = git_tools.add_remote("partition", "upstream", "not-a-valid-url")

            assert "Error" in result
            assert "Invalid remote URL" in result

    def test_add_remote_invalid_name(self, git_tools):
        """Test adding a remote with invalid name."""
        with patch.object(GitRepositoryTools, "_validate_repository", return_value=(True, "")):
            result = git_tools.add_remote(
                "partition", "up@stream", "https://gitlab.com/osdu/partition.git"
            )

            assert "Error" in result
            assert "Invalid remote name" in result

    @patch.object(GitRepositoryTools, "_execute_git_command")
    @patch.object(GitRepositoryTools, "_validate_repository")
    def test_remove_remote_success(self, mock_validate, mock_execute, git_tools):
        """Test successfully removing a remote."""
        mock_validate.return_value = (True, "")
        mock_execute.side_effect = [
            (0, "https://gitlab.com/osdu/partition.git\n", ""),  # get-url succeeds
            (0, "", ""),  # remove succeeds
        ]

        result = git_tools.remove_remote("partition", "upstream")

        assert "Successfully removed remote 'upstream'" in result

    @patch.object(GitRepositoryTools, "_execute_git_command")
    @patch.object(GitRepositoryTools, "_validate_repository")
    def test_remove_remote_not_found(self, mock_validate, mock_execute, git_tools):
        """Test removing a remote that doesn't exist."""
        mock_validate.return_value = (True, "")
        mock_execute.return_value = (1, "", "")

        result = git_tools.remove_remote("partition", "nonexistent")

        assert "Error" in result
        assert "does not exist" in result

    @patch.object(GitRepositoryTools, "_execute_git_command")
    @patch.object(GitRepositoryTools, "_validate_repository")
    def test_remove_remote_origin_warning(self, mock_validate, mock_execute, git_tools):
        """Test removing origin remote shows warning."""
        mock_validate.return_value = (True, "")
        mock_execute.side_effect = [
            (0, "https://github.com/org/partition.git\n", ""),  # get-url succeeds
            (0, "* main origin/main\n", ""),  # branch -vv shows tracking
            (0, "", ""),  # remove succeeds
        ]

        result = git_tools.remove_remote("partition", "origin")

        assert "WARNING" in result
        assert "tracking branches" in result
        assert "Successfully removed" in result


class TestUpstreamConfiguration:
    """Test upstream remote configuration orchestration."""

    @patch("spi_agent.github.variables.RepositoryVariableTools")
    @patch.object(GitRepositoryTools, "_execute_git_command")
    @patch.object(GitRepositoryTools, "_validate_repository")
    def test_configure_upstream_remote_success(
        self, mock_validate, mock_execute, mock_var_tools_class, git_tools
    ):
        """Test successfully configuring upstream remote."""
        mock_validate.return_value = (True, "")

        # Mock variable retrieval
        mock_var_tools = MagicMock()
        mock_var_tools.get_repository_variable.return_value = (
            "UPSTREAM_REPO_URL: https://gitlab.com/osdu/partition.git"
        )
        mock_var_tools_class.return_value = mock_var_tools

        # Mock git commands
        mock_execute.side_effect = [
            (1, "", ""),  # get-url fails (remote doesn't exist)
            (0, "", ""),  # add remote succeeds
            (0, "", ""),  # fetch succeeds
        ]

        result = git_tools.configure_upstream_remote("partition")

        assert "Retrieved UPSTREAM_REPO_URL" in result
        assert "gitlab.com" in result
        assert "Successfully added remote 'upstream'" in result
        assert "Fetch successful" in result

    @patch("spi_agent.github.variables.RepositoryVariableTools")
    @patch.object(GitRepositoryTools, "_validate_repository")
    def test_configure_upstream_remote_variable_not_found(
        self, mock_validate, mock_var_tools_class, git_tools
    ):
        """Test configuring upstream when variable doesn't exist."""
        mock_validate.return_value = (True, "")

        # Mock variable retrieval failure
        mock_var_tools = MagicMock()
        mock_var_tools.get_repository_variable.return_value = (
            "Variable 'UPSTREAM_REPO_URL' not found in repository 'test-org/partition'."
        )
        mock_var_tools_class.return_value = mock_var_tools

        result = git_tools.configure_upstream_remote("partition")

        assert "Failed to retrieve UPSTREAM_REPO_URL" in result
        assert "not found" in result

    @patch("spi_agent.github.variables.RepositoryVariableTools")
    @patch.object(GitRepositoryTools, "_execute_git_command")
    @patch.object(GitRepositoryTools, "_validate_repository")
    def test_configure_upstream_remote_already_configured(
        self, mock_validate, mock_execute, mock_var_tools_class, git_tools
    ):
        """Test configuring upstream when already configured with same URL."""
        mock_validate.return_value = (True, "")

        # Mock variable retrieval
        mock_var_tools = MagicMock()
        mock_var_tools.get_repository_variable.return_value = (
            "UPSTREAM_REPO_URL: https://gitlab.com/osdu/partition.git"
        )
        mock_var_tools_class.return_value = mock_var_tools

        # Mock git commands - remote already exists with same URL
        mock_execute.side_effect = [
            (0, "https://gitlab.com/osdu/partition.git\n", ""),  # get-url succeeds
            (0, "", ""),  # fetch succeeds
        ]

        result = git_tools.configure_upstream_remote("partition")

        assert "already configured" in result
        assert "correct URL" in result

    @patch("spi_agent.github.variables.RepositoryVariableTools")
    @patch.object(GitRepositoryTools, "_execute_git_command")
    @patch.object(GitRepositoryTools, "_validate_repository")
    def test_configure_upstream_remote_url_mismatch(
        self, mock_validate, mock_execute, mock_var_tools_class, git_tools
    ):
        """Test configuring upstream when remote exists with different URL."""
        mock_validate.return_value = (True, "")

        # Mock variable retrieval
        mock_var_tools = MagicMock()
        mock_var_tools.get_repository_variable.return_value = (
            "UPSTREAM_REPO_URL: https://gitlab.com/osdu/partition.git"
        )
        mock_var_tools_class.return_value = mock_var_tools

        # Mock git commands - remote exists with different URL
        mock_execute.return_value = (
            0,
            "https://different-url.com/partition.git\n",
            "",
        )

        result = git_tools.configure_upstream_remote("partition")

        assert "WARNING" in result
        assert "different URL" in result
        assert "Manual intervention required" in result

    @patch("spi_agent.github.variables.RepositoryVariableTools")
    @patch.object(GitRepositoryTools, "_execute_git_command")
    @patch.object(GitRepositoryTools, "_validate_repository")
    def test_configure_upstream_remote_no_fetch(
        self, mock_validate, mock_execute, mock_var_tools_class, git_tools
    ):
        """Test configuring upstream without fetching."""
        mock_validate.return_value = (True, "")

        # Mock variable retrieval
        mock_var_tools = MagicMock()
        mock_var_tools.get_repository_variable.return_value = (
            "UPSTREAM_REPO_URL: https://gitlab.com/osdu/partition.git"
        )
        mock_var_tools_class.return_value = mock_var_tools

        # Mock git commands
        mock_execute.side_effect = [
            (1, "", ""),  # get-url fails (remote doesn't exist)
            (0, "", ""),  # add remote succeeds
        ]

        result = git_tools.configure_upstream_remote("partition", fetch_after_add=False)

        assert "Successfully added remote 'upstream'" in result
        assert "Fetch" not in result  # Should not fetch

    @patch("spi_agent.github.variables.RepositoryVariableTools")
    @patch.object(GitRepositoryTools, "_execute_git_command")
    @patch.object(GitRepositoryTools, "_validate_repository")
    @patch.object(Path, "iterdir")
    @patch.object(Path, "exists")
    def test_configure_all_upstream_remotes(
        self,
        mock_exists,
        mock_iterdir,
        mock_validate,
        mock_execute,
        mock_var_tools_class,
        git_tools,
    ):
        """Test batch configuration of upstream remotes."""
        mock_exists.return_value = True

        # Mock two repositories
        mock_repo1 = MagicMock()
        mock_repo1.name = "partition"
        mock_repo1.is_dir.return_value = True

        mock_repo2 = MagicMock()
        mock_repo2.name = "legal"
        mock_repo2.is_dir.return_value = True

        mock_iterdir.return_value = [mock_repo1, mock_repo2]

        mock_validate.return_value = (True, "")

        # Mock variable retrieval
        mock_var_tools = MagicMock()

        def get_var_side_effect(service, var_name):
            if service == "partition":
                return "UPSTREAM_REPO_URL: https://gitlab.com/osdu/partition.git"
            elif service == "legal":
                return "Variable 'UPSTREAM_REPO_URL' not found"

        mock_var_tools.get_repository_variable.side_effect = get_var_side_effect
        mock_var_tools_class.return_value = mock_var_tools

        # Mock git commands - partition succeeds, legal fails
        mock_execute.side_effect = [
            (1, "", ""),  # partition: get-url fails (remote doesn't exist)
            (0, "", ""),  # partition: add succeeds
            # legal will fail because variable not found
        ]

        result = git_tools.configure_all_upstream_remotes()

        assert "BATCH CONFIGURATION SUMMARY" in result
        assert "Total repositories processed" in result
        assert "Successful:" in result or "Failed:" in result
