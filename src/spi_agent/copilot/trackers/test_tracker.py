"""Test tracker for Maven test execution."""

from typing import Any, Dict, List, Optional

from rich.table import Table

from spi_agent.copilot.base import BaseTracker
from spi_agent.copilot.constants import STATUS_ICONS


class TestTracker(BaseTracker):
    """Tracks the status of Maven test execution for services"""

    def __init__(self, services: List[str], provider: str = "azure"):
        self.provider = provider
        super().__init__(services)

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
                "phase": None,
                "details": "Waiting to start",
                "icon": self.get_icon("pending"),
                "tests_run": 0,
                "tests_failed": 0,
                "coverage_line": 0,
                "coverage_branch": 0,
                "quality_grade": None,
                "quality_label": None,
                "quality_summary": None,
                "recommendations": [],
            }
            for service in services
        }

    def _update_service(self, service: str, status: str, details: str, **kwargs) -> None:
        """Internal method to update service status."""
        self.services[service]["status"] = status
        self.services[service]["details"] = details
        self.services[service]["icon"] = self.get_icon(status)

        # Handle optional test-specific fields
        if "phase" in kwargs and kwargs["phase"]:
            self.services[service]["phase"] = kwargs["phase"]
        if "tests_run" in kwargs and kwargs["tests_run"] > 0:
            self.services[service]["tests_run"] = kwargs["tests_run"]
        if "tests_failed" in kwargs and kwargs["tests_failed"] > 0:
            self.services[service]["tests_failed"] = kwargs["tests_failed"]
        if "coverage_line" in kwargs and kwargs["coverage_line"] > 0:
            self.services[service]["coverage_line"] = kwargs["coverage_line"]
        if "coverage_branch" in kwargs and kwargs["coverage_branch"] > 0:
            self.services[service]["coverage_branch"] = kwargs["coverage_branch"]

    def get_table(self) -> Table:
        """Generate Rich table of test status"""
        table = Table(title="Service Status", expand=True)
        table.add_column("Service", style="cyan", no_wrap=True)
        table.add_column("Provider", style="blue", no_wrap=True)
        table.add_column("Status", style="yellow")
        table.add_column("Details", style="white", max_width=20, overflow="ellipsis")

        for service, data in self.services.items():
            status_style = {
                "pending": "dim",
                "compiling": "yellow",
                "testing": "blue",
                "coverage": "cyan",
                "assessing": "magenta",
                "compile_success": "green",
                "test_success": "green",
                "compile_failed": "red",
                "test_failed": "red",
                "error": "red",
            }.get(data["status"], "white")

            # Format status display - single word only
            status_map = {
                "pending": "Pending",
                "compiling": "Compiling",
                "testing": "Testing",
                "coverage": "Coverage",
                "assessing": "Assessing",
                "compile_success": "Compiled",
                "test_success": "Complete",
                "compile_failed": "Failed",
                "test_failed": "Failed",
                "error": "Error",
            }
            status_display = status_map.get(data["status"], data["status"].title())

            # Include test/coverage info in details for completed services
            details = data.get("details", "")
            if data["status"] == "test_success" and (data["tests_run"] > 0 or data["coverage_line"] > 0):
                test_info = f"{data['tests_run']} tests" if data["tests_run"] > 0 else ""
                cov_info = f"{data['coverage_line']}%/{data['coverage_branch']}%" if data["coverage_line"] > 0 else ""
                if data.get("quality_grade"):
                    cov_info += f" (Grade {data['quality_grade']})"

                if test_info and cov_info:
                    details = f"{test_info}, {cov_info}"
                elif test_info:
                    details = test_info
                elif cov_info:
                    details = f"Coverage: {cov_info}"

            table.add_row(
                f"{data['icon']} {service}",
                self.provider.capitalize(),
                f"[{status_style}]{status_display}[/{status_style}]",
                details,
            )

        return table
