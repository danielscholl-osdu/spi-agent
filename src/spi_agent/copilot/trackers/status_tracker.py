"""Status tracker for GitHub data gathering."""

from typing import List

from rich.table import Table


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
