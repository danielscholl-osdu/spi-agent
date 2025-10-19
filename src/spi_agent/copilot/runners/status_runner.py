"""Status runner for gathering GitHub repository information."""

import json
import logging
import os
import re
import select
import subprocess
import textwrap
import time
from datetime import datetime
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Dict, List, Optional, Union

from pydantic import ValidationError
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from spi_agent.copilot.base import BaseRunner
from spi_agent.copilot.base.runner import console
from spi_agent.copilot.config import config
from spi_agent.copilot.constants import SERVICES
from spi_agent.copilot.models import StatusResponse
from spi_agent.copilot.trackers import StatusTracker

logger = logging.getLogger(__name__)


class StatusRunner(BaseRunner):
    """Runs Copilot CLI to gather GitHub/GitLab status and displays results"""

    def __init__(self, prompt_file: Union[Path, Traversable], services: List[str], providers: Optional[List[str]] = None):
        self.providers = providers  # Optional providers for GitLab filtering (must be set before super().__init__)
        super().__init__(prompt_file, services)
        self.raw_output = []  # Keep full output for JSON extraction
        self.tracker = StatusTracker(services)
        self.log_handle = None  # File handle for incremental logging

    @property
    def log_prefix(self) -> str:
        """Return log file prefix for this runner type."""
        # Use status-glab prefix if providers specified (GitLab mode)
        if self.providers:
            return "status-glab"
        return "status"

    def load_prompt(self) -> str:
        """Load and augment prompt with arguments"""
        prompt = self.prompt_file.read_text(encoding="utf-8")

        # Replace organization placeholder with actual value from config
        prompt = prompt.replace("{{ORGANIZATION}}", config.organization)

        # Inject services argument
        services_arg = ",".join(self.services)
        augmented = f"{prompt}\n\nARGUMENTS:\nSERVICES: {services_arg}"

        # Inject providers argument if specified (for GitLab status)
        if self.providers:
            providers_arg = ",".join(self.providers)
            augmented += f"\nPROVIDERS: {providers_arg}"

        return augmented

    def parse_output(self, line: str) -> None:
        """Parse copilot output to track which services are being queried"""
        line_lower = line.lower()
        line_stripped = line.strip()

        # Detect task patterns - with or without ✓ marker
        for service in self.services:
            if service in line_lower:
                current_status = self.tracker.services[service]["status"]

                # Extract task description (remove ✓ if present)
                task_desc = line_stripped
                if task_desc.startswith("✓"):
                    task_desc = task_desc[1:].strip()
                task_desc_lower = task_desc.lower()

                # Match task patterns - check for "Get {service} {data_type}"
                # Examples: "Get partition issues", "Get legal pull requests", etc.
                if task_desc.startswith(("Get ", "Check ")):
                    # This is a task line (with or without ✓)
                    if "check" in task_desc_lower and "repository" in task_desc_lower:
                        self.tracker.update(service, "querying", "Checking repository")
                    elif "issue" in task_desc_lower:
                        self.tracker.update(service, "querying", "Getting issues")
                    elif "pull request" in task_desc_lower or "pull_request" in task_desc_lower:
                        self.tracker.update(service, "querying", "Getting pull requests")
                    elif "workflow" in task_desc_lower:
                        self.tracker.update(service, "querying", "Getting workflows")

                # Also catch lines that start with ✓ but don't start with Get/Check
                elif line_stripped.startswith("✓"):
                    if "issue" in task_desc_lower and "get" in task_desc_lower:
                        self.tracker.update(service, "querying", "Getting issues")
                    elif "pull" in task_desc_lower and "get" in task_desc_lower:
                        self.tracker.update(service, "querying", "Getting pull requests")
                    elif "workflow" in task_desc_lower and "get" in task_desc_lower:
                        self.tracker.update(service, "querying", "Getting workflows")

                # Detect narrative updates
                if "gathering data for" in line_lower or "querying" in line_lower:
                    self.tracker.update(service, "querying", "Gathering data")
                elif "completed" in line_lower and "successfully" in line_lower:
                    self.tracker.update(service, "gathered", "Data collected")
                elif "error" in line_lower or "failed" in line_lower:
                    if "check" not in line_lower:  # Ignore "checking for errors"
                        self.tracker.update(service, "error", "Failed to gather data")

    def extract_json(self, output: str) -> Optional[Dict]:
        """Extract JSON from copilot output (may be wrapped in markdown or shell commands)"""
        # First check for heredoc patterns (cat << 'EOF' ... EOF)
        heredoc_match = re.search(r"cat\s*<<\s*['\"]?EOF['\"]?\s*\n(.*?)\n\s*EOF", output, re.DOTALL)
        if heredoc_match:
            data = self._parse_json_candidate(heredoc_match.group(1), "heredoc")
            if data:
                return data

        # Check for $ cat << 'EOF' pattern with indentation
        shell_heredoc = re.search(r"\$\s*cat\s*<<\s*['\"]?EOF['\"]?\s*\n(.*?)\n\s*EOF", output, re.DOTALL)
        if shell_heredoc:
            data = self._parse_json_candidate(shell_heredoc.group(1), "shell heredoc")
            if data:
                return data

        # Check for JSON preceded by a bullet point (●)
        bullet_json = re.search(r'●\s*(\{.*?\n\s*\})', output, re.DOTALL)
        if bullet_json:
            data = self._parse_json_candidate(bullet_json.group(1), "bullet point JSON")
            if data:
                return data

        # Prefer explicit JSON code fences if present
        code_blocks = re.findall(r'```(?:json)?\s*\n(.*?)\n\s*```', output, re.DOTALL)
        for block in code_blocks:
            data = self._parse_json_candidate(block, "code fence")
            if data:
                return data

        # Fallback: scan for the first balanced JSON object in the output
        data = self._scan_for_json_object(output, "brace scan")
        if data:
            return data

        # Backwards compatibility: look for a block that clearly contains services/projects data
        json_match = re.search(r'(\{[\s\S]*?"(?:services|projects)"[\s\S]*?\})\s*$', output, re.MULTILINE)
        if json_match:
            data = self._parse_json_candidate(json_match.group(1), '"services/projects" fallback')
            if data:
                return data

        # Last resort: treat entire output as JSON
        data = self._parse_json_candidate(output, "entire output")
        if data:
            return data

        logger.warning("Could not extract JSON from any known format")
        return None

    def _parse_json_candidate(self, candidate: str, context: str) -> Optional[Dict]:
        """Attempt to load a JSON object, repairing wrapped strings if needed."""
        candidate = textwrap.dedent(candidate).strip()
        if not candidate:
            return None

        attempts = [candidate]
        repaired = self._fix_wrapped_strings(candidate)
        if repaired != candidate:
            attempts.append(repaired)

        last_error: Optional[json.JSONDecodeError] = None
        for attempt in attempts:
            try:
                data = json.loads(attempt)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError as exc:
                last_error = exc

        if last_error:
            logger.debug(f"{context} JSON parse failed: {last_error}")
        return None

    @staticmethod
    def _fix_wrapped_strings(text: str) -> str:
        """Collapse soft-wrapped lines inside JSON string literals."""
        result: List[str] = []
        in_string = False
        escape = False
        i = 0
        length = len(text)

        while i < length:
            ch = text[i]

            if in_string:
                if escape:
                    result.append(ch)
                    escape = False
                elif ch == '\\':
                    result.append(ch)
                    escape = True
                elif ch == '"':
                    result.append(ch)
                    in_string = False
                elif ch == '\n':
                    result.append(' ')
                    i += 1
                    while i < length and text[i] in (' ', '\t'):
                        i += 1
                    continue
                else:
                    result.append(ch)
            else:
                if ch == '"':
                    in_string = True
                result.append(ch)

            if not in_string and ch != '\\':
                escape = False

            i += 1

        return ''.join(result)

    def _scan_for_json_object(self, text: str, context: str) -> Optional[Dict]:
        """Search for a balanced JSON object within arbitrary text."""
        start = text.find('{')
        while start != -1:
            brace_count = 0
            for idx in range(start, len(text)):
                char = text[idx]
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        chunk = text[start:idx + 1]
                        data = self._parse_json_candidate(chunk, context)
                        if data:
                            return data
                        break
            start = text.find('{', start + 1)
        return None

    def display_status(self, data: Dict):
        """Display GitHub/GitLab status in beautiful Rich format"""

        if not data:
            console.print("[red]Error:[/red] No status data received", style="bold red")
            return

        # Handle different possible structures
        # GitLab uses "projects", GitHub uses "services"
        if "services" in data:
            services_data = data["services"]
            timestamp = data.get("timestamp", datetime.now().isoformat())
            is_gitlab = False
        elif "projects" in data:
            services_data = data["projects"]
            timestamp = data.get("timestamp", datetime.now().isoformat())
            is_gitlab = True
        elif all(key in SERVICES for key in data.keys() if key != "timestamp"):
            # Data is structured as {service_name: {...}, service_name: {...}}
            services_data = {k: v for k, v in data.items() if k != "timestamp"}
            timestamp = data.get("timestamp", datetime.now().isoformat())
            is_gitlab = False
        else:
            console.print(f"[red]Error:[/red] Unexpected data structure. Keys found: {list(data.keys())}", style="bold red")
            console.print(f"[dim]Data preview: {str(data)[:500]}...[/dim]")
            return

        # For GitLab: Collect pipelines from each MR (new structure)
        # Pipelines are now stored per-MR instead of globally
        mr_pipelines = {}  # service_name -> list of (mr_iid, pipeline) tuples
        if is_gitlab:
            for service_name, service_data in services_data.items():
                pipelines_list = []
                prs = service_data.get("merge_requests", {}).get("items", [])
                for pr in prs:
                    mr_iid = pr.get("iid")
                    mr_pipelines_data = pr.get("pipelines", [])
                    for pipeline in mr_pipelines_data:
                        pipelines_list.append((mr_iid, pipeline))
                mr_pipelines[service_name] = pipelines_list

        # Summary Table
        table_title = "📊 GitLab Status Summary" if is_gitlab else "📊 GitHub Status Summary"
        summary_table = Table(title=table_title, expand=True)
        summary_table.add_column("Service", style="cyan", no_wrap=True)
        summary_table.add_column("Issues", style="yellow")

        if is_gitlab:
            summary_table.add_column("MRs", style="magenta")
            summary_table.add_column("Pipelines", style="blue")
        else:
            summary_table.add_column("PRs", style="magenta")
            summary_table.add_column("Workflows", style="blue")

        summary_table.add_column("Last Update", style="dim")

        for service_name, service_data in services_data.items():
            # GitHub has "repo" key, GitLab now just has direct data
            if not is_gitlab:
                repo_or_project = service_data.get("repo", {})
                if not repo_or_project.get("exists", False):
                    summary_table.add_row(
                        f"✗ {service_name}",
                        "[dim]N/A[/dim]",
                        "[dim]N/A[/dim]",
                        "[dim]N/A[/dim]",
                        "[red]Not found[/red]"
                    )
                    continue
            else:
                # For GitLab, if service is in output, it exists
                repo_or_project = {"exists": True}

            issues_count = service_data.get("issues", {}).get("count", 0)
            prs_count = service_data.get("merge_requests" if is_gitlab else "pull_requests", {}).get("count", 0)

            # Workflow/Pipeline status - check recent runs
            if is_gitlab:
                # For GitLab: Use pipelines from MRs (already collected)
                workflows = [p for _, p in mr_pipelines.get(service_name, [])]
            else:
                # For GitHub: Use global workflows list
                workflows = service_data.get("workflows", {}).get("recent", [])

            if workflows:
                if is_gitlab:
                    # GitLab pipelines - status field only (no conclusion)
                    running = sum(1 for w in workflows if w.get("status") in ["running", "pending", "created"])
                    failed = sum(1 for w in workflows if w.get("status") == "failed")
                    success = sum(1 for w in workflows if w.get("status") == "success")
                    canceled = sum(1 for w in workflows if w.get("status") in ["canceled", "skipped"])

                    if running > 0:
                        workflow_display = f"[yellow]▶ {running} running[/yellow]"
                    elif failed > 0:
                        workflow_display = f"[red]✗ {failed} failed[/red]"
                    elif success > 0:
                        workflow_display = f"[green]✓ {success} ok[/green]"
                    elif canceled > 0:
                        workflow_display = f"[yellow]⊘ {canceled} canceled[/yellow]"
                    else:
                        workflow_display = f"[dim]{len(workflows)} runs[/dim]"
                else:
                    # GitHub workflows - status + conclusion
                    # Note: action_required is a CONCLUSION, not a status
                    needs_approval = sum(1 for w in workflows if w.get("conclusion") == "action_required")
                    running = sum(1 for w in workflows if w.get("status") in ["in_progress", "queued", "waiting"])
                    completed = sum(1 for w in workflows if w.get("status") == "completed" and w.get("conclusion") == "success")
                    failed = sum(1 for w in workflows if w.get("status") == "completed" and w.get("conclusion") in ["failure", "cancelled"])

                    if needs_approval > 0:
                        workflow_display = f"[red]⊙ {needs_approval} need approval[/red]"
                    elif running > 0:
                        workflow_display = f"[yellow]▶ {running} running[/yellow]"
                    elif failed > 0:
                        workflow_display = f"[red]✗ {failed} failed[/red]"
                    elif completed > 0:
                        workflow_display = f"[green]✓ {completed} ok[/green]"
                    else:
                        workflow_display = f"[dim]{len(workflows)} runs[/dim]"
            else:
                workflow_display = "[dim]None[/dim]"

            # Last update - GitHub has it in repo, GitLab doesn't have it in simplified structure
            if not is_gitlab:
                updated_at = repo_or_project.get("updated_at", "")
                if updated_at:
                    try:
                        update_time = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                        now = datetime.now(update_time.tzinfo)
                        delta = now - update_time
                        if delta.seconds < 3600:
                            time_ago = f"{delta.seconds // 60}m ago"
                        else:
                            time_ago = f"{delta.seconds // 3600}h ago"
                    except:
                        time_ago = "recently"
                else:
                    time_ago = "unknown"
            else:
                # GitLab simplified structure doesn't include last_activity_at
                time_ago = "N/A"

            summary_table.add_row(
                f"✓ {service_name}",
                f"{issues_count} open" if issues_count > 0 else "[dim]0[/dim]",
                f"{prs_count}" if prs_count > 0 else "[dim]0[/dim]",
                workflow_display,
                time_ago
            )

        console.print(summary_table)
        console.print()

        # Open Issues with grouping (MOVED BEFORE PRs)
        issue_groups = {}  # Group issues by title to detect duplicates
        for service_name, service_data in services_data.items():
            issues = service_data.get("issues", {}).get("items", [])
            for issue in issues:
                title = issue.get("title", "")
                if title not in issue_groups:
                    # Handle both GitHub (number) and GitLab (iid) field names
                    issue_number = issue.get("iid" if is_gitlab else "number")
                    issue_groups[title] = {
                        "number": issue_number,
                        "labels": issue.get("labels", []),
                        "assignees": issue.get("assignees", []),
                        "services": []
                    }
                issue_groups[title]["services"].append(service_name)

        if issue_groups:
            issue_content = []
            for title, data in issue_groups.items():
                labels = ", ".join(data["labels"]) if data["labels"] else ""
                services = ", ".join(data["services"])
                assignees = ", ".join(data["assignees"]) if data["assignees"] else "Unassigned"

                # Highlight human-required issues
                if "human-required" in data["labels"]:
                    issue_content.append(f"[bold red]#{data['number']}[/bold red] {title}")
                    issue_content.append("   [red]⚠ Requires manual intervention[/red]")
                else:
                    issue_content.append(f"[yellow]#{data['number']}[/yellow] {title}")

                if len(data["services"]) > 1:
                    issue_content.append(f"   Affects: [cyan]{services}[/cyan]")
                else:
                    issue_content.append(f"   Service: [cyan]{services}[/cyan]")

                # Show assignees
                if data["assignees"]:
                    # Highlight Copilot assignments
                    if "Copilot" in assignees or "copilot-swe-agent" in assignees:
                        issue_content.append(f"   Assigned: [blue]🤖 {assignees}[/blue]")
                    else:
                        issue_content.append(f"   Assigned: [dim]{assignees}[/dim]")
                else:
                    issue_content.append(f"   Assigned: [dim]None[/dim]")

                if labels:
                    issue_content.append(f"   Labels: [dim]{labels}[/dim]")
                issue_content.append("")

            console.print(Panel(
                "\n".join(issue_content),
                title="📝 Open Issues",
                border_style="yellow"
            ))
            console.print()

        # Open PRs/MRs Panel - Show all open PRs/MRs with details
        all_prs = []
        release_prs = []  # Track release PRs separately for "Next Steps"
        for service_name, service_data in services_data.items():
            prs_key = "merge_requests" if is_gitlab else "pull_requests"
            prs = service_data.get(prs_key, {}).get("items", [])
            for pr in prs:
                all_prs.append((service_name, pr))
                if pr.get("is_release", False):
                    release_prs.append((service_name, pr))

        if all_prs:
            pr_content = []
            for service_name, pr in all_prs:
                # Handle both GitHub (number, is_draft) and GitLab (iid, draft) field names
                if is_gitlab:
                    pr_number = pr.get("iid")
                    is_draft = pr.get("draft", False)
                    branch = pr.get("source_branch", "unknown")
                else:
                    pr_number = pr.get("number")
                    is_draft = pr.get("is_draft", False)
                    branch = pr.get("headRefName", "unknown")

                title = pr.get("title", "")
                state = pr.get("state", "unknown").upper()
                is_release = pr.get("is_release", False)
                author = pr.get("author", "unknown")

                # Detect Copilot authorship
                is_copilot_pr = "copilot" in branch.lower() or author == "app/copilot-swe-agent"

                # Format title with state indicator
                # Use ! prefix for GitLab MRs, # for GitHub PRs
                pr_prefix = "!" if is_gitlab else "#"
                if is_draft:
                    pr_content.append(f"[yellow]{pr_prefix}{pr_number}[/yellow] [dim](Draft)[/dim] {title}")
                elif is_release:
                    pr_content.append(f"[magenta]{pr_prefix}{pr_number}[/magenta] [bold]🚀 {title}[/bold]")
                else:
                    pr_content.append(f"[cyan]{pr_prefix}{pr_number}[/cyan] {title}")

                # Show author for all PRs
                if is_copilot_pr:
                    pr_content.append(f"   Author: [blue]🤖 Copilot[/blue]")
                else:
                    pr_content.append(f"   Author: [dim]{author}[/dim]")

                # Show state and branch
                state_display = f"[yellow]{state}[/yellow]" if is_draft else f"[green]{state}[/green]"
                pr_content.append(f"   State: {state_display} | Branch: [dim]{branch}[/dim]")

                # ONLY show workflow status for Copilot PRs (they require approval)
                if is_copilot_pr:
                    pr_head_sha = pr.get("headRefOid")
                    workflows = service_data.get("workflows", {}).get("recent", [])

                    # Match workflows to this specific PR by commit SHA
                    if pr_head_sha:
                        pr_workflows = [w for w in workflows if w.get("headSha") == pr_head_sha]

                        if pr_workflows:
                            needs_approval = sum(1 for w in pr_workflows if w.get("conclusion") == "action_required")
                            running = sum(1 for w in pr_workflows if w.get("status") in ["in_progress", "queued", "waiting"])
                            passed = sum(1 for w in pr_workflows if w.get("status") == "completed" and w.get("conclusion") == "success")

                            if needs_approval > 0:
                                pr_content.append(f"   Workflows: [red bold]⊙ {needs_approval} need approval[/red bold]")
                            elif running > 0:
                                pr_content.append(f"   Workflows: [yellow]▶ {running} running[/yellow]")
                            elif passed > 0:
                                pr_content.append(f"   Workflows: [green]✓ {passed} passed[/green]")

                pr_content.append("")

            panel_title = "🔀 Open Merge Requests" if is_gitlab else "🔀 Open Pull Requests"
            console.print(Panel(
                "\n".join(pr_content),
                title=panel_title,
                border_style="magenta"
            ))
            console.print()

        # Workflow/Pipeline Details Section
        # Note: mr_pipelines is already collected earlier for GitLab (line 256-268)

        # Check if there are any workflows/pipelines to display
        if is_gitlab:
            # For GitLab, check if there are any MR pipelines
            has_workflows = any(len(mr_pipelines.get(service_name, [])) > 0
                               for service_name in services_data.keys())
        else:
            # For GitHub, check if there are any workflows
            has_workflows = any(
                len(service_data.get("workflows", {}).get("recent", [])) > 0
                for service_data in services_data.values()
            )

        if has_workflows:
            table_title = "⚙️ MR Pipeline Runs" if is_gitlab else "⚙️ Recent Workflow Runs"
            workflow_table = Table(title=table_title, expand=True)
            workflow_table.add_column("Service", style="cyan", no_wrap=True)
            workflow_table.add_column("Workflow", style="white")
            workflow_table.add_column("Status", style="magenta")
            workflow_table.add_column("When", style="dim")

            for service_name, service_data in services_data.items():
                # Get workflows/pipelines
                if is_gitlab:
                    # For GitLab: Use MR-specific pipelines (already collected)
                    mr_pipeline_tuples = mr_pipelines.get(service_name, [])
                    workflows = [p for _, p in mr_pipeline_tuples]
                    # Create mapping of pipeline to MR IID for display
                    pipeline_to_mr = {p.get("id"): mr_iid for mr_iid, p in mr_pipeline_tuples}
                else:
                    # For GitHub: Use global workflows list
                    workflows = service_data.get("workflows", {}).get("recent", [])
                    pipeline_to_mr = {}

                if workflows:
                    for idx, workflow in enumerate(workflows[:10]):  # Show up to 10 MR-related pipelines
                        created = workflow.get("created_at", "")

                        if is_gitlab:
                            # GitLab pipelines - simpler status (no conclusion)
                            pipeline_id = workflow.get('id', 'Unknown')

                            # Show which MR this pipeline belongs to
                            mr_iid = pipeline_to_mr.get(pipeline_id)
                            mr_indicator = f" (MR !{mr_iid})" if mr_iid else ""

                            name = f"Pipeline #{pipeline_id}{mr_indicator}"
                            status = workflow.get("status", "unknown")

                            if status == "success":
                                status_display = "[green]✓ success[/green]"
                            elif status == "failed":
                                status_display = "[red]✗ failed[/red]"
                            elif status in ["running", "pending", "created"]:
                                status_display = f"[yellow]▶ {status}[/yellow]"
                            elif status in ["canceled", "skipped"]:
                                status_display = f"[yellow]⊘ {status}[/yellow]"
                            else:
                                status_display = f"[dim]{status}[/dim]"
                        else:
                            # GitHub workflows - status + conclusion
                            name = workflow.get("name", "Unknown")
                            status = workflow.get("status", "unknown")
                            conclusion = workflow.get("conclusion", "")

                            # Format status
                            # Note: action_required is a CONCLUSION, not a status
                            if conclusion == "action_required":
                                status_display = "[red bold]⊙ action_required[/red bold]"
                            elif status == "completed":
                                if conclusion == "success":
                                    status_display = "[green]✓ success[/green]"
                                elif conclusion == "failure":
                                    status_display = "[red]✗ failed[/red]"
                                elif conclusion == "cancelled":
                                    status_display = "[yellow]⊘ cancelled[/yellow]"
                                elif conclusion == "skipped":
                                    status_display = "[dim]⊘ skipped[/dim]"
                                else:
                                    status_display = f"[dim]{conclusion or 'completed'}[/dim]"
                            elif status in ["in_progress", "queued", "waiting"]:
                                status_display = f"[yellow]▶ {status}[/yellow]"
                            else:
                                status_display = f"[dim]{status}[/dim]"

                        # Format time
                        try:
                            created_time = datetime.fromisoformat(created.replace('Z', '+00:00'))
                            now = datetime.now(created_time.tzinfo)
                            delta = now - created_time
                            if delta.seconds < 3600:
                                time_str = f"{delta.seconds // 60}m ago"
                            elif delta.seconds < 86400:
                                time_str = f"{delta.seconds // 3600}h ago"
                            else:
                                time_str = f"{delta.days}d ago"
                        except:
                            time_str = "recently"

                        workflow_table.add_row(
                            service_name if idx == 0 else "",
                            name,
                            status_display,
                            time_str
                        )

            console.print(workflow_table)
            console.print()

        # Failed Pipeline Jobs Section (GitLab only)
        if is_gitlab:
            # Collect all failed pipelines with jobs
            failed_pipeline_jobs = []
            for service_name in services_data.keys():
                mr_pipeline_tuples = mr_pipelines.get(service_name, [])
                for mr_iid, pipeline in mr_pipeline_tuples:
                    if pipeline.get("status") == "failed" and pipeline.get("jobs"):
                        failed_pipeline_jobs.append({
                            "service": service_name,
                            "mr_iid": mr_iid,
                            "pipeline": pipeline
                        })

            if failed_pipeline_jobs:
                # Display failed pipeline jobs grouped by stage
                for item in failed_pipeline_jobs:
                    service_name = item["service"]
                    mr_iid = item["mr_iid"]
                    pipeline = item["pipeline"]
                    pipeline_id = pipeline.get("id")
                    jobs = pipeline.get("jobs", [])

                    # Create job table grouped by stage
                    job_table = Table(
                        title=f"❌ Failed Jobs - {service_name} Pipeline #{pipeline_id} (MR !{mr_iid})",
                        expand=False
                    )
                    job_table.add_column("Stage", style="cyan", no_wrap=True)
                    job_table.add_column("Job Name", style="white")
                    job_table.add_column("Status", style="magenta", justify="center")
                    job_table.add_column("Duration", style="dim", justify="right")

                    # Group jobs by stage and sort
                    stage_order = ["review", "build", "csp-build", "coverage", "containerize", "scan", "deploy", "integration", "acceptance", "publish"]
                    jobs_by_stage = {}
                    for job in jobs:
                        stage = job.get("stage", "unknown")
                        if stage not in jobs_by_stage:
                            jobs_by_stage[stage] = []
                        jobs_by_stage[stage].append(job)

                    # Sort stages by predefined order, with unknown stages at end
                    sorted_stages = sorted(
                        jobs_by_stage.keys(),
                        key=lambda s: stage_order.index(s) if s in stage_order else 999
                    )

                    # Separate parent and downstream jobs
                    parent_jobs = [j for j in jobs if not j.get("is_downstream", False)]
                    downstream_jobs = [j for j in jobs if j.get("is_downstream", False)]

                    # Display parent jobs first
                    if parent_jobs:
                        # Group parent jobs by stage
                        parent_by_stage = {}
                        for job in parent_jobs:
                            stage = job.get("stage", "unknown")
                            if stage not in parent_by_stage:
                                parent_by_stage[stage] = []
                            parent_by_stage[stage].append(job)

                        sorted_parent_stages = sorted(
                            parent_by_stage.keys(),
                            key=lambda s: stage_order.index(s) if s in stage_order else 999
                        )

                        for stage_idx, stage in enumerate(sorted_parent_stages):
                            stage_jobs = parent_by_stage[stage]
                            for job_idx, job in enumerate(stage_jobs):
                                job_name = job.get("name", "Unknown")
                                status = job.get("status", "unknown")
                                duration = job.get("duration", 0)

                                # Format status
                                if status == "success":
                                    status_display = "[green]✓ success[/green]"
                                elif status == "failed":
                                    status_display = "[red]✗ failed[/red]"
                                elif status == "canceled":
                                    status_display = "[yellow]⊘ canceled[/yellow]"
                                elif status == "skipped":
                                    status_display = "[dim]⊘ skipped[/dim]"
                                elif status in ["running", "pending"]:
                                    status_display = f"[yellow]▶ {status}[/yellow]"
                                else:
                                    status_display = f"[dim]{status}[/dim]"

                                # Format duration
                                if duration:
                                    if duration < 60:
                                        duration_str = f"{duration}s"
                                    elif duration < 3600:
                                        duration_str = f"{duration // 60}m {duration % 60}s"
                                    else:
                                        duration_str = f"{duration // 3600}h {(duration % 3600) // 60}m"
                                else:
                                    duration_str = "-"

                                stage_display = stage if job_idx == 0 else ""

                                job_table.add_row(
                                    stage_display,
                                    job_name,
                                    status_display,
                                    duration_str
                                )

                    # Add separator and downstream jobs if present
                    if downstream_jobs:
                        # Add a visual separator
                        job_table.add_row(
                            "[cyan]───[/cyan]",
                            "[cyan]Downstream Pipeline Jobs ───────────────────[/cyan]",
                            "[cyan]───[/cyan]",
                            "[cyan]───[/cyan]"
                        )

                        # Group downstream jobs by stage
                        downstream_by_stage = {}
                        for job in downstream_jobs:
                            stage = job.get("stage", "unknown")
                            if stage not in downstream_by_stage:
                                downstream_by_stage[stage] = []
                            downstream_by_stage[stage].append(job)

                        sorted_downstream_stages = sorted(
                            downstream_by_stage.keys(),
                            key=lambda s: stage_order.index(s) if s in stage_order else 999
                        )

                        for stage_idx, stage in enumerate(sorted_downstream_stages):
                            stage_jobs = downstream_by_stage[stage]
                            for job_idx, job in enumerate(stage_jobs):
                                job_name = "  " + job.get("name", "Unknown")  # Indent downstream jobs
                                status = job.get("status", "unknown")
                                duration = job.get("duration", 0)

                                # Format status
                                if status == "success":
                                    status_display = "[green]✓ success[/green]"
                                elif status == "failed":
                                    status_display = "[red]✗ failed[/red]"
                                elif status == "canceled":
                                    status_display = "[yellow]⊘ canceled[/yellow]"
                                elif status == "skipped":
                                    status_display = "[dim]⊘ skipped[/dim]"
                                elif status in ["running", "pending"]:
                                    status_display = f"[yellow]▶ {status}[/yellow]"
                                else:
                                    status_display = f"[dim]{status}[/dim]"

                                # Format duration
                                if duration:
                                    if duration < 60:
                                        duration_str = f"{duration}s"
                                    elif duration < 3600:
                                        duration_str = f"{duration // 60}m {duration % 60}s"
                                    else:
                                        duration_str = f"{duration // 3600}h {(duration % 3600) // 60}m"
                                else:
                                    duration_str = "-"

                                stage_display = stage if job_idx == 0 else ""

                                job_table.add_row(
                                    stage_display,
                                    job_name,
                                    status_display,
                                    duration_str
                                )

                    console.print(job_table)
                    console.print()

        # Next Steps / Quick Actions
        next_steps = []

        # Check for human-required issues
        human_required = [
            (title, data) for title, data in issue_groups.items()
            if "human-required" in data.get("labels", [])
        ] if issue_groups else []

        if human_required:
            for title, data in human_required:
                services_str = ", ".join(data["services"])
                next_steps.append(f"[red]⚠[/red] Review issue #{data['number']}: {title[:50]}...")
                next_steps.append(f"  Services: {services_str}")

        # Check for release PRs
        if release_prs:
            next_steps.append(f"[magenta]🚀[/magenta] Review {len(release_prs)} release PR(s) for merging")

        # Check for workflows/pipelines needing attention
        workflows_key = "pipelines" if is_gitlab else "workflows"

        if is_gitlab:
            # GitLab pipelines - check for failed pipelines (from MR-specific data)
            failed_pipelines = {}
            failed_jobs_summary = {}
            running_count = 0

            for service_name in services_data.keys():
                mr_pipeline_tuples = mr_pipelines.get(service_name, [])
                pipelines = [p for _, p in mr_pipeline_tuples]

                failed = [p for p in pipelines if p.get("status") == "failed"]
                if failed:
                    failed_pipelines[service_name] = len(failed)

                    # Collect failed job stages for actionable guidance
                    for pipeline in failed:
                        if pipeline.get("jobs"):
                            for job in pipeline.get("jobs", []):
                                if job.get("status") == "failed":
                                    stage = job.get("stage", "unknown")
                                    if service_name not in failed_jobs_summary:
                                        failed_jobs_summary[service_name] = set()
                                    failed_jobs_summary[service_name].add(stage)

                running = [p for p in pipelines if p.get("status") in ["running", "pending", "created"]]
                running_count += len(running)

            if failed_pipelines:
                # Provide stage-specific guidance instead of generic message
                if failed_jobs_summary:
                    for service, stages in failed_jobs_summary.items():
                        stages_str = ", ".join(sorted(stages))
                        next_steps.append(f"[red]✗[/red] Review failed {stages_str} stage(s) in {service}")
                else:
                    # Fallback to generic message if no job details available
                    total_failed = sum(failed_pipelines.values())
                    services_list = ", ".join(failed_pipelines.keys())
                    next_steps.append(f"[red]✗ {total_failed} failed MR pipeline(s)[/red]")
                    next_steps.append(f"  Services: {services_list}")

            if running_count > 0:
                next_steps.append(f"[yellow]▶[/yellow] {running_count} MR pipeline(s) still running")
            elif not failed_pipelines:
                next_steps.append("[green]✓[/green] All MR pipelines completed successfully")
        else:
            # GitHub workflows - check for approval needed
            approval_needed = {}
            for service_name, service_data in services_data.items():
                workflows = service_data.get("workflows", {}).get("recent", [])
                # Note: action_required is a CONCLUSION, not a status
                needs_approval = sum(1 for w in workflows if w.get("conclusion") == "action_required")
                if needs_approval > 0:
                    approval_needed[service_name] = needs_approval

            if approval_needed:
                total_approval = sum(approval_needed.values())
                services_list = ", ".join(approval_needed.keys())
                next_steps.append(f"[red bold]⊙ {total_approval} workflow(s) need approval (manual)[/red bold]")
                next_steps.append(f"  Services: {services_list}")
                next_steps.append(f"  💡 Approve in GitHub UI for Copilot PRs to continue")

            # Check for running workflows
            total_running = sum(
                sum(1 for w in service_data.get("workflows", {}).get("recent", [])
                    if w.get("status") in ["in_progress", "queued", "waiting"])
                for service_data in services_data.values()
            )
            if total_running > 0:
                next_steps.append(f"[yellow]▶[/yellow] {total_running} workflow(s) still running")
            elif not approval_needed:
                next_steps.append("[green]✓[/green] All workflows completed")

        if next_steps:
            console.print(Panel(
                "\n".join(next_steps),
                title="💡 Next Steps",
                border_style="blue"
            ))
            console.print()

        # Timestamp footer
        console.print(f"[dim]Status retrieved at: {timestamp}[/dim]")
        console.print()

    def show_config(self):
        """Display run configuration"""
        if self.providers:
            # GitLab mode
            config = f"""[cyan]Projects:[/cyan]   {', '.join(self.services)}
[cyan]Providers:[/cyan]  {', '.join(self.providers)}
[cyan]Gathering:[/cyan]  Issues, Merge Requests, Pipelines"""
            title = "🔍 GitLab Status Check"
        else:
            # GitHub mode
            config = f"""[cyan]Services:[/cyan]   {', '.join(self.services)}
[cyan]Gathering:[/cyan]  Issues, PRs, Workflows"""
            title = "🔍 GitHub Status Check"

        console.print(Panel(config, title=title, border_style="blue"))
        console.print()

    def run(self) -> int:
        """Execute copilot to gather status with live output and process monitoring"""
        global current_process

        self.show_config()
        console.print(f"[dim]Logging to: {self.log_file}[/dim]\n")

        prompt_content = self.load_prompt()

        # Use model from environment or default to Claude Sonnet 4.5
        model = os.getenv("SPI_AGENT_COPILOT_MODEL", "claude-sonnet-4.5")
        command = ["copilot", "--model", model, "-p", prompt_content, "--allow-all-tools"]

        # Open log file for incremental writes
        try:
            self.log_handle = open(self.log_file, "w", buffering=1)  # Line buffering
            # Write header
            self.log_handle.write(f"{'='*70}\n")
            self.log_handle.write("Copilot Status Check Log (Streaming)\n")
            self.log_handle.write(f"{'='*70}\n")
            self.log_handle.write(f"Timestamp: {datetime.now().isoformat()}\n")
            self.log_handle.write(f"Services: {', '.join(self.services)}\n")
            self.log_handle.write(f"{'='*70}\n\n")
            self.log_handle.write("=== RAW OUTPUT (streaming) ===\n\n")
            self.log_handle.flush()
        except Exception as e:
            logger.error(f"Failed to open log file: {e}")
            self.log_handle = None

        try:
            # Start process with streaming output
            # Redirect stderr to stdout to avoid blocking issues
            # Explicitly pass environment to ensure GitLab token is available
            env = os.environ.copy()
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,  # Prevent copilot from waiting for user input
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr into stdout to prevent deadlock
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=env,  # Pass full environment including GITLAB_TOKEN
            )

            # Set global process for signal handler
            current_process = process

            # Log process start
            logger.info(f"Started copilot process PID={process.pid}")
            debug_msg = f"[DEBUG] Started copilot process PID={process.pid}"
            self._write_to_log(debug_msg)

            # Create split layout
            layout = self.create_layout()
            layout["status"].update(self.tracker.get_table())
            layout["output"].update(self._output_panel_renderable)

            # Live display with split view
            with Live(layout, console=console, refresh_per_second=4, transient=False) as live:
                # Enhanced output reading with process monitoring
                self._read_output_with_monitoring(process, layout)

                # Final process wait (should already be done, but just in case)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("Process did not exit after output reading completed, terminating")
                    process.terminate()
                    process.wait(timeout=2)

                # Log completion
                logger.info(f"Process exited with return code: {process.returncode}")
                debug_msg = f"[DEBUG] Process exited with return code: {process.returncode}"
                self._write_to_log(debug_msg)

                # Mark any remaining services as gathered (if copilot succeeded)
                if process.returncode == 0:
                    for service in self.services:
                        if self.tracker.services[service]["status"] in ["pending", "querying"]:
                            self.tracker.update(service, "gathered", "Data collected")
                    # Note: Don't call live.refresh() here - it interferes with transient cleanup

            console.print()  # Add spacing after Live context exits

            if process.returncode != 0:
                console.print(f"[red]Error:[/red] Copilot failed with exit code {process.returncode}")
                return process.returncode

            # Extract and parse JSON from full output
            full_output = "\n".join(self.raw_output)

            # Save raw output for debugging
            raw_debug_file = Path("/tmp/copilot_status_raw.txt")
            try:
                with open(raw_debug_file, "w") as f:
                    f.write(full_output)
                logger.info(f"Saved raw output to {raw_debug_file}")
                debug_msg = f"[DEBUG] Saved raw output to {raw_debug_file}"
                self._write_to_log(debug_msg)
            except Exception as e:
                logger.warning(f"Could not save raw output: {e}")

            status_data = self.extract_json(full_output)

            if not status_data:
                console.print("[red]Error:[/red] Could not extract JSON from copilot output")
                logger.error("Could not extract JSON from copilot output")
                logger.debug(f"Raw output (first 2000 chars): {full_output[:2000]}")
                logger.debug(f"Total output length: {len(full_output)} chars")
                logger.debug(f"Output ends with: ...{full_output[-200:]}")
                return 1

            # Validate JSON with Pydantic
            try:
                validated_data = StatusResponse(**status_data)
                logger.info("Data validated successfully")

                # Convert back to dict for display (with validated data)
                status_data = validated_data.model_dump()

            except ValidationError as e:
                logger.warning(f"Data validation failed, using raw data. Errors: {e.error_count()} field(s)")
                # Continue with raw data

            # Display the results
            self.display_status(status_data)

            # Save execution log
            self._save_log(process.returncode, status_data)

            return 0

        except FileNotFoundError:
            console.print(
                "[red]Error:[/red] 'copilot' command not found. Is GitHub Copilot CLI installed?",
                style="bold red",
            )
            return 1
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}", style="bold red")
            import traceback
            traceback.print_exc()
            return 1
        finally:
            # Close log file if open
            if self.log_handle and not self.log_handle.closed:
                try:
                    self.log_handle.write(f"\n\n{'='*70}\n")
                    self.log_handle.write(f"Log closed at: {datetime.now().isoformat()}\n")
                    self.log_handle.close()
                except Exception as e:
                    logger.warning(f"Error closing log file: {e}")

            # Clear global process reference
            current_process = None

    def _read_output_with_monitoring(self, process: subprocess.Popen, layout) -> None:
        """
        Read process output with monitoring to prevent hanging.

        Uses select() to check for available data and polls process status
        to detect when the process exits, even if stdout isn't properly closed.

        Implements a hard timeout to prevent indefinite hangs.

        Args:
            process: The subprocess to monitor
            layout: Rich layout for updating UI
        """
        if not process.stdout:
            logger.warning("No stdout available from process")
            debug_msg = "[DEBUG] No stdout available from process"
            self._write_to_log(debug_msg)
            return

        logger.info("Starting output reading loop")
        debug_msg = "[DEBUG] Starting output reading loop"
        self._write_to_log(debug_msg)

        # Timeout configuration
        start_time = time.time()
        max_timeout = 600  # 10 minutes hard timeout (increased for downstream pipeline jobs)
        last_output_time = time.time()
        output_timeout = 30  # Seconds of silence before logging a warning
        line_count = 0
        poll_interval = 0.5  # Check for output every 0.5 seconds

        # Main reading loop: continue while process is running
        while process.poll() is None:
            # Check for hard timeout
            elapsed = time.time() - start_time
            if elapsed > max_timeout:
                logger.error(f"Copilot process exceeded {max_timeout}s timeout, terminating")
                error_msg = f"[ERROR] Process exceeded {max_timeout}s timeout (elapsed: {elapsed:.1f}s)"
                self._write_to_log(error_msg)

                # Graceful termination
                console.print(f"\n[red]Timeout:[/red] Copilot exceeded {max_timeout}s limit, terminating gracefully...")
                process.terminate()

                # Give it 10 seconds to cleanup
                try:
                    process.wait(timeout=10)
                    logger.info("Process terminated gracefully")
                    self._write_to_log("[DEBUG] Process terminated gracefully after timeout")
                except subprocess.TimeoutExpired:
                    logger.warning("Process did not terminate gracefully, forcing kill")
                    self._write_to_log("[DEBUG] Process did not terminate gracefully, forcing kill")
                    process.kill()
                    process.wait()
                    self._write_to_log("[DEBUG] Process killed forcefully")

                break

            # Use select to check if data is available (non-blocking)
            try:
                ready, _, _ = select.select([process.stdout], [], [], poll_interval)
            except Exception as e:
                logger.error(f"select() failed: {e}")
                debug_msg = f"[DEBUG] select() failed: {e}"
                self._write_to_log(debug_msg)
                break

            if ready:
                # Data is available, read one line
                try:
                    line = process.stdout.readline()
                    if not line:
                        # EOF reached while process still running (unusual but possible)
                        logger.info("EOF reached while process still running")
                        debug_msg = "[DEBUG] EOF reached while process still running"
                        self._write_to_log(debug_msg)
                        break

                    line = line.rstrip()
                    if line:
                        line_count += 1
                        # Add to both buffers
                        self.output_lines.append(line)
                        self.raw_output.append(line)

                        # Write to log file immediately
                        self._write_to_log(line)

                        # Parse for status updates
                        self.parse_output(line)

                        # Update both panels
                        layout["status"].update(self.tracker.get_table())
                        layout["output"].update(self._output_panel_renderable)

                        # Reset timeout timer
                        last_output_time = time.time()

                        # Log progress periodically
                        if line_count % 50 == 0:
                            logger.debug(f"Read {line_count} lines so far")

                except Exception as e:
                    logger.error(f"Error reading line: {e}")
                    debug_msg = f"[DEBUG] Error reading line: {e}"
                    self._write_to_log(debug_msg)
                    break
            else:
                # No data available, check for timeout
                silence_duration = time.time() - last_output_time

                if silence_duration > output_timeout:
                    # Log warning but continue waiting
                    logger.info(f"No output for {silence_duration:.0f}s, process still running (PID={process.pid})")
                    debug_msg = f"[DEBUG] No output for {silence_duration:.0f}s, process still running"
                    self._write_to_log(debug_msg)
                    # Reset timer to avoid spamming logs
                    last_output_time = time.time()

        # Process has exited - log final status
        logger.info(f"Process poll() returned {process.returncode}, draining remaining output")
        debug_msg = f"[DEBUG] Process exited (returncode={process.returncode}), draining remaining output"
        self._write_to_log(debug_msg)

        # Drain any remaining output from stdout buffer
        drained_lines = 0
        try:
            for line in process.stdout:
                line = line.rstrip()
                if line:
                    drained_lines += 1
                    self.output_lines.append(line)
                    self.raw_output.append(line)
                    self._write_to_log(line)
                    self.parse_output(line)
                    layout["status"].update(self.tracker.get_table())
                    layout["output"].update(self._output_panel_renderable)
        except Exception as e:
            logger.warning(f"Error draining output: {e}")
            debug_msg = f"[DEBUG] Error draining output: {e}"
            self._write_to_log(debug_msg)

        logger.info(f"Output reading complete. Total lines: {line_count}, drained: {drained_lines}")
        debug_msg = f"[DEBUG] Output reading complete. Total lines: {line_count}, drained: {drained_lines}"
        self._write_to_log(debug_msg)

    def _write_to_log(self, line: str) -> None:
        """Write a line to the log file immediately (incremental logging).

        Args:
            line: Line to write to the log file
        """
        if self.log_handle and not self.log_handle.closed:
            try:
                self.log_handle.write(line + "\n")
                self.log_handle.flush()  # Ensure immediate write for tail -f
            except Exception as e:
                logger.warning(f"Error writing to log file: {e}")

    def _save_log(self, return_code: int, status_data: Optional[Dict] = None):
        """Append final metadata to the streaming log file.

        Since raw output is already written incrementally during execution,
        this method only appends the exit code and extracted JSON.
        """
        if not self.log_handle or self.log_handle.closed:
            # Fallback: log file wasn't opened, write everything now
            try:
                with open(self.log_file, "w") as f:
                    f.write(f"{'='*70}\n")
                    f.write("Copilot Status Check Log (Post-mortem)\n")
                    f.write(f"{'='*70}\n")
                    f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                    f.write(f"Services: {', '.join(self.services)}\n")
                    f.write(f"Exit Code: {return_code}\n")
                    f.write(f"{'='*70}\n\n")
                    f.write("=== RAW OUTPUT ===\n\n")
                    f.write("\n".join(self.raw_output))
                    if status_data:
                        f.write("\n\n=== EXTRACTED JSON ===\n\n")
                        f.write(json.dumps(status_data, indent=2))
            except Exception as e:
                console.print(f"[dim]Warning: Could not save log: {e}[/dim]")
                return

        else:
            # Normal case: append final sections to streaming log
            try:
                self.log_handle.write(f"\n\n{'='*70}\n")
                self.log_handle.write(f"Exit Code: {return_code}\n")
                self.log_handle.write(f"{'='*70}\n")

                # Write extracted JSON if available
                if status_data:
                    self.log_handle.write("\n=== EXTRACTED JSON ===\n\n")
                    self.log_handle.write(json.dumps(status_data, indent=2))
                    self.log_handle.write("\n")

                self.log_handle.flush()
            except Exception as e:
                logger.warning(f"Error appending to log file: {e}")

        console.print(f"\n[dim]✓ Log saved to: {self.log_file}[/dim]")

    def get_results_panel(self, return_code: int) -> Panel:
        """Generate final results panel.

        Note: StatusRunner uses display_status() for output instead of a single panel.
        This method is required by BaseRunner but not used in StatusRunner's run() method.
        """
        return Panel(
            "Status data displayed above",
            title="✓ Status Check Complete" if return_code == 0 else "✗ Status Check Failed",
            border_style="green" if return_code == 0 else "red"
        )
