"""Tests for terminal utilities."""

import sys
from unittest.mock import Mock, patch

import pytest

from spi_agent.utils.terminal import (
    clear_screen,
    get_clear_command,
    supports_ansi_codes,
)


def test_supports_ansi_codes_tty():
    """Test ANSI support detection when terminal is a TTY."""
    with patch("sys.stdout.isatty", return_value=True), patch.dict(
        "os.environ", {"TERM": "xterm-256color"}
    ):
        assert supports_ansi_codes() is True


def test_supports_ansi_codes_no_tty():
    """Test ANSI support detection when not a TTY (redirected)."""
    with patch("sys.stdout.isatty", return_value=False):
        assert supports_ansi_codes() is False


def test_supports_ansi_codes_dumb_terminal():
    """Test ANSI support detection with dumb terminal."""
    with patch("sys.stdout.isatty", return_value=True), patch.dict(
        "os.environ", {"TERM": "dumb"}
    ):
        assert supports_ansi_codes() is False


def test_get_clear_command_darwin():
    """Test clear command detection on macOS."""
    with patch("sys.platform", "darwin"):
        assert get_clear_command() == "clear"


def test_get_clear_command_linux():
    """Test clear command detection on Linux."""
    with patch("sys.platform", "linux"):
        assert get_clear_command() == "clear"


def test_get_clear_command_windows():
    """Test clear command detection on Windows."""
    with patch("sys.platform", "win32"):
        assert get_clear_command() == "cls"


def test_get_clear_command_unknown():
    """Test clear command detection on unknown platform."""
    with patch("sys.platform", "unknown"):
        assert get_clear_command() is None


def test_clear_screen_ansi_success():
    """Test screen clearing with ANSI escape codes."""
    with patch("spi_agent.utils.terminal.supports_ansi_codes", return_value=True), patch(
        "builtins.print"
    ) as mock_print:
        result = clear_screen()
        assert result is True
        mock_print.assert_called_once_with("\033[2J\033[H", end="", flush=True)


def test_clear_screen_command_success():
    """Test screen clearing with platform command."""
    with patch(
        "spi_agent.utils.terminal.supports_ansi_codes", return_value=False
    ), patch("spi_agent.utils.terminal.get_clear_command", return_value="clear"), patch(
        "os.system", return_value=0
    ) as mock_system:
        result = clear_screen()
        assert result is True
        mock_system.assert_called_once_with("clear")


def test_clear_screen_ansi_failure_fallback():
    """Test screen clearing falls back to command when ANSI fails."""
    with patch(
        "spi_agent.utils.terminal.supports_ansi_codes", return_value=True
    ), patch("builtins.print", side_effect=Exception("ANSI failed")), patch(
        "spi_agent.utils.terminal.get_clear_command", return_value="clear"
    ), patch(
        "os.system", return_value=0
    ) as mock_system:
        result = clear_screen()
        assert result is True
        mock_system.assert_called_once_with("clear")


def test_clear_screen_all_methods_fail():
    """Test screen clearing when all methods fail."""
    with patch(
        "spi_agent.utils.terminal.supports_ansi_codes", return_value=False
    ), patch("spi_agent.utils.terminal.get_clear_command", return_value=None):
        result = clear_screen()
        assert result is False


def test_clear_screen_command_failure():
    """Test screen clearing when command returns non-zero."""
    with patch(
        "spi_agent.utils.terminal.supports_ansi_codes", return_value=False
    ), patch("spi_agent.utils.terminal.get_clear_command", return_value="clear"), patch(
        "os.system", return_value=1
    ):
        result = clear_screen()
        assert result is False


def test_clear_screen_command_exception():
    """Test screen clearing handles exceptions gracefully."""
    with patch(
        "spi_agent.utils.terminal.supports_ansi_codes", return_value=False
    ), patch("spi_agent.utils.terminal.get_clear_command", return_value="clear"), patch(
        "os.system", side_effect=Exception("Command failed")
    ):
        result = clear_screen()
        assert result is False
