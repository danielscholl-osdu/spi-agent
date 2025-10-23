"""Vulnerability analysis tracker for Maven dependency and CVE scanning."""

from typing import Any, Dict, List

from rich.table import Table

from spi_agent.copilot.base import BaseTracker
from spi_agent.copilot.constants import STATUS_ICONS


class VulnsTracker(BaseTracker):
    """Tracks the status of vulnerability analysis for services"""

    @property
    def table_title(self) -> str:
        """Return the title for the status table."""
        return "[italic]Service Status[/italic]"

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
                "critical": 0,
                "high": 0,
                "medium": 0,
                "dependencies": 0,
                "report_id": "",
                "top_cves": [],  # List of top CVE details
                "remediation": "",  # Remediation recommendations
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
            **kwargs: Additional fields (critical, high, medium, dependencies, report_id, top_cves, remediation)
        """
        self.services[service]["status"] = status
        self.services[service]["details"] = details
        self.services[service]["icon"] = self.get_icon(status)

        # Update vulnerability counts if provided
        if "critical" in kwargs:
            self.services[service]["critical"] = kwargs["critical"]
        if "high" in kwargs:
            self.services[service]["high"] = kwargs["high"]
        if "medium" in kwargs:
            self.services[service]["medium"] = kwargs["medium"]
        if "dependencies" in kwargs:
            self.services[service]["dependencies"] = kwargs["dependencies"]
        if "report_id" in kwargs:
            self.services[service]["report_id"] = kwargs["report_id"]
        if "top_cves" in kwargs:
            self.services[service]["top_cves"] = kwargs["top_cves"]
        if "remediation" in kwargs:
            self.services[service]["remediation"] = kwargs["remediation"]

    def get_table(self) -> Table:
        """Generate Rich table of triage status"""
        table = Table(title=self.table_title, expand=False)
        table.add_column("Service", style="cyan", no_wrap=True)
        table.add_column("Status", style="magenta", no_wrap=True)
        table.add_column("Critical", style="red", justify="right", no_wrap=True)
        table.add_column("High", style="yellow", justify="right", no_wrap=True)
        table.add_column("Medium", style="blue", justify="right", no_wrap=True)

        for service, data in self.services.items():
            status_style = {
                "pending": "dim",
                "analyzing": "yellow",
                "scanning": "yellow",
                "reporting": "yellow",
                "success": "green",
                "complete": "green",
                "error": "red",
                "skipped": "dim",
            }.get(data["status"], "white")

            # Format vulnerability counts
            critical_str = str(data["critical"]) if data["critical"] > 0 else "-"
            high_str = str(data["high"]) if data["high"] > 0 else "-"
            medium_str = str(data["medium"]) if data["medium"] > 0 else "-"

            # Highlight critical/high vulnerabilities
            if data["critical"] > 0:
                critical_str = f"[bold red]{critical_str}[/bold red]"
            if data["high"] > 0:
                high_str = f"[bold yellow]{high_str}[/bold yellow]"

            table.add_row(
                f"{data['icon']} {service}",
                f"[{status_style}]{data['status'].upper()}[/{status_style}]",
                critical_str,
                high_str,
                medium_str,
            )

        return table

    def get_summary(self) -> Dict[str, int]:
        """Get summary of all vulnerability counts.

        Returns:
            Dictionary with total counts for critical, high, medium vulnerabilities
        """
        summary = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "total_services": len(self.services),
            "completed_services": 0,
            "error_services": 0,
        }

        for data in self.services.values():
            summary["critical"] += data.get("critical", 0)
            summary["high"] += data.get("high", 0)
            summary["medium"] += data.get("medium", 0)

            if data["status"] in ["success", "complete"]:
                summary["completed_services"] += 1
            elif data["status"] == "error":
                summary["error_services"] += 1

        return summary
