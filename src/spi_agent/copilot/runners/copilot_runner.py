"""Copilot fork runner for repository initialization."""

import subprocess
from collections import deque
from datetime import datetime
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import List, Optional, Union

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from spi_agent.copilot.config import config, log_dir
from spi_agent.copilot.trackers import ServiceTracker

console = Console()

# Global process reference for signal handling (will be set by parent module)
current_process: Optional[subprocess.Popen] = None


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
        config_text = f"""[cyan]Prompt:[/cyan]     {self.prompt_file.name}
[cyan]Services:[/cyan]   {', '.join(self.services)}
[cyan]Branch:[/cyan]     {self.branch}
[cyan]Template:[/cyan]   azure/osdu-spi"""

        console.print(Panel(config_text, title="🤖 Copilot Automation", border_style="blue"))
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
