"""Display utilities for rich console output."""

from collections import deque
from typing import Union

from rich.panel import Panel
from rich.text import Text


def create_output_panel(
    output_lines: Union[deque, list],
    title: str = "Agent Output",
    border_style: str = "blue"
) -> Panel:
    """Create a panel with scrolling output and consistent formatting.

    Args:
        output_lines: Deque or list of output lines to display
        title: Panel title
        border_style: Border color style

    Returns:
        Rich Panel with formatted output
    """
    if not output_lines:
        output_text = Text("Waiting for output...", style="dim")
    else:
        # Join lines and create text
        output_text = Text()
        for line in output_lines:
            # Add color coding for common patterns
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

    return Panel(output_text, title=title, border_style=border_style)