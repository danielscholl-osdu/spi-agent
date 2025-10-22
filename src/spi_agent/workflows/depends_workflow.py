"""Dependency update analysis workflow using Microsoft Agent Framework.

This module provides MAF-based workflow orchestration for Maven dependency
version checking and update analysis.
"""

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List

from spi_agent.observability import record_workflow_run, tracer
from spi_agent.workflows import WorkflowResult, get_result_store

if TYPE_CHECKING:
    from spi_agent import SPIAgent

logger = logging.getLogger(__name__)


async def run_depends_workflow(
    agent: "SPIAgent",
    services: List[str],
    providers: List[str],
    include_testing: bool = False,
    create_issue: bool = False,
) -> WorkflowResult:
    """Run dependency update analysis workflow for specified services.

    This function orchestrates the dependency analysis workflow, including:
    - Analyzing Maven dependencies and checking for available updates
    - Categorizing updates as major, minor, or patch
    - Storing results in WorkflowResultStore for agent context
    - Recording observability metrics

    Args:
        agent: SPIAgent instance with MCP tools
        services: List of service names to analyze
        providers: Provider modules to include (e.g., ["azure", "aws"])
        include_testing: Whether to include testing modules
        create_issue: Whether to create GitHub tracking issues

    Returns:
        WorkflowResult with dependency analysis data
    """
    workflow_start = datetime.now()
    start_time = asyncio.get_event_loop().time()

    logger.info(f"Starting dependency analysis workflow for services: {', '.join(services)}")

    with tracer.start_as_current_span("depends_workflow") as span:
        span.set_attribute("services", ",".join(services))
        span.set_attribute("providers", ",".join(providers))
        span.set_attribute("create_issue", create_issue)

        # Store dependency updates by service
        dependency_updates_by_service: Dict[str, Dict[str, int]] = {}
        detailed_results: Dict[str, Any] = {}

        try:
            # Run dependency analysis (delegates to DependsRunner)
            from spi_agent.copilot.runners.depends_runner import DependsRunner

            # Get prompt file
            from spi_agent.copilot import get_prompt_file

            prompt_file = get_prompt_file("depends.md")

            # Create runner
            runner = DependsRunner(
                prompt_file=prompt_file,
                services=services,
                agent=agent,
                create_issue=create_issue,
                providers=providers,
                include_testing=include_testing,
            )

            # Execute dependency analysis
            logger.info("Executing dependency analysis runner...")
            exit_code = await runner.run()

            # Extract results from runner
            for service in services:
                service_data = runner.tracker.services.get(service, {})
                major = service_data.get("major_updates", 0)
                minor = service_data.get("minor_updates", 0)
                patch = service_data.get("patch_updates", 0)
                total_deps = service_data.get("total_dependencies", 0)
                outdated = service_data.get("outdated_dependencies", 0)
                status = service_data.get("status", "unknown")

                dependency_updates_by_service[service] = {
                    "major_updates": major,
                    "minor_updates": minor,
                    "patch_updates": patch,
                    "total_dependencies": total_deps,
                    "outdated_dependencies": outdated,
                    "status": status,
                }

            # Build detailed results
            detailed_results = {
                "exit_code": exit_code,
                "services_data": runner.tracker.services if hasattr(runner, "tracker") else {},
                "providers": providers,
                "include_testing": include_testing,
                "create_issue": create_issue,
            }

            # Calculate summary
            total_major = sum(v.get("major_updates", 0) for v in dependency_updates_by_service.values())
            total_minor = sum(v.get("minor_updates", 0) for v in dependency_updates_by_service.values())
            total_patch = sum(v.get("patch_updates", 0) for v in dependency_updates_by_service.values())

            summary = (
                f"Analyzed {len(services)} service(s): "
                f"{total_major}M / {total_minor}m / {total_patch}p updates available"
            )

            # Create workflow result
            result = WorkflowResult(
                workflow_type="depends",
                timestamp=workflow_start,
                services=services,
                status="success" if exit_code == 0 else "error",
                summary=summary,
                detailed_results=detailed_results,
            )

            # Add dependency_updates field to result (custom field)
            # Note: WorkflowResult doesn't have this field, but we can add it to detailed_results
            result.detailed_results["dependency_updates"] = dependency_updates_by_service

            # Store result for agent context
            result_store = get_result_store()
            await result_store.store(result)
            logger.info(f"Stored dependency analysis workflow result: {summary}")

            # Record workflow metrics
            duration = asyncio.get_event_loop().time() - start_time
            record_workflow_run(
                workflow_type="depends",
                duration=duration,
                status="success" if exit_code == 0 else "error",
                service_count=len(services),
            )

            span.set_attribute("total_updates", total_major + total_minor + total_patch)
            span.set_attribute("status", "success" if exit_code == 0 else "error")

            return result

        except Exception as e:
            logger.error(f"Dependency analysis workflow failed: {e}")
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))

            # Create error result
            result = WorkflowResult(
                workflow_type="depends",
                timestamp=workflow_start,
                services=services,
                status="error",
                summary=f"Dependency analysis workflow failed: {str(e)[:100]}",
                detailed_results={"error": str(e)},
            )

            # Store error result
            result_store = get_result_store()
            await result_store.store(result)

            # Record failed workflow
            duration = asyncio.get_event_loop().time() - start_time
            record_workflow_run(
                workflow_type="depends",
                duration=duration,
                status="error",
                service_count=len(services),
            )

            raise
