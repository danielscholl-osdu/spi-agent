#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "rich==14.1.0",
#   "pydantic==2.10.6",
#   "pydantic-settings==2.7.1",
#   "python-dotenv==1.0.1",
# ]
# ///
"""
Enhanced Copilot CLI Wrapper with Rich Console Output

Usage:
    spi-agent fork --services partition,legal --branch main
    spi-agent fork --services all
    spi-agent fork --services partition
    spi-agent status --services partition
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import textwrap
from collections import deque
from datetime import datetime
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Dict, List, Optional, Union

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.text import Text


__all__ = [
    "SERVICES",
    "CopilotConfig",
    "CopilotRunner",
    "StatusRunner",
    "parse_services",
    "get_prompt_file",
    "main",
]

console = Console()

# Global process reference for signal handling
current_process: Optional[subprocess.Popen] = None


def handle_interrupt(signum, frame):
    """Handle Ctrl+C gracefully."""
    console.print("\n[yellow]⚠ Interrupted by user[/yellow]")
    if current_process:
        console.print("[dim]Terminating copilot process...[/dim]")
        current_process.terminate()
        try:
            current_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            current_process.kill()
    sys.exit(130)  # Standard exit code for SIGINT


# Register signal handler
signal.signal(signal.SIGINT, handle_interrupt)


# Configuration
class CopilotConfig(BaseSettings):
    """Configuration for copilot wrapper"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="COPILOT_",
        extra="ignore"
    )

    organization: str = "danielscholl-osdu"
    template_repo: str = "azure/osdu-spi"
    default_branch: str = "main"
    log_directory: str = "logs"


# Load environment variables from .env if it exists
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)

# Initialize configuration
config = CopilotConfig()

# Ensure log directory exists
log_dir = Path(config.log_directory)
log_dir.mkdir(exist_ok=True)


def get_prompt_file(name: str) -> Traversable:
    """Return a prompt resource for the given name."""
    prompt = resources.files(__name__).joinpath("prompts", name)
    if not prompt.is_file():
        raise FileNotFoundError(f"Prompt '{name}' not found in packaged resources")
    return prompt

# Service definitions matching fork.md
SERVICES = {
    "partition": "Partition Service",
    "entitlements": "Entitlements Service",
    "legal": "Legal Service",
    "schema": "Schema Service",
    "file": "File Service",
    "storage": "Storage Service",
    "indexer": "Indexer Service",
    "indexer-queue": "Indexer Queue Service",
    "search": "Search Service",
    "workflow": "Workflow Service",
}


# Pydantic models for status response validation
class RepoInfo(BaseModel):
    """Repository information"""
    name: str
    full_name: str
    url: str
    updated_at: str
    exists: bool = True


class IssueInfo(BaseModel):
    """Issue information"""
    number: int
    title: str
    labels: List[str] = Field(default_factory=list)
    state: str


class IssuesData(BaseModel):
    """Issues data for a service"""
    count: int
    items: List[IssueInfo] = Field(default_factory=list)


class PullRequestInfo(BaseModel):
    """Pull request information"""
    model_config = ConfigDict(populate_by_name=True)

    number: int
    title: str
    state: str
    branch: str = Field(alias="headRefName", default="")
    is_draft: bool = Field(alias="isDraft", default=False)
    is_release: bool = False


class PullRequestsData(BaseModel):
    """Pull requests data for a service"""
    count: int
    items: List[PullRequestInfo] = Field(default_factory=list)


class WorkflowRun(BaseModel):
    """Workflow run information"""
    model_config = ConfigDict(populate_by_name=True)

    name: str
    status: str
    conclusion: Optional[str] = None
    created_at: str = Field(alias="createdAt", default="")
    updated_at: str = Field(alias="updatedAt", default="")


class WorkflowsData(BaseModel):
    """Workflows data for a service"""
    recent: List[WorkflowRun] = Field(default_factory=list)


class ServiceData(BaseModel):
    """Complete data for a service"""
    repo: RepoInfo
    issues: IssuesData = Field(default_factory=IssuesData)
    pull_requests: PullRequestsData = Field(default_factory=PullRequestsData)
    workflows: WorkflowsData = Field(default_factory=WorkflowsData)


