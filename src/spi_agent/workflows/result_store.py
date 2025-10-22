"""Workflow result store for maintaining context across agent interactions.

This module provides structured storage for workflow outputs, enabling the agent
to access detailed results from slash commands executed in interactive mode.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    """Result from a workflow execution.

    Attributes:
        workflow_type: Type of workflow (vulns, test, status, fork)
        timestamp: When the workflow was executed
        services: List of services processed
        status: Overall status (success, error, partial)
        summary: Brief summary of the workflow results
        detailed_results: Full structured data from workflow execution
        vulnerabilities: Vulnerability counts by service (vulns-specific)
        cve_analysis: CVE analysis report (vulns-specific)
        test_results: Test execution results (test-specific)
        pr_status: Pull request status information (status-specific)
        fork_status: Fork operation status (fork-specific)
    """

    workflow_type: str
    timestamp: datetime
    services: List[str]
    status: str
    summary: str
    detailed_results: Dict[str, Any]

    # Triage-specific fields
    vulnerabilities: Optional[Dict[str, Dict[str, int]]] = None
    cve_analysis: Optional[str] = None

    # Test-specific fields
    test_results: Optional[Dict[str, Dict[str, Any]]] = None

    # Status-specific fields
    pr_status: Optional[Dict[str, Dict[str, Any]]] = None

    # Fork-specific fields
    fork_status: Optional[Dict[str, str]] = None


class WorkflowResultStore:
    """Thread-safe store for workflow results.

    This store maintains recent workflow execution results, allowing the agent
    to access detailed information about slash commands executed in interactive mode.

    The store automatically limits the number of stored results to prevent
    unbounded memory growth.
    """

    def __init__(self, max_results_per_type: int = 10):
        """Initialize the workflow result store.

        Args:
            max_results_per_type: Maximum number of results to keep per workflow type
        """
        self._results: List[WorkflowResult] = []
        self._lock = asyncio.Lock()
        self._max_results_per_type = max_results_per_type

    async def store(self, result: WorkflowResult) -> None:
        """Store a workflow result.

        Args:
            result: WorkflowResult to store
        """
        async with self._lock:
            self._results.append(result)
            logger.debug(
                f"Stored {result.workflow_type} workflow result for services: {', '.join(result.services)}"
            )

            # Cleanup old results
            self._cleanup()

    async def get_recent(
        self, workflow_type: Optional[str] = None, limit: int = 5
    ) -> List[WorkflowResult]:
        """Get recent workflow results.

        Args:
            workflow_type: Filter by workflow type (None for all types)
            limit: Maximum number of results to return

        Returns:
            List of WorkflowResult objects, most recent first
        """
        async with self._lock:
            results = self._results

            # Filter by workflow type if specified
            if workflow_type:
                results = [r for r in results if r.workflow_type == workflow_type]

            # Sort by timestamp (most recent first) and limit
            return sorted(results, key=lambda r: r.timestamp, reverse=True)[:limit]

    async def get_context_summary(self, limit: int = 3) -> str:
        """Generate a context summary for agent injection.

        This creates a markdown-formatted summary of recent workflow results
        that can be injected into the agent's context via middleware.

        Args:
            limit: Maximum number of recent results to include

        Returns:
            Markdown-formatted context summary
        """
        recent = await self.get_recent(limit=limit)

        logger.debug(f"[Context Summary] Found {len(recent)} recent workflow results")

        if not recent:
            return ""

        lines = ["## Recent Workflow Results"]
        lines.append("")
        lines.append("*The following workflow results are available for your reference:*")
        lines.append("")

        for result in recent:
            # Format timestamp
            time_str = result.timestamp.strftime("%H:%M:%S")

            lines.append(f"### {result.workflow_type.title()} - {time_str}")
            lines.append(f"**Services:** {', '.join(result.services)}")
            lines.append(f"**Status:** {result.status}")
            lines.append(f"**Summary:** {result.summary}")

            # Add workflow-specific details
            if result.workflow_type == "vulns" and result.vulnerabilities:
                lines.append("")
                lines.append("**Vulnerabilities Found:**")
                for svc, counts in result.vulnerabilities.items():
                    critical = counts.get("critical", 0)
                    high = counts.get("high", 0)
                    medium = counts.get("medium", 0)
                    lines.append(
                        f"- {svc}: {critical} critical, {high} high, {medium} medium"
                    )

                # Include CVE analysis if available
                if result.cve_analysis:
                    lines.append("")
                    lines.append("**CVE Analysis Summary:**")
                    # Extract first few lines of CVE analysis for context
                    cve_lines = result.cve_analysis.split("\n")[:10]
                    lines.extend([f"  {line}" for line in cve_lines if line.strip()])
                    if len(result.cve_analysis.split("\n")) > 10:
                        lines.append("  *(Full analysis available in detailed results)*")

            elif result.workflow_type == "test" and result.test_results:
                lines.append("")
                lines.append("**Test Results:**")
                for svc, results in result.test_results.items():
                    total_tests = results.get("total_tests", 0)
                    passed = results.get("passed", 0)
                    failed = results.get("failed", 0)
                    coverage_line = results.get("coverage_line", 0)
                    coverage_branch = results.get("coverage_branch", 0)
                    quality_grade = results.get("quality_grade")

                    # Build result line with grade and coverage
                    result_parts = [f"{total_tests} tests"]
                    if failed > 0:
                        result_parts.append(f"{failed} failed")

                    if coverage_line > 0:
                        result_parts.append(
                            f"coverage: {coverage_line}% line / {coverage_branch}% branch"
                        )

                    if quality_grade:
                        result_parts.append(f"**Grade: {quality_grade}**")

                    lines.append(f"- {svc}: {', '.join(result_parts)}")

            elif result.workflow_type == "status" and result.pr_status:
                lines.append("")
                lines.append("**Status Information:**")
                for svc, status in result.pr_status.items():
                    open_prs = status.get("open_prs", 0)
                    open_issues = status.get("open_issues", 0)
                    workflows_needing_approval = status.get("workflows_needing_approval", 0)
                    pr_details = status.get("pr_details", [])
                    issue_details = status.get("issue_details", [])

                    status_line = f"- {svc}: {open_prs} open PRs, {open_issues} open issues"
                    if workflows_needing_approval > 0:
                        status_line += f", {workflows_needing_approval} workflows need approval"
                    lines.append(status_line)

                    # Include details about ALL PRs (not just ones with pending workflows)
                    if pr_details:
                        for pr in pr_details:
                            pr_num = pr.get("number")
                            pr_title = pr.get("title", "")
                            pr_state = pr.get("state", "").upper()
                            is_draft = pr.get("is_draft", False)
                            workflows_pending = pr.get("workflows_pending", 0)

                            # Build PR description
                            pr_desc = f"  - PR #{pr_num}"
                            if is_draft:
                                pr_desc += " (DRAFT)"
                            pr_desc += f": {pr_title[:60]}"

                            # Add workflow status if relevant
                            if workflows_pending > 0:
                                pr_desc += f" ({workflows_pending} workflows pending)"

                            lines.append(pr_desc)

                    # Include issue details with labels and assignees
                    if issue_details:
                        for issue in issue_details:
                            issue_num = issue.get("number")
                            issue_title = issue.get("title", "")
                            labels = issue.get("labels", [])
                            assignees = issue.get("assignees", [])

                            # Build issue description
                            issue_desc = f"  - Issue #{issue_num}: {issue_title[:60]}"

                            # Add important labels
                            if "human-required" in labels:
                                issue_desc += " [HUMAN-REQUIRED]"

                            # Add assignee info
                            if assignees:
                                if "Copilot" in assignees or "copilot-swe-agent" in assignees:
                                    issue_desc += " (Assigned: Copilot)"
                                else:
                                    issue_desc += f" (Assigned: {', '.join(assignees)})"

                            lines.append(issue_desc)

            elif result.workflow_type == "fork" and result.fork_status:
                lines.append("")
                lines.append("**Fork Status:**")
                for svc, status in result.fork_status.items():
                    lines.append(f"- {svc}: {status}")

            lines.append("")
            lines.append("---")
            lines.append("")

        # Add usage note
        lines.append("*You can reference these results when answering user questions.*")
        lines.append("")

        return "\n".join(lines)

    def _cleanup(self) -> None:
        """Remove old results to prevent unbounded memory growth.

        Keeps at most max_results_per_type results for each workflow type.
        This method should be called while holding the lock.
        """
        # Group results by workflow type
        by_type: Dict[str, List[WorkflowResult]] = {}
        for result in self._results:
            if result.workflow_type not in by_type:
                by_type[result.workflow_type] = []
            by_type[result.workflow_type].append(result)

        # Keep only the most recent N results per type
        kept_results = []
        for workflow_type, results in by_type.items():
            sorted_results = sorted(results, key=lambda r: r.timestamp, reverse=True)
            kept_results.extend(sorted_results[: self._max_results_per_type])

        # Update the results list
        self._results = kept_results

        logger.debug(f"Cleanup: Kept {len(kept_results)} workflow results")

    async def clear(self, workflow_type: Optional[str] = None) -> None:
        """Clear workflow results.

        Args:
            workflow_type: Clear only results of this type (None clears all)
        """
        async with self._lock:
            if workflow_type:
                self._results = [r for r in self._results if r.workflow_type != workflow_type]
                logger.info(f"Cleared {workflow_type} workflow results")
            else:
                self._results.clear()
                logger.info("Cleared all workflow results")

    async def get_stats(self) -> Dict[str, Any]:
        """Get statistics about stored results.

        Returns:
            Dictionary with result statistics
        """
        async with self._lock:
            by_type: Dict[str, int] = {}
            for result in self._results:
                by_type[result.workflow_type] = by_type.get(result.workflow_type, 0) + 1

            return {
                "total_results": len(self._results),
                "by_type": by_type,
                "oldest_timestamp": (
                    min(r.timestamp for r in self._results) if self._results else None
                ),
                "newest_timestamp": (
                    max(r.timestamp for r in self._results) if self._results else None
                ),
            }
