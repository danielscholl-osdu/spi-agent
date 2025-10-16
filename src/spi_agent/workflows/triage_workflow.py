"""Triage workflow using Microsoft Agent Framework.

This module provides MAF-based workflow orchestration for Maven dependency
and vulnerability triage analysis.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List

from spi_agent.observability import record_triage_scan, record_workflow_run, tracer
from spi_agent.workflows import WorkflowResult, get_result_store

if TYPE_CHECKING:
    from spi_agent import SPIAgent

logger = logging.getLogger(__name__)


async def run_triage_workflow(
    agent: "SPIAgent",
    services: List[str],
    severity_filter: List[str],
    providers: List[str],
    include_testing: bool = False,
    create_issue: bool = False,
) -> WorkflowResult:
    """Run triage workflow for specified services.

    This function orchestrates the triage analysis workflow, including:
    - Scanning services for vulnerabilities using Maven MCP
    - Analyzing CVEs across services
    - Storing results in WorkflowResultStore for agent context
    - Recording observability metrics

    Args:
        agent: SPIAgent instance with MCP tools
        services: List of service names to analyze
        severity_filter: List of severity levels to include
        providers: Provider modules to include (e.g., ["azure", "aws"])
        include_testing: Whether to include testing modules
        create_issue: Whether to create GitHub tracking issues

    Returns:
        WorkflowResult with triage analysis data
    """
    workflow_start = datetime.now()
    start_time = asyncio.get_event_loop().time()

    logger.info(f"Starting triage workflow for services: {', '.join(services)}")

    with tracer.start_as_current_span("triage_workflow") as span:
        span.set_attribute("services", ",".join(services))
        span.set_attribute("severity_filter", ",".join(severity_filter))
        span.set_attribute("create_issue", create_issue)

        # Store vulnerability results by service
        vulnerabilities_by_service: Dict[str, Dict[str, int]] = {}
        detailed_results: Dict[str, Any] = {}

        try:
            # Scan services (currently delegates to existing TriageRunner)
            # In future iterations, this will use MAF Executors
            from spi_agent.copilot.runners.triage_runner import TriageRunner

            # Get prompt file
            from spi_agent.copilot import get_prompt_file

            prompt_file = get_prompt_file("triage.md")

            # Create runner
            runner = TriageRunner(
                prompt_file=prompt_file,
                services=services,
                agent=agent,
                create_issue=create_issue,
                severity_filter=severity_filter,
                providers=providers,
                include_testing=include_testing,
            )

            # Execute triage analysis
            logger.info("Executing triage runner...")
            exit_code = await runner.run()

            # Extract results from runner
            for service in services:
                service_data = runner.tracker.services.get(service, {})
                critical = service_data.get("critical", 0)
                high = service_data.get("high", 0)
                medium = service_data.get("medium", 0)
                status = service_data.get("status", "unknown")

                vulnerabilities_by_service[service] = {
                    "critical": critical,
                    "high": high,
                    "medium": medium,
                }

                # Record observability metrics for each service
                record_triage_scan(
                    service=service,
                    critical=critical,
                    high=high,
                    medium=medium,
                    status="success" if status != "error" else "error",
                )

            # Get CVE analysis from runner if available
            cve_analysis = ""
            if hasattr(runner, "full_output") and runner.full_output:
                # Extract CVE analysis from full output
                full_output_text = "\n".join(runner.full_output)
                cve_analysis = full_output_text

            # Build detailed results
            detailed_results = {
                "exit_code": exit_code,
                "services_data": runner.tracker.services if hasattr(runner, "tracker") else {},
                "severity_filter": severity_filter,
                "providers": providers,
                "include_testing": include_testing,
                "create_issue": create_issue,
            }

            # Calculate summary
            total_critical = sum(v.get("critical", 0) for v in vulnerabilities_by_service.values())
            total_high = sum(v.get("high", 0) for v in vulnerabilities_by_service.values())
            total_medium = sum(v.get("medium", 0) for v in vulnerabilities_by_service.values())

            summary = (
                f"Scanned {len(services)} service(s): "
                f"{total_critical}C / {total_high}H / {total_medium}M vulnerabilities"
            )

            # Create workflow result
            result = WorkflowResult(
                workflow_type="triage",
                timestamp=workflow_start,
                services=services,
                status="success" if exit_code == 0 else "error",
                summary=summary,
                detailed_results=detailed_results,
                vulnerabilities=vulnerabilities_by_service,
                cve_analysis=cve_analysis,
            )

            # Store result for agent context
            result_store = get_result_store()
            await result_store.store(result)
            logger.info(f"Stored triage workflow result: {summary}")

            # Record workflow metrics
            duration = asyncio.get_event_loop().time() - start_time
            record_workflow_run(
                workflow_type="triage",
                duration=duration,
                status="success" if exit_code == 0 else "error",
                service_count=len(services),
            )

            span.set_attribute("total_vulnerabilities", total_critical + total_high + total_medium)
            span.set_attribute("status", "success" if exit_code == 0 else "error")

            return result

        except Exception as e:
            logger.error(f"Triage workflow failed: {e}")
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))

            # Create error result
            result = WorkflowResult(
                workflow_type="triage",
                timestamp=workflow_start,
                services=services,
                status="error",
                summary=f"Triage workflow failed: {str(e)[:100]}",
                detailed_results={"error": str(e)},
                vulnerabilities=vulnerabilities_by_service,
            )

            # Store error result
            result_store = get_result_store()
            await result_store.store(result)

            # Record failed workflow
            duration = asyncio.get_event_loop().time() - start_time
            record_workflow_run(
                workflow_type="triage",
                duration=duration,
                status="error",
                service_count=len(services),
            )

            raise


async def run_test_workflow(
    services: List[str],
    provider: str = "azure",
) -> WorkflowResult:
    """Run test workflow for specified services.

    This is a placeholder for future MAF Workflow migration of TestRunner.

    Args:
        services: List of service names to test
        provider: Cloud provider profile to use

    Returns:
        WorkflowResult with test execution data
    """
    workflow_start = datetime.now()

    logger.info(f"Test workflow for services: {', '.join(services)} (provider: {provider})")

    # Placeholder: delegate to existing TestRunner
    # Future: implement as MAF Workflow with Executors
    from spi_agent.copilot import get_prompt_file
    from spi_agent.copilot.runners.test_runner import TestRunner

    prompt_file = get_prompt_file("test.md")
    runner = TestRunner(prompt_file=prompt_file, services=services, provider=provider)
    exit_code = runner.run()

    # Extract test results including grade
    test_results_by_service: Dict[str, Dict[str, Any]] = {}
    for service in services:
        service_data = runner.tracker.services.get(service, {})
        test_results_by_service[service] = {
            "passed": service_data.get("tests_run", 0) - service_data.get("tests_failed", 0),
            "failed": service_data.get("tests_failed", 0),
            "skipped": 0,  # Not tracked separately
            "total_tests": service_data.get("tests_run", 0),
            "coverage_line": service_data.get("coverage_line", 0),
            "coverage_branch": service_data.get("coverage_branch", 0),
            "quality_grade": service_data.get("quality_grade"),
            "quality_label": service_data.get("quality_label"),
        }

    total_passed = sum(v.get("passed", 0) for v in test_results_by_service.values())
    total_failed = sum(v.get("failed", 0) for v in test_results_by_service.values())

    summary = f"Tested {len(services)} service(s): {total_passed} passed, {total_failed} failed"

    result = WorkflowResult(
        workflow_type="test",
        timestamp=workflow_start,
        services=services,
        status="success" if exit_code == 0 else "error",
        summary=summary,
        detailed_results={"exit_code": exit_code, "provider": provider},
        test_results=test_results_by_service,
    )

    # Store result
    result_store = get_result_store()
    await result_store.store(result)
    logger.info(f"Stored test workflow result: {summary}")

    return result


async def run_status_workflow(services: List[str]) -> WorkflowResult:
    """Run status workflow for specified services.

    This is a placeholder for future MAF Workflow migration of StatusRunner.

    Args:
        services: List of service names to check

    Returns:
        WorkflowResult with status information
    """
    workflow_start = datetime.now()

    logger.info(f"Status workflow for services: {', '.join(services)}")

    # Placeholder: delegate to existing StatusRunner
    from spi_agent.copilot import get_prompt_file
    from spi_agent.copilot.runners.status_runner import StatusRunner

    prompt_file = get_prompt_file("status.md")
    runner = StatusRunner(prompt_file=prompt_file, services=services)
    runner.run()

    # Extract status information
    pr_status_by_service: Dict[str, Dict[str, Any]] = {}
    for service in services:
        service_data = runner.tracker.services.get(service, {})
        pr_status_by_service[service] = {
            "open_prs": service_data.get("open_prs", 0),
            "open_issues": service_data.get("open_issues", 0),
            "status": service_data.get("status", "unknown"),
        }

    summary = f"Checked status for {len(services)} service(s)"

    result = WorkflowResult(
        workflow_type="status",
        timestamp=workflow_start,
        services=services,
        status="success",
        summary=summary,
        detailed_results={},
        pr_status=pr_status_by_service,
    )

    # Store result
    result_store = get_result_store()
    await result_store.store(result)
    logger.info(f"Stored status workflow result: {summary}")

    return result


async def run_fork_workflow(services: List[str], branch: str = "main") -> WorkflowResult:
    """Run fork workflow for specified services.

    This is a placeholder for future MAF Workflow migration of ForkRunner (CopilotRunner).

    Args:
        services: List of service names to fork
        branch: Branch to fork

    Returns:
        WorkflowResult with fork operation status
    """
    workflow_start = datetime.now()

    logger.info(f"Fork workflow for services: {', '.join(services)} (branch: {branch})")

    # Placeholder: delegate to existing CopilotRunner
    from spi_agent.copilot import get_prompt_file
    from spi_agent.copilot.runners.copilot_runner import CopilotRunner

    prompt_file = get_prompt_file("fork.md")
    runner = CopilotRunner(prompt_file=prompt_file, services=services, branch=branch)
    exit_code = runner.run()

    # Extract fork status
    fork_status_by_service: Dict[str, str] = {}
    for service in services:
        # Fork status is typically success/error
        fork_status_by_service[service] = "success" if exit_code == 0 else "error"

    summary = f"Forked {len(services)} service(s) (branch: {branch})"

    result = WorkflowResult(
        workflow_type="fork",
        timestamp=workflow_start,
        services=services,
        status="success" if exit_code == 0 else "error",
        summary=summary,
        detailed_results={"exit_code": exit_code, "branch": branch},
        fork_status=fork_status_by_service,
    )

    # Store result
    result_store = get_result_store()
    await result_store.store(result)
    logger.info(f"Stored fork workflow result: {summary}")

    return result