class StatusResponse(BaseModel):
    """Complete status response from copilot"""
    timestamp: str
    services: Dict[str, ServiceData]


class ServiceTracker:
    """Tracks the status of services being processed"""

    def __init__(self, services: List[str]):
        self.services = {
            service: {
                "status": "pending",
                "details": "Waiting to start",
                "icon": "⏸",
            }
            for service in services
        }

    def update(self, service: str, status: str, details: str = ""):
        """Update service status"""
        if service in self.services:
            icons = {
                "pending": "⏸",
                "running": "⏳",
                "waiting": "⏱",
                "success": "✓",
                "error": "✗",
                "skipped": "⊘",
            }
            self.services[service]["status"] = status
            self.services[service]["details"] = details
            self.services[service]["icon"] = icons.get(status, "•")

    def get_table(self) -> Table:
        """Generate Rich table of service status"""
        table = Table(title="Service Processing Status", expand=True)
        table.add_column("Service", style="cyan", no_wrap=True)
        table.add_column("Status", style="magenta")
        table.add_column("Details", style="white")

        for service, data in self.services.items():
            status_style = {
                "pending": "dim",
                "running": "yellow",
                "waiting": "blue",
                "success": "green",
                "error": "red",
                "skipped": "dim",
            }.get(data["status"], "white")

            table.add_row(
                f"{data['icon']} {service}",
                f"[{status_style}]{data['status'].upper()}[/{status_style}]",
                data["details"],
            )

        return table


