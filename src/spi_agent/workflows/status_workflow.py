"""Status workflow for gathering and storing GitHub/GitLab repository status.

This workflow wraps the StatusRunner to store results in WorkflowResultStore,
enabling the agent to access status information in conversation context.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from spi_agent.observability import record_workflow_run, tracer
from spi_agent.workflows import WorkflowResult, get_result_store

logger = logging.getLogger(__name__)


async def run_status_workflow(
    services: List[str],
    platform: str = "github",
    providers: Optional[List[str]] = None,
) -> WorkflowResult:
    """Run status workflow for specified services.

    Gathers status information from GitHub or GitLab and stores results
    for agent context.

    Args:
        services: List of service names to check
        platform: Platform to check ("github" or "gitlab")
        providers: Provider filters for GitLab (e.g., ["Azure", "Core"])

    Returns:
        WorkflowResult with status data
    """
    workflow_start = datetime.now()
    start_time = asyncio.get_event_loop().time()

    logger.info(
        f"Status workflow for services: {', '.join(services)} "
        f"(platform: {platform}, providers: {providers})"
    )

    with tracer.start_as_current_span("status_workflow") as span:
        span.set_attribute("services", ",".join(services))
        span.set_attribute("platform", platform)
        if providers:
            span.set_attribute("providers", ",".join(providers))

        try:
            # Import here to avoid circular dependency
            from spi_agent.config import AgentConfig
            from spi_agent.copilot.runners.status_runner import StatusRunner

            is_gitlab = platform == "gitlab"

            # Create status runner
            runner = StatusRunner(None, services, providers if is_gitlab else None)

            # Get status data using direct API client
            if is_gitlab:
                from spi_agent.gitlab.direct_client import GitLabDirectClient
                agent_config = AgentConfig()
                direct_client = GitLabDirectClient(agent_config)
                status_data = await direct_client.get_all_status(
                    services,
                    providers or ["Azure", "Core"]
                )
            else:
                from spi_agent.github.direct_client import GitHubDirectClient
                agent_config = AgentConfig()
                direct_client = GitHubDirectClient(agent_config)
                status_data = await direct_client.get_all_status(services)

            # Display the status (visual output for user)
            runner.display_status(status_data)

            # Extract PR/MR and issue status for agent context
            pr_status_by_service: Dict[str, Dict[str, Any]] = {}
            total_open_prs = 0
            total_open_issues = 0
            total_workflows_needing_approval = 0
            prs_with_pending_workflows: List[Dict[str, Any]] = []

            # Get services data from the response structure
            services_data = status_data.get("services", {})

            for service_name, service_data in services_data.items():
                if not service_data or service_data.get("error"):
                    continue

                # Direct client returns structured data: {"items": [...]} for issues/PRs
                issues_data = service_data.get("issues", {})
                issues = issues_data.get("items", [])
                open_issues = len(issues)

                prs_key = "pull_requests" if not is_gitlab else "merge_requests"
                prs_data = service_data.get(prs_key, {})
                prs = prs_data.get("items", [])
                open_prs = len(prs)

                total_open_issues += open_issues
                total_open_prs += open_prs

                # Track issue details
                issue_details = []
                for issue in issues:
                    issue_number = issue.get("number" if not is_gitlab else "iid")
                    issue_title = issue.get("title", "")
                    issue_labels = issue.get("labels", [])
                    issue_assignees = issue.get("assignees", [])

                    issue_details.append({
                        "number": issue_number,
                        "title": issue_title,
                        "labels": issue_labels,
                        "assignees": issue_assignees,
                    })

                # Track all PRs/MRs with their details
                pr_details = []
                for pr in prs:
                    pr_number = pr.get("number" if not is_gitlab else "iid")
                    pr_title = pr.get("title", "")
                    pr_state = pr.get("state")
                    is_draft = pr.get("is_draft" if not is_gitlab else "draft", False)

                    # Build PR detail dict with common fields
                    pr_detail = {
                        "number": pr_number,
                        "title": pr_title,
                        "state": pr_state,
                        "is_draft": is_draft,
                    }

                    # GitHub: Check for workflows needing approval
                    if not is_gitlab:
                        workflows = service_data.get("workflows", {}).get("recent", [])
                        workflows_needing_approval = sum(
                            1 for w in workflows if w.get("conclusion") == "action_required"
                        )
                        pr_detail["workflows_pending"] = workflows_needing_approval

                        if workflows_needing_approval > 0:
                            total_workflows_needing_approval += workflows_needing_approval
                            prs_with_pending_workflows.append({
                                "service": service_name,
                                "pr_number": pr_number,
                                "workflows_pending": workflows_needing_approval,
                            })

                    # Store ALL PRs, not just ones with pending workflows
                    pr_details.append(pr_detail)

                pr_status_by_service[service_name] = {
                    "open_prs": open_prs,
                    "open_issues": open_issues,
                    "pr_details": pr_details,
                    "issue_details": issue_details,
                    "workflows_needing_approval": sum(
                        p.get("workflows_pending", 0) for p in pr_details
                    ) if not is_gitlab else 0,
                }

            # Build summary
            if is_gitlab:
                summary = (
                    f"GitLab status for {len(services)} service(s): "
                    f"{total_open_issues} open issues, {total_open_prs} open MRs"
                )
            else:
                summary = (
                    f"GitHub status for {len(services)} service(s): "
                    f"{total_open_issues} open issues, {total_open_prs} open PRs"
                )
                if total_workflows_needing_approval > 0:
                    summary += f", {total_workflows_needing_approval} workflow(s) need approval"

            # Create workflow result
            result = WorkflowResult(
                workflow_type="status",
                timestamp=workflow_start,
                services=services,
                status="success",
                summary=summary,
                detailed_results={
                    "platform": platform,
                    "providers": providers,
                    "status_data": status_data,
                    "prs_with_pending_workflows": prs_with_pending_workflows,
                },
                pr_status=pr_status_by_service,
            )

            # Store result for agent context
            result_store = get_result_store()
            await result_store.store(result)
            logger.info(f"Stored status workflow result: {summary}")

            # Record workflow metrics
            duration = asyncio.get_event_loop().time() - start_time
            record_workflow_run(
                workflow_type="status",
                duration=duration,
                status="success",
                service_count=len(services),
            )

            span.set_attribute("total_open_prs", total_open_prs)
            span.set_attribute("total_open_issues", total_open_issues)
            span.set_attribute("workflows_needing_approval", total_workflows_needing_approval)
            span.set_attribute("status", "success")

            return result

        except Exception as e:
            logger.error(f"Status workflow failed: {e}")
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))

            # Create error result
            result = WorkflowResult(
                workflow_type="status",
                timestamp=workflow_start,
                services=services,
                status="error",
                summary=f"Status workflow failed: {str(e)[:100]}",
                detailed_results={
                    "error": str(e),
                    "platform": platform,
                    "providers": providers,
                },
                pr_status={},
            )

            # Store error result
            result_store = get_result_store()
            await result_store.store(result)

            # Record failed workflow
            duration = asyncio.get_event_loop().time() - start_time
            record_workflow_run(
                workflow_type="status",
                duration=duration,
                status="error",
                service_count=len(services),
            )

            raise
