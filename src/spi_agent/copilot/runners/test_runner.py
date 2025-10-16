"""Test runner for executing Maven tests with coverage analysis."""

import logging
import re
import subprocess
from datetime import datetime
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import List, Union

from rich.live import Live
from rich.panel import Panel

from spi_agent.copilot.base import BaseRunner
from spi_agent.copilot.base.runner import console
from spi_agent.copilot.config import config
from spi_agent.copilot.trackers import TestTracker


class TestRunner(BaseRunner):
    """Runs Copilot CLI to execute Maven tests with live output and coverage analysis"""

    def __init__(
        self,
        prompt_file: Union[Path, Traversable],
        services: List[str],
        provider: str = "azure",
    ):
        super().__init__(prompt_file, services)
        self.provider = provider
        self.tracker = TestTracker(services, provider)

        # Initialize logger for coverage extraction debugging
        self.logger = logging.getLogger(__name__)

    @property
    def log_prefix(self) -> str:
        """Return log file prefix for this runner type."""
        return "test"

    def load_prompt(self) -> str:
        """Load and augment prompt with arguments"""
        prompt = self.prompt_file.read_text(encoding="utf-8")

        # Replace organization placeholder
        prompt = prompt.replace("{{ORGANIZATION}}", config.organization)

        # Inject arguments
        services_arg = ",".join(self.services)
        augmented = f"{prompt}\n\nARGUMENTS:\nSERVICES: {services_arg}\nPROVIDER: {self.provider}"

        return augmented

    def show_config(self):
        """Display run configuration"""
        config_text = f"""[cyan]Services:[/cyan]   {', '.join(self.services)}
[cyan]Provider:[/cyan]   {self.provider}"""

        console.print(Panel(config_text, title="🧪 Maven Test Execution", border_style="blue"))
        console.print()

    def parse_output(self, line: str) -> None:
        """Parse copilot's task announcements for test status updates"""
        line_lower = line.lower()
        line_stripped = line.strip()

        # Strategy: Only parse copilot's task announcements, not raw Maven output
        # Copilot tells us everything we need through its task markers

        # Find which service this line is about
        target_service = None
        for service in self.services:
            # Match service name in various formats: "partition", "Partition", "**partition**"
            if service in line_lower or f"**{service}**" in line_lower:
                target_service = service
                break

        if not target_service:
            return

        # Parse copilot's status updates (matches the exact format from test.md prompt)
        # Strip leading bullets (● prefix)
        line_for_parsing = line_stripped.lstrip("●").strip()

        # Only parse lines starting with ✓ (task completion markers)
        if line_for_parsing.startswith("✓") and ":" in line_for_parsing:
            # Expected formats from prompt:
            # "✓ partition: Starting compile phase"
            # "✓ partition: Starting test phase"
            # "✓ partition: Starting coverage phase"
            # "✓ partition: Compiled successfully, 61 tests passed, Coverage report generated"

            if "starting compile phase" in line_lower:
                self.tracker.update(target_service, "compiling", "Compiling", phase="compile")

            elif "starting test phase" in line_lower:
                self.tracker.update(target_service, "testing", "Testing", phase="test")

            elif "starting coverage phase" in line_lower:
                self.tracker.update(target_service, "coverage", "Coverage", phase="coverage")

            elif "compiled successfully" in line_lower:
                # Completion summary - extract test count
                test_count_match = re.search(r'(\d+)\s+tests?\s+passed', line_lower)
                tests_run = int(test_count_match.group(1)) if test_count_match else 0

                self.tracker.update(target_service, "test_success", "Complete",
                                  phase="coverage", tests_run=tests_run, tests_failed=0)

        # Detect errors
        if "build failure" in line_lower and target_service:
            self.tracker.update(target_service, "test_failed", "Build failed", phase="test")
        elif "compilation failure" in line_lower and target_service:
            self.tracker.update(target_service, "compile_failed", "Failed", phase="compile")

    def run(self) -> int:
        """Execute copilot to run Maven tests with live output"""
        global current_process

        self.show_config()
        console.print(f"[dim]Logging to: {self.log_file}[/dim]\n")

        prompt_content = self.load_prompt()
        command = ["copilot", "-p", prompt_content, "--allow-all-tools"]

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            current_process = process

            layout = self.create_layout()
            layout["status"].update(self.tracker.get_table())
            layout["output"].update(self.get_output_panel())

            with Live(layout, console=console, refresh_per_second=2) as live:
                if process.stdout:
                    last_update = 0
                    for line in process.stdout:
                        line = line.rstrip()
                        if line:
                            self.output_lines.append(line)
                            self.full_output.append(line)

                            # Parse output and check if status changed
                            old_status = dict(self.tracker.services)
                            self.parse_output(line)

                            # Only update display if status changed or every 10 lines
                            status_changed = old_status != self.tracker.services
                            last_update += 1

                            if status_changed or last_update >= 10:
                                layout["status"].update(self.tracker.get_table())
                                layout["output"].update(self.get_output_panel())
                                last_update = 0

                process.wait()

                # Mark any remaining services as completed based on return code
                if process.returncode == 0:
                    for service in self.services:
                        status = self.tracker.services[service]["status"]
                        # Only update if not already in a completed state
                        if status not in ["compile_failed", "test_failed", "error", "test_success", "compile_success"]:
                            if status == "compiling":
                                self.tracker.update(service, "compile_success", "Compiled")
                            else:
                                # Mark as complete but don't overwrite test data
                                self.tracker.update(service, "test_success", "Complete")

                    # Final update before exiting Live
                    layout["status"].update(self.tracker.get_table())
                    live.refresh()

            # ALL post-processing happens OUTSIDE Live context to prevent panel jumping
            console.print()  # Add spacing

            # Extract coverage from JaCoCo reports (post-processing)
            self._extract_coverage_from_reports()

            # Assess coverage quality
            self._assess_coverage_quality()

            # Update quality results in tracker
            for service in self.services:
                if self.tracker.services[service].get("quality_grade"):
                    grade = self.tracker.services[service]["quality_grade"]
                    label = self.tracker.services[service].get("quality_label", "")
                    self.tracker.services[service]["details"] = f"Grade {grade}: {label}"

            # Print the final results panel
            console.print(self.get_results_panel(process.returncode))

            self._save_log(process.returncode)

            return process.returncode

        except FileNotFoundError:
            console.print(
                "[red]Error:[/red] 'copilot' command not found. Is GitHub Copilot CLI installed?",
                style="bold red",
            )
            return 1
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}", style="bold red")
            import traceback
            traceback.print_exc()
            return 1
        finally:
            current_process = None

    def _extract_coverage_from_csv(self, service: str, base_path: Path) -> tuple[float, float]:
        """
        Extract coverage data from JaCoCo CSV reports.

        CSV format is stable and reliable across JaCoCo versions.
        Returns (line_coverage_percent, branch_coverage_percent).
        """
        # Search for jacoco.csv in multiple locations
        csv_paths = [
            base_path / "target" / "site" / "jacoco" / "jacoco.csv",
        ]

        # Also check provider-specific subdirectories
        provider_dir = base_path / "provider"
        if provider_dir.exists():
            for subdir in provider_dir.iterdir():
                if subdir.is_dir():
                    csv_paths.append(subdir / "target" / "site" / "jacoco" / "jacoco.csv")

        # Check for multi-module structures
        for item in base_path.iterdir():
            if item.is_dir() and item.name not in ["target", "src", ".git", "provider"]:
                potential_csv = item / "target" / "site" / "jacoco" / "jacoco.csv"
                if potential_csv not in csv_paths:
                    csv_paths.append(potential_csv)

        total_line_covered = 0
        total_line_missed = 0
        total_branch_covered = 0
        total_branch_missed = 0
        files_parsed = 0

        for csv_path in csv_paths:
            if not csv_path.exists():
                continue

            try:
                self.logger.debug(f"[{service}] Found CSV report: {csv_path}")
                content = csv_path.read_text(encoding='utf-8')
                lines = content.strip().split('\n')

                if len(lines) < 2:
                    self.logger.debug(f"[{service}] CSV file is empty or has no data rows")
                    continue

                # Skip header row, parse data rows
                for i, line in enumerate(lines[1:], start=2):
                    if not line.strip():
                        continue

                    parts = line.split(',')
                    if len(parts) < 9:
                        self.logger.debug(f"[{service}] Skipping malformed CSV row {i}: insufficient columns")
                        continue

                    try:
                        # CSV columns: GROUP,PACKAGE,CLASS,INSTRUCTION_MISSED,INSTRUCTION_COVERED,
                        #              BRANCH_MISSED,BRANCH_COVERED,LINE_MISSED,LINE_COVERED,...
                        branch_missed = int(parts[5])
                        branch_covered = int(parts[6])
                        line_missed = int(parts[7])
                        line_covered = int(parts[8])

                        total_line_covered += line_covered
                        total_line_missed += line_missed
                        total_branch_covered += branch_covered
                        total_branch_missed += branch_missed

                    except (ValueError, IndexError) as e:
                        self.logger.debug(f"[{service}] Skipping malformed CSV row {i}: {e}")
                        continue

                files_parsed += 1
                self.logger.debug(f"[{service}] Parsed CSV with totals - Lines: {total_line_covered}/{total_line_missed}, Branches: {total_branch_covered}/{total_branch_missed}")

            except Exception as e:
                self.logger.debug(f"[{service}] Failed to parse CSV at {csv_path}: {e}")
                continue

        # Calculate percentages
        line_cov = 0.0
        branch_cov = 0.0

        if total_line_covered + total_line_missed > 0:
            line_cov = (total_line_covered / (total_line_covered + total_line_missed)) * 100

        if total_branch_covered + total_branch_missed > 0:
            branch_cov = (total_branch_covered / (total_branch_covered + total_branch_missed)) * 100

        if files_parsed > 0:
            self.logger.debug(f"[{service}] CSV parsing succeeded: {line_cov:.1f}% line, {branch_cov:.1f}% branch coverage")
        else:
            self.logger.debug(f"[{service}] No CSV files found or parsed")

        return (line_cov, branch_cov)

    def _extract_coverage_from_html(self, service: str, base_path: Path) -> tuple[int, int]:
        """
        Extract coverage data from JaCoCo HTML reports (DEPRECATED - use CSV).

        HTML parsing is fragile and version-dependent. Use CSV parsing instead.
        Returns (line_coverage_percent, branch_coverage_percent).
        """
        # Try multiple report paths
        report_paths = [
            base_path / "target" / "site" / "jacoco" / "index.html",
        ]

        # Also check provider-specific subdirectories
        provider_dir = base_path / "provider"
        if provider_dir.exists():
            for subdir in provider_dir.iterdir():
                if subdir.is_dir():
                    report_paths.append(subdir / "target" / "site" / "jacoco" / "index.html")

        for report_path in report_paths:
            if not report_path.exists():
                continue

            try:
                self.logger.debug(f"[{service}] Found HTML report: {report_path}")
                content = report_path.read_text(encoding='utf-8')

                # Parse JaCoCo HTML - extract from "X of Y" format in bar cells
                total_section = re.search(r'<tfoot>.*?</tfoot>', content, re.DOTALL)
                if total_section:
                    tfoot_html = total_section.group()

                    # Extract all "X of Y" patterns from bar cells
                    bar_matches = re.findall(r'class="bar">(\d+(?:,\d+)?) of (\d+(?:,\d+)?)</td>', tfoot_html)

                    if len(bar_matches) >= 2:
                        # Parse branches
                        branch_missed = int(bar_matches[1][0].replace(',', ''))
                        branch_total = int(bar_matches[1][1].replace(',', ''))
                        branch_covered = branch_total - branch_missed
                        branch_cov = int((branch_covered / branch_total) * 100) if branch_total > 0 else 0

                        # Extract all ctr1 values (missed counts)
                        ctr1_values = re.findall(r'class="ctr1">(\d+(?:,\d+)?)</td>', tfoot_html)
                        # Extract all non-percentage ctr2 values (total counts)
                        ctr2_all = re.findall(r'class="ctr2">(\d+(?:,\d+)?)</td>', tfoot_html)
                        ctr2_values = [v for v in ctr2_all if not v.endswith('%') and '%' not in v]

                        # Lines should be: ctr1[1] (missed), ctr2[1] (total)
                        if len(ctr1_values) >= 2 and len(ctr2_values) >= 2:
                            line_missed = int(ctr1_values[1].replace(',', ''))
                            line_total = int(ctr2_values[1].replace(',', ''))
                            line_cov = int(((line_total - line_missed) / line_total) * 100) if line_total > 0 else 0
                        else:
                            # Fallback: use instruction coverage as proxy
                            inst_missed = int(bar_matches[0][0].replace(',', ''))
                            inst_total = int(bar_matches[0][1].replace(',', ''))
                            inst_covered = inst_total - inst_missed
                            line_cov = int((inst_covered / inst_total) * 100) if inst_total > 0 else 0

                        if line_cov > 0 or branch_cov > 0:
                            self.logger.debug(f"[{service}] HTML parsing succeeded: {line_cov}% line, {branch_cov}% branch")
                            return (line_cov, branch_cov)

            except Exception as e:
                self.logger.debug(f"[{service}] Failed to parse HTML at {report_path}: {e}")
                continue

        self.logger.debug(f"[{service}] No HTML files found or parsed")
        return (0, 0)

    def _extract_coverage_from_reports(self):
        """
        Extract coverage data from JaCoCo reports (post-processing).

        Prioritizes CSV parsing (stable, reliable) with HTML fallback (deprecated).
        """
        for service in self.services:
            if self.tracker.services[service]["coverage_line"] > 0:
                continue  # Already have coverage data

            # Look for JaCoCo report in multiple possible locations
            search_paths = [
                Path.cwd() / "repos" / service,
                Path.cwd() / service,
            ]

            coverage_found = False
            for base_path in search_paths:
                if not base_path.exists():
                    self.logger.debug(f"[{service}] Path does not exist: {base_path}")
                    continue

                self.logger.debug(f"[{service}] Searching for coverage reports in: {base_path}")

                # PRIORITY 1: Try CSV extraction (stable, reliable)
                line_cov, branch_cov = self._extract_coverage_from_csv(service, base_path)

                if line_cov > 0 or branch_cov > 0:
                    self.logger.info(f"[{service}] CSV parsing succeeded: {line_cov:.1f}% line, {branch_cov:.1f}% branch")
                    self.tracker.update(
                        service,
                        self.tracker.services[service]["status"],  # Keep current status
                        f"Coverage: {int(line_cov)}%/{int(branch_cov)}%",
                        phase="coverage",
                        coverage_line=int(line_cov),
                        coverage_branch=int(branch_cov),
                    )
                    coverage_found = True
                    break

                # PRIORITY 2: Fallback to HTML parsing (deprecated, fragile)
                self.logger.warning(f"[{service}] CSV parsing returned 0% coverage, falling back to HTML parsing (deprecated)")
                line_cov_html, branch_cov_html = self._extract_coverage_from_html(service, base_path)

                if line_cov_html > 0 or branch_cov_html > 0:
                    self.logger.warning(f"[{service}] HTML parsing succeeded (deprecated): {line_cov_html}% line, {branch_cov_html}% branch")
                    self.tracker.update(
                        service,
                        self.tracker.services[service]["status"],  # Keep current status
                        f"Coverage: {line_cov_html}%/{branch_cov_html}%",
                        phase="coverage",
                        coverage_line=line_cov_html,
                        coverage_branch=branch_cov_html,
                    )
                    coverage_found = True
                    break
                else:
                    self.logger.warning(f"[{service}] Both CSV and HTML parsing failed to extract coverage")

                if coverage_found:
                    break

            if not coverage_found:
                self.logger.warning(f"[{service}] No coverage data found in any location")

    def _assess_coverage_quality(self):
        """Assess coverage quality based on coverage metrics."""
        for service in self.services:
            line_cov = self.tracker.services[service]["coverage_line"]
            branch_cov = self.tracker.services[service]["coverage_branch"]

            # Determine quality grade
            if line_cov >= 90 and branch_cov >= 85:
                grade = "A"
                label = "Excellent"
                summary = "Outstanding test coverage with all critical paths well-tested."
            elif line_cov >= 80 and branch_cov >= 70:
                grade = "B"
                label = "Good"
                summary = "Good test coverage with most critical paths tested."
            elif line_cov >= 70 and branch_cov >= 60:
                grade = "C"
                label = "Acceptable"
                summary = "Acceptable coverage but room for improvement."
            elif line_cov >= 60 and branch_cov >= 50:
                grade = "D"
                label = "Needs Improvement"
                summary = "Coverage is below recommended levels. Consider adding more tests."
            elif line_cov == 0 and branch_cov == 0:
                # Special case: No coverage detected at all
                grade = "F"
                label = "No Coverage"
                summary = "No coverage data detected. Ensure JaCoCo plugin is properly configured."
            else:
                grade = "F"
                label = "Poor"
                summary = "Critical gaps in test coverage. Immediate attention needed."

            # Generate recommendations based on coverage levels
            recommendations = []

            # Special recommendations for zero coverage
            if line_cov == 0 and branch_cov == 0:
                recommendations.append({
                    "priority": 1,
                    "action": "Ensure JaCoCo Maven plugin is configured in pom.xml",
                    "expected_improvement": "Enable coverage reporting"
                })
                recommendations.append({
                    "priority": 2,
                    "action": "Verify tests are being executed during Maven build",
                    "expected_improvement": "Generate coverage data"
                })
            else:
                # Normal recommendations for non-zero coverage
                if branch_cov < line_cov - 15:
                    recommendations.append({
                        "priority": 1,
                        "action": "Improve branch coverage by testing edge cases and conditions",
                        "expected_improvement": f"+{min(10, line_cov - branch_cov)}% branch coverage"
                    })

                if line_cov < 80:
                    recommendations.append({
                        "priority": 1 if not recommendations else 2,
                        "action": "Add unit tests for uncovered methods and classes",
                        "expected_improvement": f"+{min(15, 80 - line_cov)}% line coverage"
                    })

                if line_cov >= 80 and branch_cov < 80:
                    recommendations.append({
                        "priority": len(recommendations) + 1,
                        "action": "Focus on testing complex conditional logic",
                        "expected_improvement": "Better branch coverage"
                    })

                if grade in ["A", "B"] and len(recommendations) == 0:
                    recommendations.append({
                        "priority": 1,
                        "action": "Maintain current coverage levels with new code",
                        "expected_improvement": "Sustained quality"
                    })

            # Store assessment results
            self.tracker.services[service]["quality_grade"] = grade
            self.tracker.services[service]["quality_label"] = label
            self.tracker.services[service]["quality_summary"] = summary
            self.tracker.services[service]["recommendations"] = recommendations[:3]  # Top 3 only

    def get_quality_panel(self) -> Panel:
        """Generate quality assessment panel with clean columnar layout"""
        from rich.table import Table

        # Create a table for the results
        table = Table(expand=True, show_header=True, header_style="bold cyan")
        table.add_column("Service", style="cyan", no_wrap=True)
        table.add_column("Provider", style="blue", no_wrap=True)
        table.add_column("Result", style="yellow", no_wrap=True)
        table.add_column("Grade", justify="center", no_wrap=True)
        table.add_column("Recommendation", style="white", ratio=2)

        for service, data in self.tracker.services.items():
            # Determine result status
            result = "Pending"
            result_style = "dim"

            if data["status"] == "compile_failed":
                result = "Compile Failed"
                result_style = "red"
            elif data["status"] == "test_failed":
                result = f"Failed ({data['tests_failed']}/{data['tests_run']} tests)"
                result_style = "red"
            elif data["status"] == "test_success":
                # Prioritize coverage display when available (basis for grade)
                if data.get("coverage_line", 0) > 0 or data.get("coverage_branch", 0) > 0:
                    result = f"Cov: {data['coverage_line']}%/{data['coverage_branch']}%"
                    result_style = "green"
                elif data["tests_run"] > 0:
                    # Fallback to test count if no coverage data
                    result = f"Passed ({data['tests_run']} tests)"
                    result_style = "green"
                else:
                    # No tests and no coverage
                    result = "No tests"
                    result_style = "yellow"
            elif data["status"] == "compile_success":
                result = "Compiled"
                result_style = "green"
            elif data["status"] == "assessing":
                result = "Assessing..."
                result_style = "magenta"
            elif data["status"] == "compiling":
                result = "Compiling..."
                result_style = "yellow"
            elif data["status"] == "testing":
                result = "Testing..."
                result_style = "blue"
            elif data["status"] == "coverage":
                result = "Coverage..."
                result_style = "cyan"

            # Grade column
            grade = ""
            grade_style = "white"
            if data.get("quality_grade"):
                grade = data["quality_grade"]
                grade_style = {
                    "A": "green",
                    "B": "cyan",
                    "C": "yellow",
                    "D": "magenta",
                    "F": "red"
                }.get(grade, "white")

            # Recommendation column
            recommendation = ""
            if data.get("recommendations"):
                # Get first recommendation
                rec = data["recommendations"][0]
                recommendation = rec.get("action", "")
                # Truncate if too long
                if len(recommendation) > 60:
                    recommendation = recommendation[:57] + "..."
            elif data.get("quality_label"):
                recommendation = data["quality_label"]

            table.add_row(
                service,
                self.tracker.provider.capitalize(),
                f"[{result_style}]{result}[/{result_style}]",
                f"[{grade_style}]{grade}[/{grade_style}]" if grade else "",
                recommendation
            )

        # Return table in panel
        return Panel(
            table,
            title="📊 Test Results",
            border_style="cyan"
        )

    def _save_log(self, return_code: int):
        """Save execution log to file"""
        try:
            with open(self.log_file, "w") as f:
                f.write(f"{'='*70}\n")
                f.write("Maven Test Execution Log\n")
                f.write(f"{'='*70}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Services: {', '.join(self.services)}\n")
                f.write(f"Provider: {self.provider}\n")
                f.write(f"Exit Code: {return_code}\n")
                f.write(f"{'='*70}\n\n")

                f.write("=== TEST RESULTS ===\n\n")
                for service, data in self.tracker.services.items():
                    f.write(f"{service}:\n")
                    f.write(f"  Status: {data['status']}\n")
                    f.write(f"  Phase: {data.get('phase', 'N/A')}\n")
                    f.write(f"  Tests Run: {data['tests_run']}\n")
                    f.write(f"  Tests Failed: {data['tests_failed']}\n")
                    f.write(f"  Coverage Line: {data['coverage_line']}%\n")
                    f.write(f"  Coverage Branch: {data['coverage_branch']}%\n")
                    if data.get("quality_grade"):
                        f.write(f"  Quality Grade: {data['quality_grade']} - {data.get('quality_label', 'N/A')}\n")
                        f.write(f"  Quality Summary: {data.get('quality_summary', 'N/A')}\n")
                        if data.get("recommendations"):
                            f.write("  Recommendations:\n")
                            for rec in data["recommendations"][:5]:
                                f.write(f"    - {rec.get('action', 'N/A')}")
                                if rec.get("expected_improvement"):
                                    f.write(f" ({rec['expected_improvement']})")
                                f.write("\n")
                    f.write("\n")

                f.write("\n=== FULL OUTPUT ===\n\n")
                f.write("\n".join(self.full_output))

            console.print(f"\n[dim]✓ Log saved to: {self.log_file}[/dim]")
        except Exception as e:
            console.print(f"[dim]Warning: Could not save log: {e}[/dim]")

    def get_results_panel(self, return_code: int) -> Panel:
        """Generate final results panel - uses the same clean table format as quality panel"""
        # Simply return the quality panel which already has the clean columnar layout
        return self.get_quality_panel()


