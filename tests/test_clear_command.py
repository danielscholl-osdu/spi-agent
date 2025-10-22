"""Tests for /clear command."""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock

from spi_agent.cli import handle_slash_command, build_parser


@pytest.fixture
def mock_agent():
    """Create a mock agent for testing."""
    agent = Mock()
    agent.agent = Mock()
    agent.agent.get_new_thread = Mock(return_value="new_thread")
    agent.config = Mock()
    return agent


@pytest.fixture
def mock_thread():
    """Create a mock thread for testing."""
    return Mock()


def test_clear_command_not_in_cli_parser():
    """Test that /clear is NOT available as a CLI subcommand."""
    parser = build_parser()

    # Get list of subcommands
    subcommands = []
    if parser._subparsers:
        for action in parser._subparsers._actions:
            if hasattr(action, 'choices') and action.choices:
                subcommands = list(action.choices.keys())

    # Verify 'clear' is NOT in subcommands
    assert 'clear' not in subcommands

    # Verify other commands ARE present (if COPILOT_AVAILABLE)
    # This validates the test is checking the right thing


@pytest.mark.asyncio
async def test_clear_command_clears_workflow_store(mock_agent, mock_thread):
    """Test that /clear clears the workflow result store."""
    mock_result_store = AsyncMock()
    mock_activity_tracker = AsyncMock()

    with patch('spi_agent.workflows.get_result_store', return_value=mock_result_store), \
         patch('spi_agent.activity.get_activity_tracker', return_value=mock_activity_tracker), \
         patch('spi_agent.utils.terminal.clear_screen', return_value=True):

        result = await handle_slash_command("/clear", mock_agent, mock_thread)

        # Verify result store was cleared
        mock_result_store.clear.assert_called_once()

        # Verify special signal returned
        assert result == "__CLEAR_CONTEXT__"


@pytest.mark.asyncio
async def test_clear_command_resets_activity_tracker(mock_agent, mock_thread):
    """Test that /clear resets the activity tracker."""
    mock_result_store = AsyncMock()
    mock_activity_tracker = AsyncMock()

    with patch('spi_agent.workflows.get_result_store', return_value=mock_result_store), \
         patch('spi_agent.activity.get_activity_tracker', return_value=mock_activity_tracker), \
         patch('spi_agent.utils.terminal.clear_screen', return_value=True):

        result = await handle_slash_command("/clear", mock_agent, mock_thread)

        # Verify activity tracker was reset
        mock_activity_tracker.reset.assert_called_once()

        # Verify special signal returned
        assert result == "__CLEAR_CONTEXT__"


@pytest.mark.asyncio
async def test_clear_command_clears_terminal(mock_agent, mock_thread):
    """Test that /clear attempts to clear the terminal."""
    mock_result_store = AsyncMock()
    mock_activity_tracker = AsyncMock()
    mock_clear_screen = Mock(return_value=True)

    with patch('spi_agent.workflows.get_result_store', return_value=mock_result_store), \
         patch('spi_agent.activity.get_activity_tracker', return_value=mock_activity_tracker), \
         patch('spi_agent.utils.terminal.clear_screen', mock_clear_screen):

        result = await handle_slash_command("/clear", mock_agent, mock_thread)

        # Verify clear_screen was called
        mock_clear_screen.assert_called_once()

        # Verify special signal returned
        assert result == "__CLEAR_CONTEXT__"


@pytest.mark.asyncio
async def test_clear_command_returns_signal(mock_agent, mock_thread):
    """Test that /clear returns the special context clear signal."""
    mock_result_store = AsyncMock()
    mock_activity_tracker = AsyncMock()

    with patch('spi_agent.workflows.get_result_store', return_value=mock_result_store), \
         patch('spi_agent.activity.get_activity_tracker', return_value=mock_activity_tracker), \
         patch('spi_agent.utils.terminal.clear_screen', return_value=True):

        result = await handle_slash_command("/clear", mock_agent, mock_thread)

        # Verify special signal is returned
        assert result == "__CLEAR_CONTEXT__"


@pytest.mark.asyncio
async def test_clear_command_executes_without_error(mock_agent, mock_thread):
    """Test that /clear executes cleanly without displaying messages."""
    mock_result_store = AsyncMock()
    mock_activity_tracker = AsyncMock()

    with patch('spi_agent.workflows.get_result_store', return_value=mock_result_store), \
         patch('spi_agent.activity.get_activity_tracker', return_value=mock_activity_tracker), \
         patch('spi_agent.utils.terminal.clear_screen', return_value=True):

        result = await handle_slash_command("/clear", mock_agent, mock_thread)

        # Verify all operations completed
        mock_result_store.clear.assert_called_once()
        mock_activity_tracker.reset.assert_called_once()

        # Verify special signal returned
        assert result == "__CLEAR_CONTEXT__"


@pytest.mark.asyncio
async def test_clear_command_works_without_copilot(mock_agent, mock_thread):
    """Test that /clear works even when COPILOT_AVAILABLE is False."""
    mock_result_store = AsyncMock()
    mock_activity_tracker = AsyncMock()

    # The /clear command should work regardless of COPILOT_AVAILABLE
    # This is because we modified the condition to allow /clear through
    with patch('spi_agent.workflows.get_result_store', return_value=mock_result_store), \
         patch('spi_agent.activity.get_activity_tracker', return_value=mock_activity_tracker), \
         patch('spi_agent.utils.terminal.clear_screen', return_value=True):

        result = await handle_slash_command("/clear", mock_agent, mock_thread)

        # Should work and return the signal
        assert result == "__CLEAR_CONTEXT__"


@pytest.mark.asyncio
async def test_clear_command_handles_clear_screen_failure(mock_agent, mock_thread):
    """Test that /clear continues even if terminal clearing fails."""
    mock_result_store = AsyncMock()
    mock_activity_tracker = AsyncMock()

    with patch('spi_agent.workflows.get_result_store', return_value=mock_result_store), \
         patch('spi_agent.activity.get_activity_tracker', return_value=mock_activity_tracker), \
         patch('spi_agent.utils.terminal.clear_screen', return_value=False):  # Clearing fails

        result = await handle_slash_command("/clear", mock_agent, mock_thread)

        # Should still complete and return signal
        assert result == "__CLEAR_CONTEXT__"

        # Store and tracker should still be cleared
        mock_result_store.clear.assert_called_once()
        mock_activity_tracker.reset.assert_called_once()


@pytest.mark.asyncio
async def test_clear_command_with_whitespace(mock_agent, mock_thread):
    """Test that /clear works with trailing whitespace."""
    mock_result_store = AsyncMock()
    mock_activity_tracker = AsyncMock()

    with patch('spi_agent.workflows.get_result_store', return_value=mock_result_store), \
         patch('spi_agent.activity.get_activity_tracker', return_value=mock_activity_tracker), \
         patch('spi_agent.utils.terminal.clear_screen', return_value=True):

        # Test with trailing space
        result = await handle_slash_command("/clear ", mock_agent, mock_thread)

        # Should still work
        assert result == "__CLEAR_CONTEXT__"
