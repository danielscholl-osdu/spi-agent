"""Tests for middleware functionality."""

import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from spi_agent.middleware import (
    logging_chat_middleware,
    logging_function_middleware,
    workflow_context_agent_middleware,
)


class TestLoggingFunctionMiddleware:
    """Tests for logging_function_middleware."""

    @pytest.mark.asyncio
    async def test_logs_tool_call_success(self):
        """Test logging successful tool call."""
        # Mock context
        context = Mock()
        context.function = Mock()
        context.function.name = "list_issues"
        context.arguments = {"repo": "partition", "state": "open"}
        context.result = "Found 5 issues"

        # Mock next middleware
        next_called = False

        async def mock_next(ctx):
            nonlocal next_called
            next_called = True
            # Simulate some work
            await AsyncMock()()

        # Execute middleware
        with patch("spi_agent.middleware.logger") as mock_logger:
            with patch("spi_agent.middleware.tracer") as mock_tracer:
                with patch("spi_agent.middleware.record_tool_call") as mock_record:
                    mock_span = Mock()
                    mock_tracer.start_as_current_span.return_value.__enter__.return_value = (
                        mock_span
                    )

                    await logging_function_middleware(context, mock_next)

                    # Verify next was called
                    assert next_called

                    # Verify logging
                    mock_logger.info.assert_any_call("[Tool Call] list_issues")
                    assert mock_logger.info.call_count >= 2  # Start and complete

                    # Verify tracing
                    mock_span.set_attribute.assert_any_call("tool.name", "list_issues")

                    # Verify metrics recorded
                    assert mock_record.called

    @pytest.mark.asyncio
    async def test_logs_tool_call_error(self):
        """Test logging tool call error."""
        context = Mock()
        context.function = Mock()
        context.function.name = "create_issue"
        context.arguments = {}

        # Mock next that raises error
        async def mock_next_error(ctx):
            raise ValueError("Invalid arguments")

        with patch("spi_agent.middleware.logger") as mock_logger:
            with patch("spi_agent.middleware.tracer") as mock_tracer:
                with patch("spi_agent.middleware.record_tool_call") as mock_record:
                    mock_span = Mock()
                    mock_tracer.start_as_current_span.return_value.__enter__.return_value = (
                        mock_span
                    )

                    with pytest.raises(ValueError):
                        await logging_function_middleware(context, mock_next_error)

                    # Verify error logging
                    mock_logger.error.assert_called_once()
                    assert "Invalid arguments" in str(mock_logger.error.call_args)

                    # Verify error span attributes
                    mock_span.set_attribute.assert_any_call("error", True)

                    # Verify metrics recorded with error status
                    assert mock_record.called
                    call_args = mock_record.call_args[0]
                    assert call_args[2] == "error"  # status parameter

    @pytest.mark.asyncio
    async def test_sanitizes_sensitive_arguments(self):
        """Test that sensitive arguments are not logged in spans."""
        context = Mock()
        context.function = Mock()
        context.function.name = "authenticate"
        context.arguments = {
            "username": "alice",
            "password": "secret123",
            "api_key": "key_abc",
            "token": "tok_xyz",
        }

        async def mock_next(ctx):
            pass

        with patch("spi_agent.middleware.tracer") as mock_tracer:
            with patch("spi_agent.middleware.record_tool_call"):
                mock_span = Mock()
                mock_tracer.start_as_current_span.return_value.__enter__.return_value = (
                    mock_span
                )

                await logging_function_middleware(context, mock_next)

                # Check that set_attribute was called for tool.arguments
                calls = [
                    call for call in mock_span.set_attribute.call_args_list if call[0][0] == "tool.arguments"
                ]

                if calls:
                    args_value = str(calls[0][0][1])
                    # Sensitive fields should not be in the arguments
                    assert "password" not in args_value or "secret123" not in args_value
                    assert "api_key" not in args_value or "key_abc" not in args_value
                    assert "token" not in args_value or "tok_xyz" not in args_value


