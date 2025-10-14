"""Service status tracker for copilot CLI wrapper."""

from typing import Any, Dict, List

from rich.table import Table

from spi_agent.copilot.base import BaseTracker
from spi_agent.copilot.constants import STATUS_ICONS


class ServiceTracker(BaseTracker):
    """Tracks the status of services being processed"""

    @property
    def table_title(self) -> str:
        """Return the title for the status table."""
        return "Service Status"

    @property
    def status_icons(self) -> Dict[str, str]:
        """Return status icon mapping."""
        return STATUS_ICONS

    def _initialize_services(self, services: List[str]) -> Dict[str, Dict[str, Any]]:
        """Initialize service tracking dictionary."""
        return {
            service: {
                "status": "pending",
                "details": "Waiting to start",
                "icon": self.get_icon("pending"),
            }
            for service in services
        }

    def _update_service(self, service: str, status: str, details: str, **kwargs) -> None:
        """Internal method to update service status."""
        self.services[service]["status"] = status
        self.services[service]["details"] = details
        self.services[service]["icon"] = self.get_icon(status)

    def get_table(self) -> Table:
        """Generate Rich table of service status"""
        table = Table(title=self.table_title, expand=True)
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
