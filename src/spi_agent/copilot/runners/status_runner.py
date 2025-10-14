"""Status runner for gathering GitHub repository information."""

import json
import re
import subprocess
import textwrap
from datetime import datetime
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Dict, List, Optional, Union

from pydantic import ValidationError
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from spi_agent.copilot.base import BaseRunner
from spi_agent.copilot.base.runner import console, current_process
from spi_agent.copilot.config import config
from spi_agent.copilot.constants import SERVICES
from spi_agent.copilot.models import StatusResponse
from spi_agent.copilot.trackers import StatusTracker


class StatusRunner(BaseRunner):
    """Runs Copilot CLI to gather GitHub status and displays results"""

    def __init__(self, prompt_file: Union[Path, Traversable], services: List[str]):
        super().__init__(prompt_file, services)
        self.raw_output = []  # Keep full output for JSON extraction
        self.tracker = StatusTracker(services)

    @property
    def log_prefix(self) -> str:
        """Return log file prefix for this runner type."""
        return "status"

    def load_prompt(self) -> str:
        """Load and augment prompt with arguments"""
        prompt = self.prompt_file.read_text(encoding="utf-8")

        # Replace organization placeholder with actual value from config
        prompt = prompt.replace("{{ORGANIZATION}}", config.organization)

        # Inject services argument
        services_arg = ",".join(self.services)
        augmented = f"{prompt}\n\nARGUMENTS:\nSERVICES: {services_arg}"
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
        """Extract JSON from copilot output (may be wrapped in markdown)"""
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

        # Backwards compatibility: look for a block that clearly contains services data
        json_match = re.search(r'(\{[\s\S]*?"services"[\s\S]*?\})\s*$', output, re.MULTILINE)
        if json_match:
            data = self._parse_json_candidate(json_match.group(1), '"services" fallback')
            if data:
                return data

        # Last resort: treat entire output as JSON
        data = self._parse_json_candidate(output, "entire output")
        if data:
            return data

        console.print("[yellow]Warning:[/yellow] Could not extract JSON from any known format")
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
            console.print(f"[dim]{context} JSON parse failed: {last_error}[/dim]")
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
        """Display GitHub status in beautiful Rich format"""

        if not data:
            console.print("[red]Error:[/red] No status data received", style="bold red")
            return

        # Handle different possible structures
        if "services" in data:
            services_data = data["services"]
            timestamp = data.get("timestamp", datetime.now().isoformat())
        elif all(key in SERVICES for key in data.keys() if key != "timestamp"):
            # Data is structured as {service_name: {...}, service_name: {...}}
            services_data = {k: v for k, v in data.items() if k != "timestamp"}
            timestamp = data.get("timestamp", datetime.now().isoformat())
        else:
            console.print(f"[red]Error:[/red] Unexpected data structure. Keys found: {list(data.keys())}", style="bold red")
            console.print(f"[dim]Data preview: {str(data)[:500]}...[/dim]")
            return

        # Summary Table
        summary_table = Table(title="📊 GitHub Status Summary", expand=True)
        summary_table.add_column("Service", style="cyan", no_wrap=True)
        summary_table.add_column("Issues", style="yellow")
        summary_table.add_column("PRs", style="magenta")
        summary_table.add_column("Workflows", style="blue")
        summary_table.add_column("Last Update", style="dim")

        for service_name, service_data in services_data.items():
            if not service_data.get("repo", {}).get("exists", False):
                summary_table.add_row(
                    f"✗ {service_name}",
                    "[dim]N/A[/dim]",
                    "[dim]N/A[/dim]",
                    "[dim]N/A[/dim]",
                    "[red]Not found[/red]"
                )
                continue

            issues_count = service_data.get("issues", {}).get("count", 0)
            prs_count = service_data.get("pull_requests", {}).get("count", 0)

            # Workflow status - check recent runs
            workflows = service_data.get("workflows", {}).get("recent", [])
            if workflows:
                # Count workflow statuses
                running = sum(1 for w in workflows if w.get("status") in ["in_progress", "queued", "waiting"])
                completed = sum(1 for w in workflows if w.get("status") == "completed")
                failed = sum(1 for w in workflows if w.get("status") == "completed" and w.get("conclusion") in ["failure", "cancelled"])

                if running > 0:
                    workflow_display = f"[yellow]▶ {running} running[/yellow]"
                elif failed > 0:
                    workflow_display = f"[red]✗ {failed} failed[/red]"
                elif completed > 0:
                    workflow_display = f"[green]✓ {completed} ok[/green]"
                else:
                    workflow_display = f"[dim]{len(workflows)} runs[/dim]"
            else:
                workflow_display = "[dim]None[/dim]"

            # Last update
            updated_at = service_data.get("repo", {}).get("updated_at", "")
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

            summary_table.add_row(
                f"✓ {service_name}",
                f"{issues_count} open" if issues_count > 0 else "[dim]0[/dim]",
                f"{prs_count}" if prs_count > 0 else "[dim]0[/dim]",
                workflow_display,
                time_ago
            )

        console.print(summary_table)
        console.print()

        # Release PRs Table (if any)
        release_prs = []
        for service_name, service_data in services_data.items():
            prs = service_data.get("pull_requests", {}).get("items", [])
            for pr in prs:
                if pr.get("is_release", False):
                    release_prs.append((service_name, pr))

        if release_prs:
            pr_table = Table(title="🚀 Release Pull Requests", expand=True)
            pr_table.add_column("Service", style="cyan")
            pr_table.add_column("PR", style="magenta")
            pr_table.add_column("Status", style="yellow")

            for service_name, pr in release_prs:
                state = pr.get("state", "unknown")
                state_color = "green" if state == "open" else "dim"
                pr_table.add_row(
                    service_name,
                    f"#{pr['number']}: {pr['title']}",
                    f"[{state_color}]{state}[/{state_color}]"
                )

            console.print(pr_table)
            console.print()

        # Workflow Details Section
        has_workflows = any(
            len(service_data.get("workflows", {}).get("recent", [])) > 0
            for service_data in services_data.values()
        )

        if has_workflows:
            workflow_table = Table(title="⚙️ Recent Workflow Runs", expand=True)
            workflow_table.add_column("Service", style="cyan", no_wrap=True)
            workflow_table.add_column("Workflow", style="white")
            workflow_table.add_column("Status", style="magenta")
            workflow_table.add_column("When", style="dim")

            for service_name, service_data in services_data.items():
                workflows = service_data.get("workflows", {}).get("recent", [])
                if workflows:
                    for idx, workflow in enumerate(workflows[:5]):  # Show max 5 per service
                        name = workflow.get("name", "Unknown")
                        status = workflow.get("status", "unknown")
                        conclusion = workflow.get("conclusion", "")
                        created = workflow.get("created_at", "")

                        # Format status
                        if status == "completed":
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

        # Open Issues with grouping
        issue_groups = {}  # Group issues by title to detect duplicates
        for service_name, service_data in services_data.items():
            issues = service_data.get("issues", {}).get("items", [])
            for issue in issues:
                title = issue.get("title", "")
                if title not in issue_groups:
                    issue_groups[title] = {
                        "number": issue.get("number"),
                        "labels": issue.get("labels", []),
                        "services": []
                    }
                issue_groups[title]["services"].append(service_name)

        if issue_groups:
            issue_content = []
            for title, data in issue_groups.items():
                labels = ", ".join(data["labels"]) if data["labels"] else ""
                services = ", ".join(data["services"])

                # Highlight human-required issues
                if "human-required" in data["labels"]:
                    issue_content.append(f"[bold red]#{data['number']}[/bold red] {title}")
                    issue_content.append(f"   [red]⚠ Requires manual intervention[/red]")
                else:
                    issue_content.append(f"[yellow]#{data['number']}[/yellow] {title}")

                if len(data["services"]) > 1:
                    issue_content.append(f"   Affects: [cyan]{services}[/cyan]")
                else:
                    issue_content.append(f"   Service: [cyan]{services}[/cyan]")

                if labels:
                    issue_content.append(f"   Labels: [dim]{labels}[/dim]")
                issue_content.append("")

            console.print(Panel(
                "\n".join(issue_content),
                title="📝 Open Issues",
                border_style="yellow"
            ))
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

        # Check for running workflows
        total_running = sum(
            sum(1 for w in service_data.get("workflows", {}).get("recent", [])
                if w.get("status") in ["in_progress", "queued", "waiting"])
            for service_data in services_data.values()
        )
        if total_running > 0:
            next_steps.append(f"[yellow]▶[/yellow] {total_running} workflow(s) still running")
        else:
            next_steps.append(f"[green]✓[/green] All workflows completed")

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
        config = f"""[cyan]Services:[/cyan]   {', '.join(self.services)}
[cyan]Gathering:[/cyan]  Issues, PRs, Workflows"""

        console.print(Panel(config, title="🔍 GitHub Status Check", border_style="blue"))
        console.print()

    def run(self) -> int:
        """Execute copilot to gather status with live output"""
        global current_process

        self.show_config()
        console.print(f"[dim]Logging to: {self.log_file}[/dim]\n")

        prompt_content = self.load_prompt()
        command = ["copilot", "-p", prompt_content, "--allow-all-tools"]

        try:
            # Start process with streaming output
            # Redirect stderr to stdout to avoid blocking issues
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr into stdout to prevent deadlock
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            # Set global process for signal handler
            current_process = process

            # Create split layout
            layout = self.create_layout()
            layout["status"].update(self.tracker.get_table())
            layout["output"].update(self.get_output_panel())

            # Live display with split view
            with Live(layout, console=console, refresh_per_second=4) as live:
                # Read stdout line by line
                if process.stdout:
                    for line in process.stdout:
                        line = line.rstrip()
                        if line:
                            # Add to both buffers
                            self.output_lines.append(line)
                            self.raw_output.append(line)

                            # Parse for status updates
                            self.parse_output(line)

                            # Update both panels
                            layout["status"].update(self.tracker.get_table())
                            layout["output"].update(self.get_output_panel())

                # Wait for process to complete
                process.wait()

                # Mark any remaining services as gathered (if copilot succeeded)
                if process.returncode == 0:
                    for service in self.services:
                        if self.tracker.services[service]["status"] in ["pending", "querying"]:
                            self.tracker.update(service, "gathered", "Data collected")

                    # Update table one final time
                    layout["status"].update(self.tracker.get_table())
                    live.refresh()

            console.print()  # Add spacing

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
                console.print(f"[dim]Debug: Saved raw output to {raw_debug_file}[/dim]")
            except Exception:
                pass

            status_data = self.extract_json(full_output)

            if not status_data:
                console.print("[red]Error:[/red] Could not extract JSON from copilot output")
                console.print("\n[dim]Raw output (first 2000 chars):[/dim]")
                console.print(full_output[:2000])
                console.print(f"\n[dim]Total output length: {len(full_output)} chars[/dim]")
                console.print(f"[dim]Output ends with: ...{full_output[-200:]}[/dim]")
                return 1

            # Validate JSON with Pydantic
            try:
                validated_data = StatusResponse(**status_data)
                console.print(f"[dim]✓ Data validated successfully[/dim]\n")

                # Convert back to dict for display (with validated data)
                status_data = validated_data.model_dump()

            except ValidationError as e:
                console.print(f"[yellow]Warning:[/yellow] Data validation failed, using raw data")
                console.print(f"[dim]Validation errors: {e.error_count()} field(s)[/dim]\n")
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
            # Clear global process reference
            current_process = None

    def _save_log(self, return_code: int, status_data: Optional[Dict] = None):
        """Save execution log to file"""
        try:
            with open(self.log_file, "w") as f:
                f.write(f"{'='*70}\n")
                f.write(f"Copilot Status Check Log\n")
                f.write(f"{'='*70}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Services: {', '.join(self.services)}\n")
                f.write(f"Exit Code: {return_code}\n")
                f.write(f"{'='*70}\n\n")

                # Write raw output
                f.write("=== RAW OUTPUT ===\n\n")
                f.write("\n".join(self.raw_output))

                # Write extracted JSON if available
                if status_data:
                    f.write("\n\n=== EXTRACTED JSON ===\n\n")
                    f.write(json.dumps(status_data, indent=2))

            console.print(f"\n[dim]✓ Log saved to: {self.log_file}[/dim]")
        except Exception as e:
            console.print(f"[dim]Warning: Could not save log: {e}[/dim]")

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


