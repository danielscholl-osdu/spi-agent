"""Test tracker for Maven test execution."""

from typing import List, Optional

from rich.table import Table


class TestTracker:
    """Tracks the status of Maven test execution for services"""

    def __init__(self, services: List[str], provider: str = "azure"):
        self.provider = provider
        self.services = {
            service: {
                "status": "pending",
                "phase": None,
                "details": "Waiting to start",
                "icon": "⏸",
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

    def update(
        self,
        service: str,
        status: str,
        details: str = "",
        phase: Optional[str] = None,
        tests_run: int = 0,
        tests_failed: int = 0,
        coverage_line: int = 0,
        coverage_branch: int = 0,
    ):
        """Update service test status"""
        if service in self.services:
            icons = {
                "pending": "⏸",
                "compiling": "▶",
                "testing": "▶",
                "coverage": "▶",
                "assessing": "▶",
                "compile_success": "✓",
                "test_success": "✓",
                "compile_failed": "✗",
                "test_failed": "✗",
                "error": "✗",
            }
            self.services[service]["status"] = status
            self.services[service]["details"] = details
            self.services[service]["icon"] = icons.get(status, "•")
            if phase:
                self.services[service]["phase"] = phase
            if tests_run > 0:
                self.services[service]["tests_run"] = tests_run
            if tests_failed > 0:
                self.services[service]["tests_failed"] = tests_failed
            if coverage_line > 0:
                self.services[service]["coverage_line"] = coverage_line
            if coverage_branch > 0:
                self.services[service]["coverage_branch"] = coverage_branch

    def get_table(self) -> Table:
        """Generate Rich table of test status"""
        table = Table(title="Test Execution Status", expand=True)
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
