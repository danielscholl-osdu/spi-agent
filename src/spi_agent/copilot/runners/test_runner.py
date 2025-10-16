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

        # Parse provider into profiles list
        self.profiles = self._parse_provider_to_profiles(provider)

        # Create tracker with profiles if multiple specified
        self.tracker = TestTracker(services, provider, profiles=self.profiles if len(self.profiles) > 1 else [])

        # Initialize logger for coverage extraction debugging
        # Configure to write only to log file, not console
        self.logger = logging.getLogger(f"{__name__}.{id(self)}")  # Unique logger per instance
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False  # Prevent propagation to root logger (blocks console output)

        # Add file handler
        file_handler = logging.FileHandler(self.log_file)
        file_handler.setFormatter(
            logging.Formatter('[%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s] %(message)s')
        )
        self.logger.addHandler(file_handler)

    @property
    def log_prefix(self) -> str:
        """Return log file prefix for this runner type."""
        return "test"

    def _parse_provider_to_profiles(self, provider: str) -> List[str]:
        """Parse provider string into list of profiles.

        Args:
            provider: Provider string (e.g., "azure", "azure,aws", "all")

        Returns:
            List of profile names
        """
        if provider == "all":
            return ["core", "core-plus", "azure", "aws", "gc", "ibm"]
        elif "," in provider:
            # Multiple providers specified
            return [p.strip() for p in provider.split(",")]
        else:
            # Single provider
            return [provider]

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
        if len(self.profiles) > 1:
            profiles_str = ', '.join(self.profiles)
            config_text = f"""[cyan]Services:[/cyan]   {', '.join(self.services)}
[cyan]Profiles:[/cyan]   {profiles_str}"""
        else:
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

    def _extract_coverage_from_csv(self, service: str, base_path: Path, profile: str = None) -> tuple[float, float]:
        """
        Extract coverage data from JaCoCo CSV reports.

        CSV format is stable and reliable across JaCoCo versions.
        Returns (line_coverage_percent, branch_coverage_percent).

        Args:
            service: Service name
            base_path: Base path to search for coverage reports
            profile: Optional profile name to filter coverage by module
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
                profile_prefix = f"[{service}:{profile}] " if profile else f"[{service}] "
                self.logger.debug(f"{profile_prefix}Found CSV report: {csv_path}")
                content = csv_path.read_text(encoding='utf-8')
                lines = content.strip().split('\n')

                if len(lines) < 2:
                    self.logger.debug(f"{profile_prefix}CSV file is empty or has no data rows")
                    continue

                # Skip header row, parse data rows
                for i, line in enumerate(lines[1:], start=2):
                    if not line.strip():
                        continue

                    parts = line.split(',')
                    if len(parts) < 9:
                        self.logger.debug(f"{profile_prefix}Skipping malformed CSV row {i}: insufficient columns")
                        continue

                    # If profile filtering is enabled, check if this row matches the profile
                    if profile:
                        # CSV columns: GROUP,PACKAGE,CLASS,...
                        group = parts[0].lower()
                        package = parts[1].lower()

                        # Profile matching logic:
                        # - Check if group or package contains profile name
                        # - Examples: "partition-azure", "partition.azure", "provider.partition-azure"
                        # - Also handle: "core", "core-plus"
                        profile_normalized = profile.lower().replace("-", "")
                        module_path = f"{group}.{package}"

                        # Check for profile match
                        if profile == "core-plus":
                            # Special handling for core-plus
                            if "coreplus" not in module_path and "core-plus" not in module_path:
                                continue
                        elif profile == "core":
                            # Core should not match core-plus
                            if "coreplus" in module_path or "core-plus" in module_path:
                                continue
                            # Must have "core" but not as part of "coreplus"
                            if "core" not in module_path:
                                continue
                        else:
                            # Regular profile matching
                            if profile_normalized not in module_path.replace("-", ""):
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
                        self.logger.debug(f"{profile_prefix}Skipping malformed CSV row {i}: {e}")
                        continue

                files_parsed += 1
                self.logger.debug(f"{profile_prefix}Parsed CSV with totals - Lines: {total_line_covered}/{total_line_missed}, Branches: {total_branch_covered}/{total_branch_missed}")

            except Exception as e:
                self.logger.debug(f"{profile_prefix}Failed to parse CSV at {csv_path}: {e}")
                continue

        # Calculate percentages
        line_cov = 0.0
        branch_cov = 0.0

        if total_line_covered + total_line_missed > 0:
            line_cov = (total_line_covered / (total_line_covered + total_line_missed)) * 100

        if total_branch_covered + total_branch_missed > 0:
            branch_cov = (total_branch_covered / (total_branch_covered + total_branch_missed)) * 100

        profile_prefix = f"[{service}:{profile}] " if profile else f"[{service}] "
        if files_parsed > 0:
            self.logger.debug(f"{profile_prefix}CSV parsing succeeded: {line_cov:.1f}% line, {branch_cov:.1f}% branch coverage")
        else:
            self.logger.debug(f"{profile_prefix}No CSV files found or parsed")

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
        If multiple profiles specified, extracts coverage for each profile separately.
        """
        for service in self.services:
            # Look for JaCoCo report in multiple possible locations
            search_paths = [
                Path.cwd() / "repos" / service,
                Path.cwd() / service,
            ]

            # Find valid base path
            base_path = None
            for path in search_paths:
                if path.exists():
                    base_path = path
                    break

            if not base_path:
                self.logger.warning(f"[{service}] No valid path found for coverage extraction")
                continue

            self.logger.debug(f"[{service}] Searching for coverage reports in: {base_path}")

            if len(self.profiles) > 1:
                # Multi-profile mode: extract coverage for each profile
                for profile in self.profiles:
                    line_cov, branch_cov = self._extract_coverage_from_csv(service, base_path, profile=profile)

                    if line_cov > 0 or branch_cov > 0:
                        self.logger.info(f"[{service}:{profile}] CSV parsing succeeded: {line_cov:.1f}% line, {branch_cov:.1f}% branch")
                        self.tracker.update(
                            service,
                            "test_success",
                            f"Coverage: {int(line_cov)}%/{int(branch_cov)}%",
                            profile=profile,
                            coverage_line=int(line_cov),
                            coverage_branch=int(branch_cov),
                        )
                    else:
                        self.logger.warning(f"[{service}:{profile}] No coverage data found for profile")

                # Aggregate profile data to service level
                self.tracker._aggregate_profile_data(service)

            else:
                # Single-profile mode (original behavior)
                if self.tracker.services[service]["coverage_line"] > 0:
                    continue  # Already have coverage data

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
                else:
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
                    else:
                        self.logger.warning(f"[{service}] Both CSV and HTML parsing failed to extract coverage")

    def _assess_profile_coverage(self, line_cov: int, branch_cov: int, profile: str = None) -> tuple:
        """Assess coverage quality for a profile or service.

        Args:
            line_cov: Line coverage percentage
            branch_cov: Branch coverage percentage
            profile: Profile name (for profile-specific recommendations)

        Returns:
            Tuple of (grade, label, recommendations)
        """
        # Determine quality grade
        if line_cov >= 90 and branch_cov >= 85:
            grade = "A"
            label = "Excellent"
        elif line_cov >= 80 and branch_cov >= 70:
            grade = "B"
            label = "Good"
        elif line_cov >= 70 and branch_cov >= 60:
            grade = "C"
            label = "Acceptable"
        elif line_cov >= 60 and branch_cov >= 50:
            grade = "D"
            label = "Needs Improvement"
        elif line_cov == 0 and branch_cov == 0:
            grade = "F"
            label = "No Coverage"
        else:
            grade = "F"
            label = "Poor"

        # Generate recommendations
        recommendations = []
        profile_context = f" in {profile}" if profile else ""

        if line_cov == 0 and branch_cov == 0:
            recommendations.append({
                "priority": 1,
                "action": f"Ensure JaCoCo is configured for {profile} module" if profile else "Ensure JaCoCo Maven plugin is configured in pom.xml",
                "expected_improvement": "Enable coverage reporting"
            })
            recommendations.append({
                "priority": 2,
                "action": f"Verify tests are being executed during Maven build{profile_context}",
                "expected_improvement": "Generate coverage data"
            })
        else:
            if branch_cov < line_cov - 15:
                recommendations.append({
                    "priority": 1,
                    "action": f"Improve branch coverage by testing edge cases{profile_context}",
                    "expected_improvement": f"+{min(10, line_cov - branch_cov)}% branch coverage"
                })

            if line_cov < 80:
                recommendations.append({
                    "priority": 1 if not recommendations else 2,
                    "action": f"Add unit tests for uncovered methods and classes{profile_context}",
                    "expected_improvement": f"+{min(15, 80 - line_cov)}% line coverage"
                })

            if line_cov >= 80 and branch_cov < 80:
                recommendations.append({
                    "priority": len(recommendations) + 1,
                    "action": f"Focus on testing complex conditional logic{profile_context}",
                    "expected_improvement": "Better branch coverage"
                })

            if grade in ["A", "B"] and len(recommendations) == 0:
                recommendations.append({
                    "priority": 1,
                    "action": f"Maintain current coverage levels with new code{profile_context}",
                    "expected_improvement": "Sustained quality"
                })

        return (grade, label, recommendations[:3])

    def _assess_coverage_quality(self):
        """Assess coverage quality based on coverage metrics."""
        for service in self.services:
            if len(self.profiles) > 1:
                # Multi-profile mode: assess each profile individually
                for profile in self.profiles:
                    profile_data = self.tracker.services[service]["profiles"][profile]
                    line_cov = profile_data.get("coverage_line", 0)
                    branch_cov = profile_data.get("coverage_branch", 0)

                    grade, label, recommendations = self._assess_profile_coverage(line_cov, branch_cov, profile=profile)

                    # Update profile data
                    self.tracker.update(
                        service,
                        "test_success",
                        f"Grade {grade}: {label}",
                        profile=profile,
                        quality_grade=grade,
                        quality_label=label,
                        recommendations=recommendations,
                    )

                # Re-aggregate after assessment
                self.tracker._aggregate_profile_data(service)

                # Set service-level summary
                worst_grade = self.tracker.services[service].get("quality_grade", "F")
                self.tracker.services[service]["quality_summary"] = f"Profile grades vary - worst: {worst_grade}"

            else:
                # Single-profile mode (original behavior)
                line_cov = self.tracker.services[service]["coverage_line"]
                branch_cov = self.tracker.services[service]["coverage_branch"]

                grade, label, recommendations = self._assess_profile_coverage(line_cov, branch_cov)

                # Store assessment results
                self.tracker.services[service]["quality_grade"] = grade
                self.tracker.services[service]["quality_label"] = label

                # Set quality summary based on grade
                if line_cov == 0 and branch_cov == 0:
                    summary = "No coverage data detected. Ensure JaCoCo plugin is properly configured."
                elif grade == "A":
                    summary = "Outstanding test coverage with all critical paths well-tested."
                elif grade == "B":
                    summary = "Good test coverage with most critical paths tested."
                elif grade == "C":
                    summary = "Acceptable coverage but room for improvement."
                elif grade == "D":
                    summary = "Coverage is below recommended levels. Consider adding more tests."
                else:
                    summary = "Critical gaps in test coverage. Immediate attention needed."

                self.tracker.services[service]["quality_summary"] = summary
                self.tracker.services[service]["recommendations"] = recommendations

    def get_profile_breakdown_panel(self) -> Panel:
        """Generate profile breakdown panel with hierarchical display.

        Returns:
            Rich Panel with hierarchical table showing service (total) and profile rows
        """
        from rich.table import Table
        from rich.text import Text

        # Create table
        table = Table(show_header=True, header_style="bold", box=None, expand=True)
        table.add_column("Service", style="cyan", width=25)
        table.add_column("Provider", style="blue", width=15)
        table.add_column("Result", style="white", width=20)
        table.add_column("Grade", justify="center", width=7)
        table.add_column("Recommendation", style="white")

        # Track overall worst grade for border color
        worst_grade_value = 6
        grade_values = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}

        for service, data in self.tracker.services.items():
            # Get service-level metrics
            svc_line_cov = data["coverage_line"]
            svc_branch_cov = data["coverage_branch"]
            svc_grade = data.get("quality_grade")

            if svc_grade and grade_values.get(svc_grade, 0) < worst_grade_value:
                worst_grade_value = grade_values[svc_grade]

            # Determine service-level result
            if data["status"] == "test_failed":
                result_text = Text(f"Failed ({data['tests_failed']}/{data['tests_run']} tests)", style="red")
                svc_grade_text = Text("—", style="dim")
                svc_rec = "Fix test failures"
            elif data["status"] == "compile_failed":
                result_text = Text("Compile Failed", style="red")
                svc_grade_text = Text("—", style="dim")
                svc_rec = "Fix compilation errors"
            elif svc_grade:
                result_text = Text(f"Cov: {svc_line_cov}%/{svc_branch_cov}%",
                                 style="green" if svc_grade in ["A", "B"] else "yellow" if svc_grade == "C" else "red")
                grade_style = {"A": "green bold", "B": "blue bold", "C": "yellow bold",
                              "D": "red bold", "F": "red bold"}.get(svc_grade, "white")
                svc_grade_text = Text(svc_grade, style=grade_style)
                svc_rec = data.get("quality_label", "")
            else:
                result_text = Text("Pending", style="dim")
                svc_grade_text = Text("—", style="dim")
                svc_rec = ""

            # Add service (total) row
            table.add_row(
                f"[bold]{service} (total)[/bold]",
                "",  # No provider for total row
                result_text,
                svc_grade_text,
                svc_rec
            )

            # Add profile rows
            profiles = data.get("profiles", {})
            if profiles:
                # Show profiles in standard order
                profile_order = ["core", "core-plus", "azure", "aws", "gc", "ibm", "testing"]
                for profile_name in profile_order:
                    if profile_name not in profiles:
                        continue

                    profile_data = profiles[profile_name]
                    p_line_cov = profile_data.get("coverage_line", 0)
                    p_branch_cov = profile_data.get("coverage_branch", 0)
                    p_grade = profile_data.get("quality_grade")

                    # Track worst grade
                    if p_grade and grade_values.get(p_grade, 0) < worst_grade_value:
                        worst_grade_value = grade_values[p_grade]

                    # Format profile result
                    if p_grade:
                        p_result = Text(f"Cov: {p_line_cov}%/{p_branch_cov}%",
                                      style="green" if p_grade in ["A", "B"] else "yellow" if p_grade == "C" else "dim")
                        p_grade_style = {"A": "green", "B": "blue", "C": "yellow",
                                        "D": "red", "F": "red"}.get(p_grade, "white")
                        p_grade_text = Text(p_grade, style=p_grade_style)

                        # Get first recommendation
                        p_recs = profile_data.get("recommendations", [])
                        if p_recs:
                            p_rec = p_recs[0].get("action", "")
                            if len(p_rec) > 50:
                                p_rec = p_rec[:47] + "..."
                        else:
                            p_rec = profile_data.get("quality_label", "")
                    else:
                        p_result = Text("No data", style="dim")
                        p_grade_text = Text("—", style="dim")
                        p_rec = ""

                    table.add_row(
                        f"  ↳ {profile_name}",
                        profile_name.capitalize(),
                        p_result,
                        p_grade_text,
                        p_rec
                    )

        # Determine border color based on worst grade
        border_color_map = {5: "green", 4: "blue", 3: "yellow", 2: "red", 1: "red"}
        border_color = border_color_map.get(worst_grade_value, "cyan")

        # Subtitle showing profile count
        if self.profiles:
            subtitle = f"{len(self.services)} service{'s' if len(self.services) > 1 else ''} × {len(self.profiles)} profiles"
        else:
            subtitle = f"{len(self.services)} service{'s' if len(self.services) > 1 else ''}"

        return Panel(
            table,
            title="📊 Test Results",
            subtitle=subtitle,
            border_style=border_color,
            padding=(1, 2)
        )

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
                # Show coverage if we have a quality grade (even if 0%)
                # This ensures consistent display and explains the grade
                if data.get("quality_grade"):
                    result = f"Cov: {data['coverage_line']}%/{data['coverage_branch']}%"
                    result_style = "green"
                elif data["tests_run"] > 0:
                    # Fallback to test count only if no grade assigned
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

                    # Add profile breakdown if multiple profiles
                    profiles = data.get("profiles", {})
                    if profiles:
                        f.write("\n  Profile Breakdown:\n")
                        for profile_name in ["core", "core-plus", "azure", "aws", "gc", "ibm", "testing"]:
                            if profile_name not in profiles:
                                continue
                            profile_data = profiles[profile_name]
                            f.write(f"    {profile_name}:\n")
                            f.write(f"      Tests Run: {profile_data.get('tests_run', 0)}\n")
                            f.write(f"      Tests Failed: {profile_data.get('tests_failed', 0)}\n")
                            f.write(f"      Coverage Line: {profile_data.get('coverage_line', 0)}%\n")
                            f.write(f"      Coverage Branch: {profile_data.get('coverage_branch', 0)}%\n")
                            if profile_data.get("quality_grade"):
                                f.write(f"      Quality Grade: {profile_data['quality_grade']} - {profile_data.get('quality_label', 'N/A')}\n")
                                if profile_data.get("recommendations"):
                                    f.write("      Recommendations:\n")
                                    for rec in profile_data["recommendations"][:3]:
                                        f.write(f"        - {rec.get('action', 'N/A')}")
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
        """Generate final results panel.

        Args:
            return_code: Process return code

        Returns:
            Rich Panel with test results (hierarchical if multiple profiles, flat otherwise)
        """
        # If multiple profiles, use hierarchical breakdown panel
        if len(self.profiles) > 1:
            return self.get_profile_breakdown_panel()
        else:
            # Single profile: use original quality panel
            return self.get_quality_panel()


