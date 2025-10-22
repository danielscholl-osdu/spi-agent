"""Dependency update analysis tracker for Maven version checking."""

from typing import Any, Dict, List

from rich.table import Table

from spi_agent.copilot.base import BaseTracker
from spi_agent.copilot.constants import STATUS_ICONS


class DependsTracker(BaseTracker):
    """Tracks the status of dependency update analysis for services"""

    @property
    def table_title(self) -> str:
        """Return the title for the status table."""
        return "📦 Dependency Update Analysis Status"

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
                "major_updates": 0,
                "minor_updates": 0,
                "patch_updates": 0,
                "total_dependencies": 0,
                "outdated_dependencies": 0,
                "report_id": "",
                "top_updates": [],  # List of top update recommendations
                "modules": {},  # Module-level breakdown
            }
            for service in services
        }

    def _update_service(self, service: str, status: str, details: str, **kwargs) -> None:
        """Internal method to update service status.

        Args:
            service: Service name to update
            status: New status value
            details: Optional status details
            **kwargs: Additional fields (major_updates, minor_updates, patch_updates,
                     total_dependencies, outdated_dependencies, report_id, top_updates)
        """
        self.services[service]["status"] = status
        self.services[service]["details"] = details
        self.services[service]["icon"] = self.get_icon(status)

        # Update dependency counts if provided
        if "major_updates" in kwargs:
            self.services[service]["major_updates"] = kwargs["major_updates"]
        if "minor_updates" in kwargs:
            self.services[service]["minor_updates"] = kwargs["minor_updates"]
        if "patch_updates" in kwargs:
            self.services[service]["patch_updates"] = kwargs["patch_updates"]
        if "total_dependencies" in kwargs:
            self.services[service]["total_dependencies"] = kwargs["total_dependencies"]
        if "outdated_dependencies" in kwargs:
            self.services[service]["outdated_dependencies"] = kwargs["outdated_dependencies"]
        if "report_id" in kwargs:
            self.services[service]["report_id"] = kwargs["report_id"]
        if "top_updates" in kwargs:
            self.services[service]["top_updates"] = kwargs["top_updates"]

    def get_table(self) -> Table:
        """Generate Rich table of dependency analysis status"""
        table = Table(title=self.table_title, expand=False)
        table.add_column("Service", style="cyan", no_wrap=True)
        table.add_column("Status", style="magenta", no_wrap=True)
        table.add_column("Major", style="red", justify="right", no_wrap=True)
        table.add_column("Minor", style="yellow", justify="right", no_wrap=True)
        table.add_column("Patch", style="blue", justify="right", no_wrap=True)

        for service, data in self.services.items():
            status_style = {
                "pending": "dim",
                "analyzing": "yellow",
                "checking": "yellow",
                "reporting": "yellow",
                "success": "green",
                "complete": "green",
                "error": "red",
                "skipped": "dim",
            }.get(data["status"], "white")

            # Format update counts
            major_str = str(data["major_updates"]) if data["major_updates"] > 0 else "-"
            minor_str = str(data["minor_updates"]) if data["minor_updates"] > 0 else "-"
            patch_str = str(data["patch_updates"]) if data["patch_updates"] > 0 else "-"

            # Highlight major updates
            if data["major_updates"] > 0:
                major_str = f"[bold red]{major_str}[/bold red]"
            if data["minor_updates"] > 0:
                minor_str = f"[bold yellow]{minor_str}[/bold yellow]"

            table.add_row(
                f"{data['icon']} {service}",
                f"[{status_style}]{data['status'].upper()}[/{status_style}]",
                major_str,
                minor_str,
                patch_str,
            )

        return table

    def get_summary(self) -> Dict[str, int]:
        """Get summary of all dependency update counts.

        Returns:
            Dictionary with total counts for major, minor, patch updates
        """
        summary = {
            "major_updates": 0,
            "minor_updates": 0,
            "patch_updates": 0,
            "total_dependencies": 0,
            "outdated_dependencies": 0,
            "total_services": len(self.services),
            "completed_services": 0,
            "error_services": 0,
        }

        for data in self.services.values():
            summary["major_updates"] += data.get("major_updates", 0)
            summary["minor_updates"] += data.get("minor_updates", 0)
            summary["patch_updates"] += data.get("patch_updates", 0)
            summary["total_dependencies"] += data.get("total_dependencies", 0)
            summary["outdated_dependencies"] += data.get("outdated_dependencies", 0)

            if data["status"] in ["success", "complete"]:
                summary["completed_services"] += 1
            elif data["status"] == "error":
                summary["error_services"] += 1

        return summary