class TestLoggingChatMiddleware:
    """Tests for logging_chat_middleware."""

    @pytest.mark.asyncio
    async def test_logs_llm_request_success(self):
        """Test logging successful LLM request."""
        context = Mock()
        context.messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "List issues in partition"},
        ]
        context.response = "Here are the issues..."

        next_called = False

        async def mock_next(ctx):
            nonlocal next_called
            next_called = True

        with patch("spi_agent.middleware.logger") as mock_logger:
            with patch("spi_agent.middleware.tracer") as mock_tracer:
                mock_span = Mock()
                mock_tracer.start_as_current_span.return_value.__enter__.return_value = (
                    mock_span
                )

                await logging_chat_middleware(context, mock_next)

                # Verify next was called
                assert next_called

                # Verify logging
                mock_logger.info.assert_any_call("[LLM Request] 2 messages")

                # Verify span attributes
                mock_span.set_attribute.assert_any_call("llm.message_count", 2)

    @pytest.mark.asyncio
    async def test_logs_llm_error(self):
        """Test logging LLM error."""
        context = Mock()
        context.messages = [{"role": "user", "content": "Test query"}]

        async def mock_next_error(ctx):
            raise RuntimeError("API timeout")

        with patch("spi_agent.middleware.logger") as mock_logger:
            with patch("spi_agent.middleware.tracer") as mock_tracer:
                mock_span = Mock()
                mock_tracer.start_as_current_span.return_value.__enter__.return_value = (
                    mock_span
                )

                with pytest.raises(RuntimeError):
                    await logging_chat_middleware(context, mock_next_error)

                # Verify error logging
                mock_logger.error.assert_called_once()

                # Verify error span attributes
                mock_span.set_attribute.assert_any_call("error", True)

    @pytest.mark.asyncio
    async def test_handles_missing_messages(self):
        """Test handling context without messages."""
        context = Mock(spec=[])  # Explicitly no messages attribute

        async def mock_next(ctx):
            pass

        with patch("spi_agent.middleware.logger") as mock_logger:
            with patch("spi_agent.middleware.tracer") as mock_tracer:
                mock_span = Mock()
                mock_tracer.start_as_current_span.return_value.__enter__.return_value = (
                    mock_span
                )

                # Should not raise error
                await logging_chat_middleware(context, mock_next)

                # Should log 0 messages
                mock_logger.info.assert_any_call("[LLM Request] 0 messages")


class TestWorkflowContextAgentMiddleware:
    """Tests for workflow_context_agent_middleware."""

    @pytest.mark.asyncio
    async def test_injects_workflow_context(self):
        """Test injection of workflow results into agent context."""
        from agent_framework import ChatMessage, Role
        from spi_agent.workflows import WorkflowResult, get_result_store

        # Create a workflow result
        result_store = get_result_store()
        await result_store.clear()  # Clean state

        result = WorkflowResult(
            workflow_type="triage",
            timestamp=Mock(),
            services=["partition"],
            status="success",
            summary="5 critical vulnerabilities",
            detailed_results={},
            vulnerabilities={"partition": {"critical": 5, "high": 10, "medium": 3}},
        )
        await result_store.store(result)

        # Mock agent run context with ChatMessage objects
        context = Mock()
        context.messages = [
            ChatMessage(role=Role.SYSTEM, text="You are a helpful assistant"),
            ChatMessage(role=Role.USER, text="What CVEs did you find?"),
        ]

        next_called = False

        async def mock_next(ctx):
            nonlocal next_called
            next_called = True

        # Execute middleware
        with patch("builtins.print"):  # Suppress debug output in tests
            await workflow_context_agent_middleware(context, mock_next)

        # Verify next was called
        assert next_called

        # Verify context was injected (should have 3 messages now)
        assert len(context.messages) == 3
        injected_message = context.messages[-2]  # Second to last (before user query)
        assert injected_message.role == Role.SYSTEM
        assert "Recent Workflow Results" in injected_message.text
        assert "partition" in injected_message.text
        assert "5 critical" in injected_message.text

        # Cleanup
        await result_store.clear()

    @pytest.mark.asyncio
    async def test_no_injection_when_no_results(self):
        """Test no injection when no workflow results available."""
        from agent_framework import ChatMessage, Role
        from spi_agent.workflows import get_result_store

        result_store = get_result_store()
        await result_store.clear()  # Ensure empty

        context = Mock()
        context.messages = [
            ChatMessage(role=Role.SYSTEM, text="You are a helpful assistant"),
            ChatMessage(role=Role.USER, text="Hello"),
        ]

        next_called = False

        async def mock_next(ctx):
            nonlocal next_called
            next_called = True

        with patch("builtins.print"):
            await workflow_context_agent_middleware(context, mock_next)

        # Verify next was called
        assert next_called

        # Verify no injection (still 2 messages)
        assert len(context.messages) == 2

    @pytest.mark.asyncio
    async def test_handles_empty_messages_list(self):
        """Test handling context with empty messages list."""
        from spi_agent.workflows import WorkflowResult, get_result_store

        result_store = get_result_store()
        await result_store.clear()

        result = WorkflowResult(
            workflow_type="test",
            timestamp=Mock(),
            services=["partition"],
            status="success",
            summary="All tests passed",
            detailed_results={},
        )
        await result_store.store(result)

        context = Mock()
        context.messages = []  # Empty list

        async def mock_next(ctx):
            pass

        with patch("builtins.print"):
            # Should not raise error even with empty messages
            await workflow_context_agent_middleware(context, mock_next)

        # Cleanup
        await result_store.clear()

    @pytest.mark.asyncio
    async def test_handles_missing_messages_attribute(self):
        """Test handling context without messages attribute."""
        context = Mock(spec=[])  # No messages attribute

        async def mock_next(ctx):
            pass

        with patch("builtins.print"):
            # Should not raise error
            await workflow_context_agent_middleware(context, mock_next)