class CopilotRunner:
    """Runs Copilot CLI with enhanced output"""

    def __init__(
        self,
        prompt_file: Union[Path, Traversable],
        services: List[str],
        branch: str = "main",
    ):
        self.prompt_file = prompt_file
        self.services = services
        self.branch = branch
        self.tracker = ServiceTracker(services)
        self.output_lines = deque(maxlen=50)  # Keep last 50 lines of output
        self.full_output = []  # Keep all output for logging

        # Generate log file path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        services_str = "-".join(services[:3])  # Max 3 service names in filename
        if len(services) > 3:
            services_str += f"-and-{len(services)-3}-more"
        self.log_file = log_dir / f"fork_{timestamp}_{services_str}.log"

    def load_prompt(self) -> str:
        """Load and augment prompt with arguments"""
        prompt = self.prompt_file.read_text(encoding="utf-8")

        # Replace organization placeholder with actual value from config
        prompt = prompt.replace("{{ORGANIZATION}}", config.organization)

        # Inject arguments into prompt
        services_arg = ",".join(self.services)
        augmented = f"{prompt}\n\nARGUMENTS:\nSERVICES: {services_arg}\nBRANCH: {self.branch}"
        return augmented

    def show_config(self):
        """Display run configuration"""
        config = f"""[cyan]Prompt:[/cyan]     {self.prompt_file.name}
[cyan]Services:[/cyan]   {', '.join(self.services)}
[cyan]Branch:[/cyan]     {self.branch}
[cyan]Template:[/cyan]   azure/osdu-spi"""

        console.print(Panel(config, title="🤖 Copilot Automation", border_style="blue"))
        console.print()

    def get_output_panel(self) -> Panel:
        """Create panel with scrolling output"""
        if not self.output_lines:
            output_text = Text("Waiting for output...", style="dim")
        else:
            # Join lines and create text
            output_text = Text()
            for line in self.output_lines:
                # Add some color coding for common patterns
                if line.startswith("$"):
                    output_text.append(line + "\n", style="cyan")
                elif line.startswith("✓") or "success" in line.lower():
                    output_text.append(line + "\n", style="green")
                elif line.startswith("✗") or "error" in line.lower() or "failed" in line.lower():
                    output_text.append(line + "\n", style="red")
                elif line.startswith("●"):
                    output_text.append(line + "\n", style="yellow")
                else:
                    output_text.append(line + "\n", style="white")

        return Panel(output_text, title="📋 Live Output", border_style="blue")

    def create_layout(self) -> Layout:
        """Create split layout with status and output"""
        layout = Layout()
        layout.split_row(
            Layout(name="status", ratio=1),
            Layout(name="output", ratio=2)
        )
        return layout

    def parse_output_line(self, line: str):
        """Parse copilot output for status updates"""
        line_lower = line.lower()
        line_stripped = line.strip()

        # Detect service-specific section headers (markdown style)
        # Pattern: "### ✅ Partition Service" or "### ✅ Legal Service"
        for service in self.services:
            # Check for completion headers
            if f"✅ {service}" in line or f"✓ {service}" in line:
                if "service" in line_lower:
                    self.tracker.update(service, "success", "Completed successfully")
                    continue
            # Check for section headers mentioning service
            elif line_stripped.startswith("###") and service in line_lower and "service" in line_lower:
                if "✅" in line or "✓" in line:
                    self.tracker.update(service, "success", "Completed successfully")
                    continue

        # Detect global completion messages (multiple patterns)
        completion_patterns = [
            "successfully completed repository initialization",
            "successfully completed workflow for",
            "✅ successfully completed workflow for",
            "all repositories are now:",
            "repository status:",
        ]
        if any(pattern in line_lower for pattern in completion_patterns):
            # Mark all pending/running services as success
            for service in self.services:
                status = self.tracker.services[service]["status"]
                if status not in ["success", "skipped", "error"]:
                    self.tracker.update(service, "success", "Completed successfully")

        # Find currently active service (first non-completed service)
        active_service = None
        for service in self.services:
            status = self.tracker.services[service]["status"]
            if status not in ["success", "skipped"]:
                active_service = service
                break

        # Detect copilot's task completion markers (highest priority)
        # First, check if this task mentions a specific service
        target_service = None
        for service in self.services:
            if service in line_lower:
                target_service = service
                break

        # Use target_service if found, otherwise fall back to active_service
        service_to_update = target_service or active_service

        if service_to_update and line_stripped.startswith("✓"):
            # Extract the task description for context
            task_desc = line_stripped[1:].strip().lower()
            current_status = self.tracker.services[service_to_update]["status"]
            current_details = self.tracker.services[service_to_update]["details"].lower()

            # Map specific tasks to status updates
            if "check if" in task_desc and "repository already exists" in task_desc:
                # Don't update yet - waiting for result
                pass
            elif "create" in task_desc and "repository" in task_desc:
                self.tracker.update(service_to_update, "running", "Creating repository")
            elif "wait" in task_desc or "workflow" in task_desc:
                self.tracker.update(service_to_update, "waiting", "Waiting for workflow")
            elif "read" in task_desc and "issue" in task_desc:
                self.tracker.update(service_to_update, "running", "Reading initialization issue")
            elif "comment" in task_desc:
                self.tracker.update(service_to_update, "running", "Commenting on issue")
            elif "pull" in task_desc or ("clone" in task_desc and "finalization" not in current_details):
                # Distinguish between initial clone and final pull
                if current_status == "waiting" or "workflow" in current_details or "verifying" in current_details:
                    self.tracker.update(service_to_update, "running", "Finalizing - pulling updates")
                else:
                    self.tracker.update(service_to_update, "running", "Syncing repository")
            elif "check" in task_desc and ("branch" in task_desc or "commit" in task_desc or "issue" in task_desc or "closed" in task_desc):
                self.tracker.update(service_to_update, "running", "Verifying workflow results")
            elif "verify" in task_desc or "view" in task_desc:
                self.tracker.update(service_to_update, "running", "Final verification")

        # Detect copilot's error markers
        elif service_to_update and line_stripped.startswith("✗"):
            task_desc = line_stripped[1:].strip()
            self.tracker.update(service_to_update, "error", f"Failed: {task_desc[:30]}")

        # Global response patterns (copilot's narrative)
        # Prefer service_to_update (if service mentioned), else use active_service
        service_for_narrative = service_to_update or active_service

        if service_for_narrative:
            # Key decision points and outcomes
            if "doesn't exist yet" in line_lower or "repo_not_found" in line_lower:
                self.tracker.update(service_for_narrative, "running", "Repository not found - creating")
            elif "good!" in line_lower and "repository is cloned locally" in line_lower:
                self.tracker.update(service_for_narrative, "running", "Repository synced")
            elif "excellent!" in line_lower:
                if "created and cloned" in line_lower:
                    self.tracker.update(service_for_narrative, "running", "Repository created")
                elif "successfully updated" in line_lower:
                    self.tracker.update(service_for_narrative, "success", "Completed successfully")
            elif "perfect!" in line_lower:
                if "workflow has completed successfully" in line_lower:
                    self.tracker.update(service_for_narrative, "running", "Workflow completed")
                else:
                    self.tracker.update(service_for_narrative, "running", "Verification complete")
            elif "great!" in line_lower and "found the issue" in line_lower:
                self.tracker.update(service_for_narrative, "running", "Found initialization issue")

        # Service-specific updates
        for service in self.services:
            if service in line_lower:
                current_status = self.tracker.services[service]["status"]

                # Only mark as skipped if workflow explicitly terminates
                if ("terminate workflow" in line_lower or "do not continue" in line_lower) and "success" in line_lower:
                    self.tracker.update(service, "skipped", "Already exists")
                # Permission/access errors
                elif "permission denied" in line_lower or "could not request permission" in line_lower:
                    self.tracker.update(service, "error", "Permission denied")

    def run(self) -> int:
        """Execute copilot with streaming output"""
        global current_process

        self.show_config()

        prompt_content = self.load_prompt()
        command = ["copilot", "-p", prompt_content, "--allow-all-tools"]

        console.print(f"[dim]Logging to: {self.log_file}[/dim]\n")

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

            # Live display with split view: status table (left) and output (right)
            with Live(layout, console=console, refresh_per_second=4) as live:
                # Read stdout line by line
                if process.stdout:
                    for line in process.stdout:
                        line = line.rstrip()
                        if line:
                            # Add to both buffers
                            self.output_lines.append(line)
                            self.full_output.append(line)

                            # Parse for status updates
                            self.parse_output_line(line)

                            # Update both panels
                            layout["status"].update(self.tracker.get_table())
                            layout["output"].update(self.get_output_panel())

                # Wait for process to complete
                process.wait()

                # Update layout with final summary in left panel
                layout["status"].update(self.get_summary_panel(process.returncode))
                # Force one final refresh to show the summary
                live.refresh()

            # Print final layout one more time so it stays visible
            console.print(layout)

            # Save full output to log file
            self._save_log(process.returncode)

            return process.returncode

        except FileNotFoundError:
            console.print(
                "[red]Error:[/red] 'copilot' command not found. Is GitHub Copilot CLI installed?",
                style="bold red",
            )
            return 1
        except Exception as e:
            console.print(f"[red]Error executing command:[/red] {e}", style="bold red")
            return 1
        finally:
            # Clear global process reference
            current_process = None

    def _save_log(self, return_code: int):
        """Save execution log to file"""
        try:
            with open(self.log_file, "w") as f:
                f.write(f"{'='*70}\n")
                f.write(f"Copilot Fork Execution Log\n")
                f.write(f"{'='*70}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Services: {', '.join(self.services)}\n")
                f.write(f"Branch: {self.branch}\n")
                f.write(f"Exit Code: {return_code}\n")
                f.write(f"{'='*70}\n\n")
                f.write("\n".join(self.full_output))

            console.print(f"\n[dim]✓ Log saved to: {self.log_file}[/dim]")
        except Exception as e:
            console.print(f"[dim]Warning: Could not save log: {e}[/dim]")

    def get_summary_panel(self, return_code: int) -> Panel:
        """Generate final summary panel"""
        # Count status
        status_counts = {
            "success": 0,
            "error": 0,
            "skipped": 0,
            "pending": 0,
        }
        for service, data in self.tracker.services.items():
            status_counts[data["status"]] = status_counts.get(data["status"], 0) + 1

        summary_style = "green" if return_code == 0 else "red"
        summary_text = "✓ Completed" if return_code == 0 else "✗ Failed"

        # Build detailed service list
        service_list = []
        for service, data in self.tracker.services.items():
            icon = data["icon"]
            status = data["status"].upper()
            details = data["details"]

            status_color = {
                "success": "green",
                "error": "red",
                "skipped": "yellow",
                "pending": "dim"
            }.get(data["status"], "white")

            service_list.append(f"  [{status_color}]{icon} {service:<15} {status:<10}[/{status_color}] {details}")

        services_text = "\n".join(service_list)

        summary = f"""[{summary_style}]{'='*50}[/{summary_style}]
[{summary_style}]{summary_text}[/{summary_style}]
[{summary_style}]{'='*50}[/{summary_style}]

[bold]Services:[/bold]
{services_text}

[bold]Summary:[/bold]
[green]✓ Success:[/green]  {status_counts.get('success', 0)}
[yellow]⊘ Skipped:[/yellow] {status_counts.get('skipped', 0)}
[red]✗ Errors:[/red]   {status_counts.get('error', 0)}
[dim]⏸ Pending:[/dim]  {status_counts.get('pending', 0)}"""

        return Panel(summary, title="📊 Final Report", border_style=summary_style)


