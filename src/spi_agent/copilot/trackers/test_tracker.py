"""Test tracker for Maven test execution."""

from typing import Any, Dict, List

from rich.table import Table

from spi_agent.copilot.base import BaseTracker
from spi_agent.copilot.constants import STATUS_ICONS


class TestTracker(BaseTracker):
    """Tracks the status of Maven test execution for services"""

    def __init__(self, services: List[str], provider: str = "azure", profiles: List[str] = None):
        self.provider = provider
        self.profiles = profiles if profiles else []
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
        service_dict = {}
        for service in services:
            service_dict[service] = {
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
                "profiles": {},  # Profile-level breakdown
            }

            # Initialize profile-level data if profiles specified
            if self.profiles:
                for profile in self.profiles:
                    service_dict[service]["profiles"][profile] = {
                        "status": "pending",
                        "tests_run": 0,
                        "tests_failed": 0,
                        "coverage_line": 0,
                        "coverage_branch": 0,
                        "quality_grade": None,
                        "quality_label": None,
                        "recommendations": [],
                    }

        return service_dict

    def _update_service(self, service: str, status: str, details: str, **kwargs) -> None:
        """Internal method to update service status.

        Args:
            service: Service name
            status: Status string
            details: Details string
            **kwargs: Optional fields including:
                - profile: If provided, update profile-level data instead of service-level
                - phase, tests_run, tests_failed, coverage_line, coverage_branch
                - quality_grade, quality_label, recommendations
        """
        profile = kwargs.pop("profile", None)

        if profile and profile in self.services[service]["profiles"]:
            # Update profile-level data
            profile_data = self.services[service]["profiles"][profile]
            profile_data["status"] = status

            if "tests_run" in kwargs:
                profile_data["tests_run"] = kwargs["tests_run"]
            if "tests_failed" in kwargs:
                profile_data["tests_failed"] = kwargs["tests_failed"]
            if "coverage_line" in kwargs:
                profile_data["coverage_line"] = kwargs["coverage_line"]
            if "coverage_branch" in kwargs:
                profile_data["coverage_branch"] = kwargs["coverage_branch"]
            if "quality_grade" in kwargs:
                profile_data["quality_grade"] = kwargs["quality_grade"]
            if "quality_label" in kwargs:
                profile_data["quality_label"] = kwargs["quality_label"]
            if "recommendations" in kwargs:
                profile_data["recommendations"] = kwargs["recommendations"]
        else:
            # Update service-level data (original behavior)
            self.services[service]["status"] = status
            self.services[service]["details"] = details
            self.services[service]["icon"] = self.get_icon(status)

            # Handle optional test-specific fields
            if "phase" in kwargs and kwargs["phase"]:
                self.services[service]["phase"] = kwargs["phase"]
            # Store test counts including 0 (previously prevented by > 0 check)
            if "tests_run" in kwargs:
                self.services[service]["tests_run"] = kwargs["tests_run"]
            if "tests_failed" in kwargs:
                self.services[service]["tests_failed"] = kwargs["tests_failed"]
            if "coverage_line" in kwargs and kwargs["coverage_line"] > 0:
                self.services[service]["coverage_line"] = kwargs["coverage_line"]
            if "coverage_branch" in kwargs and kwargs["coverage_branch"] > 0:
                self.services[service]["coverage_branch"] = kwargs["coverage_branch"]

    def _aggregate_profile_data(self, service: str) -> None:
        """Aggregate profile-level data to service-level totals.

        Args:
            service: Service name to aggregate
        """
        if not self.profiles or not self.services[service]["profiles"]:
            return

        profiles = self.services[service]["profiles"]

        # Aggregate test counts
        total_tests_run = sum(p.get("tests_run", 0) for p in profiles.values())
        total_tests_failed = sum(p.get("tests_failed", 0) for p in profiles.values())

        # Calculate weighted average coverage (or use worst case)
        # Using weighted average based on test count
        total_line_cov = 0
        total_branch_cov = 0
        profile_count = 0

        for profile_data in profiles.values():
            if profile_data.get("coverage_line", 0) > 0:
                total_line_cov += profile_data["coverage_line"]
                total_branch_cov += profile_data["coverage_branch"]
                profile_count += 1

        if profile_count > 0:
            avg_line_cov = int(total_line_cov / profile_count)
            avg_branch_cov = int(total_branch_cov / profile_count)
        else:
            avg_line_cov = 0
            avg_branch_cov = 0

        # Update service-level data
        self.services[service]["tests_run"] = total_tests_run
        self.services[service]["tests_failed"] = total_tests_failed
        self.services[service]["coverage_line"] = avg_line_cov
        self.services[service]["coverage_branch"] = avg_branch_cov

        # Update service status if there are failures
        if total_tests_failed > 0:
            self.services[service]["status"] = "test_failed"

        # Service-level grade is worst grade among profiles
        grades_order = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1, None: 0}
        worst_grade = None
        worst_grade_value = 6

        for profile_data in profiles.values():
            grade = profile_data.get("quality_grade")
            if grade and grades_order.get(grade, 0) < worst_grade_value:
                worst_grade = grade
                worst_grade_value = grades_order[grade]

        if worst_grade:
            self.services[service]["quality_grade"] = worst_grade

    def get_table(self) -> Table:
        """Generate Rich table of test status"""
        table = Table(title="Service Status", expand=True)
        table.add_column("Service", style="cyan", no_wrap=True)
        table.add_column("Status", style="yellow")
        table.add_column("P", style="green", justify="right", no_wrap=True)
        table.add_column("F", style="red", justify="right", no_wrap=True)

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

            # Format pass/fail counts similar to triage vulnerability columns
            tests_passed = data["tests_run"] - data["tests_failed"]

            # Pass column: show count or "-" if no tests
            if data["tests_run"] > 0:
                pass_str = f"[green]{tests_passed}[/green]"
            else:
                pass_str = "-"

            # Fail column: show bold red count if failures, otherwise "-"
            if data["tests_failed"] > 0:
                fail_str = f"[bold red]{data['tests_failed']}[/bold red]"
            else:
                fail_str = "-"

            table.add_row(
                f"{data['icon']} {service}",
                f"[{status_style}]{status_display}[/{status_style}]",
                pass_str,
                fail_str,
            )

        return table
