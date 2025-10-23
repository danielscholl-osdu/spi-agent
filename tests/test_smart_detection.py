"""Tests for smart service detection feature."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from spi_agent.cli import detect_available_services, format_auto_detection_message
from spi_agent.config import AgentConfig
from spi_agent.copilot import parse_services


class TestDetectAvailableServices:
    """Tests for detect_available_services() function."""

    @pytest.mark.asyncio
    async def test_no_repos_directory(self, tmp_path, monkeypatch):
        """Test that empty list is returned when repos directory doesn't exist."""
        # Change to temp directory where repos/ doesn't exist
        monkeypatch.chdir(tmp_path)

        config = AgentConfig()
        result = await detect_available_services(config)

        assert result == []

    @pytest.mark.asyncio
    async def test_empty_repos_directory(self, tmp_path, monkeypatch):
        """Test that empty list is returned when repos directory is empty."""
        # Create empty repos directory
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        config = AgentConfig()
        result = await detect_available_services(config)

        assert result == []

    @pytest.mark.asyncio
    async def test_repos_with_valid_services(self, tmp_path, monkeypatch):
        """Test detection of valid services that exist both locally and on GitHub."""
        # Create repos directory with services
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        (repos_dir / "partition").mkdir()
        (repos_dir / "legal").mkdir()
        monkeypatch.chdir(tmp_path)

        # Mock GitHub client to return exists=True for these services
        with patch("spi_agent.github.direct_client.GitHubDirectClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client._get_repo_info = AsyncMock(return_value={"exists": True})

            config = AgentConfig()
            result = await detect_available_services(config)

            assert set(result) == {"legal", "partition"}
            assert result == sorted(result)  # Verify sorted order

    @pytest.mark.asyncio
    async def test_repos_with_non_existent_github_services(self, tmp_path, monkeypatch):
        """Test that services not on GitHub are filtered out."""
        # Create repos directory with services
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        (repos_dir / "partition").mkdir()
        (repos_dir / "legal").mkdir()
        (repos_dir / "schema").mkdir()
        monkeypatch.chdir(tmp_path)

        # Mock GitHub client to return exists=True only for partition and legal
        with patch("spi_agent.github.direct_client.GitHubDirectClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            async def mock_get_repo_info(repo_name):
                # Only partition and legal exist on GitHub
                if "partition" in repo_name or "legal" in repo_name:
                    return {"exists": True}
                return {"exists": False}

            mock_client._get_repo_info = AsyncMock(side_effect=mock_get_repo_info)

            config = AgentConfig()
            result = await detect_available_services(config)

            assert set(result) == {"legal", "partition"}

    @pytest.mark.asyncio
    async def test_repos_with_non_service_directories(self, tmp_path, monkeypatch):
        """Test that non-service directories are ignored."""
        # Create repos directory with service and non-service directories
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        (repos_dir / "partition").mkdir()
        (repos_dir / "random_dir").mkdir()  # Not a configured service
        (repos_dir / ".git").mkdir()  # Hidden directory
        monkeypatch.chdir(tmp_path)

        # Mock GitHub client
        with patch("spi_agent.github.direct_client.GitHubDirectClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client._get_repo_info = AsyncMock(return_value={"exists": True})

            config = AgentConfig()
            result = await detect_available_services(config)

            # Only partition should be returned (random_dir is not in config.repositories)
            assert result == ["partition"]

    @pytest.mark.asyncio
    async def test_repos_with_files_not_directories(self, tmp_path, monkeypatch):
        """Test that files in repos/ are ignored."""
        # Create repos directory with a file and a directory
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        (repos_dir / "partition").mkdir()
        (repos_dir / "README.md").touch()  # File, not directory
        monkeypatch.chdir(tmp_path)

        # Mock GitHub client
        with patch("spi_agent.github.direct_client.GitHubDirectClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client._get_repo_info = AsyncMock(return_value={"exists": True})

            config = AgentConfig()
            result = await detect_available_services(config)

            assert result == ["partition"]

    @pytest.mark.asyncio
    async def test_github_api_failures(self, tmp_path, monkeypatch):
        """Test graceful handling of GitHub API failures."""
        # Create repos directory with services
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        (repos_dir / "partition").mkdir()
        (repos_dir / "legal").mkdir()
        monkeypatch.chdir(tmp_path)

        # Mock GitHub client to raise exception for legal, succeed for partition
        with patch("spi_agent.github.direct_client.GitHubDirectClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            async def mock_get_repo_info(repo_name):
                if "legal" in repo_name:
                    raise Exception("API error")
                return {"exists": True}

            mock_client._get_repo_info = AsyncMock(side_effect=mock_get_repo_info)

            config = AgentConfig()
            result = await detect_available_services(config)

            # Only partition should be returned (legal failed)
            assert result == ["partition"]

    @pytest.mark.asyncio
    async def test_permission_error_accessing_repos(self, tmp_path, monkeypatch):
        """Test graceful handling of permission errors."""
        # Create repos directory
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        # Mock Path.iterdir() to raise PermissionError
        with patch("pathlib.Path.iterdir") as mock_iterdir:
            mock_iterdir.side_effect = PermissionError("Permission denied")

            config = AgentConfig()
            result = await detect_available_services(config)

            assert result == []


class TestFormatAutoDetectionMessage:
    """Tests for format_auto_detection_message() function."""

    def test_empty_service_list(self):
        """Test message formatting with empty service list."""
        result = format_auto_detection_message([])
        assert result == "No available services found in ./repos/"

    def test_single_service(self):
        """Test message formatting with single service (singular)."""
        result = format_auto_detection_message(["partition"])
        assert result == "Auto-detected 1 service: partition"

    def test_multiple_services(self):
        """Test message formatting with multiple services (plural)."""
        result = format_auto_detection_message(["partition", "legal", "schema"])
        assert result == "Auto-detected 3 services: partition, legal, schema"

    def test_service_order_preserved(self):
        """Test that service order is preserved in message."""
        result = format_auto_detection_message(["legal", "partition"])
        assert result == "Auto-detected 2 services: legal, partition"


class TestParseServicesExtended:
    """Tests for extended parse_services() function."""

    def test_parse_services_with_none_and_available_services(self):
        """Test parsing with None arg and available_services provided."""
        result = parse_services(None, available_services=["partition"])
        assert result == ["partition"]

    def test_parse_services_with_none_and_no_available_services(self):
        """Test that ValueError is raised when both args are None."""
        with pytest.raises(ValueError, match="Either services_arg or available_services"):
            parse_services(None, available_services=None)

    def test_parse_services_all_ignores_available_services(self):
        """Test that 'all' keyword ignores available_services."""
        result = parse_services("all", available_services=["partition"])

        # Should return all services, not just partition
        from spi_agent.copilot.constants import SERVICES

        assert set(result) == set(SERVICES.keys())

    def test_parse_services_backward_compatibility(self):
        """Test backward compatibility with string arguments."""
        # Single service
        assert parse_services("partition") == ["partition"]

        # Multiple services
        assert parse_services("partition,legal") == ["partition", "legal"]

        # With whitespace
        assert parse_services("partition , legal") == ["partition", "legal"]


class TestCLIModeIntegration:
    """Integration tests for CLI mode (spi status, spi test, etc.)."""

    @pytest.mark.asyncio
    async def test_status_without_service_uses_auto_detection(self, tmp_path, monkeypatch):
        """Test that status command without --service uses auto-detection."""
        # Setup repos directory
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        (repos_dir / "partition").mkdir()
        monkeypatch.chdir(tmp_path)

        # Mock detect_available_services
        with patch("spi_agent.cli.detect_available_services") as mock_detect:
            mock_detect.return_value = ["partition"]

            # Mock copilot module
            with patch("spi_agent.cli.copilot_module") as mock_copilot:
                mock_copilot.parse_services.return_value = ["partition"]
                mock_copilot.SERVICES = {"partition": "Partition Service"}
                mock_copilot.StatusRunner.return_value.run_direct = AsyncMock(return_value=0)

                # Import and run async_main
                from spi_agent.cli import async_main

                # Set COPILOT_AVAILABLE to True
                with patch("spi_agent.cli.COPILOT_AVAILABLE", True):
                    result = await async_main(["status"])

                    # Verify auto-detection was called
                    mock_detect.assert_called_once()

                    # Verify parse_services was called with None and available_services
                    mock_copilot.parse_services.assert_called()
                    call_args = mock_copilot.parse_services.call_args
                    assert call_args[0][0] is None  # services_arg is None
                    assert call_args[1]["available_services"] == ["partition"]

    @pytest.mark.asyncio
    async def test_status_with_service_no_auto_detection(self, tmp_path, monkeypatch):
        """Test that status command with --service doesn't use auto-detection."""
        monkeypatch.chdir(tmp_path)

        # Mock detect_available_services (should not be called)
        with patch("spi_agent.cli.detect_available_services") as mock_detect:
            # Mock copilot module
            with patch("spi_agent.cli.copilot_module") as mock_copilot:
                mock_copilot.parse_services.return_value = ["partition"]
                mock_copilot.SERVICES = {"partition": "Partition Service"}
                mock_copilot.StatusRunner.return_value.run_direct = AsyncMock(return_value=0)

                # Import and run async_main
                from spi_agent.cli import async_main

                # Set COPILOT_AVAILABLE to True
                with patch("spi_agent.cli.COPILOT_AVAILABLE", True):
                    result = await async_main(["status", "--service", "partition"])

                    # Verify auto-detection was NOT called
                    mock_detect.assert_not_called()

                    # Verify parse_services was called with service string
                    mock_copilot.parse_services.assert_called()
                    call_args = mock_copilot.parse_services.call_args
                    assert call_args[0][0] == "partition"

    @pytest.mark.asyncio
    async def test_fork_requires_service(self, tmp_path, monkeypatch):
        """Test that fork command requires --service flag."""
        monkeypatch.chdir(tmp_path)

        from spi_agent.cli import async_main

        # Set COPILOT_AVAILABLE to True
        with patch("spi_agent.cli.COPILOT_AVAILABLE", True):
            # Should raise SystemExit because --service is required
            with pytest.raises(SystemExit):
                await async_main(["fork"])


class TestInteractiveModeIntegration:
    """Integration tests for interactive mode (/status, /test, etc.)."""

    @pytest.mark.asyncio
    async def test_slash_status_without_service_uses_auto_detection(self, tmp_path, monkeypatch):
        """Test that /status without service uses auto-detection."""
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        (repos_dir / "partition").mkdir()
        monkeypatch.chdir(tmp_path)

        # Mock detect_available_services
        with patch("spi_agent.cli.detect_available_services") as mock_detect:
            mock_detect.return_value = ["partition"]

            # Mock copilot module and workflows
            with patch("spi_agent.cli.copilot_module") as mock_copilot:
                mock_copilot.parse_services.return_value = ["partition"]
                mock_copilot.SERVICES = {"partition": "Partition Service"}

                with patch("spi_agent.workflows.status_workflow.run_status_workflow") as mock_workflow:
                    mock_workflow.return_value = None

                    # Mock agent
                    mock_agent = MagicMock()

                    from spi_agent.cli import handle_slash_command

                    result = await handle_slash_command("/status", mock_agent, None)

                    # Verify auto-detection was called
                    mock_detect.assert_called_once()

                    # Result should be None (no error)
                    assert result is None

    @pytest.mark.asyncio
    async def test_slash_fork_requires_service(self):
        """Test that /fork without service returns error."""
        # Mock agent
        mock_agent = MagicMock()

        from spi_agent.cli import handle_slash_command

        # Set COPILOT_AVAILABLE to True
        with patch("spi_agent.cli.COPILOT_AVAILABLE", True):
            with patch("spi_agent.cli.copilot_module"):
                result = await handle_slash_command("/fork", mock_agent, None)

                # Should return error message
                assert result is not None
                assert "Usage" in result
                assert "fork" in result.lower()


class TestEdgeCases:
    """Tests for edge cases in smart detection."""

    @pytest.mark.asyncio
    async def test_all_services_available(self, tmp_path, monkeypatch):
        """Test detection when all configured services exist locally and remotely."""
        from spi_agent.copilot.constants import SERVICES

        # Create repos directory with all services
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        for service in SERVICES.keys():
            (repos_dir / service).mkdir()
        monkeypatch.chdir(tmp_path)

        # Mock GitHub client to return exists=True for all
        with patch("spi_agent.github.direct_client.GitHubDirectClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client._get_repo_info = AsyncMock(return_value={"exists": True})

            config = AgentConfig()
            result = await detect_available_services(config)

            # Should return all services
            assert set(result) == set(SERVICES.keys())

    @pytest.mark.asyncio
    async def test_no_services_available_error_message(self, tmp_path, monkeypatch):
        """Test that helpful error is shown when no services available."""
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        # Mock detect_available_services to return empty
        with patch("spi_agent.cli.detect_available_services") as mock_detect:
            mock_detect.return_value = []

            # Mock copilot module
            with patch("spi_agent.cli.copilot_module"):
                from spi_agent.cli import async_main

                # Capture console output
                with patch("spi_agent.cli.console.print") as mock_print:
                    with patch("spi_agent.cli.COPILOT_AVAILABLE", True):
                        result = await async_main(["status"])

                        # Should return error code
                        assert result == 1

                        # Verify error message was printed
                        error_printed = False
                        for call in mock_print.call_args_list:
                            if "No available services found" in str(call):
                                error_printed = True
                                break
                        assert error_printed