class StatusTracker:
    """Tracks the status of GitHub data gathering for services"""

    def __init__(self, services: List[str]):
        self.services = {
            service: {
                "status": "pending",
                "details": "Waiting to query",
                "icon": "⏸",
            }
            for service in services
        }

    def update(self, service: str, status: str, details: str = ""):
        """Update service status"""
        if service in self.services:
            icons = {
                "pending": "⏸",
                "querying": "🔍",
                "gathered": "✓",
                "error": "✗",
            }
            self.services[service]["status"] = status
            self.services[service]["details"] = details
            self.services[service]["icon"] = icons.get(status, "•")

    def get_table(self) -> Table:
        """Generate Rich table of gathering status"""
        table = Table(title="GitHub Data Gathering Status", expand=True)
        table.add_column("Service", style="cyan", no_wrap=True)
        table.add_column("Status", style="magenta")
        table.add_column("Details", style="white")

        for service, data in self.services.items():
            status_style = {
                "pending": "dim",
                "querying": "yellow",
                "gathered": "green",
                "error": "red",
            }.get(data["status"], "white")

            table.add_row(
                f"{data['icon']} {service}",
                f"[{status_style}]{data['status'].upper()}[/{status_style}]",
                data["details"],
            )

        return table


class StatusRunner:
    """Runs Copilot CLI to gather GitHub status and displays results"""

    def __init__(self, prompt_file: Union[Path, Traversable], services: List[str]):
        self.prompt_file = prompt_file
        self.services = services
        self.output_lines = deque(maxlen=50)  # Keep last 50 lines of output
        self.raw_output = []  # Keep full output for JSON extraction
        self.tracker = StatusTracker(services)

        # Generate log file path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        services_str = "-".join(services[:3])
        if len(services) > 3:
            services_str += f"-and-{len(services)-3}-more"
        self.log_file = log_dir / f"status_{timestamp}_{services_str}.log"

    def load_prompt(self) -> str:
        """Load and augment prompt with arguments"""
        prompt = self.prompt_file.read_text(encoding="utf-8")

        # Replace organization placeholder with actual value from config
        prompt = prompt.replace("{{ORGANIZATION}}", config.organization)

        # Inject services argument
        services_arg = ",".join(self.services)
        augmented = f"{prompt}\n\nARGUMENTS:\nSERVICES: {services_arg}"
        return augmented

    def get_output_panel(self) -> Panel:
        """Create panel with scrolling output"""
        if not self.output_lines:
            output_text = Text("Waiting for output...", style="dim")
        else:
            # Join lines and create text
            output_text = Text()
            for line in self.output_lines:
                # Add some color coding for common patterns
                if line.startswith("$"):
                    output_text.append(line + "\n", style="cyan")
                elif line.startswith("✓") or "success" in line.lower():
                    output_text.append(line + "\n", style="green")
                elif line.startswith("✗") or "error" in line.lower() or "failed" in line.lower():
                    output_text.append(line + "\n", style="red")
                elif line.startswith("●"):
                    output_text.append(line + "\n", style="yellow")
                else:
                    output_text.append(line + "\n", style="white")

        return Panel(output_text, title="📋 Copilot Activity", border_style="blue")

    def parse_status_line(self, line: str):
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

    def create_layout(self) -> Layout:
        """Create split layout with status and output"""
        layout = Layout()
        layout.split_row(
            Layout(name="status", ratio=1),
            Layout(name="output", ratio=2)
        )
        return layout

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
                    workflow_display = f"[yellow]⏳ {running} running[/yellow]"
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
                            status_display = f"[yellow]⏳ {status}[/yellow]"
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
            next_steps.append(f"[yellow]⏳[/yellow] {total_running} workflow(s) still running")
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
                            self.parse_status_line(line)

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


