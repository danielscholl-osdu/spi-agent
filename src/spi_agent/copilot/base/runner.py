"""Abstract base class for all copilot runners."""

import subprocess
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import List, Optional, Union

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

from spi_agent.copilot.config import log_dir

console = Console()


class BaseRunner(ABC):
    """Abstract base class for all copilot CLI runners."""

    def __init__(
        self,
        prompt_file: Union[Path, Traversable],
        services: List[str],
    ):
        """Initialize base runner.

        Args:
            prompt_file: Path to the prompt template file
            services: List of service names to process
        """
        self.prompt_file = prompt_file
        self.services = services
        self.output_lines = deque(maxlen=200)  # Keep last 200 lines (supports multi-service output)
        self.full_output = []  # Keep all output for logging
        self.tracker = None  # Must be set by subclass

        # Generate log file path - subclasses should override log_prefix
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        services_str = "-".join(services[:3])  # Max 3 service names in filename
        if len(services) > 3:
            services_str += f"-and-{len(services)-3}-more"
        self.log_file = log_dir / f"{self.log_prefix}_{timestamp}_{services_str}.log"

    @property
    @abstractmethod
    def log_prefix(self) -> str:
        """Return log file prefix for this runner type."""
        pass

    @abstractmethod
    def load_prompt(self) -> str:
        """Load and augment prompt with arguments.

        Returns:
            The augmented prompt string
        """
        pass

    @abstractmethod
    def parse_output(self, line: str) -> None:
        """Parse a line of copilot output for status updates.

        Args:
            line: Output line to parse
        """
        pass

    @abstractmethod
    def get_results_panel(self, return_code: int) -> Panel:
        """Generate final results panel.

        Args:
            return_code: Process return code

        Returns:
            Rich Panel with results display
        """
        pass

    def create_layout(self) -> Layout:
        """Create split layout with status and output.

        Returns:
            Layout with status and output panels
        """
        layout = Layout()
        layout.split_row(
            Layout(name="status", ratio=1),
            Layout(name="output", ratio=2)
        )
        return layout

    def get_output_panel(self) -> Panel:
        """Create panel with scrolling output.

        Returns:
            Rich Panel with formatted output
        """
        if not self.output_lines:
            output_text = Text("Waiting for output...", style="dim")
        else:
            # Join lines and create text
            output_text = Text()
            for line in self.output_lines:
                line_lower = line.lower()

                # Add color coding for common patterns
                if line.startswith("$"):
                    output_text.append(line + "\n", style="cyan")
                elif line.startswith("✓") or "success" in line_lower:
                    output_text.append(line + "\n", style="green")
                elif line.startswith("✗") or "error" in line_lower or "failed" in line_lower:
                    output_text.append(line + "\n", style="red")
                elif line.startswith("●"):
                    output_text.append(line + "\n", style="yellow")
                # Highlight tool executions
                elif "executed:" in line_lower or "_tool" in line_lower:
                    output_text.append(line + "\n", style="cyan bold")
                # Highlight summaries and scan results
                elif "summary" in line_lower or "scan result" in line_lower:
                    output_text.append(line + "\n", style="yellow bold")
                # Highlight starting messages
                elif "starting" in line_lower and "analysis" in line_lower:
                    output_text.append(line + "\n", style="cyan")
                else:
                    output_text.append(line + "\n", style="white")

        return Panel(output_text, title="📋 Agent Output", border_style="blue")

    @abstractmethod
    def show_config(self) -> None:
        """Display run configuration."""
        pass

    def run(self) -> int:
        """Execute copilot with streaming output.

        Returns:
            Process return code
        """
        global current_process

        self.show_config()
        console.print(f"[dim]Logging to: {self.log_file}[/dim]\n")

        prompt_content = self.load_prompt()
        command = ["copilot", "-p", prompt_content, "--allow-all-tools"]

        try:
            # Start process with streaming output
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

            # Initialize panels with content before entering Live context
            if self.tracker:
                layout["status"].update(self.tracker.get_table())
            layout["output"].update(self.get_output_panel())

            # Live display with split view
            from rich.live import Live
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
                            self.parse_output(line)

                            # Update both panels
                            if self.tracker:
                                layout["status"].update(self.tracker.get_table())
                            layout["output"].update(self.get_output_panel())

                # Wait for process to complete
                process.wait()

            # Post-processing happens outside Live context
            console.print()  # Add spacing

            # Print the final results panel
            console.print(self.get_results_panel(process.returncode))

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
        """Save execution log to file.

        Args:
            return_code: Process return code
        """
        try:
            with open(self.log_file, "w") as f:
                f.write(f"{'='*70}\n")
                f.write(f"Copilot {self.log_prefix.title()} Execution Log\n")
                f.write(f"{'='*70}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Services: {', '.join(self.services)}\n")
                f.write(f"Exit Code: {return_code}\n")
                f.write(f"{'='*70}\n\n")
                f.write("\n".join(self.full_output))

            console.print(f"\n[dim]✓ Log saved to: {self.log_file}[/dim]")
        except Exception as e:
            console.print(f"[dim]Warning: Could not save log: {e}[/dim]")


# Global process reference for signal handling
current_process: Optional[subprocess.Popen] = None