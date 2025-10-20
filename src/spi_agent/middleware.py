"""Agent middleware for logging and context injection.

This module provides middleware functions that intercept agent interactions
with tools and LLMs, enabling logging, metrics, and context injection.
"""

import logging
import time
from typing import Awaitable, Callable

from agent_framework import AgentRunContext, ChatContext, FunctionInvocationContext

from spi_agent.observability import record_tool_call, tracer

logger = logging.getLogger(__name__)


async def logging_function_middleware(
    context: FunctionInvocationContext,
    next: Callable[[FunctionInvocationContext], Awaitable[None]],
) -> None:
    """Function middleware that logs and traces tool execution.

    This middleware intercepts all tool calls (GitHub tools and Maven MCP tools)
    and provides:
    - Structured logging of tool name and arguments
    - OpenTelemetry tracing for observability
    - Execution duration metrics
    - Error tracking

    Args:
        context: Function invocation context containing tool name, arguments, and result
        next: Next middleware or the actual function execution
    """
    # Pre-processing: Log before function execution
    tool_name = context.function.name if hasattr(context.function, "name") else str(context.function)

    logger.info(f"[Tool Call] {tool_name}")

    # Log arguments at debug level (can be verbose)
    if hasattr(context, "arguments") and context.arguments:
        logger.debug(f"[Tool Args] {context.arguments}")

    # Start OpenTelemetry span for tracing
    with tracer.start_as_current_span("tool_call") as span:
        span.set_attribute("tool.name", tool_name)

        # Add arguments as span attributes (sanitized)
        if hasattr(context, "arguments") and context.arguments:
            # Only add non-sensitive arguments
            safe_args = {
                k: v
                for k, v in (context.arguments.items() if isinstance(context.arguments, dict) else {})
                if k not in ["token", "api_key", "password", "secret"]
            }
            if safe_args:
                span.set_attribute("tool.arguments", str(safe_args))

        start_time = time.time()
        status = "success"

        try:
            # Continue to next middleware or function execution
            await next(context)

        except Exception as e:
            # Track errors
            status = "error"
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            logger.error(f"[Tool Error] {tool_name}: {str(e)}")
            raise

        finally:
            # Post-processing: Log after function execution
            duration = time.time() - start_time
            span.set_attribute("tool.duration", duration)

            logger.info(f"[Tool Complete] {tool_name} ({duration:.2f}s)")

            # Log result at debug level
            if hasattr(context, "result") and context.result:
                result_preview = str(context.result)[:200]  # First 200 chars
                logger.debug(f"[Tool Result] {result_preview}...")

            # Record metrics
            record_tool_call(tool_name, duration, status)


async def logging_chat_middleware(
    context: ChatContext,
    next: Callable[[ChatContext], Awaitable[None]],
) -> None:
    """Chat middleware that logs and traces LLM interactions.

    This middleware intercepts all agent-to-LLM communications and provides:
    - Structured logging of message counts
    - OpenTelemetry tracing
    - Request/response logging at debug level

    Args:
        context: Chat context containing messages and model configuration
        next: Next middleware or the actual LLM service call
    """
    # Pre-processing: Log before AI call
    message_count = len(context.messages) if hasattr(context, "messages") else 0
    logger.info(f"[LLM Request] {message_count} messages")

    # Log last message at debug level (usually the user query)
    if hasattr(context, "messages") and context.messages:
        last_message = context.messages[-1]
        if isinstance(last_message, dict) and "content" in last_message:
            content_preview = str(last_message["content"])[:200]  # First 200 chars
            logger.debug(f"[LLM Query] {content_preview}...")

    # Start OpenTelemetry span for tracing
    with tracer.start_as_current_span("llm_call") as span:
        span.set_attribute("llm.message_count", message_count)

        # Add model info if available
        if hasattr(context, "model"):
            span.set_attribute("llm.model", context.model)

        start_time = time.time()

        try:
            # Continue to next middleware or AI service
            await next(context)

            # Post-processing: Log after AI response
            duration = time.time() - start_time
            span.set_attribute("llm.duration", duration)

            logger.info(f"[LLM Response] Received ({duration:.2f}s)")

            # Log response at debug level
            if hasattr(context, "response") and context.response:
                response_preview = str(context.response)[:200]  # First 200 chars
                logger.debug(f"[LLM Response Content] {response_preview}...")

        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            logger.error(f"[LLM Error] {str(e)}")
            raise


async def workflow_context_agent_middleware(
    context: AgentRunContext,
    next: Callable[[AgentRunContext], Awaitable[None]],
) -> None:
    """Agent middleware that injects workflow context before agent execution.

    This middleware intercepts EVERY agent.run() call and automatically adds
    context from recent workflow executions (slash commands) to the messages.
    This enables the agent to reference detailed workflow results when
    answering follow-up questions.

    Args:
        context: Agent run context containing messages, agent, and metadata
        next: Next middleware or the actual agent execution

    Example:
        User executes /vulns partition, then asks "What CVEs did you find?"
        The middleware injects vulns results before agent execution, allowing
        the agent to answer with specific CVE details.
    """
    # Import here to avoid circular dependency
    from spi_agent.workflows import get_result_store

    # Get recent workflow results
    result_store = get_result_store()
    context_summary = await result_store.get_context_summary(limit=3)

    logger.debug(f"[Context Retrieval] Found {len(context_summary)} chars of workflow context")

    if context_summary and hasattr(context, "messages") and context.messages:
        # Enhanced context with explicit instruction to use the data
        enhanced_context = f"""{context_summary}

**IMPORTANT INSTRUCTION:**
When the user asks about recent workflow results (tests, vulns, status, fork),
YOU MUST reference the workflow results shown above. DO NOT call GitHub tools
to fetch information that is already available in these results.

For example:
- "what was the grade?" → Reference the Grade from Test Results above
- "what CVEs did you find?" → Reference the Vulnerabilities from vulnerability scan results above
- "how many tests passed?" → Reference the Test Results above

Always check this context FIRST before calling any tools."""

        # Create a user message with the workflow context
        # Insert it right before the current user query
        from agent_framework import ChatMessage, Role

        context_message = ChatMessage(
            role=Role.SYSTEM,
            text=enhanced_context
        )

        # Insert before the last message (current user query)
        context.messages.insert(-1, context_message)

        logger.info(f"[Context Injection] Injected workflow context ({len(context_summary)} chars)")
    else:
        logger.debug(
            f"[Context Injection] No workflow results to inject "
            f"(has {len(context.messages) if hasattr(context, 'messages') else 0} messages)"
        )

    # Continue to next middleware or agent execution
    await next(context)