def parse_services(services_arg: str) -> List[str]:
    """Parse services argument into list"""
    if services_arg.lower() == "all":
        return list(SERVICES.keys())
    return [s.strip() for s in services_arg.split(",")]


def main():
    parser = argparse.ArgumentParser(
        description="Enhanced GitHub Copilot CLI Automation Wrapper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s fork --services partition
  %(prog)s fork --services partition,legal,entitlements
  %(prog)s fork --services all --branch develop

  %(prog)s status --services partition
  %(prog)s status --services partition,legal,entitlements
  %(prog)s status --services all
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Fork command
    fork_parser = subparsers.add_parser(
        "fork",
        help="Fork and initialize OSDU SPI service repositories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --services partition
  %(prog)s --services partition,legal,entitlements
  %(prog)s --services all
  %(prog)s --services partition --branch develop

Available services:
  partition, entitlements, legal, schema, file, storage,
  indexer, indexer-queue, search, workflow
        """,
    )
    fork_parser.add_argument(
        "--services",
        "-s",
        required=True,
        metavar="SERVICES",
        help="Service name(s): 'all', single name, or comma-separated list",
    )
    fork_parser.add_argument(
        "--branch",
        "-b",
        default="main",
        metavar="BRANCH",
        help="Branch name (default: main)",
    )

    # Status command
    status_parser = subparsers.add_parser(
        "status",
        help="Get GitHub status for OSDU SPI service repositories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --services partition
  %(prog)s --services partition,legal,entitlements
  %(prog)s --services all

Available services:
  partition, entitlements, legal, schema, file, storage,
  indexer, indexer-queue, search, workflow

Information gathered:
  - Open issues count and details
  - Pull requests (highlighting release PRs)
  - Recent workflow runs (Build, Test, CodeQL, etc.)
  - Workflow status (running, completed, failed)
        """,
    )
    status_parser.add_argument(
        "--services",
        "-s",
        required=True,
        metavar="SERVICES",
        help="Service name(s): 'all', single name, or comma-separated list",
    )

    # Custom error handling for better UX
    try:
        args = parser.parse_args()
    except SystemExit as e:
        if e.code != 0:
            # Print hint after argparse error
            console.print(
                "\n[cyan]Hint:[/cyan] Run with --help to see examples and usage",
                style="dim",
            )
        raise

    if not args.command:
        parser.print_help()
        return 1

    # Handle fork command
    if args.command == "fork":
        try:
            prompt_file = get_prompt_file("fork.md")
        except FileNotFoundError as exc:
            console.print(
                f"[red]Error:[/red] {exc}",
                style="bold red",
            )
            return 1

        # Parse services
        services = parse_services(args.services)

        # Validate services
        invalid = [s for s in services if s not in SERVICES]
        if invalid:
            console.print(
                f"[red]Error:[/red] Invalid service(s): {', '.join(invalid)}",
                style="bold red",
            )
            console.print(f"\n[cyan]Available services:[/cyan] {', '.join(SERVICES.keys())}")
            return 1

        # Run copilot
        runner = CopilotRunner(prompt_file, services, args.branch)
        return runner.run()

    # Handle status command
    if args.command == "status":
        try:
            prompt_file = get_prompt_file("status.md")
        except FileNotFoundError as exc:
            console.print(
                f"[red]Error:[/red] {exc}",
                style="bold red",
            )
            return 1

        # Parse services
        services = parse_services(args.services)

        # Validate services
        invalid = [s for s in services if s not in SERVICES]
        if invalid:
            console.print(
                f"[red]Error:[/red] Invalid service(s): {', '.join(invalid)}",
                style="bold red",
            )
            console.print(f"\n[cyan]Available services:[/cyan] {', '.join(SERVICES.keys())}")
            return 1

        # Run status check
        runner = StatusRunner(prompt_file, services)
        return runner.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
