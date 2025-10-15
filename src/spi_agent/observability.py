"""Observability module for SPI Agent using OpenTelemetry.

This module provides tracing and metrics capabilities through Microsoft Agent Framework's
OpenTelemetry integration, enabling monitoring via Azure AI Foundry dashboards.
"""

import logging
import os
from typing import Optional

from agent_framework.observability import get_meter, get_tracer

logger = logging.getLogger(__name__)

# Set default service name for OpenTelemetry if not already configured
os.environ.setdefault("OTEL_SERVICE_NAME", "spi-agent")

# Initialize OpenTelemetry tracer and meter
tracer = get_tracer()
meter = get_meter()

# Define metrics for monitoring agent operations

# Tool invocation metrics
tool_calls_counter = meter.create_counter(
    "spi_agent.tool_calls.total",
    description="Total number of tool calls made by the agent",
)

tool_duration_histogram = meter.create_histogram(
    "spi_agent.tool_calls.duration_seconds",
    description="Duration of tool calls in seconds",
)

# Workflow metrics
workflow_runs_counter = meter.create_counter(
    "spi_agent.workflows.runs.total",
    description="Total number of workflow runs",
)

workflow_duration_histogram = meter.create_histogram(
    "spi_agent.workflows.duration_seconds",
    description="Duration of workflow execution in seconds",
)

# Triage-specific metrics
triage_scans_counter = meter.create_counter(
    "spi_agent.triage.scans.total",
    description="Total number of triage scans performed",
)

triage_vulnerabilities_counter = meter.create_counter(
    "spi_agent.triage.vulnerabilities.total",
    description="Total vulnerabilities found by severity",
)

# Test-specific metrics
test_runs_counter = meter.create_counter(
    "spi_agent.tests.runs.total",
    description="Total number of test runs",
)

test_results_counter = meter.create_counter(
    "spi_agent.tests.results.total",
    description="Test results by status (passed/failed)",
)

# LLM interaction metrics
llm_calls_counter = meter.create_counter(
    "spi_agent.llm.calls.total",
    description="Total number of LLM calls",
)

llm_tokens_counter = meter.create_counter(
    "spi_agent.llm.tokens.total",
    description="Total tokens used (prompt + completion)",
)


def record_tool_call(tool_name: str, duration: float, status: str = "success") -> None:
    """Record a tool call metric.

    Args:
        tool_name: Name of the tool that was called
        duration: Duration of the tool call in seconds
        status: Status of the tool call (success/error)
    """
    tool_calls_counter.add(1, {"tool": tool_name, "status": status})
    tool_duration_histogram.record(duration, {"tool": tool_name})


def record_workflow_run(
    workflow_type: str, duration: float, status: str = "success", service_count: int = 1
) -> None:
    """Record a workflow run metric.

    Args:
        workflow_type: Type of workflow (triage, test, status, fork)
        duration: Duration of the workflow in seconds
        status: Status of the workflow (success/error)
        service_count: Number of services processed
    """
    workflow_runs_counter.add(
        1, {"workflow": workflow_type, "status": status, "services": service_count}
    )
    workflow_duration_histogram.record(duration, {"workflow": workflow_type})


def record_triage_scan(
    service: str,
    critical: int,
    high: int,
    medium: int,
    low: int = 0,
    status: str = "success",
) -> None:
    """Record triage scan metrics.

    Args:
        service: Service that was scanned
        critical: Number of critical vulnerabilities
        high: Number of high vulnerabilities
        medium: Number of medium vulnerabilities
        low: Number of low vulnerabilities
        status: Status of the scan (success/error)
    """
    triage_scans_counter.add(1, {"service": service, "status": status})

    # Record vulnerability counts by severity
    if critical > 0:
        triage_vulnerabilities_counter.add(critical, {"severity": "critical", "service": service})
    if high > 0:
        triage_vulnerabilities_counter.add(high, {"severity": "high", "service": service})
    if medium > 0:
        triage_vulnerabilities_counter.add(medium, {"severity": "medium", "service": service})
    if low > 0:
        triage_vulnerabilities_counter.add(low, {"severity": "low", "service": service})


def record_test_run(
    service: str, passed: int, failed: int, skipped: int = 0, status: str = "success"
) -> None:
    """Record test run metrics.

    Args:
        service: Service that was tested
        passed: Number of tests that passed
        failed: Number of tests that failed
        skipped: Number of tests that were skipped
        status: Overall test run status (success/error)
    """
    test_runs_counter.add(1, {"service": service, "status": status})

    # Record test results by status
    if passed > 0:
        test_results_counter.add(passed, {"result": "passed", "service": service})
    if failed > 0:
        test_results_counter.add(failed, {"result": "failed", "service": service})
    if skipped > 0:
        test_results_counter.add(skipped, {"result": "skipped", "service": service})


def record_llm_call(
    model: str, prompt_tokens: int, completion_tokens: int, duration: Optional[float] = None
) -> None:
    """Record LLM interaction metrics.

    Args:
        model: Model name used for the call
        prompt_tokens: Number of prompt tokens used
        completion_tokens: Number of completion tokens generated
        duration: Duration of the LLM call in seconds (optional)
    """
    llm_calls_counter.add(1, {"model": model})
    llm_tokens_counter.add(prompt_tokens, {"type": "prompt", "model": model})
    llm_tokens_counter.add(completion_tokens, {"type": "completion", "model": model})
